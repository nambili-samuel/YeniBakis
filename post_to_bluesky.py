import os
import json
import feedparser
from atproto import Client

RSS_URL = os.environ["RSS_URL"]
YOUTUBE_RSS_URL = os.environ["RSS_URL"]
HANDLE = os.environ["BSKY_HANDLE"]
PASSWORD = os.environ["BSKY_APP_PASSWORD"]

STATE_FILE = "last_post.json"

feed = feedparser.parse(RSS_URL)
latest = feed.entries[0]

latest_id = latest.id
latest_title = latest.title
latest_link = latest.link

# Load last posted ID
if os.path.exists(STATE_FILE):
    with open(STATE_FILE, "r") as f:
        last_id = json.load(f).get("last_id")
else:
    last_id = None

if latest_id == last_id:
    print("No new post")
    exit(0)

# Login to Bluesky
client = Client()
client.login(HANDLE, PASSWORD)

text = f"🎬 New video:\n{latest_title}\n{latest_link}"

client.send_post(text=text)

# Save state
with open(STATE_FILE, "w") as f:
    json.dump({"last_id": latest_id}, f)

print("Posted to Bluesky")
