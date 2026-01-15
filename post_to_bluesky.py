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
from bs4 import BeautifulSoup

# Force UTF-8 encoding for stdout
if sys.stdout.encoding != 'utf-8':
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
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://yenibakisgazetesi.com/'
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
    text = text.replace('&#8217;', "'")
    text = text.replace('&#8220;', '"')
    text = text.replace('&#8221;', '"')
    text = text.replace('&#8216;', "'")
    text = text.replace('&quot;', '"')
    text = text.replace('&apos;', "'")
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    # Remove CDATA markers
    text = text.replace('<![CDATA[', '')
    text = text.replace(']]>', '')
    return text.strip()

def fetch_article_thumbnail(article_url):
    """Fetch featured image from WordPress article page"""
    if not article_url or article_url == '#':
        return None
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        print(f"🌐 Makale sayfası açılıyor: {article_url}")
        response = requests.get(article_url, timeout=15, headers=headers)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            print(f"⚠ Makale sayfası yüklenemedi: HTTP {response.status_code}")
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Method 1: Open Graph image (most reliable for WordPress)
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            url = og_image['content']
            print(f"✓ Thumbnail bulundu (og:image): {url}")
            return url
        
        # Method 2: Twitter card image
        twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
        if twitter_image and twitter_image.get('content'):
            url = twitter_image['content']
            print(f"✓ Thumbnail bulundu (twitter:image): {url}")
            return url
        
        # Method 3: WordPress featured image
        featured_img = soup.select_one('.wp-post-image, .featured-image img, article img, .entry-content img')
        if featured_img and featured_img.get('src'):
            url = featured_img['src']
            # Skip tiny images
            if 'placeholder' not in url.lower() and '1x1' not in url.lower():
                print(f"✓ Thumbnail bulundu (featured image): {url}")
                return url
        
        # Method 4: First large image in content
        content_images = soup.select('article img, .entry-content img, .post-content img')
        for img in content_images:
            src = img.get('src') or img.get('data-src')
            if src and 'placeholder' not in src.lower() and '1x1' not in src.lower():
                # Check if image has reasonable dimensions
                width = img.get('width', '0')
                height = img.get('height', '0')
                try:
                    if int(width) >= 300 or int(height) >= 300:
                        print(f"✓ Thumbnail bulundu (content image): {src}")
                        return src
                except:
                    print(f"✓ Thumbnail bulundu (content image): {src}")
                    return src
        
        print("⚠ Makale sayfasında thumbnail bulunamadı")
        return None
        
    except Exception as e:
        print(f"✗ Makale sayfası okuma hatası: {e}")
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

def create_beautiful_post(title, link, category=""):
    """Create a beautiful, professional Bluesky post with proper formatting"""
    
    # Decode HTML entities in title
    title = clean_html(title)
    
    # Add appropriate emoji based on category
    category_emojis = {
        'SPOR': '⚽',
        'EKONOMİ': '💰',
        'DÜNYA': '🌍',
        'TÜRKİYE': '🇹🇷',
        'KIBRIS': '🇨🇾',
        'GÜNEY KIBRIS': '🇨🇾',
        'SAĞLIK': '🏥',
        'TEKNOLOJİ': '💻',
        'KÜLTÜR': '🎭',
        'SANAT': '🎨',
    }
    
    emoji = category_emojis.get(category.upper(), '📰')
    
    # Create post with beautiful formatting
    post_text = f"{emoji} Yeni Haber\n\n{title}\n\n🔗 Devamı için tıklayın"
    
    # Limit to 300 characters for Bluesky
    if len(post_text) > 300:
        # Trim title if too long
        max_title_len = 300 - len(f"{emoji} Yeni Haber\n\n") - len("\n\n🔗 Devamı için tıklayın")
        title_trimmed = title[:max_title_len-3] + "..."
        post_text = f"{emoji} Yeni Haber\n\n{title_trimmed}\n\n🔗 Devamı için tıklayın"
    
    return post_text

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

# Extract basic info with proper encoding
title = clean_html(entry.title)
link = entry.link
summary = clean_html(entry.get("summary", entry.get("description", "")))

# Extract category
categories = []
if hasattr(entry, 'tags'):
    categories = [tag.term for tag in entry.tags]
category = categories[0] if categories else "GENEL"

print(f"📌 En son içerik:")
print(f"   Başlık: {title}")
print(f"   Link: {link}")
print(f"   Kategori: {category}")
print(f"   Özet: {summary[:100]}...")

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
    # For WordPress, fetch from article page (most reliable)
    thumbnail_url = fetch_article_thumbnail(link)

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

# Create embed card with rich preview
embed = {
    "$type": "app.bsky.embed.external",
    "external": {
        "uri": link,
        "title": title[:300],  # Bluesky title limit
        "description": summary[:300] if summary else "Yeni Bakış Gazetesi'nde detayları okuyun.",
    },
}

if thumb_blob:
    embed["external"]["thumb"] = thumb_blob
    print(f"✓ Embed thumbnail ile oluşturuldu")
else:
    print(f"⚠ Embed thumbnail olmadan oluşturuldu")

# Create beautiful post text
post_text = create_beautiful_post(title, link, category)

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
    print(f"📂 Kategori: {category}")
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
