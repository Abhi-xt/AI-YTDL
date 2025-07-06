import os
import time
import asyncio
import requests
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from yt_dlp import YoutubeDL

# Load credentials
load_dotenv()
API_ID = 
API_HASH = ''
BOT_TOKEN = ''

# Create client
app = Client("ytbot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
os.makedirs("downloads", exist_ok=True)

# 🔍 Get available formats
def get_formats(url):
    with YoutubeDL({'quiet': True}) as ydl:
        info = ydl.extract_info(url, download=False)
        formats = []
        for f in info['formats']:
            f_id = f['format_id']
            ext = f.get('ext')
            res = f.get('format_note') or f.get('height') or "audio"
            size = f.get('filesize') or f.get('filesize_approx')
            size = round(size / (1024*1024), 1) if size else "?"
            v = f.get('vcodec') != 'none'
            a = f.get('acodec') != 'none'
            type_ = "audio" if not v and a else "video" if v and a else "unknown"
            formats.append((f_id, ext, res, size, type_))
    return formats, info

# 🖼 Get thumbnail bytes (or fallback)
def get_thumbnail(url):
    try:
        video_id = url.split("v=")[-1] if "v=" in url else url.split("/")[-1]
        thumb_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        r = requests.get(thumb_url, timeout=10)
        return r.content if r.ok and len(r.content) < 200 * 1024 else None
    except:
        return None

# ⏬ Download file using yt-dlp
def download_youtube(url, format_id, progress_callback):
    filename = None
    ydl_opts = {
        'format': format_id,
        'progress_hooks': [progress_callback],
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'quiet': True,
        'merge_output_format': 'mp4'
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url)
        filename = ydl.prepare_filename(info)
    return filename

# ✅ /start command
@app.on_message(filters.command("start"))
async def start(_, msg):
    await msg.reply("👋 Send a YouTube video link to download.")

# 📩 YouTube link handler
@app.on_message(filters.regex(r"^https?://(www\.)?(youtube\.com|youtu\.be)/"))
async def yt_handler(_, msg):
    url = msg.text.strip()
    try:
        formats, info = get_formats(url)
    except Exception as e:
        await msg.reply(f"❌ Failed to fetch video info.\n{e}")
        return

    # 🧭 Format buttons
    keyboard = []
    for f_id, ext, res, size, type_ in formats:
        label = f"{res} | {size} MB"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"{f_id}|{url}")])

    # 🖼 Get thumbnail (YouTube or fallback)
    thumb_bytes = get_thumbnail(url)
    fallback_path = "default.jpg"
    thumb_input = thumb_bytes if thumb_bytes else open(fallback_path, 'rb')

    await msg.reply_photo(
        photo=thumb_input,
        caption=f"🎬 {info['title']}\n\nChoose a format:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    if not thumb_bytes:
        thumb_input.close()

# ⌨️ Format button handler
@app.on_callback_query()
async def cb_handler(client, cb):
    await cb.message.edit_text("⏬ Downloading... (0%)")
    format_id, url = cb.data.split("|")

    last_update = time.time()

    def hook(d):
        nonlocal last_update
        if d['status'] == 'downloading':
            now = time.time()
            if now - last_update >= 5:
                last_update = now
                perc = d.get('_percent_str', '').strip()
                asyncio.run_coroutine_threadsafe(
                    cb.message.edit_text(f"⏬ Downloading... ({perc})"), client.loop
                )

    try:
        file_path = download_youtube(url, format_id, hook)
    except Exception as e:
        await cb.message.edit_text(f"❌ Error: {e}")
        return

    await cb.message.edit_text("📤 Uploading to Telegram... (0%)")

    async def update_progress(current, total):
        if total:
            percent = round(current * 100 / total)
            if percent % 5 == 0:
                await cb.message.edit_text(f"📤 Uploading to Telegram... ({percent}%)")

    await client.send_video(
    chat_id=cb.message.chat.id,
    video=file_path,
    supports_streaming=True,
    caption=os.path.basename(file_path),
    progress=update_progress)

    await cb.message.edit_text("✅ Done!")
    try:
        os.remove(file_path)
    except:
        pass

# 🚀 Launch the bot
if __name__ == "__main__":
    print("✅ Bot is running... Waiting for messages.")
    app.run()
