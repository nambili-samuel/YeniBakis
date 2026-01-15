#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import feedparser
import requests
from atproto import Client
from io import BytesIO
from PIL import Image
import re
from datetime import datetime

# Force UTF-8 encoding for stdout
sys.stdout.reconfigure(encoding='utf-8')

RSS_URL = os.environ["RSS_URL"]
BSKY_HANDLE = os.environ["BSKY_HANDLE"]
BSKY_APP_PASSWORD = os.environ["BSKY_APP_PASSWORD"]

STATE_FILE = "last_post.txt"
MAX_IMAGE_SIZE = 976_000  # ~950 KB (1MB limit with safety margin)

def get_last_link():
    """Get the last posted article link"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""

def save_last_link(link):
    """Save the last posted article link"""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(link)
    print(f"✓ Durum kaydedildi: {link[:50]}...")

def optimize_image(image_data):
    """Optimize image to fit within size limit while maintaining quality"""
    try:
        img = Image.open(BytesIO(image_data))
        
        # Convert to RGB if necessary
        if img.mode in ('RGBA', 'P', 'LA'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode in ('RGBA', 'LA'):
                background.paste(img, mask=img.split()[-1])
            img = background
        
        # Resize if too large (maintain aspect ratio)
        max_dimension = 2000
        if max(img.size) > max_dimension:
            ratio = max_dimension / max(img.size)
            new_size = tuple(int(dim * ratio) for dim in img.size)
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        # Save with progressive optimization
        output = BytesIO()
        quality = 85
        
        while quality > 20:
            output.seek(0)
            output.truncate()
            img.save(output, format='JPEG', quality=quality, optimize=True, progressive=True)
            
            if output.tell() <= MAX_IMAGE_SIZE:
                print(f"✓ Görsel optimize edildi: {len(image_data)} -> {output.tell()} bytes (kalite: {quality})")
                return output.getvalue()
            
            quality -= 5
        
        print("⚠ Görsel optimize edilemedi, boyut sınırı aşılıyor")
        return None
        
    except Exception as e:
        print(f"✗ Görsel optimizasyon hatası: {e}")
        return None

def fetch_image(url):
    """Fetch and optimize image from URL"""
    if not url:
        return None
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7'
        }
        
        print(f"📥 Görsel indiriliyor: {url}")
        r = requests.get(url, timeout=15, headers=headers, stream=True)
        r.raise_for_status()
        
        content = r.content
        print(f"✓ Görsel indirildi: {len(content)} bytes")
        
        # If image is already small enough, return it
        if len(content) <= MAX_IMAGE_SIZE:
            return content
        
        # Otherwise, optimize it
        return optimize_image(content)
        
    except Exception as e:
        print(f"✗ Görsel indirme hatası ({url}): {e}")
        return None

def clean_html(text):
    """Remove HTML tags and clean text"""
    if not text:
        return ""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text)
    # Decode HTML entities
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&quot;', '"')
    text = text.replace('&apos;', "'")
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    return text.strip()

def extract_wordpress_thumbnail(entry):
    """Extract thumbnail from WordPress RSS feed with multiple methods"""
    
    # Method 1: media:content
    if hasattr(entry, 'media_content') and entry.media_content:
        url = entry.media_content[0].get('url')
        if url:
            print(f"✓ Thumbnail bulundu (media:content): {url}")
            return url
    
    # Method 2: media:thumbnail
    if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
        url = entry.media_thumbnail[0].get('url')
        if url:
            print(f"✓ Thumbnail bulundu (media:thumbnail): {url}")
            return url
    
    # Method 3: enclosures
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enclosure in entry.enclosures:
            enc_type = enclosure.get('type', '').lower()
            if 'image' in enc_type:
                url = enclosure.get('href') or enclosure.get('url')
                if url:
                    print(f"✓ Thumbnail bulundu (enclosure): {url}")
                    return url
    
    # Method 4: Parse content/description/summary for img tags
    for field in ['content', 'description', 'summary']:
        if hasattr(entry, field):
            content_val = getattr(entry, field)
            
            # Handle list content (like Atom feeds)
            if isinstance(content_val, list) and content_val:
                content_val = content_val[0].get('value', '') if isinstance(content_val[0], dict) else str(content_val[0])
            
            content_str = str(content_val)
            
            # Look for img tags with src attribute
            img_matches = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content_str, re.IGNORECASE)
            if img_matches:
                # Get first reasonable image (skip small icons)
                for img_url in img_matches:
                    # Skip data URIs, tracking pixels, and very small images
                    if (not img_url.startswith('data:') and 
                        'spacer' not in img_url.lower() and 
                        'pixel' not in img_url.lower() and
                        '1x1' not in img_url.lower()):
                        print(f"✓ Thumbnail bulundu ({field} img tag): {img_url}")
                        return img_url
    
    print("⚠ Thumbnail bulunamadı")
    return None

def extract_youtube_thumbnail(entry, link):
    """Extract high-quality thumbnail from YouTube"""
    video_id = None
    
    # Try to get video ID from entry
    if hasattr(entry, 'yt_videoid'):
        video_id = entry.yt_videoid
    elif hasattr(entry, 'id'):
        # YouTube RSS sometimes has video ID in the id field
        id_str = str(entry.id)
        if 'yt:video:' in id_str:
            video_id = id_str.split('yt:video:')[-1]
    
    # Extract from link if not found
    if not video_id and 'v=' in link:
        video_id = link.split('v=')[1].split('&')[0]
    
    if video_id:
        print(f"✓ YouTube video ID: {video_id}")
        
        # Try different quality thumbnails in order of preference
        thumbnail_urls = [
            f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
            f"https://i.ytimg.com/vi/{video_id}/sddefault.jpg",
            f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        ]
        
        for url in thumbnail_urls:
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                r = requests.head(url, timeout=5, headers=headers, allow_redirects=True)
                if r.status_code == 200:
                    print(f"✓ YouTube thumbnail bulundu: {url}")
                    return url
            except:
                continue
    
    # Fallback to media_thumbnail
    if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
        url = entry.media_thumbnail[0].get('url')
        if url:
            print(f"✓ YouTube media_thumbnail kullanılıyor: {url}")
            return url
    
    print("⚠ YouTube thumbnail bulunamadı")
    return None

# Parse RSS feed with UTF-8 support
print(f"\n{'='*60}")
print(f"📰 RSS Feed İşleniyor: {RSS_URL}")
print(f"{'='*60}\n")

feed = feedparser.parse(RSS_URL)

if not feed.entries:
    print("⚠ RSS beslemesinde içerik bulunamadı.")
    sys.exit(0)

print(f"✓ RSS beslemesi okundu: {len(feed.entries)} içerik bulundu\n")

entry = feed.entries[0]

# Extract basic info
title = entry.title
link = entry.link
summary = entry.get("summary", entry.get("description", title))
summary_clean = clean_html(summary)

print(f"📌 En son içerik:")
print(f"   Başlık: {title}")
print(f"   Link: {link}")
print(f"   Özet: {summary_clean[:100]}...")

# Check if already posted
last_link = get_last_link()
if link == last_link:
    print(f"\n⏭ Bu içerik zaten paylaşıldı.")
    print(f"   Son paylaşılan: {last_link}")
    print(f"   Şu anki içerik: {link}")
    print(f"\n✓ Yeni içerik yok. Bot durdu.\n")
    sys.exit(0)

print(f"\n✅ YENİ İÇERİK TESPİT EDİLDİ!")
print(f"   Son paylaşılan: {last_link if last_link else '(İlk paylaşım)'}")
print(f"   Yeni içerik: {link}\n")

# Detect source type and extract thumbnail
is_youtube = 'youtube.com' in RSS_URL.lower() or 'youtu.be' in RSS_URL.lower()

print(f"🔍 Kaynak tipi: {'YouTube' if is_youtube else 'WordPress/RSS'}\n")

thumbnail_url = None
if is_youtube:
    thumbnail_url = extract_youtube_thumbnail(entry, link)
else:
    thumbnail_url = extract_wordpress_thumbnail(entry)

# Login to Bluesky
print(f"\n🔐 Bluesky'a giriş yapılıyor...")
client = Client()
try:
    client.login(BSKY_HANDLE, BSKY_APP_PASSWORD)
    print(f"✓ Bluesky girişi başarılı: {BSKY_HANDLE}\n")
except Exception as e:
    print(f"✗ Bluesky giriş hatası: {e}")
    sys.exit(1)

# Fetch and upload thumbnail
thumb_blob = None
if thumbnail_url:
    print(f"📸 Thumbnail işleniyor...")
    image_data = fetch_image(thumbnail_url)
    
    if image_data:
        try:
            thumb_blob = client.upload_blob(image_data).blob
            print(f"✓ Thumbnail Bluesky'a yüklendi\n")
        except Exception as e:
            print(f"✗ Thumbnail yükleme hatası: {e}")
            print(f"⚠ Thumbnail olmadan devam ediliyor...\n")
    else:
        print(f"⚠ Thumbnail indirilemedi, devam ediliyor...\n")
else:
    print(f"⚠ Thumbnail bulunamadı, devam ediliyor...\n")

# Create embed with proper Turkish character support
embed = {
    "$type": "app.bsky.embed.external",
    "external": {
        "uri": link,
        "title": title[:300],  # Bluesky title limit
        "description": summary_clean[:300],  # Truncate description
    },
}

if thumb_blob:
    embed["external"]["thumb"] = thumb_blob
    print(f"✓ Embed thumbnail ile oluşturuldu")
else:
    print(f"⚠ Embed thumbnail olmadan oluşturuldu")

# Create post text with proper Turkish formatting
# Use proper emoji that displays correctly
post_text = f"📰 Yeni içerik yayında!\n\n{title[:280]}"

# Post to Bluesky
print(f"\n📤 Bluesky'a gönderiliyor...")
print(f"{'='*60}")

try:
    client.post(text=post_text, embed=embed)
    save_last_link(link)
    
    print(f"\n{'='*60}")
    print(f"✅ BAŞARIYLA PAYLAŞILDI!")
    print(f"{'='*60}")
    print(f"📌 Başlık: {title}")
    print(f"🔗 Link: {link}")
    print(f"🖼️  Thumbnail: {'Evet ✓' if thumb_blob else 'Hayır ✗'}")
    print(f"⏰ Zaman: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
except Exception as e:
    print(f"\n{'='*60}")
    print(f"✗ PAYLAŞIM HATASI!")
    print(f"{'='*60}")
    print(f"Hata: {e}")
    print(f"{'='*60}\n")
    sys.exit(1)
