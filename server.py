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
import html
import http.cookies
import json
import mimetypes
import os
import re
import secrets
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent
SEED_CONTENT_FILE = BASE_DIR / "data" / "content.json"
STORAGE_ROOT = os.environ.get("STORAGE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
if STORAGE_ROOT:
    DATA_DIR = Path(STORAGE_ROOT) / "data"
    UPLOADS_DIR = Path(STORAGE_ROOT) / "uploads"
else:
    DATA_DIR = BASE_DIR / "data"
    UPLOADS_DIR = BASE_DIR / "uploads"

CONTENT_FILE = DATA_DIR / "content.json"
SECRET_FILE = DATA_DIR / "admin_secret.json"
FEEDS_FILE = DATA_DIR / "feeds.json"

CONTENT_LOCK = threading.Lock()
BOT_INTERVAL_SECONDS = 300  # 5 dakikada bir otomatik kontrol
BOT_LAST_RUN = {"time": None, "added": 0, "error": None}

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
    if not CONTENT_FILE.exists() and SEED_CONTENT_FILE.exists():
        shutil.copy2(SEED_CONTENT_FILE, CONTENT_FILE)


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


def _write_secret_file(payload: dict):
    ensure_dirs()
    tmp = SECRET_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SECRET_FILE)


def load_secret() -> dict | None:
    if not SECRET_FILE.exists():
        return None
    with SECRET_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if "webhook_secret" not in data:
        data["webhook_secret"] = secrets.token_hex(24)
        _write_secret_file(data)
    return data


def save_secret(username: str, password: str):
    salt_hex, pw_hash = hash_password(password)
    existing = load_secret() or {}
    payload = {
        "username": username.strip(),
        "salt": salt_hex,
        "password_hash": pw_hash,
        "session_secret": secrets.token_hex(32),
        "webhook_secret": existing.get("webhook_secret") or secrets.token_hex(24),
        "created_at": int(time.time()),
    }
    _write_secret_file(payload)


def rotate_webhook_secret() -> str:
    data = load_secret()
    if not data:
        raise RuntimeError("Admin kurulumu henüz yapılmamış.")
    new_sec = secrets.token_hex(24)
    data["webhook_secret"] = new_sec
    _write_secret_file(data)
    return new_sec


CHAT_RATE_LIMIT: dict[str, list[float]] = {}
CHAT_MAX_REQUESTS = 20
CHAT_WINDOW_SECONDS = 60
GEMINI_MODELS = [
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-3-flash",
    "gemini-3.5-flash",
    "gemini-2.0-flash",
]
_CACHED_GEMINI_MODEL: str | None = None


def get_gemini_api_key() -> tuple[str | None, str | None]:
    """Ortam değişkeni (Railway GEMINI_API_KEY) veya admin panelindeki anahtarı döndürür."""
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key, "env"
    secret_data = load_secret() or {}
    saved_key = str(secret_data.get("gemini_api_key", "")).strip()
    if saved_key:
        return saved_key, "admin"
    return None, None


def mask_gemini_key(api_key: str | None) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "****"
    return f"{api_key[:4]}...{api_key[-4:]}"


