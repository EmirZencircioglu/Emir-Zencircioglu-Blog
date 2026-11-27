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
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
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
MESSAGES_FILE = DATA_DIR / "messages.json"
CHAT_LOGS_FILE = DATA_DIR / "chat_logs.json"
TRANSLATION_EN_FILE = DATA_DIR / "translations_en.json"

CONTENT_LOCK = threading.Lock()
MESSAGES_LOCK = threading.Lock()
CHAT_LOGS_LOCK = threading.Lock()
TRANSLATE_LOCK = threading.Lock()
BOT_INTERVAL_SECONDS = 300  # 5 dakikada bir otomatik kontrol
BOT_LAST_RUN = {"time": None, "added": 0, "error": None}

SESSION_COOKIE_NAME = "blog_admin_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 gün
MAX_UPLOAD_BYTES = 12 * 1024 * 1024  # 12 MB
ALLOWED_IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "gif"}
ALLOWED_UPLOAD_EXTS = ALLOWED_IMAGE_EXTS | {"pdf"}

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
        **existing,
        "username": username.strip(),
        "salt": salt_hex,
        "password_hash": pw_hash,
        "session_secret": secrets.token_hex(32),
        "webhook_secret": existing.get("webhook_secret") or secrets.token_hex(24),
        "created_at": existing.get("created_at") or int(time.time()),
        "updated_at": int(time.time()),
    }
    _write_secret_file(payload)


def apply_env_admin_reset():
    """Ortam değişkeni (ADMIN_RESET_PASSWORD / ADMIN_RESET_USERNAME) ile güvenli şifre sıfırlama."""
    reset_pw = os.environ.get("ADMIN_RESET_PASSWORD", "").strip()
    if not reset_pw:
        return
    if len(reset_pw) < 8:
        print("[Admin Reset] ADMIN_RESET_PASSWORD en az 8 karakter olmalı, atlandı.", flush=True)
        return
    existing = load_secret() or {}
    reset_user = (
        os.environ.get("ADMIN_RESET_USERNAME", "").strip()
        or str(existing.get("username") or "").strip()
        or "admin"
    )
    if len(reset_user) < 3:
        print("[Admin Reset] Kullanıcı adı en az 3 karakter olmalı, atlandı.", flush=True)
        return
    if (
        existing.get("username") == reset_user
        and existing.get("salt")
        and existing.get("password_hash")
        and verify_password(reset_pw, existing["salt"], existing["password_hash"])
    ):
        return
    save_secret(reset_user, reset_pw)
    print(
        f"[Admin Reset] Admin şifresi güncellendi (kullanıcı adı: {reset_user}). "
        "Giriş yaptıktan sonra ADMIN_RESET_PASSWORD değişkenini silebilirsiniz.",
        flush=True,
    )


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
    # Gemini 4 ailesi (en yeni nesil öncelikli)
    "gemini-4.5-flash",
    "gemini-4.0-flash",
    "gemini-4-flash",
    "gemini-4-flash-lite",
    "gemini-4.5-pro",
    "gemini-4.0-pro",
    "gemini-4-pro",
    # Gemini 3 ailesi & güncel takma adlar
    "gemini-3.8-flash",
    "gemini-3.8-flash-lite",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-3.8-pro",
    "gemini-pro-latest",
]
_CACHED_GEMINI_MODEL: str | None = None
_DISCOVERED_MODELS_CACHE: dict[str, object] = {"ts": 0.0, "models": []}
_MODEL_COOLDOWN: dict[str, float] = {}
_MODEL_STATE_LOCK = threading.Lock()


def _is_model_cooled_down(model: str) -> bool:
    with _MODEL_STATE_LOCK:
        until = _MODEL_COOLDOWN.get(model, 0.0)
        if until <= time.time():
            _MODEL_COOLDOWN.pop(model, None)
            return False
        return True


def _set_model_cooldown(model: str, seconds: float):
    with _MODEL_STATE_LOCK:
        _MODEL_COOLDOWN[model] = time.time() + seconds


def _save_working_gemini_model(model: str):
    global _CACHED_GEMINI_MODEL
    with _MODEL_STATE_LOCK:
        _CACHED_GEMINI_MODEL = model
        _MODEL_COOLDOWN.pop(model, None)
    try:
        secret_data = load_secret()
        if secret_data and secret_data.get("gemini_working_model") != model:
            secret_data["gemini_working_model"] = model
            _write_secret_file(secret_data)
    except Exception:
        pass


