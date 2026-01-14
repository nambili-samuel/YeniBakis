import os
import feedparser
import requests
from atproto import Client

RSS_URL = os.environ["RSS_URL"]
BSKY_HANDLE = os.environ["BSKY_HANDLE"]
BSKY_APP_PASSWORD = os.environ["BSKY_APP_PASSWORD"]

STATE_FILE = "last_post.txt"
MAX_IMAGE_SIZE = 900_000  # 900 KB safe limit

def get_last_link():
    if os.path.exists(STATE_FILE):
        return open(STATE_FILE, "r", encoding="utf-8").read().strip()
    return ""

def save_last_link(link):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(link)

def fetch_image(url):
    if not url:
        return None
    try:
        r = requests.get(url, timeout=10, stream=True)
        content = r.content
        if len(content) > MAX_IMAGE_SIZE:
            return None
        return content
    except:
        return None

feed = feedparser.parse(RSS_URL)
entry = feed.entries[0]

title = entry.title
link = entry.link
summary = entry.get("summary", title)

thumbnail_url = None

# WordPress
if "media_content" in entry:
    thumbnail_url = entry.media_content[0].get("url")

# YouTube
elif "media_thumbnail" in entry:
    thumbnail_url = entry.media_thumbnail[0].get("url")

last_link = get_last_link()
if link == last_link:
    print("No new content.")
    exit(0)

client = Client()
client.login(BSKY_HANDLE, BSKY_APP_PASSWORD)

thumb_blob = None
image_data = fetch_image(thumbnail_url)

if image_data:
    try:
        thumb_blob = client.upload_blob(image_data).blob
    except Exception as e:
        print("Thumbnail upload failed, continuing without image.")

embed = {
    "$type": "app.bsky.embed.external",
    "external": {
        "uri": link,
        "title": title,
        "description": summary[:240],
    },
}

if thumb_blob:
    embed["external"]["thumb"] = thumb_blob

post_text = f"📰 Yeni içerik yayında!\n\n{title}"

client.post(text=post_text, embed=embed)

save_last_link(link)
print("Posted successfully.")