def _build_portfolio_system_prompt(content: dict) -> str:
    profile = content.get("profile") or {}
    projects = content.get("projects") or []
    events = content.get("events") or []
    ideas = content.get("ideas") or []
    social = content.get("socialPosts") or []
    institutions = content.get("institutions") or []

    proj_lines = [
        f"- {p.get('title')} ({p.get('year', '')}, {p.get('status', '')}): {p.get('description', '')} | Teknolojiler: {', '.join(p.get('stack') or [])}"
        for p in projects[:15]
    ]
    event_lines = [
        f"- [{e.get('categoryLabel', '')}] {e.get('title')} ({e.get('place', '')}, {e.get('date', '')}): {e.get('description', '')}"
        for e in events[:15]
    ]
    idea_lines = [
        f"- [{i.get('tag', '')}] {i.get('title')} ({i.get('date', '')}): {i.get('summary', '')}"
        for i in ideas[:12]
    ]
    social_lines = [
        f"- [{s.get('platformLabel', '')}] {s.get('title')} ({s.get('date', '')}): {s.get('excerpt', '')}"
        for s in social[:10]
    ]

    return (
        "Sen Emir Zencircioğlu'nun kişisel blog ve portfolyo sitesindeki resmi yapay zeka asistanısın ('Emir AI').\n"
        "Görevin: Siteyi inceleyen İK uzmanları, banka/finans yöneticileri, şirket çalışanları ve ziyaretçilerin "
        "Emir hakkındaki sorularını net, kibar, profesyonel ve ikna edici biçimde yanıtlamak.\n\n"
        "Kurallar:\n"
        "1. Ziyaretçi hangi dilde yazarsa o dilde yanıt ver (varsayılan Türkçe).\n"
        "2. Sadece aşağıdaki güncel site verilerine ve bağlama dayan; bilmediğin bilgileri uydurma.\n"
        "3. Kısa, okunabilir ve doğrudan sorulara odaklanan yanıtlar ver.\n"
        "4. İletişim veya staj/iş birliği sorulursa telefon (0537 775 12 24) ve e-posta bilgilerini paylaş.\n\n"
        f"=== PROFİL ===\n"
        f"Ad Soyad: {profile.get('name', 'Emir Zencircioğlu')}\n"
        f"Rol: {profile.get('role', '')}\n"
        f"Durum: {profile.get('status', '')}\n"
        f"Biyografi: {profile.get('bio', '')}\n"
        f"Kariyer Hedefi & Konumlandırma: Üniversite eğitimini yazılım ve ürün geliştirme projeleriyle beslerken "
        f"sermaye piyasaları, yatırım, hazine ve bankacılık süreçlerinde de kendini aktif geliştiren bir öğrenci; "
        f"büyük ölçekli bankaların ve kurumsal şirketlerin hazine, yatırım veya teknoloji ekiplerinde sorumluluk almaya açık.\n"
        f"İlgi Alanları: {', '.join(profile.get('interests') or [])}\n"
        f"Güncel Odak: {'; '.join(profile.get('now') or [])}\n"
        f"E-posta: {profile.get('email', 'ezencircioglu0024@gmail.com')}\n"
        f"Telefon: 0537 775 12 24 (+90 537 775 12 24)\n"
        f"Katıldığı Kurumlar / Ekosistemler: {', '.join(institutions)}\n\n"
        f"=== PROJELER ===\n" + ("\n".join(proj_lines) or "Henüz proje listelenmedi.") + "\n\n"
        f"=== ETKİNLİK, BANKA VE ZİRVEMELER ===\n" + ("\n".join(event_lines) or "Henüz etkinlik listelenmedi.") + "\n\n"
        f"=== FİKİRLER VE YAZILAR ===\n" + ("\n".join(idea_lines) or "Henüz yazı listelenmedi.") + "\n\n"
        f"=== SON SOSYAL PAYLAŞIMLAR ===\n" + ("\n".join(social_lines) or "Henüz paylaşım listelenmedi.")
    )


