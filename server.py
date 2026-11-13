#!/usr/bin/env python3
"""
Kişisel Blog & Güvenli Admin Paneli Sunucusu
-------------------------------------------
Hiçbir harici paket gerektirmeden (yalnızca Python standart kütüphanesi)
hem blog siteni hem de sadece senin erişebileceğin şifreli Admin Panelini sunar.

Kullanım:
  python server.py                 -> Sunucuyu http://localhost:8000 adresinde başlatır
  python server.py --port 3000     -> Belirtilen portta başlatır
  python server.py --reset-password -> Terminal üzerinden admin şifresini sıfırlar
"""

import argparse
import base64
import getpass
import hashlib
import hmac
import http.cookies
import json
import mimetypes
import os
import secrets
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CONTENT_FILE = DATA_DIR / "content.json"
SECRET_FILE = DATA_DIR / "admin_secret.json"
UPLOADS_DIR = BASE_DIR / "uploads"

SESSION_COOKIE_NAME = "blog_admin_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 gün
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8 MB
ALLOWED_IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "gif"}

# Basit IP bazlı brute-force koruması: { ip: [timestamp, ...] }
FAILED_LOGINS = {}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 300


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    if salt_hex is None:
        salt_hex = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        200_000,
    )
    return salt_hex, dk.hex()


def verify_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    _, computed = hash_password(password, salt_hex)
    return hmac.compare_digest(computed, expected_hash)


def load_secret() -> dict | None:
    if not SECRET_FILE.exists():
        return None
    with SECRET_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_secret(username: str, password: str):
    ensure_dirs()
    salt_hex, pw_hash = hash_password(password)
    payload = {
        "username": username.strip(),
        "salt": salt_hex,
        "password_hash": pw_hash,
        "session_secret": secrets.token_hex(32),
        "created_at": int(time.time()),
    }
    tmp = SECRET_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SECRET_FILE)


def load_content() -> dict:
    with CONTENT_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_content(data: dict):
    ensure_dirs()
    tmp = CONTENT_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONTENT_FILE)


