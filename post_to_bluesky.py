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

def extract_wordpress_thumbnail(entry):
    """Extract thumbnail from WordPress RSS feed"""
    thumbnail_url = None
    
    # Method 1: media:content
    if hasattr(entry, 'media_content') and entry.media_content:
        thumbnail_url = entry.media_content[0].get('url')
        if thumbnail_url:
            print(f"Found thumbnail via media_content: {thumbnail_url}")
            return thumbnail_url
    
    # Method 2: media:thumbnail
    if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
        thumbnail_url = entry.media_thumbnail[0].get('url')
        if thumbnail_url:
            print(f"Found thumbnail via media_thumbnail: {thumbnail_url}")
            return thumbnail_url
    
    # Method 3: enclosures
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enclosure in entry.enclosures:
            if 'image' in enclosure.get('type', '').lower():
                thumbnail_url = enclosure.get('href') or enclosure.get('url')
                if thumbnail_url:
                    print(f"Found thumbnail via enclosures: {thumbnail_url}")
                    return thumbnail_url
    
    # Method 4: Parse content/description for img tags
    import re
    for field in ['content', 'description', 'summary']:
        if hasattr(entry, field):
            content = getattr(entry, field)
            if isinstance(content, list):
                content = content[0].get('value', '') if content else ''
            
            # Look for img tags
            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', str(content))
            if img_match:
                thumbnail_url = img_match.group(1)
                print(f"Found thumbnail via {field} img tag: {thumbnail_url}")
                return thumbnail_url
    
    return None

def extract_youtube_thumbnail(entry, link):
    """Extract high-quality thumbnail from YouTube"""
    thumbnail_url = None
    video_id = None
    
    # Try to get video ID from entry
    if hasattr(entry, 'yt_videoid'):
        video_id = entry.yt_videoid
    elif 'v=' in link:
        video_id = link.split('v=')[1].split('&')[0]
    
    if video_id:
        print(f"YouTube video ID: {video_id}")
        # Try different quality thumbnails in order of preference
        thumbnail_urls = [
            f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
            f"https://i.ytimg.com/vi/{video_id}/sddefault.jpg",
            f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        ]
        
        for url in thumbnail_urls:
            # Quick check if thumbnail exists
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                r = requests.head(url, timeout=5, headers=headers)
                if r.status_code == 200:
                    print(f"✓ Found YouTube thumbnail: {url}")
                    return url
            except:
                continue
    
    # Fallback to media_thumbnail if available
    if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
        thumbnail_url = entry.media_thumbnail[0].get('url')
        if thumbnail_url:
            print(f"Using YouTube media_thumbnail: {thumbnail_url}")
            return thumbnail_url
    
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

# Detect source type and extract thumbnail accordingly
thumbnail_url = None
is_youtube = 'youtube.com' in RSS_URL.lower() or 'youtu.be' in RSS_URL.lower()

if is_youtube:
    print("Detected YouTube RSS feed")
    thumbnail_url = extract_youtube_thumbnail(entry, link)
else:
    print("Detected WordPress RSS feed")
    thumbnail_url = extract_wordpress_thumbnail(entry)

if not thumbnail_url:
    print("⚠ No thumbnail found in RSS feed")

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
    print("⚠ No thumbnail to upload")

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
    print("✓ Embed created with thumbnail")
else:
    print("⚠ Embed created without thumbnail")

# Create post text with proper formatting
post_text = f"📰 Yeni içerik yayında!\n\n{title[:280]}"

# Post to Bluesky
try:
    client.post(text=post_text, embed=embed)
    save_last_link(link)
    print("✓ Posted successfully to Bluesky!")
    print(f"  Title: {title}")
    print(f"  Link: {link}")
    if thumb_blob:
        print(f"  Thumbnail: Yes")
    else:
        print(f"  Thumbnail: No")
except Exception as e:
    print(f"✗ Posting failed: {e}")
    exit(1)
