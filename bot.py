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
    await message.reply_text("Send me a YouTube link (video or playlist). Use /add to upload cookies.txt")

@app.on_message(filters.command("add"))
async def add_cookies(client, message):
    await message.reply_text("Send me the `cookies.txt` file as a document.")

@app.on_message(filters.command("rm"))
async def remove_cookies(client, message):
    if os.path.exists("cookies.txt"):
        os.remove("cookies.txt")
        await message.reply("✅ `cookies.txt` removed.")
    else:
        await message.reply("❌ No `cookies.txt` found.")

@app.on_message(filters.document & filters.private)
async def receive_file(client, message):
    if message.document.file_name == "cookies.txt":
        path = await message.download()
        os.rename(path, "cookies.txt")
        await message.reply("✅ `cookies.txt` saved successfully.")

@app.on_message(filters.regex(r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/\S+"))
async def youtube_handler(client, message):
    url = message.text.strip()
    ydl_opts = {'quiet': True, 'extract_flat': False}
    if os.path.exists("cookies.txt"):
        ydl_opts["cookiefile"] = "cookies.txt"

    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            return await message.reply_text(f"Error: {e}")

    if 'entries' in info:
        videos = info['entries']
        count = len(videos)
        status = await message.reply_text(f"📃 Playlist detected with {count} videos. Starting download...")
        for i, entry in enumerate(videos, start=1):
            try:
                video_url = entry['url']
                video_title = entry.get('title', f"Video {i}")
                await status.edit_text(f"📥 Downloading video {i}/{count}:
`{video_title}`")
                temp_msg = await message.reply("⏬ Starting download...")
                asyncio.create_task(downstatus(client, f"{temp_msg.id}downstatus.txt", temp_msg, message.chat.id))
                filename, title = await download_video(video_url, "360p", temp_msg)
                os.remove(f"{temp_msg.id}downstatus.txt")
                thumb = await generate_thumbnail(video_url)
                asyncio.create_task(upstatus(client, f"{temp_msg.id}upstatus.txt", temp_msg, message.chat.id))
                await client.send_video(
                    chat_id=message.chat.id,
                    video=filename,
                    caption=f"{i:02d}_ {title}",
                    thumb=thumb,
                    supports_streaming=True,
                    progress=progress,
                    progress_args=(temp_msg, "up")
                )
                os.remove(filename)
                if thumb and os.path.exists(thumb):
                    os.remove(thumb)
                os.remove(f"{temp_msg.id}upstatus.txt")
                await temp_msg.delete()
            except Exception as e:
                await message.reply(f"❌ Failed video {i}: {e}")
        await status.edit_text(f"✅ All {count} videos downloaded.")
    else:
        # Single video
        title = info.get("title", "Video")
        formats = info.get("formats", [])
        resolutions = []
        for fmt in formats:
            if fmt.get("vcodec") != "none" and fmt.get("acodec") != "none":
                height = fmt.get("height")
                if height:
                    resolutions.append(f"{height}p")
        resolutions = sorted(set(resolutions), key=lambda x: int(x.replace("p", "")))
        buttons = [[InlineKeyboardButton(res, callback_data=f"yt_{res}")] for res in resolutions]
        await message.reply_text(
            f"**{title}**\nSelect the desired resolution:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

@app.on_callback_query(filters.regex(r"yt_(\d{{3}}p)"))
async def download_callback(client, callback_query):
    resolution = callback_query.data.split("_")[1]
    url = callback_query.message.reply_to_message.text.strip()
    chat_id = callback_query.message.chat.id
    smsg = await callback_query.message.reply("📥 Downloading...")
    asyncio.create_task(downstatus(client, f"{smsg.id}downstatus.txt", smsg, chat_id))
    try:
        video_path, title = await download_video(url, resolution, smsg)
        os.remove(f"{smsg.id}downstatus.txt")
        thumb_path = await generate_thumbnail(url)
        asyncio.create_task(upstatus(client, f"{smsg.id}upstatus.txt", smsg, chat_id))
        await client.send_video(
            chat_id=chat_id,
            video=video_path,
            caption=title,
            thumb=thumb_path,
            supports_streaming=True,
            progress=progress,
            progress_args=(smsg, "up")
        )
        os.remove(video_path)
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)
        os.remove(f"{smsg.id}upstatus.txt")
    except Exception as e:
        await smsg.edit(f"Error: {e}")

app.run()