def create_session_token(username: str, session_secret: str) -> str:
    exp = int(time.time()) + SESSION_TTL_SECONDS
    payload = f"{username}|{exp}"
    sig = hmac.new(
        session_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    raw = f"{payload}|{sig}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def verify_session_token(token: str, secret_data: dict) -> str | None:
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        username, exp_str, sig = decoded.split("|", 2)
        exp = int(exp_str)
        if exp < int(time.time()):
            return None
        payload = f"{username}|{exp_str}"
        expected_sig = hmac.new(
            secret_data["session_secret"].encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        if not hmac.compare_digest(username, secret_data["username"]):
            return None
        return username
    except Exception:
        return None


class BlogHandler(BaseHTTPRequestHandler):
    server_version = "PersonalBlogServer/1.0"

    def log_message(self, format, *args):
        # Temiz konsol çıktısı
        sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")

    def _send_json(self, status: int, data: dict, extra_headers: dict | None = None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self, max_bytes: int = 12 * 1024 * 1024) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length <= 0 or length > max_bytes:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    def _get_authenticated_user(self) -> str | None:
        secret_data = load_secret()
        if not secret_data:
            return None
        cookie_header = self.headers.get("Cookie", "")
        if not cookie_header:
            return None
        cookies = http.cookies.SimpleCookie()
        try:
            cookies.load(cookie_header)
        except Exception:
            return None
        morsel = cookies.get(SESSION_COOKIE_NAME)
        if not morsel:
            return None
        return verify_session_token(morsel.value, secret_data)

    def _is_rate_limited(self, ip: str) -> bool:
        now = time.time()
        attempts = [t for t in FAILED_LOGINS.get(ip, []) if now - t < LOCKOUT_SECONDS]
        FAILED_LOGINS[ip] = attempts
        return len(attempts) >= MAX_FAILED_ATTEMPTS

    def _record_failed_login(self, ip: str):
        now = time.time()
        attempts = [t for t in FAILED_LOGINS.get(ip, []) if now - t < LOCKOUT_SECONDS]
        attempts.append(now)
        FAILED_LOGINS[ip] = attempts

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == "/api/content":
            try:
                content = load_content()
                self._send_json(200, content)
            except Exception as e:
                self._send_json(500, {"error": f"İçerik okunamadı: {e}"})
            return

        if path == "/api/auth/status":
            secret_data = load_secret()
            user = self._get_authenticated_user()
            self._send_json(
                200,
                {
                    "needsSetup": secret_data is None,
                    "authenticated": user is not None,
                    "username": user,
                },
            )
            return

        # /admin kısa yolu
        if path in ("/admin", "/admin/"):
            path = "/admin.html"
        elif path == "/":
            path = "/index.html"

        self._serve_static(path)

    def _build_cookie(self, value: str, max_age: int) -> str:
        proto = self.headers.get("X-Forwarded-Proto", "").lower()
        secure_flag = "; Secure" if proto == "https" else ""
        return f"{SESSION_COOKIE_NAME}={value}; HttpOnly; SameSite=Strict; Path=/; Max-Age={max_age}{secure_flag}"

    def do_POST(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        # İlk kurulum (yalnızca admin_secret.json yoksa çalışır)
        if path == "/api/auth/setup":
            if load_secret() is not None:
                self._send_json(403, {"error": "Admin hesabı zaten kurulmuş."})
                return
            body = self._read_json_body(4096)
            if not body:
                self._send_json(400, {"error": "Geçersiz istek."})
                return
            username = str(body.get("username", "")).strip()
            password = str(body.get("password", ""))
            if len(username) < 3 or len(password) < 8:
                self._send_json(
                    400,
                    {"error": "Kullanıcı adı en az 3, şifre en az 8 karakter olmalıdır."},
                )
                return
            save_secret(username, password)
            secret_data = load_secret()
            token = create_session_token(username, secret_data["session_secret"])
            cookie = self._build_cookie(token, SESSION_TTL_SECONDS)
            self._send_json(
                201,
                {"ok": True, "username": username},
                {"Set-Cookie": cookie},
            )
            return

        # Giriş
        if path == "/api/auth/login":
            client_ip = self.client_address[0]
            if self._is_rate_limited(client_ip):
                self._send_json(
                    429,
                    {"error": "Çok fazla hatalı deneme. Lütfen 5 dakika sonra tekrar dene."},
                )
                return
            secret_data = load_secret()
            if not secret_data:
                self._send_json(400, {"error": "Önce ilk kurulumu tamamlamalısın."})
                return
            body = self._read_json_body(4096)
            if not body:
                self._send_json(400, {"error": "Geçersiz istek."})
                return
            username = str(body.get("username", "")).strip()
            password = str(body.get("password", ""))
            user_ok = hmac.compare_digest(username, secret_data["username"])
            pw_ok = verify_password(password, secret_data["salt"], secret_data["password_hash"])
            if not (user_ok and pw_ok):
                self._record_failed_login(client_ip)
                self._send_json(401, {"error": "Kullanıcı adı veya şifre hatalı."})
                return

            FAILED_LOGINS.pop(client_ip, None)
            token = create_session_token(username, secret_data["session_secret"])
            cookie = self._build_cookie(token, SESSION_TTL_SECONDS)
            self._send_json(
                200,
                {"ok": True, "username": username},
                {"Set-Cookie": cookie},
            )
            return

        # Çıkış
        if path == "/api/auth/logout":
            cookie = self._build_cookie("", 0)
            self._send_json(200, {"ok": True}, {"Set-Cookie": cookie})
            return

        # Buradan sonrası YETKİ GEREKTİRİR
        user = self._get_authenticated_user()
        if not user:
            self._send_json(401, {"error": "Yetkisiz erişim. Lütfen giriş yap."})
            return

        if path == "/api/admin/upload":
            body = self._read_json_body(MAX_UPLOAD_BYTES + 2 * 1024 * 1024)
            if not body:
                self._send_json(400, {"error": "Görsel verisi okunamadı veya boyut çok büyük."})
                return
            filename = str(body.get("filename", "image.png"))
            data_url = str(body.get("dataUrl", ""))
            if "," not in data_url or not data_url.startswith("data:image/"):
                self._send_json(400, {"error": "Geçersiz görsel formatı."})
                return

            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
            if ext not in ALLOWED_IMAGE_EXTS:
                self._send_json(400, {"error": "Yalnızca PNG, JPG, WEBP veya GIF yüklenebilir."})
                return

            try:
                b64_part = data_url.split(",", 1)[1]
                raw_bytes = base64.b64decode(b64_part, validate=True)
            except Exception:
                self._send_json(400, {"error": "Görsel çözümlenemedi."})
                return

            if len(raw_bytes) > MAX_UPLOAD_BYTES:
                self._send_json(400, {"error": "Görsel boyutu 8 MB sınırını aşamaz."})
                return

            ensure_dirs()
            safe_name = f"{uuid.uuid4().hex}.{ext}"
            target = UPLOADS_DIR / safe_name
            with target.open("wb") as f:
                f.write(raw_bytes)

            self._send_json(201, {"ok": True, "url": f"/uploads/{safe_name}"})
            return

        if path == "/api/admin/item":
            body = self._read_json_body(1024 * 1024)
            if not body:
                self._send_json(400, {"error": "Geçersiz içerik verisi."})
                return
            section = body.get("section")
            item = body.get("item")
            if section not in {"socialPosts", "projects", "ideas", "events"} or not isinstance(item, dict):
                self._send_json(400, {"error": "Geçersiz bölüm veya öğe."})
                return

            if not item.get("id"):
                item["id"] = f"{section[:3]}-{uuid.uuid4().hex[:8]}"

            content = load_content()
            content.setdefault(section, []).insert(0, item)
            save_content(content)
            self._send_json(201, {"ok": True, "item": item})
            return

        self._send_json(404, {"error": "Bilinmeyen uç nokta."})

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        user = self._get_authenticated_user()
        if not user:
            self._send_json(401, {"error": "Yetkisiz erişim."})
            return

        if path == "/api/admin/profile":
            body = self._read_json_body(512 * 1024)
            if not body or not isinstance(body.get("profile"), dict):
                self._send_json(400, {"error": "Geçersiz profil verisi."})
                return
            content = load_content()
            content["profile"].update(body["profile"])
            if isinstance(body.get("institutions"), list):
                content["institutions"] = [str(x).strip() for x in body["institutions"] if str(x).strip()]
            save_content(content)
            self._send_json(200, {"ok": True})
            return

        self._send_json(404, {"error": "Bilinmeyen uç nokta."})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        user = self._get_authenticated_user()
        if not user:
            self._send_json(401, {"error": "Yetkisiz erişim."})
            return

        if path == "/api/admin/item":
            body = self._read_json_body(16 * 1024)
            if not body:
                self._send_json(400, {"error": "Geçersiz istek."})
                return
            section = body.get("section")
            item_id = body.get("id")
            if section not in {"socialPosts", "projects", "ideas", "events"} or not item_id:
                self._send_json(400, {"error": "Geçersiz bölüm veya ID."})
                return

            content = load_content()
            items = content.get(section, [])
            new_items = [x for x in items if x.get("id") != item_id]
            if len(new_items) == len(items):
                self._send_json(404, {"error": "Öğe bulunamadı."})
                return
            content[section] = new_items
            save_content(content)
            self._send_json(200, {"ok": True})
            return

        self._send_json(404, {"error": "Bilinmeyen uç nokta."})

    def _serve_static(self, req_path: str):
        rel = req_path.lstrip("/")
        if not rel:
            rel = "index.html"

        # Güvenlik: gizli dosyalar, data/, server.py ve path traversal engellenir
        parts = Path(rel).parts
        if (
            not parts
            or ".." in parts
            or any(p.startswith(".") for p in parts)
            or parts[0] in {"data", "__pycache__"}
            or rel in {"server.py"}
        ):
            self.send_error(403, "Erişim reddedildi")
            return

        target = (BASE_DIR / rel).resolve()
        try:
            target.relative_to(BASE_DIR)
        except ValueError:
            self.send_error(403, "Erişim reddedildi")
            return

        if not target.is_file():
            self.send_error(404, "Dosya bulunamadı")
            return

        mime, _ = mimetypes.guess_type(str(target))
        if not mime:
            mime = "application/octet-stream"

        with target.open("rb") as f:
            data = f.read()

        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)


def reset_password_cli():
    print("=== Admin Şifre Sıfırlama ===")
    username = input("Yeni Admin Kullanıcı Adı: ").strip()
    while len(username) < 3:
        print("Kullanıcı adı en az 3 karakter olmalı.")
        username = input("Yeni Admin Kullanıcı Adı: ").strip()

    password = getpass.getpass("Yeni Şifre (en az 8 karakter): ")
    while len(password) < 8:
        print("Şifre en az 8 karakter olmalı.")
        password = getpass.getpass("Yeni Şifre (en az 8 karakter): ")

    save_secret(username, password)
    print("Admin bilgileri güvenli şekilde güncellendi.")


def main():
    default_port = int(os.environ.get("PORT", "8000"))
    parser = argparse.ArgumentParser(description="Kişisel Blog & Admin Sunucusu")
    parser.add_argument("--host", default="0.0.0.0", help="Dinlenecek adres (varsayılan: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=default_port, help="Port numarası (varsayılan: PORT env veya 8000)")
    parser.add_argument("--reset-password", action="store_true", help="Admin şifresini terminalden sıfırla")
    args = parser.parse_args()

    ensure_dirs()

    if args.reset_password:
        reset_password_cli()
        return

    server = ThreadingHTTPServer((args.host, args.port), BlogHandler)
    print(f"Blog sunucusu çalışıyor: http://localhost:{args.port}")
    print(f"Admin paneli adresi:     http://localhost:{args.port}/admin")
    print("Durdurmak için Ctrl+C tuşlarına basın.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSunucu kapatılıyor...")
        server.server_close()


if __name__ == "__main__":
    main()
