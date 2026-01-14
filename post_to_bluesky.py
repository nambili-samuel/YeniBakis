import os
import feedparser
import requests
from atproto import Client

RSS_URL = os.environ["RSS_URL"]
BSKY_HANDLE = os.environ["BSKY_HANDLE"]
BSKY_APP_PASSWORD = os.environ["BSKY_APP_PASSWORD"]

STATE_FILE = "last_post.txt"

def get_last_link():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""

def save_last_link(link):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(link)

def fetch_image(url):
    if not url:
        return None
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.content
    except:
        pass
    return None

feed = feedparser.parse(RSS_URL)
entry = feed.entries[0]

title = entry.title
link = entry.link
summary = entry.get("summary", "Yeni Bakış Gazetesi")

# --- Detect thumbnail ---
thumbnail_url = None

# WordPress
if "media_content" in entry:
    thumbnail_url = entry.media_content[0]["url"]

# YouTube
elif "media_thumbnail" in entry:
    thumbnail_url = entry.media_thumbnail[0]["url"]

last_link = get_last_link()
if link == last_link:
    print("No new content.")
    exit(0)

client = Client()
client.login(BSKY_HANDLE, BSKY_APP_PASSWORD)

thumb_blob = None
image_data = fetch_image(thumbnail_url)
if image_data:
    thumb_blob = client.upload_blob(image_data).blob

post_text = f"📰 Yeni içerik yayında!\n\n{title}"

embed = {
    "$type": "app.bsky.embed.external",
    "external": {
        "uri": link,
        "title": title,
        "description": summary[:240],
        "thumb": thumb_blob,
    },
}

client.post(text=post_text, embed=embed)

save_last_link(link)
print("Posted to Bluesky successfully.")
