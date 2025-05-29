import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from yt_dlp import YoutubeDL
from helpers import download_video, generate_thumbnail, progress, downstatus, upstatus

API_ID = 1234567
API_HASH = "your_api_hash"
BOT_TOKEN = "your_bot_token"

app = Client("yt_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("👋 Send a YouTube video or playlist link.\nI'll let you choose a resolution and download it.")

@app.on_message(filters.regex(r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/\S+"))
async def handle_youtube(client, message):
    url = message.text.strip()
    ydl_opts = {'quiet': True, 'extract_flat': False}
    if os.path.exists("cookies.txt"):
        ydl_opts["cookiefile"] = "cookies.txt"

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        return await message.reply(f"❌ Error: {e}")

    if 'entries' in info:  # Playlist
        videos = info['entries']
        count = len(videos)
        status_msg = await message.reply(f"📃 Playlist detected with {count} videos. Starting download...")
        for i, entry in enumerate(videos, 1):
            try:
                video_url = entry['url']
                title = entry.get("title", f"Video {i}")
                await status_msg.edit(f"📥 Downloading video {i}/{count}:\n`{title}`")
                smsg = await message.reply("🔄 Preparing download...")
                asyncio.create_task(downstatus(client, f"{smsg.id}downstatus.txt", smsg, message.chat.id))
                filename, real_title = await download_video(video_url, "360p", smsg, prefix=f"{i:02d}_")
                os.remove(f"{smsg.id}downstatus.txt")
                thumb = await generate_thumbnail(video_url)
                asyncio.create_task(upstatus(client, f"{smsg.id}upstatus.txt", smsg, message.chat.id))
                await client.send_video(
                    chat_id=message.chat.id,
                    video=filename,
                    caption=real_title,
                    thumb=thumb,
                    supports_streaming=True,
                    progress=progress,
                    progress_args=(smsg, "up")
                )
                os.remove(filename)
                if thumb and os.path.exists(thumb):
                    os.remove(thumb)
                os.remove(f"{smsg.id}upstatus.txt")
                await smsg.delete()
            except Exception as e:
                await message.reply(f"❌ Failed to download video {i}: {e}")
        return await status_msg.edit("✅ All playlist videos downloaded.")

    # Single video
    formats = info.get("formats", [])
    buttons = []
    seen = set()
    for f in formats:
        if f.get("vcodec") != "none" and f.get("acodec") != "none" and f.get("height"):
            label = f"{f['height']}p"
            if label not in seen:
                seen.add(label)
                buttons.append([InlineKeyboardButton(label, callback_data=f"{label}|{url}")])
    await message.reply_text(
        f"🎞️ **{info.get('title')}**\nSelect the resolution to download:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_callback_query(filters.regex(r"^(\d{3}p)\|(.+)"))
async def format_selected(client, callback_query):
    resolution, url = callback_query.data.split("|")
    await callback_query.answer(f"Selected {resolution}")
    smsg = await callback_query.message.reply("📥 Starting download...")
    asyncio.create_task(downstatus(client, f"{smsg.id}downstatus.txt", smsg, callback_query.message.chat.id))
    try:
        filename, title = await download_video(url, resolution, smsg)
        os.remove(f"{smsg.id}downstatus.txt")
        thumb = await generate_thumbnail(url)
        asyncio.create_task(upstatus(client, f"{smsg.id}upstatus.txt", smsg, callback_query.message.chat.id))
        await client.send_video(
            chat_id=callback_query.message.chat.id,
            video=filename,
            caption=title,
            thumb=thumb,
            supports_streaming=True,
            progress=progress,
            progress_args=(smsg, "up")
        )
        os.remove(filename)
        if thumb and os.path.exists(thumb):
            os.remove(thumb)
        os.remove(f"{smsg.id}upstatus.txt")
        await smsg.delete()
    except Exception as e:
        await smsg.edit(f"❌ Download error: {e}")

@app.on_message(filters.command(["add"]))
async def add_cookies(client, message):
    await message.reply_text("📤 Send `cookies.txt` as a file.")

@app.on_message(filters.document & filters.private)
async def receive_file(client, message):
    if message.document.file_name == "cookies.txt":
        path = await message.download()
        os.rename(path, "cookies.txt")
        await message.reply("✅ `cookies.txt` saved.")

@app.on_message(filters.command(["rm"]))
async def rm_cookies(client, message):
    if os.path.exists("cookies.txt"):
        os.remove("cookies.txt")
        await message.reply("✅ `cookies.txt` removed.")
    else:
        await message.reply("❌ No cookies.txt found.")

app.run()
            
