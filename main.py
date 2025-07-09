# main.py

import os
import re
import asyncio
import yt_dlp
import aiohttp
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from helper_utils import (
    get_best_formats, extract_info, get_clean_caption,
    download_video_audio, generate_thumbnail, readable_size,
    sanitize_title, parse_range_string, get_temp_dir
)

API_ID = int(os.getenv("API_ID", "123456"))
API_HASH = os.getenv("API_HASH", "your_api_hash")
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token")

bot = Client("yt_downloader_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

bot.playlist_data = {}
bot.active_jobs = {}
MAX_PLAYLIST_VIDEOS = 25

@bot.on_message(filters.command("start") & filters.private)
async def start_handler(_, message: Message):
    await message.reply_text("👋 Send a YouTube link (video or playlist) to begin.")

@bot.on_message(filters.command("cancel") & filters.private)
async def cancel_handler(_, message: Message):
    chat_id = message.chat.id
    playlist = bot.playlist_data.pop(chat_id, None)
    active = bot.active_jobs.pop(chat_id, None)
    if playlist or active:
        await message.reply("❌ Download cancelled.")
    else:
        await message.reply("⚠️ Nothing is running.")

@bot.on_message(filters.private & filters.regex(r"https?://(www\.)?(youtube\.com|youtu\.be)/"))
async def link_handler(_, message: Message):
    url = message.text.strip()
    msg = await message.reply("🔍 Fetching info...")
    try:
        info = await extract_info(url)
    except Exception as e:
        return await msg.edit(f"❌ Failed to fetch info:\n`{e}`")

    if "entries" in info:
        total = len(info["entries"])
        videos = info["entries"]
        bot.playlist_data[message.chat.id] = {"videos": videos, "total": total}

        return await msg.edit(
            f"📁 Playlist with {total} videos found.\n"
            f"📥 You can download up to 25 at a time.\n\n"
            "✏️ Enter range (e.g. 1-25 or 26-50).\n"
            "✋ Use /cancel to stop anytime."
        )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎞 Video", callback_data=f"single_video|{url}"),
         InlineKeyboardButton("🎧 Audio", callback_data=f"single_audio|{url}")]
    ])
    await msg.edit("📦 What do you want to download?", reply_markup=keyboard)

@bot.on_message(filters.text & filters.private)
async def playlist_range_handler(_, message: Message):
    data = bot.playlist_data.get(message.chat.id)
    if not data:
        return

    text = message.text.strip()
    total = len(data["videos"])
    selected = list(range(1, total+1)) if text == "0" else parse_range_string(text)
    selected = [i for i in selected if 1 <= i <= total]
    if not selected:
        return await message.reply("❌ Invalid range.")

    data["selected"] = selected
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔘 {r}p", callback_data=f"playlist_res|{r}") for r in [144, 240, 360]],
        [InlineKeyboardButton(f"🔘 {r}p", callback_data=f"playlist_res|{r}") for r in [480, 720, 1080]]
    ])
    await message.reply("📺 Choose max resolution:", reply_markup=keyboard)

async def upload_progress(current, total, message):
    percent = int(current * 100 / total)
    if percent % 10 == 0 or current == total:
        try:
            await message.edit(f"⏫ Uploading: {percent}%")
        except: pass