def _get_working_gemini_model() -> str | None:
    global _CACHED_GEMINI_MODEL
    with _MODEL_STATE_LOCK:
        if _CACHED_GEMINI_MODEL:
            return _CACHED_GEMINI_MODEL
    try:
        secret_data = load_secret() or {}
        saved = str(secret_data.get("gemini_working_model") or "").strip()
        if saved:
            with _MODEL_STATE_LOCK:
                _CACHED_GEMINI_MODEL = saved
            return saved
    except Exception:
        pass
    return None


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
    hero = content.get("hero") or {}
    contact = content.get("contact") or {}
    projects = content.get("projects") or []
    events = content.get("events") or []
    ideas = content.get("ideas") or []
    social = content.get("socialPosts") or []
    credentials = content.get("credentials") or []
    institutions = content.get("institutions") or []
    phone_disp = str(contact.get("phoneDisplay") or "0537 775 12 24").strip()
    contact_desc = str(
        contact.get("description")
        or "Üniversite eğitimini yazılım ve ürün geliştirme projeleriyle beslerken sermaye piyasaları, yatırım, hazine ve bankacılık süreçlerinde de kendini aktif geliştiren bir öğrenci; büyük ölçekli bankaların ve kurumsal şirketlerin hazine, yatırım veya teknoloji ekiplerinde sorumluluk almaya açık."
    ).strip()

    proj_lines = [
        f"- {p.get('title')} ({p.get('year', '')}, {p.get('status', '')}): {p.get('description', '')} | Teknolojiler: {', '.join(p.get('stack') or [])}"
        for p in projects[:15]
    ]
    cred_lines = [
        f"- [{c.get('kindLabel', c.get('kind', ''))}] {c.get('title')} — {c.get('org', '')} ({c.get('date', '')}): {c.get('detail', '')}"
        for c in credentials[:20]
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
    has_cv_tr = bool(profile.get("cvUrlTr") or profile.get("cvUrl"))
    has_cv_en = bool(profile.get("cvUrlEn"))
    if has_cv_tr and has_cv_en:
        cv_note = "Siteden hem Türkçe hem İngilizce PDF özgeçmiş (CV) indirilebilir."
    elif has_cv_tr or has_cv_en:
        cv_note = "Siteden PDF özgeçmiş (CV) indirilebilir."
    else:
        cv_note = ""

    return (
        "Sen Emir Zencircioğlu'nun kişisel blog ve portfolyo sitesindeki resmi yapay zeka asistanısın ('Emir AI').\n"
        "Görevin: Siteyi inceleyen İK uzmanları, banka/finans yöneticileri, şirket çalışanları ve ziyaretçilerin "
        "Emir hakkındaki sorularını net, kibar, profesyonel ve ikna edici biçimde yanıtlamak.\n\n"
        "Kurallar:\n"
        "1. Ziyaretçi hangi dilde yazarsa o dilde yanıt ver (varsayılan Türkçe).\n"
        "2. Sadece aşağıdaki güncel site verilerine ve bağlama dayan; bilmediğin bilgileri uydurma.\n"
        "3. Kısa, okunabilir ve doğrudan sorulara odaklanan yanıtlar ver.\n"
        f"4. İletişim veya staj/iş birliği sorulursa telefon ({phone_disp}), e-posta ve sitedeki hızlı iletişim formunu paylaş. {cv_note}\n\n"
        f"=== PROFİL ===\n"
        f"Ad Soyad: {profile.get('name', 'Emir Zencircioğlu')}\n"
        f"Rol: {profile.get('role', '')}\n"
        f"Durum: {profile.get('status', '')}\n"
        f"Biyografi: {profile.get('bio', '')}\n"
        f"Giriş Özeti: {hero.get('subtitle', '')}\n"
        f"Kariyer Hedefi & Konumlandırma: {contact_desc}\n"
        f"İlgi Alanları: {', '.join(profile.get('interests') or [])}\n"
        f"Güncel Odak: {'; '.join(profile.get('now') or [])}\n"
        f"E-posta: {profile.get('email', 'ezencircioglu0024@gmail.com')}\n"
        f"Telefon: {phone_disp}\n"
        f"Katıldığı Kurumlar / Ekosistemler: {', '.join(institutions)}\n\n"
        f"=== EĞİTİM, SERTİFİKA & YETKİNLİKLER ===\n" + ("\n".join(cred_lines) or "Henüz eğitim/sertifika eklenmedi.") + "\n\n"
        f"=== PROJELER ===\n" + ("\n".join(proj_lines) or "Henüz proje listelenmedi.") + "\n\n"
        f"=== ETKİNLİK, BANKA VE ZİRVEMELER ===\n" + ("\n".join(event_lines) or "Henüz etkinlik listelenmedi.") + "\n\n"
        f"=== FİKİRLER VE YAZILAR ===\n" + ("\n".join(idea_lines) or "Henüz yazı listelenmedi.") + "\n\n"
        f"=== SON SOSYAL PAYLAŞIMLAR ===\n" + ("\n".join(social_lines) or "Henüz paylaşım listelenmedi.")
    )


CONTACT_RATE_LIMIT: dict[str, list[float]] = {}
_MARKET_PULSE_CACHE: dict[str, object] = {"ts": 0.0, "items": []}


def load_messages() -> list:
    ensure_dirs()
    with MESSAGES_LOCK:
        if not MESSAGES_FILE.exists():
            return []
        try:
            with MESSAGES_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []


def save_messages(items: list):
    ensure_dirs()
    with MESSAGES_LOCK:
        tmp = MESSAGES_FILE.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        os.replace(tmp, MESSAGES_FILE)


def load_chat_logs() -> list:
    ensure_dirs()
    with CHAT_LOGS_LOCK:
        if not CHAT_LOGS_FILE.exists():
            return []
        try:
            with CHAT_LOGS_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []


def append_chat_log(
    question: str,
    model_used: str | None,
    ok: bool,
    answer: str | None = None,
):
    ensure_dirs()
    entry = {
        "id": f"cl-{uuid.uuid4().hex[:8]}",
        "question": str(question or "").strip()[:500],
        "answer": str(answer or "").strip()[:8000],
        "model": model_used or "",
        "ok": bool(ok),
        "createdAt": datetime.now(TR_TZ).strftime("%d.%m.%Y %H:%M"),
    }
    with CHAT_LOGS_LOCK:
        logs = []
        if CHAT_LOGS_FILE.exists():
            try:
                with CHAT_LOGS_FILE.open("r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, list):
                    logs = loaded
            except Exception:
                logs = []
        logs.insert(0, entry)
        logs = logs[:250]
        tmp = CHAT_LOGS_FILE.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CHAT_LOGS_FILE)


def fetch_market_pulse() -> list[dict]:
    """Canlı döviz ve piyasa referans değerlerini 5 dk önbellekle çeker."""
    now_ts = time.time()
    cached = _MARKET_PULSE_CACHE.get("items") or []
    if cached and now_ts - float(_MARKET_PULSE_CACHE.get("ts") or 0.0) < 300:
        return list(cached)

    items: list[dict] = []
    try:
        req = urllib.request.Request(
            "https://open.er-api.com/v6/latest/USD",
            headers={"User-Agent": "EmirPortfolioPulse/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            fx = json.loads(resp.read().decode("utf-8"))
        rates = fx.get("rates") or {}
        usd_try = float(rates.get("TRY") or 0)
        eur_per_usd = float(rates.get("EUR") or 0)
        gbp_per_usd = float(rates.get("GBP") or 0)
        if usd_try > 0:
            items.append({"symbol": "USD/TRY", "value": f"{usd_try:.2f}"})
            if eur_per_usd > 0:
                items.append({"symbol": "EUR/TRY", "value": f"{usd_try / eur_per_usd:.2f}"})
            if gbp_per_usd > 0:
                items.append({"symbol": "GBP/TRY", "value": f"{usd_try / gbp_per_usd:.2f}"})
            if eur_per_usd > 0:
                items.append({"symbol": "EUR/USD", "value": f"{1.0 / eur_per_usd:.4f}"})
    except Exception:
        pass

    if items:
        _MARKET_PULSE_CACHE["ts"] = now_ts
        _MARKET_PULSE_CACHE["items"] = items
    return items


def _model_sort_key(name: str) -> tuple:
    lower = name.lower()
    is_gemini = 0 if lower.startswith("gemini") else 1
    m = re.search(r"(\d+)(?:\.(\d+))?", lower)
    major = int(m.group(1)) if m else 0
    minor = int(m.group(2) or 0) if m else 0
    # flash-lite / flash önce (hızlı), sonra pro, sonra diğerleri
    if "flash" in lower and "lite" not in lower:
        tier = 0
    elif "flash" in lower:
        tier = 1
    elif "pro" in lower:
        tier = 2
    else:
        tier = 3
    is_exp = 1 if any(tag in lower for tag in ("exp", "preview")) else 0
    return (is_gemini, -major, -minor, tier, is_exp, lower)


def _discover_gemini_models(api_key: str) -> list[str]:
    """Kullanılabilir tüm generateContent Gemini/Gemma modellerini API'den dinamik çeker."""
    now_ts = time.time()
    cached_list = _DISCOVERED_MODELS_CACHE.get("models") or []
    if cached_list and now_ts - float(_DISCOVERED_MODELS_CACHE.get("ts") or 0.0) < 600:
        return list(cached_list)

    raw_models = []
    page_token = ""
    for _ in range(4):
        url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=100"
        if page_token:
            url += f"&pageToken={urllib.request.quote(page_token)}"
        req = urllib.request.Request(url, method="GET", headers={"x-goog-api-key": api_key})
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            print(f"[Gemini discover] HTTP {e.code}: {err_body[:300]}", flush=True)
            if e.code in (401, 403) or (e.code == 400 and "api key" in err_body.lower()):
                raise RuntimeError("Gemini API anahtarı geçersiz veya yetkisiz görünüyor.") from e
            break
        except Exception as e:
            print(f"[Gemini discover] Exception: {e}", flush=True)
            break

        raw_models.extend(data.get("models") or [])
        page_token = str(data.get("nextPageToken") or "").strip()
        if not page_token:
            break

    excluded = (
        "tts", "image", "embedding", "aqa", "robotics",
        "computer-use", "audio", "veo", "imagen", "lyria",
        "transcribe", "nano-banana",
    )
    candidates = []
    seen = set()
    for m in raw_models:
        methods = m.get("supportedGenerationMethods") or []
        if "generateContent" not in methods:
            continue
        name = str(m.get("name") or "").removeprefix("models/").strip()
        lower = name.lower()
        if not name or name in seen or any(tag in lower for tag in excluded):
            continue
        seen.add(name)
        candidates.append(name)

    candidates.sort(key=_model_sort_key)
    print(f"[Gemini discover] {len(candidates)} active chat models: {candidates[:20]}", flush=True)
    if candidates:
        _DISCOVERED_MODELS_CACHE["ts"] = now_ts
        _DISCOVERED_MODELS_CACHE["models"] = candidates
    return candidates


def _try_gemini_model(api_key: str, model: str, payload_bytes: bytes, fallback_bytes: bytes | None = None, timeout_sec: float = 7) -> tuple[str | None, str | None, bool]:
    """Tek bir modeli dener: (reply_text, err_msg, retryable). Yoğunlukta (429/503) diğer modele geçer."""
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
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        candidates = data.get("candidates") or []
        if candidates:
            parts = (candidates[0].get("content") or {}).get("parts") or []
            visible_parts = [p for p in parts if not p.get("thought")]
            reply_text = "".join(str(p.get("text", "")) for p in (visible_parts or parts)).strip()
            finish_reason = candidates[0].get("finishReason") or ""
            if reply_text:
                print(
                    f"[Gemini success] model={model} finishReason={finish_reason} chars={len(reply_text)}",
                    flush=True,
                )
                return reply_text, None, False
        _set_model_cooldown(model, 45)
        return None, f"Model boş yanıt döndürdü ({model}).", True
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        print(f"[Gemini try {model}] HTTP {e.code}: {err_body[:220]}", flush=True)
        if e.code in (401, 403) or (e.code == 400 and "api key" in err_body.lower()):
            raise RuntimeError("Gemini API anahtarı geçersiz veya yetkisiz görünüyor.") from e
        if e.code == 400 and "developer instruction" in err_body.lower() and fallback_bytes is not None:
            return _try_gemini_model(api_key, model, fallback_bytes, None, timeout_sec)
        if e.code == 429:
            _set_model_cooldown(model, 300)
        elif e.code == 404:
            _set_model_cooldown(model, 600)
        elif e.code in (500, 502, 503, 504):
            _set_model_cooldown(model, 90)
        else:
            _set_model_cooldown(model, 60)

        if e.code in (404, 429, 500, 502, 503, 504):
            detail = ""
            try:
                detail = str((json.loads(err_body).get("error") or {}).get("message") or "")
            except Exception:
                detail = err_body[:120]
            return None, f"{model} ({e.code}): {detail[:120]}", True
        return None, f"Gemini API hatası ({e.code}, {model}): {err_body[:160]}", True
    except Exception as e:
        print(f"[Gemini try {model}] Exception: {e}", flush=True)
        _set_model_cooldown(model, 90)
        return None, f"Bağlantı hatası ({model}): {e}", True


def _run_gemini_with_failover(
    api_key: str,
    payload_bytes: bytes,
    fallback_bytes: bytes,
    timeout_sec: float = 12,
    budget_sec: float = 24,
    max_attempts: int = 4,
) -> str:
    """Ücretsiz katman kotasını koruyarak sıralı (tekil) model failover uygular."""
    global _CACHED_GEMINI_MODEL
    last_error = "Gemini servisine bağlanılamadı."
    start_ts = time.monotonic()
    attempts = 0
    quota_hits = 0

    cached_model = _get_working_gemini_model()
    if cached_model and not _is_model_cooled_down(cached_model):
        attempts += 1
        reply_text, err_msg, _ = _try_gemini_model(api_key, cached_model, payload_bytes, fallback_bytes, timeout_sec)
        if reply_text:
            _save_working_gemini_model(cached_model)
            return reply_text
        if err_msg:
            last_error = err_msg
            if "(429)" in err_msg:
                quota_hits += 1
        with _MODEL_STATE_LOCK:
            if _CACHED_GEMINI_MODEL == cached_model:
                _CACHED_GEMINI_MODEL = None

    discovered = _discover_gemini_models(api_key)
    pool = discovered if discovered else list(GEMINI_MODELS)
    active_pool = [m for m in pool if m and m != cached_model and not _is_model_cooled_down(m)]
    if not active_pool:
        active_pool = [m for m in pool if m and m != cached_model][:max(1, max_attempts - attempts)]

    for model_name in active_pool:
        if attempts >= max_attempts or time.monotonic() - start_ts > budget_sec:
            break
        if quota_hits >= 2:
            break
        attempts += 1
        reply_text, err_msg, _ = _try_gemini_model(api_key, model_name, payload_bytes, fallback_bytes, timeout_sec)
        if reply_text:
            _save_working_gemini_model(model_name)
            return reply_text
        if err_msg:
            last_error = err_msg
            if "(429)" in err_msg:
                quota_hits += 1

    raise RuntimeError(f"Tüm Gemini modelleri şu anda yoğun. Lütfen birkaç saniye sonra tekrar deneyin. ({last_error})")


def call_gemini_api(api_key: str, system_prompt: str, history: list, user_message: str) -> str:
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
            "generationConfig": {"temperature": 0.65, "maxOutputTokens": 4096},
        },
        ensure_ascii=False,
    ).encode("utf-8")

    fallback_contents = [
        {"role": "user", "parts": [{"text": f"[SİSTEM TALİMATI]\n{system_prompt}\n\n[SORU]\n{contents[0]['parts'][0]['text']}"}]},
        *contents[1:],
    ]
    fallback_bytes = json.dumps(
        {
            "contents": fallback_contents,
            "generationConfig": {"temperature": 0.65, "maxOutputTokens": 4096},
        },
        ensure_ascii=False,
    ).encode("utf-8")

    return _run_gemini_with_failover(api_key, payload_bytes, fallback_bytes, timeout_sec=12, budget_sec=24)


def _extract_translatable_payload(content: dict) -> dict:
    profile = content.get("profile") or {}
    hero = content.get("hero") or {}
    contact = content.get("contact") or {}
    site = content.get("site") or {}

    return {
        "profile": {
            "brandName": profile.get("brandName") or "",
            "role": profile.get("role") or "",
            "status": profile.get("status") or "",
            "bio": profile.get("bio") or "",
            "interests": list(profile.get("interests") or []),
            "now": list(profile.get("now") or []),
        },
        "hero": {
            "kicker": hero.get("kicker") or "FİNANS · SERMAYE PİYASALARI · TEKNOLOJİ",
            "titleLine1": hero.get("titleLine1") or "Piyasaları okuyan,",
            "titlePrefix": hero.get("titlePrefix") or "teknolojiyle",
            "titleHighlight": hero.get("titleHighlight") or "değer üreten",
            "titleLine3": hero.get("titleLine3") or "bir bakış açısı.",
            "subtitle": hero.get("subtitle") or "Yazılım ve ürün geliştirme çalışmalarımı sermaye piyasaları, yatırım ve hazine perspektifimle birleştiriyor; katıldığım kurumları, zirveleri ve fikirlerimi burada şeffafça paylaşıyorum.",
            "pillars": list(hero.get("pillars") or ["Sermaye Piyasaları & Yatırım", "Hazine & Bankacılık", "Yazılım & Dijital Ürün"]),
            "primaryCtaText": hero.get("primaryCtaText") or "Benimle Tanışın",
            "secondaryCtaText": hero.get("secondaryCtaText") or "Projeler & Zirveler",
        },
        "contact": {
            "titlePrefix": contact.get("titlePrefix") or "Sermaye piyasaları, hazine ve teknolojinin kesişiminde",
            "titleHighlight": contact.get("titleHighlight") or "değer üretmeye hazırım.",
            "description": contact.get("description") or "Üniversite eğitimimi yazılım projeleri ve zirvelerle beslerken sermaye piyasaları, yatırım ve hazine süreçlerinde de kendimi aktif olarak geliştiriyorum. Büyük ölçekli bankaların ve kurumsal şirketlerin hazine, yatırım veya teknoloji ekiplerinde sorumluluk alarak öğrenmeye ve somut katkı sunmaya açığım.",
            "footerNote": contact.get("footerNote") or "Tüm hakları saklıdır.",
        },
        "site": {
            "topCtaText": site.get("topCtaText") or "Tanışalım ↗",
            "tickerItems": list(site.get("tickerItems") or ["SERMAYE PİYASALARI", "YATIRIM & HAZİNE", "YAZILIM & FİNTECH", "ZİRVELER & KURUMLAR", "AÇIK KAYNAK PROJELER"]),
            "tabRoles": list(site.get("tabRoles") or ["Sermaye Piyasaları", "Finans", "Hazine & Yatırım", "Teknoloji", "Fintech & Analiz"]),
            "aboutTitlePrefix": site.get("aboutTitlePrefix") or "Disiplinler Arası",
            "aboutTitleHighlight": site.get("aboutTitleHighlight") or "Profil",
            "projectsTitlePrefix": site.get("projectsTitlePrefix") or "Ürettiğim",
            "projectsTitleHighlight": site.get("projectsTitleHighlight") or "Sistemler",
            "eventsTitlePrefix": site.get("eventsTitlePrefix") or "Katıldığım",
            "eventsTitleHighlight": site.get("eventsTitleHighlight") or "Ekosistemler",
            "ideasTitlePrefix": site.get("ideasTitlePrefix") or "Notlar &",
            "ideasTitleHighlight": site.get("ideasTitleHighlight") or "Bakış Açıları",
            "socialTitlePrefix": site.get("socialTitlePrefix") or "Instagram, LinkedIn, GitHub &",
            "socialTitleHighlight": site.get("socialTitleHighlight") or "YouTube",
        },
        "projects": [
            {"id": p.get("id"), "title": p.get("title") or "", "status": p.get("status") or "", "description": p.get("description") or ""}
            for p in (content.get("projects") or [])
        ],
        "events": [
            {"id": e.get("id"), "categoryLabel": e.get("categoryLabel") or "", "date": e.get("date") or "", "place": e.get("place") or "", "title": e.get("title") or "", "description": e.get("description") or ""}
            for e in (content.get("events") or [])
        ],
        "ideas": [
            {"id": i.get("id"), "tag": i.get("tag") or "", "date": i.get("date") or "", "readTime": i.get("readTime") or "", "title": i.get("title") or "", "summary": i.get("summary") or "", "content": list(i.get("content") or [])}
            for i in (content.get("ideas") or [])
        ],
        "socialPosts": [
            {"id": s.get("id"), "date": s.get("date") or "", "title": s.get("title") or "", "excerpt": s.get("excerpt") or "", "metric": s.get("metric") or ""}
            for s in (content.get("socialPosts") or [])
        ],
        "credentials": [
            {"id": c.get("id"), "kindLabel": c.get("kindLabel") or "", "date": c.get("date") or "", "title": c.get("title") or "", "org": c.get("org") or "", "detail": c.get("detail") or ""}
            for c in (content.get("credentials") or [])
        ],
        "institutions": list(content.get("institutions") or []),
    }


def _merge_translated_payload(content: dict, tr_en: dict) -> dict:
    merged = json.loads(json.dumps(content, ensure_ascii=False))
    for section_key in ("profile", "hero", "contact", "site"):
        if isinstance(tr_en.get(section_key), dict):
            merged.setdefault(section_key, {}).update(tr_en[section_key])
    if isinstance(tr_en.get("institutions"), list) and len(tr_en["institutions"]) == len(merged.get("institutions") or []):
        merged["institutions"] = tr_en["institutions"]

    for list_key in ("projects", "events", "ideas", "socialPosts", "credentials"):
        orig_list = merged.get(list_key) or []
        trans_list = tr_en.get(list_key) or []
        by_id = {x.get("id"): x for x in trans_list if isinstance(x, dict) and x.get("id")}
        for idx, item in enumerate(orig_list):
            match = by_id.get(item.get("id")) or (trans_list[idx] if idx < len(trans_list) and isinstance(trans_list[idx], dict) else None)
            if match:
                for k, v in match.items():
                    if k != "id" and v not in (None, ""):
                        item[k] = v
    return merged


def get_english_translation() -> tuple[dict | None, bool]:
    """İngilizce çeviriyi hash önbelleğinden okur; değişmişse Gemini ile çevirip kaydeder."""
    content = load_content()
    src_payload = _extract_translatable_payload(content)
    content_hash = hashlib.sha256(
        json.dumps(src_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()

    if TRANSLATION_EN_FILE.exists():
        try:
            with TRANSLATION_EN_FILE.open("r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("hash") == content_hash and isinstance(cached.get("data"), dict):
                return _merge_translated_payload(content, cached["data"]), True
        except Exception:
            pass

    api_key, _ = get_gemini_api_key()
    if not api_key:
        return None, False

    with TRANSLATE_LOCK:
        if TRANSLATION_EN_FILE.exists():
            try:
                with TRANSLATION_EN_FILE.open("r", encoding="utf-8") as f:
                    cached = json.load(f)
                if cached.get("hash") == content_hash and isinstance(cached.get("data"), dict):
                    return _merge_translated_payload(content, cached["data"]), True
            except Exception:
                pass

        sys_instr = (
            "You are a professional bilingual financial & technology translator. "
            "Translate all Turkish values in the input JSON into natural, executive-grade English suitable for "
            "investment banking, capital markets, treasury, and tech recruiting audiences.\n"
            "Rules:\n"
            "1. Return ONLY valid raw JSON matching the exact input schema, keys, array lengths, and every 'id'.\n"
            "2. Keep personal names (e.g. Emir Zencircioğlu) and official proper names (like Borsa İstanbul, Microsoft Türkiye, İş Bankası, DenizBank) recognizable (you may translate generic role/descriptor words or add clean English equivalents like 'Capital Markets Congress').\n"
            "3. Translate Turkish dates cleanly (e.g. '10 Kasım 2026' -> 'Nov 10, 2026').\n"
            "4. Keep all punctuation, arrows (↗), and concise executive tone."
        )
        src_json = json.dumps(src_payload, ensure_ascii=False)
        payload_bytes = json.dumps(
            {
                "systemInstruction": {"parts": [{"text": sys_instr}]},
                "contents": [{"role": "user", "parts": [{"text": src_json}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 6144,
                    "responseMimeType": "application/json",
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")
        fallback_bytes = json.dumps(
            {
                "contents": [{"role": "user", "parts": [{"text": f"{sys_instr}\n\nJSON:\n{src_json}"}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 6144},
            },
            ensure_ascii=False,
        ).encode("utf-8")

        raw_reply = _run_gemini_with_failover(
            api_key,
            payload_bytes,
            fallback_bytes,
            timeout_sec=16,
            budget_sec=28,
            max_attempts=2,
        )
        cleaned = raw_reply.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.DOTALL).strip()
        start_brace = cleaned.find("{")
        end_brace = cleaned.rfind("}")
        if start_brace != -1 and end_brace > start_brace:
            cleaned = cleaned[start_brace:end_brace + 1]
        translated_dict = json.loads(cleaned)

        ensure_dirs()
        tmp = TRANSLATION_EN_FILE.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump({"hash": content_hash, "data": translated_dict, "updatedAt": int(time.time())}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, TRANSLATION_EN_FILE)
        print("[Translate EN] Generated and cached English translation", flush=True)
        return _merge_translated_payload(content, translated_dict), False


_LAST_PREWARM_TS = 0.0


def _prewarm_en_translation():
    global _LAST_PREWARM_TS
    now_ts = time.time()
    if now_ts - _LAST_PREWARM_TS < 120:
        return
    _LAST_PREWARM_TS = now_ts
    try:
        get_english_translation()
    except Exception as e:
        print(f"[Translate prewarm] skipped: {e}", flush=True)


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
    threading.Thread(target=_prewarm_en_translation, daemon=True).start()


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

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def _send_json(self, status: int, data: dict, extra_headers: dict | None = None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        req_path = urlparse(self.path).path
        if req_path in ("/api/chat", "/api/chat/status", "/api/content", "/api/contact", "/api/market-pulse", "/api/translate"):
            self.send_header("Access-Control-Allow-Origin", "*")
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

        if path == "/api/market-pulse":
            self._send_json(200, {"items": fetch_market_pulse()})
            return

        if path == "/api/translate":
            try:
                translated, from_cache = get_english_translation()
                if not translated:
                    self._send_json(503, {"error": "Çeviri için Gemini API anahtarı gerekli."})
                    return
                self._send_json(200, {"ok": True, "cached": from_cache, "data": translated})
            except Exception as e:
                self._send_json(502, {"error": f"Çeviri şu anda oluşturulamadı: {e}"})
            return

        if path == "/api/admin/messages":
            user = self._get_authenticated_user()
            if not user:
                self._send_json(401, {"error": "Yetkisiz erişim."})
                return
            msgs = load_messages()
            unread = sum(1 for m in msgs if not m.get("read"))
            self._send_json(200, {"messages": msgs, "unreadCount": unread})
            return

        if path == "/api/admin/analytics":
            user = self._get_authenticated_user()
            if not user:
                self._send_json(401, {"error": "Yetkisiz erişim."})
                return
            logs = load_chat_logs()
            q_counts: dict[str, int] = {}
            q_latest_answer: dict[str, str] = {}
            for row in logs:
                q_text = str(row.get("question") or "").strip()
                if q_text:
                    q_counts[q_text] = q_counts.get(q_text, 0) + 1
                    if q_text not in q_latest_answer:
                        ans = str(row.get("answer") or "").strip()
                        if ans:
                            q_latest_answer[q_text] = ans
            top_questions = [
                {
                    "question": q,
                    "count": cnt,
                    "latestAnswer": q_latest_answer.get(q, ""),
                }
                for q, cnt in sorted(q_counts.items(), key=lambda x: -x[1])[:8]
            ]
            self._send_json(
                200,
                {
                    "totalChats": len(logs),
                    "successChats": sum(1 for r in logs if r.get("ok")),
                    "recentLogs": logs[:60],
                    "topQuestions": top_questions,
                },
            )
            return

        if path == "/robots.txt":
            base_url = self._get_base_url()
            txt = f"User-agent: *\nAllow: /\nDisallow: /admin\nSitemap: {base_url}/sitemap.xml\n".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(txt)))
            self.end_headers()
            self.wfile.write(txt)
            return

        if path == "/sitemap.xml":
            base_url = self._get_base_url()
            xml_body = (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                f'  <url><loc>{html.escape(base_url)}/</loc><changefreq>weekly</changefreq><priority>1.0</priority></url>\n'
                '</urlset>\n'
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/xml; charset=utf-8")
            self.send_header("Content-Length", str(len(xml_body)))
            self.end_headers()
            self.wfile.write(xml_body)
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

        # Herkese Açık Hızlı İletişim / Görüşme Talebi Formu
        if path == "/api/contact":
            client_ip = (self.headers.get("X-Forwarded-For", "").split(",")[0].strip() or self.client_address[0])
            now_ts = time.time()
            recent = [t for t in CONTACT_RATE_LIMIT.get(client_ip, []) if now_ts - t < 60]
            if len(recent) >= 8:
                self._send_json(429, {"error": "Çok sık mesaj gönderildi. Lütfen 1 dakika bekleyin."})
                return
            recent.append(now_ts)
            CONTACT_RATE_LIMIT[client_ip] = recent

            body = self._read_json_body(16 * 1024)
            if not body:
                self._send_json(400, {"error": "Geçersiz form verisi."})
                return
            name = str(body.get("name", "")).strip()
            organization = str(body.get("organization", "")).strip()
            contact_info = str(body.get("contactInfo", "")).strip()
            topic = str(body.get("topic", "")).strip()
            message = str(body.get("message", "")).strip()
            if len(name) < 2 or len(message) < 5:
                self._send_json(400, {"error": "Lütfen adınızı ve en az 5 karakterlik bir mesaj yazın."})
                return

            new_msg = {
                "id": f"msg-{uuid.uuid4().hex[:8]}",
                "name": name[:120],
                "organization": organization[:140],
                "contactInfo": contact_info[:140],
                "topic": topic[:100] or "Genel / Tanışma",
                "message": message[:2000],
                "createdAt": datetime.now(TR_TZ).strftime("%d.%m.%Y %H:%M"),
                "read": False,
            }
            msgs = load_messages()
            msgs.insert(0, new_msg)
            save_messages(msgs[:300])
            self._send_json(201, {"ok": True, "id": new_msg["id"]})
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
                append_chat_log(message, _get_working_gemini_model(), True, answer=reply)
                self._send_json(200, {"ok": True, "reply": reply})
            except RuntimeError as e:
                append_chat_log(message, None, False, answer=str(e))
                self._send_json(502, {"error": str(e)})
            except Exception as e:
                append_chat_log(message, None, False, answer=str(e))
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
            body = self._read_json_body(MAX_UPLOAD_BYTES + 4 * 1024 * 1024)
            if not body:
                self._send_json(400, {"error": "Dosya verisi okunamadı veya boyut çok büyük."})
                return
            filename = str(body.get("filename", "image.png"))
            data_url = str(body.get("dataUrl", ""))
            is_img = data_url.startswith("data:image/")
            is_pdf = data_url.startswith("data:application/pdf")
            if "," not in data_url or not (is_img or is_pdf):
                self._send_json(400, {"error": "Yalnızca görsel veya PDF dosyası yüklenebilir."})
                return

            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ("pdf" if is_pdf else "png")
            if ext not in ALLOWED_UPLOAD_EXTS or (is_pdf and ext != "pdf"):
                self._send_json(400, {"error": "Yalnızca PNG, JPG, WEBP, GIF veya PDF yüklenebilir."})
                return

            try:
                b64_part = data_url.split(",", 1)[1]
                raw_bytes = base64.b64decode(b64_part, validate=True)
            except Exception:
                self._send_json(400, {"error": "Dosya çözümlenemedi."})
                return

            if len(raw_bytes) > MAX_UPLOAD_BYTES:
                self._send_json(400, {"error": "Dosya boyutu 12 MB sınırını aşamaz."})
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
            if section not in {"socialPosts", "projects", "ideas", "events", "credentials"} or not isinstance(item, dict):
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

        if path in ("/api/admin/profile", "/api/admin/site"):
            body = self._read_json_body(512 * 1024)
            if not isinstance(body, dict):
                self._send_json(400, {"error": "Geçersiz veri formatı."})
                return
            with CONTENT_LOCK:
                content = load_content()
                if isinstance(body.get("profile"), dict):
                    content.setdefault("profile", {}).update(body["profile"])
                if isinstance(body.get("institutions"), list):
                    content["institutions"] = [str(x).strip() for x in body["institutions"] if str(x).strip()]
                if isinstance(body.get("hero"), dict):
                    content.setdefault("hero", {}).update(body["hero"])
                if isinstance(body.get("contact"), dict):
                    content.setdefault("contact", {}).update(body["contact"])
                if isinstance(body.get("site"), dict):
                    content.setdefault("site", {}).update(body["site"])
                save_content(content)
            self._send_json(200, {"ok": True})
            return

        if path == "/api/admin/messages":
            body = self._read_json_body(4096) or {}
            msg_id = body.get("id")
            msgs = load_messages()
            if body.get("markAllRead"):
                for m in msgs:
                    m["read"] = True
            elif msg_id:
                for m in msgs:
                    if m.get("id") == msg_id:
                        m["read"] = bool(body.get("read", True))
                        break
            save_messages(msgs)
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
            if section not in {"socialPosts", "projects", "ideas", "events", "credentials"} or not item_id or not isinstance(item, dict):
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

        if path == "/api/admin/messages":
            body = self._read_json_body(4096) or {}
            msg_id = body.get("id")
            msgs = [m for m in load_messages() if m.get("id") != msg_id]
            save_messages(msgs)
            self._send_json(200, {"ok": True})
            return

        if path == "/api/admin/analytics":
            with CHAT_LOGS_LOCK:
                tmp = CHAT_LOGS_FILE.with_suffix(".tmp")
                with tmp.open("w", encoding="utf-8") as f:
                    json.dump([], f)
                os.replace(tmp, CHAT_LOGS_FILE)
            self._send_json(200, {"ok": True})
            return

        if path == "/api/admin/item":
            body = self._read_json_body(16 * 1024)
            if not body:
                self._send_json(400, {"error": "Geçersiz istek."})
                return
            section = body.get("section")
            item_id = body.get("id")
            if section not in {"socialPosts", "projects", "ideas", "events", "credentials"} or not item_id:
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

        # Ana sayfa için dinamik Open Graph (LinkedIn / WhatsApp link önizleme kartı) enjeksiyonu
        if rel == "index.html":
            try:
                content = load_content()
                profile = content.get("profile") or {}
                hero = content.get("hero") or {}
                base_url = self._get_base_url()
                name = str(profile.get("name") or "Emir Zencircioğlu").strip()
                role = str(profile.get("role") or "Sermaye Piyasaları, Finans & Yazılım").strip()
                desc = str(hero.get("subtitle") or profile.get("bio") or "").strip()[:240]
                raw_img = str(hero.get("portraitImage") or profile.get("avatar") or "").strip()
                og_img = ""
                if raw_img.startswith(("http://", "https://")):
                    og_img = raw_img
                elif raw_img.startswith("/"):
                    og_img = f"{base_url}{raw_img}"

                meta_lines = [
                    f'<meta property="og:type" content="website" />',
                    f'<meta property="og:url" content="{html.escape(base_url)}/" />',
                    f'<meta property="og:title" content="{html.escape(name)} — {html.escape(role)}" />',
                    f'<meta property="og:description" content="{html.escape(desc)}" />',
                    f'<meta name="twitter:card" content="summary_large_image" />',
                    f'<meta name="twitter:title" content="{html.escape(name)} — {html.escape(role)}" />',
                    f'<meta name="twitter:description" content="{html.escape(desc)}" />',
                ]
                if og_img:
                    meta_lines.append(f'<meta property="og:image" content="{html.escape(og_img)}" />')
                    meta_lines.append(f'<meta name="twitter:image" content="{html.escape(og_img)}" />')
                html_text = data.decode("utf-8").replace("</head>", "  " + "\n  ".join(meta_lines) + "\n</head>", 1)
                data = html_text.encode("utf-8")
            except Exception:
                pass

        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        query_str = urlparse(self.path).query or ""
        if target.suffix.lower() == ".pdf" and "download=1" in query_str:
            if "lang=en" in query_str:
                dl_name = "Emir_Zencircioglu_CV_EN.pdf"
            elif "lang=tr" in query_str:
                dl_name = "Emir_Zencircioglu_CV_TR.pdf"
            else:
                dl_name = "Emir_Zencircioglu_CV.pdf"
            self.send_header("Content-Disposition", f'attachment; filename="{dl_name}"')
        self.end_headers()
        self.wfile.write(data)

    def _get_base_url(self) -> str:
        proto = (self.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip() or "https"
        host = (self.headers.get("Host") or "localhost:8000").strip()
        if host.startswith("localhost") or host.startswith("127.0.0.1"):
            proto = "http"
        return f"{proto}://{host}"


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
    apply_env_admin_reset()

    if args.reset_password:
        reset_password_cli()
        return

    start_feed_bot_thread()
    threading.Timer(4.0, _prewarm_en_translation).start()
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