def _discover_gemini_models(api_key: str) -> list[str]:
    """Kullanılabilir generateContent modellerini Gemini API'den dinamik olarak çeker."""
    url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=100"
    req = urllib.request.Request(url, method="GET", headers={"x-goog-api-key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        print(f"[Gemini discover] HTTP {e.code}: {err_body[:300]}", flush=True)
        if e.code in (400, 401, 403):
            raise RuntimeError("Gemini API anahtarı geçersiz veya yetkisiz görünüyor.") from e
        return []
    except Exception as e:
        print(f"[Gemini discover] Exception: {e}", flush=True)
        return []

    raw_models = data.get("models") or []
    print(f"[Gemini discover] {len(raw_models)} models listed: {[m.get('name') for m in raw_models[:12]]}", flush=True)

    excluded = ("tts", "image", "embedding", "aqa", "robotics", "computer-use", "audio")
    candidates = []
    for m in raw_models:
        methods = m.get("supportedGenerationMethods") or []
        if "generateContent" not in methods:
            continue
        name = str(m.get("name") or "").removeprefix("models/").strip()
        lower = name.lower()
        if not name or not lower.startswith("gemini") or any(tag in lower for tag in excluded):
            continue
        priority = 0 if "flash" in lower else (1 if "pro" in lower else 2)
        candidates.append((priority, name))

    candidates.sort(key=lambda item: (item[0], item[1]))
    flash_first = [name for pr, name in candidates if pr == 0]
    flash_first.reverse()
    others = [name for pr, name in candidates if pr > 0]
    return flash_first + others


def _try_gemini_model(api_key: str, model: str, payload_bytes: bytes) -> tuple[str | None, str | None, bool]:
    """Tek bir modeli dener: (reply_text, err_msg, is_not_found)."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    req = urllib.request.Request(
        url,
        data=payload_bytes,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        candidates = data.get("candidates") or []
        if candidates:
            parts = (candidates[0].get("content") or {}).get("parts") or []
            reply_text = "".join(str(p.get("text", "")) for p in parts).strip()
            if reply_text:
                return reply_text, None, False
        return None, "Gemini boş yanıt döndürdü.", False
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        print(f"[Gemini try {model}] HTTP {e.code}: {err_body[:300]}", flush=True)
        if e.code == 404:
            detail = ""
            try:
                detail = str((json.loads(err_body).get("error") or {}).get("message") or "")
            except Exception:
                detail = err_body[:120]
            return None, f"Model bulunamadı ({model}): {detail}", True
        if e.code in (401, 403) or (e.code == 400 and "api key" in err_body.lower()):
            raise RuntimeError("Gemini API anahtarı geçersiz veya yetkisiz görünüyor.") from e
        if e.code == 429:
            raise RuntimeError("Gemini API istek limiti geçici olarak doldu, lütfen biraz sonra tekrar deneyin.") from e
        return None, f"Gemini API hatası ({e.code}, {model}): {err_body[:160]}", False
    except Exception as e:
        print(f"[Gemini try {model}] Exception: {e}", flush=True)
        return None, f"Bağlantı hatası ({model}): {e}", False


def call_gemini_api(api_key: str, system_prompt: str, history: list, user_message: str) -> str:
    global _CACHED_GEMINI_MODEL
    contents = []
    if isinstance(history, list):
        for turn in history[-10:]:
            if not isinstance(turn, dict):
                continue
            role = "model" if turn.get("role") == "model" else "user"
            text = str(turn.get("text", "")).strip()
            if text:
                contents.append({"role": role, "parts": [{"text": text[:1500]}]})
    contents.append({"role": "user", "parts": [{"text": user_message[:1500]}]})

    payload_bytes = json.dumps(
        {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {
                "temperature": 0.65,
                "maxOutputTokens": 650,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")

    tried = set()
    initial_models = ([_CACHED_GEMINI_MODEL] if _CACHED_GEMINI_MODEL else []) + list(GEMINI_MODELS)
    last_error = "Gemini servisine bağlanılamadı."
    all_404 = True

    for model in initial_models:
        if not model or model in tried:
            continue
        tried.add(model)
        reply_text, err_msg, is_404 = _try_gemini_model(api_key, model, payload_bytes)
        if reply_text:
            _CACHED_GEMINI_MODEL = model
            return reply_text
        if not is_404:
            all_404 = False
        if err_msg:
            last_error = err_msg

    if all_404:
        for model in _discover_gemini_models(api_key):
            if model in tried:
                continue
            tried.add(model)
            reply_text, err_msg, _ = _try_gemini_model(api_key, model, payload_bytes)
            if reply_text:
                _CACHED_GEMINI_MODEL = model
                return reply_text
            if err_msg:
                last_error = err_msg

    raise RuntimeError(last_error)


TR_MONTHS = [
    "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]


TR_TZ = timezone(timedelta(hours=3))


def parse_any_datetime(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        ts = value / 1000.0 if value > 1e12 else float(value)
        return datetime.fromtimestamp(ts, tz=TR_TZ)
    raw = str(value).strip()
    if not raw:
        return None
    try:
        iso = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TR_TZ)
        return dt.astimezone(TR_TZ)
    except Exception:
        pass
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TR_TZ)
        return dt.astimezone(TR_TZ)
    except Exception:
        return None


def format_tr_date(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(TR_TZ)
    return f"{dt.day:02d} {TR_MONTHS[dt.month]} {dt.year}"


def download_image_safely(url: str) -> str | None:
    if not url or not url.startswith(("http://", "https://")):
        return None
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "PersonalBlogSync/1.0"},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if not ctype.startswith("image/"):
                return url
            raw = resp.read(MAX_UPLOAD_BYTES + 1)
            if len(raw) > MAX_UPLOAD_BYTES:
                return url
            ext = "jpg"
            if "png" in ctype:
                ext = "png"
            elif "webp" in ctype:
                ext = "webp"
            elif "gif" in ctype:
                ext = "gif"
            ensure_dirs()
            fname = f"{uuid.uuid4().hex}.{ext}"
            with (UPLOADS_DIR / fname).open("wb") as f:
                f.write(raw)
            return f"/uploads/{fname}"
    except Exception:
        return url


def fetch_github_repos(username: str) -> list[dict]:
    clean_user = username.strip().lstrip("@")
    if not clean_user:
        raise ValueError("GitHub kullanıcı adı boş olamaz.")
    api_url = f"https://api.github.com/users/{clean_user}/repos?sort=updated&per_page=8"
    req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": "PersonalBlogSync/1.0",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_content() -> dict:
    with CONTENT_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_content(data: dict):
    ensure_dirs()
    tmp = CONTENT_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONTENT_FILE)


def load_feeds() -> list[dict]:
    if not FEEDS_FILE.exists():
        return []
    with FEEDS_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_feeds(feeds: list[dict]):
    ensure_dirs()
    tmp = FEEDS_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(feeds, f, ensure_ascii=False, indent=2)
    os.replace(tmp, FEEDS_FILE)


def _strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_img_from_html(raw_html: str) -> str | None:
    if not raw_html:
        return None
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw_html, re.IGNORECASE)
    return html.unescape(m.group(1)) if m else None


def parse_feed_items(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    items = []

    # RSS 2.0 (<channel><item>...)
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc_raw = item.findtext("description") or ""
        content_encoded = ""
        for child in item:
            if child.tag.endswith("encoded") and child.text:
                content_encoded = child.text
                break

        img_url = None
        enclosure = item.find("enclosure")
        if enclosure is not None and (enclosure.attrib.get("type") or "").startswith("image/"):
            img_url = enclosure.attrib.get("url")
        if not img_url:
            for child in item:
                if child.tag.endswith("content") or child.tag.endswith("thumbnail"):
                    cand = child.attrib.get("url")
                    if cand:
                        img_url = cand
                        break
        if not img_url:
            img_url = _extract_img_from_html(content_encoded or desc_raw)

        pub_raw = (item.findtext("pubDate") or "").strip()
        excerpt = _strip_html(desc_raw or content_encoded)[:240]
        if link:
            items.append({
                "title": _strip_html(title)[:120] or "Yeni Paylaşım",
                "url": link,
                "excerpt": excerpt,
                "image": img_url,
                "publishedAt": pub_raw,
            })

    # Atom (<feed><entry>...)
    if not items:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall(".//atom:entry", ns) or root.findall(".//entry")
        for entry in entries:
            title_el = entry.find("atom:title", ns) or entry.find("title")
            link_el = entry.find("atom:link", ns) or entry.find("link")
            sum_el = entry.find("atom:summary", ns) or entry.find("summary") or entry.find("atom:content", ns) or entry.find("content")
            pub_el = entry.find("atom:published", ns) or entry.find("published") or entry.find("atom:updated", ns) or entry.find("updated")
            title = (title_el.text if title_el is not None and title_el.text else "").strip()
            link = (link_el.attrib.get("href", "") if link_el is not None else "").strip()
            raw_body = sum_el.text if sum_el is not None and sum_el.text else ""
            pub_raw = (pub_el.text if pub_el is not None and pub_el.text else "").strip()
            if link:
                items.append({
                    "title": _strip_html(title)[:120] or "Yeni Paylaşım",
                    "url": link,
                    "excerpt": _strip_html(raw_body)[:240],
                    "image": _extract_img_from_html(raw_body),
                    "publishedAt": pub_raw,
                })

    return items[:10]


def run_feed_bot_once() -> dict:
    feeds = load_feeds()
    platform_labels = {
        "instagram": "Instagram",
        "linkedin": "LinkedIn",
        "github": "GitHub",
        "youtube": "YouTube",
    }
    added_total = 0
    errors = []

    for feed in feeds:
        feed_url = (feed.get("feedUrl") or "").strip()
        platform = (feed.get("platform") or "").strip().lower()
        if not feed_url or platform not in platform_labels:
            continue
        try:
            req = urllib.request.Request(
                feed_url,
                headers={"User-Agent": "PersonalBlogBot/1.0"},
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                xml_bytes = resp.read(2 * 1024 * 1024)
            parsed_items = parse_feed_items(xml_bytes)
        except Exception as e:
            errors.append(f"{platform_labels[platform]}: {e}")
            continue

        with CONTENT_LOCK:
            content = load_content()
            existing_urls = {p.get("url") for p in content.get("socialPosts", [])}
            new_for_feed = []
            for entry in parsed_items:
                if entry["url"] in existing_urls:
                    continue
                saved_img = download_image_safely(entry["image"]) if entry.get("image") else None
                pub_dt = parse_any_datetime(entry.get("publishedAt"))
                new_for_feed.append({
                    "id": f"bot-{uuid.uuid4().hex[:8]}",
                    "platform": platform,
                    "platformLabel": platform_labels[platform],
                    "date": format_tr_date(pub_dt),
                    "title": entry["title"],
                    "excerpt": entry["excerpt"] or f"Yeni {platform_labels[platform]} paylaşımı.",
                    "image": saved_img,
                    "metric": "Otomatik Bot",
                    "url": entry["url"],
                })
                existing_urls.add(entry["url"])

            if new_for_feed:
                for post in reversed(new_for_feed):
                    content.setdefault("socialPosts", []).insert(0, post)
                save_content(content)
                added_total += len(new_for_feed)

    # Kayıtlı GitHub kullanıcı adı varsa yeni public repoları da otomatik kontrol et
    gh_user = (load_content().get("profile", {}).get("githubUsername") or "").strip()
    if gh_user:
        try:
            added_total += sync_github_user_repos(gh_user)
        except Exception as e:
            errors.append(f"GitHub: {e}")

    BOT_LAST_RUN["time"] = datetime.now(TR_TZ).strftime("%H:%M:%S")
    BOT_LAST_RUN["added"] = added_total
    BOT_LAST_RUN["error"] = "; ".join(errors) if errors else None
    return {"added": added_total, "errors": errors, "lastRun": BOT_LAST_RUN["time"]}


def sync_github_user_repos(gh_user: str) -> int:
    repos = fetch_github_repos(gh_user)
    with CONTENT_LOCK:
        content = load_content()
        content.setdefault("profile", {})["githubUsername"] = gh_user
        existing_urls = {p.get("url") for p in content.get("socialPosts", [])}
        added = 0
        for repo in reversed(repos):
            if repo.get("fork"):
                continue
            repo_url = repo.get("html_url")
            if not repo_url or repo_url in existing_urls:
                continue
            lang = repo.get("language") or "Kod"
            stars = repo.get("stargazers_count", 0)
            repo_dt = parse_any_datetime(repo.get("created_at") or repo.get("pushed_at"))
            new_post = {
                "id": f"gh-{uuid.uuid4().hex[:8]}",
                "platform": "github",
                "platformLabel": "GitHub",
                "date": format_tr_date(repo_dt),
                "title": repo.get("name", "GitHub Projesi"),
                "excerpt": repo.get("description") or "GitHub üzerinde paylaşılan yeni açık kaynak depo.",
                "image": None,
                "metric": f"★ {stars} yıldız · {lang}",
                "url": repo_url,
            }
            content.setdefault("socialPosts", []).insert(0, new_post)
            existing_urls.add(repo_url)
            added += 1
        save_content(content)
        return added


def start_feed_bot_thread():
    def loop():
        time.sleep(15)
        while True:
            try:
                has_gh = bool((load_content().get("profile", {}).get("githubUsername") or "").strip())
                if load_feeds() or has_gh:
                    run_feed_bot_once()
            except Exception as e:
                sys.stderr.write(f"[FeedBot] Hata: {e}\n")
            time.sleep(BOT_INTERVAL_SECONDS)

    t = threading.Thread(target=loop, daemon=True)
    t.start()


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

        if path == "/api/chat/status":
            gemini_key, _ = get_gemini_api_key()
            self._send_json(200, {"configured": bool(gemini_key)})
            return

        if path == "/api/admin/automation":
            user = self._get_authenticated_user()
            if not user:
                self._send_json(401, {"error": "Yetkisiz erişim."})
                return
            secret_data = load_secret() or {}
            content = load_content()
            gemini_key, gemini_source = get_gemini_api_key()
            self._send_json(
                200,
                {
                    "webhookPath": "/api/webhook/social",
                    "webhookSecret": secret_data.get("webhook_secret", ""),
                    "githubUsername": content.get("profile", {}).get("githubUsername", ""),
                    "igUserId": secret_data.get("ig_user_id", ""),
                    "igConfigured": bool(secret_data.get("ig_access_token")),
                    "geminiConfigured": bool(gemini_key),
                    "geminiSource": gemini_source,
                    "geminiMasked": mask_gemini_key(gemini_key),
                    "feeds": load_feeds(),
                    "botLastRun": BOT_LAST_RUN,
                },
            )
            return

        # /admin kısa yolu ve favicon eşlemesi
        if path in ("/admin", "/admin/"):
            path = "/admin.html"
        elif path == "/favicon.ico":
            path = "/assets/favicon.svg"
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

        # Otomasyon Webhook Alıcısı (GitHub, Instagram, LinkedIn, Make/n8n/Zapier)
        if path == "/api/webhook/social":
            self._handle_social_webhook()
            return

        # Herkese Açık Gemini Chatbot Uç Noktası
        if path == "/api/chat":
            client_ip = (self.headers.get("X-Forwarded-For", "").split(",")[0].strip() or self.client_address[0])
            now_ts = time.time()
            recent = [t for t in CHAT_RATE_LIMIT.get(client_ip, []) if now_ts - t < CHAT_WINDOW_SECONDS]
            if len(recent) >= CHAT_MAX_REQUESTS:
                self._send_json(429, {"error": "Çok hızlı mesaj gönderildi. Lütfen kısa bir süre bekleyin."})
                return
            recent.append(now_ts)
            CHAT_RATE_LIMIT[client_ip] = recent

            body = self._read_json_body(32 * 1024)
            if not body:
                self._send_json(400, {"error": "Geçersiz sohbet isteği."})
                return
            message = str(body.get("message", "")).strip()
            if not message:
                self._send_json(400, {"error": "Mesaj boş olamaz."})
                return
            history = body.get("history") or []

            api_key, _ = get_gemini_api_key()
            if not api_key:
                self._send_json(
                    503,
                    {
                        "error": "Gemini API anahtarı henüz bağlanmamış. Admin Panelinden veya Railway üzerinden GEMINI_API_KEY ekleyebilirsiniz.",
                        "code": "NO_API_KEY",
                    },
                )
                return

            try:
                system_prompt = _build_portfolio_system_prompt(load_content())
                reply = call_gemini_api(api_key, system_prompt, history, message)
                self._send_json(200, {"ok": True, "reply": reply})
            except RuntimeError as e:
                self._send_json(502, {"error": str(e)})
            except Exception as e:
                self._send_json(500, {"error": f"Sohbet yanıtı alınamadı: {e}"})
            return

        # Buradan sonrası YETKİ GEREKTİRİR
        user = self._get_authenticated_user()
        if not user:
            self._send_json(401, {"error": "Yetkisiz erişim. Lütfen giriş yap."})
            return

        if path == "/api/admin/gemini":
            global _CACHED_GEMINI_MODEL
            body = self._read_json_body(4096) or {}
            api_key = str(body.get("apiKey", "")).strip()
            secret_data = load_secret()
            if not secret_data:
                self._send_json(400, {"error": "Önce admin hesabını kurun."})
                return
            if api_key:
                secret_data["gemini_api_key"] = api_key
            else:
                secret_data.pop("gemini_api_key", None)
            _CACHED_GEMINI_MODEL = None
            _write_secret_file(secret_data)
            active_key, source = get_gemini_api_key()
            self._send_json(
                200,
                {
                    "ok": True,
                    "geminiConfigured": bool(active_key),
                    "geminiSource": source,
                    "geminiMasked": mask_gemini_key(active_key),
                },
            )
            return

        if path == "/api/admin/feeds":
            body = self._read_json_body(4096) or {}
            platform = str(body.get("platform", "")).strip().lower()
            feed_url = str(body.get("feedUrl", "")).strip()
            if platform not in {"instagram", "linkedin", "github", "youtube"} or not feed_url.startswith(("http://", "https://")):
                self._send_json(400, {"error": "Geçerli bir platform ve https:// RSS adresi gir."})
                return
            feeds = load_feeds()
            new_feed = {
                "id": f"feed-{uuid.uuid4().hex[:8]}",
                "platform": platform,
                "feedUrl": feed_url,
            }
            feeds.append(new_feed)
            save_feeds(feeds)
            self._send_json(201, {"ok": True, "feed": new_feed})
            return

        if path == "/api/admin/feeds/run":
            result = run_feed_bot_once()
            self._send_json(200, {"ok": True, **result})
            return

        if path == "/api/admin/automation/rotate-secret":
            try:
                new_secret = rotate_webhook_secret()
                self._send_json(200, {"ok": True, "webhookSecret": new_secret})
            except Exception as e:
                self._send_json(400, {"error": str(e)})
            return

        if path == "/api/admin/sync/github":
            body = self._read_json_body(4096) or {}
            gh_user = str(body.get("username", "")).strip().lstrip("@")
            if not gh_user:
                self._send_json(400, {"error": "GitHub kullanıcı adı gerekli."})
                return
            try:
                added = sync_github_user_repos(gh_user)
            except urllib.error.HTTPError as e:
                self._send_json(400, {"error": f"GitHub API hatası: {e.code}"})
                return
            except Exception as e:
                self._send_json(500, {"error": f"GitHub bağlantısı başarısız: {e}"})
                return

            self._send_json(200, {"ok": True, "added": added, "username": gh_user})
            return

        if path == "/api/admin/sync/instagram":
            body = self._read_json_body(8192) or {}
            secret_data = load_secret() or {}
            ig_user_id = str(body.get("igUserId") or secret_data.get("ig_user_id") or "").strip()
            ig_token = str(body.get("igAccessToken") or secret_data.get("ig_access_token") or "").strip()

            if not ig_user_id or not ig_token:
                self._send_json(400, {"error": "Instagram Kullanıcı ID ve Access Token gerekli."})
                return

            # Bilgileri şifreli sunucu dosyasında sakla (sonraki senkronizasyonlarda tekrar girmek gerekmez)
            if body.get("igUserId") or body.get("igAccessToken"):
                secret_data["ig_user_id"] = ig_user_id
                secret_data["ig_access_token"] = ig_token
                _write_secret_file(secret_data)

            api_url = (
                f"https://graph.instagram.com/{ig_user_id}/media"
                f"?fields=id,caption,media_type,media_url,thumbnail_url,permalink,timestamp"
                f"&limit=8&access_token={urllib.request.quote(ig_token)}"
            )
            try:
                req = urllib.request.Request(api_url, headers={"User-Agent": "PersonalBlogSync/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    ig_resp = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                self._send_json(400, {"error": f"Instagram Graph API hatası: {e.code}"})
                return
            except Exception as e:
                self._send_json(500, {"error": f"Instagram bağlantısı başarısız: {e}"})
                return

            content = load_content()
            existing_urls = {p.get("url") for p in content.get("socialPosts", [])}
            added = 0
            for media in ig_resp.get("data", []):
                permalink = media.get("permalink")
                if not permalink or permalink in existing_urls:
                    continue
                caption = (media.get("caption") or "Instagram Paylaşımı").strip()
                first_line = caption.splitlines()[0][:90] if caption else "Instagram Paylaşımı"
                raw_img = media.get("thumbnail_url") if media.get("media_type") == "VIDEO" else media.get("media_url")
                saved_img = download_image_safely(raw_img) if raw_img else None
                new_post = {
                    "id": f"ig-{uuid.uuid4().hex[:8]}",
                    "platform": "instagram",
                    "platformLabel": "Instagram",
                    "date": format_tr_date(),
                    "title": first_line,
                    "excerpt": caption[:240],
                    "image": saved_img,
                    "metric": "Instagram",
                    "url": permalink,
                }
                content.setdefault("socialPosts", []).insert(0, new_post)
                existing_urls.add(permalink)
                added += 1

            save_content(content)
            self._send_json(200, {"ok": True, "added": added})
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

        if path == "/api/admin/feeds":
            body = self._read_json_body(4096) or {}
            feed_id = body.get("id")
            feeds = load_feeds()
            new_feeds = [f for f in feeds if f.get("id") != feed_id]
            save_feeds(new_feeds)
            self._send_json(200, {"ok": True})
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

            with CONTENT_LOCK:
                content = load_content()
                content.setdefault(section, []).insert(0, item)
                save_content(content)
            self._send_json(201, {"ok": True, "item": item})
            return

        self._send_json(404, {"error": "Bilinmeyen uç nokta."})

    def _handle_social_webhook(self):
        secret_data = load_secret()
        if not secret_data or not secret_data.get("webhook_secret"):
            self._send_json(503, {"error": "Webhook henüz yapılandırılmamış."})
            return

        expected_secret = secret_data["webhook_secret"]
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"error": "Geçersiz Content-Length."})
            return
        if length <= 0 or length > 1024 * 1024:
            self._send_json(400, {"error": "Geçersiz istek boyutu."})
            return

        raw_body = self.rfile.read(length)

        # Doğrulama: X-Webhook-Secret, Authorization: Bearer veya GitHub X-Hub-Signature-256
        header_secret = self.headers.get("X-Webhook-Secret", "").strip()
        auth_header = self.headers.get("Authorization", "").strip()
        if auth_header.lower().startswith("bearer "):
            header_secret = auth_header[7:].strip()

        gh_sig = self.headers.get("X-Hub-Signature-256", "").strip()
        authorized = False
        if header_secret and hmac.compare_digest(header_secret, expected_secret):
            authorized = True
        elif gh_sig.startswith("sha256="):
            mac = hmac.new(
                expected_secret.encode("utf-8"),
                raw_body,
                hashlib.sha256,
            ).hexdigest()
            if hmac.compare_digest(gh_sig[7:], mac):
                authorized = True

        if not authorized:
            self._send_json(401, {"error": "Geçersiz webhook anahtarı veya imzası."})
            return

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            self._send_json(400, {"error": "Geçersiz JSON gövdesi."})
            return

        gh_event = self.headers.get("X-GitHub-Event", "").strip().lower()
        if gh_event == "ping":
            self._send_json(200, {"ok": True, "message": "GitHub webhook bağlantısı doğrulandı."})
            return

        platform_labels = {
            "instagram": "Instagram",
            "linkedin": "LinkedIn",
            "github": "GitHub",
            "youtube": "YouTube",
        }

        if gh_event:
            repo = payload.get("repository") or {}
            repo_name = repo.get("name") or "GitHub"
            repo_url = repo.get("html_url") or "https://github.com"
            lang = repo.get("language") or "Kod"
            stars = repo.get("stargazers_count", 0)

            event_dt = None
            if gh_event == "push":
                head = payload.get("head_commit") or {}
                title = f"{repo_name} — Yeni Güncelleme"
                excerpt = (head.get("message") or repo.get("description") or "Yeni kod güncellemesi paylaşıldı.").splitlines()[0]
                url = head.get("url") or repo_url
                event_dt = parse_any_datetime(head.get("timestamp"))
            elif gh_event == "release":
                rel = payload.get("release") or {}
                title = f"{repo_name} {rel.get('tag_name', '')}".strip()
                excerpt = (rel.get("name") or rel.get("body") or "Yeni sürüm yayınlandı.")[:180]
                url = rel.get("html_url") or repo_url
                event_dt = parse_any_datetime(rel.get("published_at") or rel.get("created_at"))
            else:
                title = repo_name
                excerpt = repo.get("description") or f"GitHub üzerinde {gh_event} aktivitesi."
                url = repo_url
                event_dt = parse_any_datetime(repo.get("created_at"))

            new_post = {
                "id": f"wh-{uuid.uuid4().hex[:8]}",
                "platform": "github",
                "platformLabel": "GitHub",
                "date": format_tr_date(event_dt),
                "title": title,
                "excerpt": excerpt,
                "image": None,
                "metric": f"★ {stars} yıldız · {lang}",
                "url": url,
            }
        else:
            platform = str(payload.get("platform", "")).strip().lower()
            if platform not in platform_labels:
                self._send_json(400, {"error": "platform alanı instagram, linkedin, github veya youtube olmalıdır."})
                return

            title = str(payload.get("title", "")).strip() or f"Yeni {platform_labels[platform]} Paylaşımı"
            excerpt = str(payload.get("excerpt", "")).strip()
            url = str(payload.get("url", "")).strip() or "https://"
            raw_image = str(payload.get("image") or "").strip()
            saved_image = download_image_safely(raw_image) if raw_image else None
            pub_dt = parse_any_datetime(payload.get("publishedAt"))
            date_str = str(payload.get("date") or "").strip() or format_tr_date(pub_dt)

            new_post = {
                "id": f"wh-{uuid.uuid4().hex[:8]}",
                "platform": platform,
                "platformLabel": platform_labels[platform],
                "date": date_str,
                "title": title[:140],
                "excerpt": excerpt[:320],
                "image": saved_image,
                "metric": str(payload.get("metric") or "").strip() or "Yeni",
                "url": url,
            }
            if platform == "youtube" and payload.get("youtubeId"):
                new_post["youtubeId"] = str(payload["youtubeId"]).strip()

        with CONTENT_LOCK:
            content = load_content()
            existing_urls = {p.get("url") for p in content.get("socialPosts", []) if p.get("url")}
            if new_post.get("url") and new_post["url"] in existing_urls:
                self._send_json(200, {"ok": True, "duplicate": True, "url": new_post["url"]})
                return
            content.setdefault("socialPosts", []).insert(0, new_post)
            save_content(content)
        self._send_json(201, {"ok": True, "item": new_post})

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
            with CONTENT_LOCK:
                content = load_content()
                content["profile"].update(body["profile"])
                if isinstance(body.get("institutions"), list):
                    content["institutions"] = [str(x).strip() for x in body["institutions"] if str(x).strip()]
                save_content(content)
            self._send_json(200, {"ok": True})
            return

        if path == "/api/admin/item":
            body = self._read_json_body(1024 * 1024)
            if not body:
                self._send_json(400, {"error": "Geçersiz içerik verisi."})
                return
            section = body.get("section")
            item_id = body.get("id")
            item = body.get("item")
            if section not in {"socialPosts", "projects", "ideas", "events"} or not item_id or not isinstance(item, dict):
                self._send_json(400, {"error": "Geçersiz bölüm, ID veya öğe."})
                return

            with CONTENT_LOCK:
                content = load_content()
                items = content.get(section, [])
                updated = None
                for idx, existing in enumerate(items):
                    if existing.get("id") == item_id:
                        merged = dict(existing)
                        merged.update(item)
                        merged["id"] = item_id
                        items[idx] = merged
                        updated = merged
                        break
                if updated is None:
                    self._send_json(404, {"error": "Düzenlenecek öğe bulunamadı."})
                    return
                save_content(content)
            self._send_json(200, {"ok": True, "item": updated})
            return

        self._send_json(404, {"error": "Bilinmeyen uç nokta."})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        user = self._get_authenticated_user()
        if not user:
            self._send_json(401, {"error": "Yetkisiz erişim."})
            return

        if path == "/api/admin/feeds":
            body = self._read_json_body(4096) or {}
            feed_id = body.get("id")
            feeds = load_feeds()
            new_feeds = [f for f in feeds if f.get("id") != feed_id]
            save_feeds(new_feeds)
            self._send_json(200, {"ok": True})
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
            self.send_error(403, "Forbidden")
            return

        if parts[0] == "uploads" and len(parts) == 2:
            target = (UPLOADS_DIR / parts[1]).resolve()
            try:
                target.relative_to(UPLOADS_DIR.resolve())
            except ValueError:
                self.send_error(403, "Forbidden")
                return
            if not target.is_file():
                fallback = (BASE_DIR / "uploads" / parts[1]).resolve()
                if fallback.is_file():
                    target = fallback
        else:
            target = (BASE_DIR / rel).resolve()
            try:
                target.relative_to(BASE_DIR)
            except ValueError:
                self.send_error(403, "Forbidden")
                return

        if not target.is_file():
            self.send_error(404, "Not Found")
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

    start_feed_bot_thread()
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