@bot.on_callback_query(filters.regex(r"playlist_res\|"))
async def playlist_download_handler(bot, callback):
    await callback.answer()
    _, res = callback.data.split("|")
    res = int(res)

    data = bot.playlist_data.get(callback.message.chat.id)
    if not data:
        return await callback.message.edit("❌ Playlist session expired.")

    all_selected = [v for v in data["videos"] if v.get("playlist_index") in data["selected"]]
    selected_videos = all_selected[:MAX_PLAYLIST_VIDEOS]

    status = await callback.message.edit(f"📥 Starting download of {len(selected_videos)} videos...")
    bot.active_jobs[callback.message.chat.id] = True

    if len(all_selected) > MAX_PLAYLIST_VIDEOS:
        await status.edit(f"⚠️ You selected {len(all_selected)} videos.\nOnly first {MAX_PLAYLIST_VIDEOS} will be downloaded.")

    for idx, video in enumerate(selected_videos, 1):
        if not bot.active_jobs.get(callback.message.chat.id):
            await status.edit("❌ Cancelled.")
            break

        temp_dir = get_temp_dir()
        title = video.get("title")
        url = video.get("webpage_url")

        try:
            await status.edit(f"📥 [{idx}/{len(selected_videos)}] Downloading **{sanitize_title(title)[:40]}**")
            result = await download_video_audio(
                url, f"b[height<={res}][ext=mp4]/bv[height<={res}][ext=mp4]+ba[ext=m4a]", "video",
                temp_dir, status, callback.message.chat.id
            )
            if result["filesize"] > 2 * 1024 * 1024 * 1024:
                await status.edit(f"❌ `{title}` skipped (over 2GB)")
                continue

            caption = get_clean_caption(result["filename"], result["quality"])
            thumb = await generate_thumbnail(result["thumbnail_url"], result["filepath"])
            await bot.send_video(
                callback.message.chat.id,
                result["filepath"],
                caption=caption,
                thumb=thumb,
                supports_streaming=True,
                progress=upload_progress,
                progress_args=(status,)
            )
        except Exception as e:
            await status.edit(f"❌ Error: {e}")
        finally:
            try:
                for f in os.listdir(temp_dir): os.remove(os.path.join(temp_dir, f))
                os.rmdir(temp_dir)
            except: pass

    await status.edit("✅ Playlist done.")
    bot.playlist_data.pop(callback.message.chat.id, None)
    bot.active_jobs.pop(callback.message.chat.id, None)

@bot.on_callback_query(filters.regex(r"single_(video|audio)\|"))
async def single_menu(bot, callback):
    await callback.answer()
    media_type, url = callback.data.split("|", 1)
    msg = await callback.message.edit("📡 Fetching formats...")
    try:
        info = await extract_info(url)
        formats = get_best_formats(info, media_type)
        buttons = [[InlineKeyboardButton(f["label"], callback_data=f"dl|{f['format_id']}|{media_type}|{url}")] for f in formats]
        best = "🎞 Best" if media_type == "video" else "🎧 Best"
        buttons.append([InlineKeyboardButton(best, callback_data=f"dl|best|{media_type}|{url}")])
        await msg.edit("🎚 Choose format:", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        await msg.edit(f"❌ Failed: {e}")

@bot.on_callback_query(filters.regex(r"dl\|"))
async def download_callback(bot, callback):
    await callback.answer()
    _, fmt_id, media_type, url = callback.data.split("|", 3)
    status = await callback.message.edit("⏳ Starting download...")
    bot.active_jobs[callback.message.chat.id] = True
    temp_dir = get_temp_dir()

    try:
        if not bot.active_jobs.get(callback.message.chat.id):
            return await status.edit("❌ Cancelled.")

        result = await download_video_audio(url, fmt_id, media_type, temp_dir, status, callback.message.chat.id)

        if result["filesize"] > 2 * 1024 * 1024 * 1024:
            return await status.edit("❌ File exceeds 2GB.")

        caption = get_clean_caption(result["filename"], result["quality"])
        thumb = await generate_thumbnail(result["thumbnail_url"], result["filepath"])
        await status.edit("⏫ Uploading...")
        if media_type == "video":
            await bot.send_video(callback.message.chat.id, result["filepath"], caption=caption, thumb=thumb, supports_streaming=True)
        else:
            await bot.send_audio(callback.message.chat.id, result["filepath"], caption=caption, thumb=thumb)
        await status.delete()
    except Exception as e:
        await status.edit(f"❌ Failed: {e}")
    finally:
        bot.active_jobs.pop(callback.message.chat.id, None)
        try:
            for f in os.listdir(temp_dir): os.remove(os.path.join(temp_dir, f))
            os.rmdir(temp_dir)
        except: pass

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bot.run()
