#!/usr/bin/env python3
"""
LinkedIn -> Blog Otomatik Senkronizasyon Botu
---------------------------------------------
LinkedIn profilinin Gönderiler bölümündeki son paylaşımları okur,
yayınlanma tarihini (UTC+3) doğru şekilde çıkarır, daha önce bloga
eklenmemiş olan yeni gönderileri tek tek bloguna aktarır.

Kullanım:
  python linkedin_bot.py           -> Tek seferlik kontrol yapar
  python linkedin_bot.py --loop    -> 5 dakikada bir sürekli kontrol eder
  python linkedin_bot.py --setup   -> Ayarları yeniden girer
"""

import argparse
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "data" / "linkedin_config.json"
TR_TZ = timezone(timedelta(hours=3))


def load_config() -> dict | None:
    if not CONFIG_FILE.exists():
        return None
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg: dict):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_FILE)


def setup_wizard() -> dict:
    print("\n=== LinkedIn Bot İlk Kurulumu ===")
    print("1. Tarayıcıda linkedin.com'a giriş yap.")
    print("2. F12 -> Application (Uygulama) -> Cookies -> https://www.linkedin.com")
    print("   altından 'li_at' çerezinin değerini kopyala.\n")

    raw_profile = input("LinkedIn profil linkin veya kullanıcı adın (ör. emir-zencircioğlu): ").strip()
    if "linkedin.com/in/" in raw_profile:
        raw_profile = raw_profile.split("linkedin.com/in/", 1)[1].strip("/")
    profile_slug = urllib.parse.unquote(raw_profile)

    li_at = input("LinkedIn 'li_at' çerez değeri: ").strip()
    blog_url = input("Blog adresin [https://emirzencircioglu.me]: ").strip().rstrip("/") or "https://emirzencircioglu.me"
    webhook_secret = input("Admin Paneli -> Gizli Webhook Anahtarı: ").strip()

    cfg = {
        "profile_slug": profile_slug,
        "li_at": li_at,
        "blog_url": blog_url,
        "webhook_secret": webhook_secret,
    }
    save_config(cfg)
    print(f"\nAyarlar kaydedildi: {CONFIG_FILE}\n")
    return cfg


def build_linkedin_opener(li_at: str) -> tuple[urllib.request.OpenerDirector, str]:
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        ("Accept", "application/vnd.linkedin.normalized+json+2.1"),
        ("x-restli-protocol-version", "2.0.0"),
        ("Cookie", f"li_at={li_at}"),
    ]

    # JSESSIONID / csrf-token almak için ana sayfaya hafif istek
    try:
        req = urllib.request.Request("https://www.linkedin.com/feed/", headers={"Cookie": f"li_at={li_at}"})
        opener.open(req, timeout=12).read(1024)
    except Exception:
        pass

    csrf_token = "ajax:0000000000000000000"
    for c in cj:
        if c.name == "JSESSIONID":
            csrf_token = c.value.strip('"')
            break

    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        ("Accept", "application/vnd.linkedin.normalized+json+2.1"),
        ("x-restli-protocol-version", "2.0.0"),
        ("csrf-token", csrf_token),
        ("Cookie", f'li_at={li_at}; JSESSIONID="{csrf_token}"'),
    ]
    return opener, csrf_token


def activity_id_to_iso(activity_id: str) -> str | None:
    try:
        ts_ms = int(activity_id) >> 22
        dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=TR_TZ)
        return dt.isoformat()
    except Exception:
        return None


def extract_posts_from_voyager(data: dict) -> list[dict]:
    included = data.get("included") or []
    posts = []
    seen_ids = set()

    for obj in included:
        urn = str(obj.get("entityUrn") or obj.get("urn") or "")
        m = re.search(r"urn:li:activity:(\d+)", urn)
        if not m:
            continue
        act_id = m.group(1)
        if act_id in seen_ids:
            continue

        # Gönderi metnini çıkar
        commentary = obj.get("commentary") or {}
        text_obj = commentary.get("text") if isinstance(commentary, dict) else None
        text = ""
        if isinstance(text_obj, dict):
            text = (text_obj.get("text") or "").strip()
        elif isinstance(commentary, str):
            text = commentary.strip()

        if not text:
            continue

        seen_ids.add(act_id)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        title = (lines[0] if lines else "LinkedIn Paylaşımı")[:110]
        excerpt = text[:280]

        # Görsel varsa çıkar
        image_url = None
        content_block = obj.get("content") or {}
        img_comp = content_block.get("imageComponent") or {}
        images = img_comp.get("images") or []
        if images and isinstance(images, list):
            attrs = images[0].get("attributes") or []
            if attrs:
                vec = (attrs[0].get("vectorImage") or {})
                root_url = vec.get("rootUrl") or ""
                artifacts = vec.get("artifacts") or []
                if root_url and artifacts:
                    seg = artifacts[-1].get("fileIdentifyingUrlPathSegment") or ""
                    if seg:
                        image_url = root_url + seg

        posts.append({
            "activityId": act_id,
            "url": f"https://www.linkedin.com/feed/update/urn:li:activity:{act_id}/",
            "title": title,
            "excerpt": excerpt,
            "image": image_url,
            "publishedAt": activity_id_to_iso(act_id),
        })

    # En yeniden en eskiye sırala
    posts.sort(key=lambda p: int(p["activityId"]), reverse=True)
    return posts[:10]


