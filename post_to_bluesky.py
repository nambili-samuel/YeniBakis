import os
import feedparser
import requests
from atproto import Client
from io import BytesIO
from PIL import Image

RSS_URL = os.environ["RSS_URL"]
BSKY_HANDLE = os.environ["BSKY_HANDLE"]
BSKY_APP_PASSWORD = os.environ["BSKY_APP_PASSWORD"]

STATE_FILE = "last_post.txt"
MAX_IMAGE_SIZE = 976_000  # ~950 KB (1MB limit with safety margin)

def get_last_link():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""

def save_last_link(link):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(link)

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
        
        # Resize if too large
        max_dimension = 2000
        if max(img.size) > max_dimension:
            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        
        # Save with optimization
        output = BytesIO()
        quality = 85
        
        while quality > 20:
            output.seek(0)
            output.truncate()
            img.save(output, format='JPEG', quality=quality, optimize=True)
            
            if output.tell() <= MAX_IMAGE_SIZE:
                return output.getvalue()
            
            quality -= 5
        
        return None
    except Exception as e:
        print(f"Image optimization error: {e}")
        return None

def fetch_image(url):
    """Fetch and optimize image from URL"""
    if not url:
        return None
    
    try:
        # Add headers to avoid being blocked
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        r = requests.get(url, timeout=15, headers=headers, stream=True)
        r.raise_for_status()
        
        content = r.content
        
        # If image is already small enough, return it
        if len(content) <= MAX_IMAGE_SIZE:
            return content
        
        # Otherwise, optimize it
        return optimize_image(content)
        
    except Exception as e:
        print(f"Image fetch error for {url}: {e}")
        return None

# Parse RSS feed with proper encoding
feed = feedparser.parse(RSS_URL)

if not feed.entries:
    print("No entries found in RSS feed.")
    exit(0)

entry = feed.entries[0]

title = entry.title
link = entry.link
summary = entry.get("summary", entry.get("description", title))

# Remove HTML tags from summary
import re
summary = re.sub('<[^<]+?>', '', summary)
summary = summary.strip()

thumbnail_url = None

# WordPress - check multiple possible fields
if "media_content" in entry and entry.media_content:
    thumbnail_url = entry.media_content[0].get("url")
elif "media_thumbnail" in entry and entry.media_thumbnail:
    # YouTube - try to get highest quality thumbnail
    thumbnail_url = entry.media_thumbnail[0].get("url")
    
    # YouTube provides different quality thumbnails, try to get higher quality
    if thumbnail_url and "youtube" in RSS_URL.lower():
        # Extract video ID and construct high-quality thumbnail URL
        video_id = None
        if "yt:videoId" in entry:
            video_id = entry.yt_videoid
        elif "youtube.com/watch?v=" in link:
            video_id = link.split("v=")[1].split("&")[0]
        
        if video_id:
            # Try maxresdefault first (highest quality)
            high_quality_urls = [
                f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
                f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                thumbnail_url  # fallback to original
            ]
            
            for url in high_quality_urls:
                test_img = fetch_image(url)
                if test_img:
                    thumbnail_url = url
                    break

# Check for enclosures (another common RSS field for images)
elif hasattr(entry, 'enclosures') and entry.enclosures:
    for enclosure in entry.enclosures:
        if 'image' in enclosure.get('type', ''):
            thumbnail_url = enclosure.get('href') or enclosure.get('url')
            break

# Check if this post was already published
last_link = get_last_link()
if link == last_link:
    print("No new content.")
    exit(0)

# Login to Bluesky
client = Client()
client.login(BSKY_HANDLE, BSKY_APP_PASSWORD)

# Fetch and upload thumbnail
thumb_blob = None
if thumbnail_url:
    print(f"Fetching thumbnail from: {thumbnail_url}")
    image_data = fetch_image(thumbnail_url)
    
    if image_data:
        try:
            thumb_blob = client.upload_blob(image_data).blob
            print("✓ Thumbnail uploaded successfully")
        except Exception as e:
            print(f"✗ Thumbnail upload failed: {e}")
    else:
        print("✗ Could not fetch thumbnail")
else:
    print("No thumbnail URL found")

# Create embed with proper Turkish character support
embed = {
    "$type": "app.bsky.embed.external",
    "external": {
        "uri": link,
        "title": title[:300],  # Bluesky title limit
        "description": summary[:300],  # Truncate description
    },
}

if thumb_blob:
    embed["external"]["thumb"] = thumb_blob

# Create post text with proper formatting
# Use emoji that work well across platforms
post_text = f"📰 Yeni içerik yayında!\n\n{title[:280]}"

# Post to Bluesky
try:
    client.post(text=post_text, embed=embed)
    save_last_link(link)
    print("✓ Posted successfully to Bluesky!")
    print(f"  Title: {title}")
    print(f"  Link: {link}")
except Exception as e:
    print(f"✗ Posting failed: {e}")
    exit(1)