def _extract_profile_urn(prof_data: dict) -> str | None:
    for obj in prof_data.get("included") or []:
        urn = str(obj.get("entityUrn") or "")
        if "urn:li:fsd_profile:" in urn or "urn:li:fs_profile:" in urn:
            return urn
    data_block = prof_data.get("data") or {}
    for el in data_block.get("elements") or []:
        urn = str(el.get("entityUrn") or el or "")
        if "urn:li:fsd_profile:" in urn or "urn:li:fs_profile:" in urn:
            return urn
    return None


def fetch_linkedin_posts(cfg: dict) -> list[dict]:
    opener, _ = build_linkedin_opener(cfg["li_at"])
    slug = urllib.parse.quote(cfg["profile_slug"])

    # 1. Güncel Dash Profiles API üzerinden Profil URN'ini al
    profile_urn = None
    dash_url = f"https://www.linkedin.com/voyager/api/identity/dash/profiles?q=memberIdentity&memberIdentity={slug}"
    try:
        with opener.open(dash_url, timeout=15) as resp:
            prof_data = json.loads(resp.read().decode("utf-8"))
        profile_urn = _extract_profile_urn(prof_data)
    except urllib.error.HTTPError as e:
        if e.code not in (404, 410):
            raise

    # Yedek: /voyager/api/me üzerinden kendi profil URN'ini al
    if not profile_urn:
        with opener.open("https://www.linkedin.com/voyager/api/me", timeout=15) as resp:
            me_data = json.loads(resp.read().decode("utf-8"))
        for obj in me_data.get("included") or []:
            urn = str(obj.get("entityUrn") or "")
            if "urn:li:fs_miniProfile:" in urn:
                profile_id = urn.rsplit(":", 1)[-1]
                profile_urn = f"urn:li:fsd_profile:{profile_id}"
                break

    if not profile_urn:
        raise RuntimeError("LinkedIn profil URN bulunamadı (li_at çerezi süresi dolmuş olabilir).")

    # 2. Profilin Gönderiler akışını çek
    encoded_urn = urllib.parse.quote(profile_urn)
    feed_urls = [
        f"https://www.linkedin.com/voyager/api/identity/profileUpdatesV2?q=memberShareFeed&moduleKey=member-shares:phone&count=10&start=0&profileUrn={encoded_urn}",
        f"https://www.linkedin.com/voyager/api/feed/updates?q=memberShareFeed&profileUrn={encoded_urn}&count=10",
    ]
    feed_data = None
    last_err = None
    for f_url in feed_urls:
        try:
            with opener.open(f_url, timeout=15) as resp:
                feed_data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (404, 410):
                continue
            raise

    if feed_data is None:
        raise last_err or RuntimeError("LinkedIn gönderi akışı alınamadı.")

    return extract_posts_from_voyager(feed_data)


def fetch_existing_blog_urls(blog_url: str) -> set[str]:
    req = urllib.request.Request(f"{blog_url}/api/content", headers={"User-Agent": "LinkedInBlogBot/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return {p.get("url") for p in data.get("socialPosts", []) if p.get("url")}


def push_to_blog(cfg: dict, post: dict) -> bool:
    payload = json.dumps({
        "platform": "linkedin",
        "title": post["title"],
        "excerpt": post["excerpt"],
        "url": post["url"],
        "image": post.get("image"),
        "publishedAt": post.get("publishedAt"),
        "metric": "LinkedIn",
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        f"{cfg['blog_url']}/api/webhook/social",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Secret": cfg["webhook_secret"],
            "User-Agent": "LinkedInBlogBot/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        return not res.get("duplicate", False)


def sync_once(cfg: dict):
    now_str = datetime.now(TR_TZ).strftime("%H:%M:%S")
    print(f"[{now_str}] LinkedIn gönderileri kontrol ediliyor...")
    posts = fetch_linkedin_posts(cfg)
    existing_urls = fetch_existing_blog_urls(cfg["blog_url"])

    new_posts = [p for p in posts if p["url"] not in existing_urls]
    if not new_posts:
        print(f"[{now_str}] Yeni LinkedIn gönderisi yok (toplam taranan: {len(posts)}).")
        return

    added = 0
    for post in reversed(new_posts):
        if push_to_blog(cfg, post):
            added += 1
            print(f"  + Eklendi: {post['title']} ({post.get('publishedAt', '')[:10]})")

    print(f"[{now_str}] Tamamlandı: {added} yeni gönderi bloga yüklendi.")


def main():
    parser = argparse.ArgumentParser(description="LinkedIn -> Blog Senkronizasyon Botu")
    parser.add_argument("--setup", action="store_true", help="Ayarları yeniden gir")
    parser.add_argument("--loop", action="store_true", help="Sürekli arka planda kontrol et")
    parser.add_argument("--interval", type=int, default=300, help="Kontrol aralığı (saniye, varsayılan: 300)")
    args = parser.parse_args()

    cfg = None if args.setup else load_config()
    if not cfg:
        cfg = setup_wizard()

    if args.loop:
        print(f"LinkedIn botu sürekli modda başlatıldı (her {args.interval} saniyede bir kontrol).")
        while True:
            try:
                sync_once(cfg)
            except urllib.error.HTTPError as e:
                print(f"[HATA] HTTP {e.code}: {e.reason}")
            except Exception as e:
                print(f"[HATA] {e}")
            time.sleep(args.interval)
    else:
        sync_once(cfg)


if __name__ == "__main__":
    main()
