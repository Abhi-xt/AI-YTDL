import os
import time
import asyncio
import logging
import requests
import yt_dlp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters, ContextTypes
)
BOT_TOKEN = "1980052148:AAHZyC-efejzwWWWk90J-r_kjqvgJtPDfFk"

logging.basicConfig(level=logging.INFO)
TEMP_DIR = "downloads"
os.makedirs(TEMP_DIR, exist_ok=True)

# ⏳ Download progress hook (every 5 sec)
def download_hook(d):
    if d['status'] == 'downloading':
        current = time.time()
        last = d.get('last_update', 0)
        if current - last >= 5:
            d['last_update'] = current
            context = d.get('context')
            percent = d.get('_percent_str', '').strip()
            if context:
                asyncio.run_coroutine_threadsafe(
                    context['msg'].edit_text(f"📥 Downloading to server: {percent}"),
                    context['loop']
                )

# 🖼 Download official YouTube thumbnail
def download_thumbnail(url, title):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        filename = os.path.join(TEMP_DIR, f"{title}_thumb.jpg")
        with open(filename, 'wb') as f:
            f.write(response.content)
        if os.path.getsize(filename) > 200 * 1024:
            return None
        return filename
    except Exception as e:
        print(f"Thumbnail error: {e}")
        return None

# 📦 /start handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Send a YouTube video link to begin.")

# 🔗 Handle YouTube URL
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    ydl_opts = {"quiet": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to fetch video info.\n{e}")
        return

    title = info.get("title", "Video")
    formats = info.get("formats", [])
    buttons = []

    for f in formats:
        f_id = f['format_id']
        ext = f['ext']
        height = f.get('height')
        abr = f.get('abr')
        size = f.get('filesize') or f.get('filesize_approx')
        size_mb = f"{round(size / (1024 * 1024), 2)}MB" if size else "?"
        label = ""

        if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
            label = f"📹🔊 {height or 'Auto'}p | {size_mb}"
        elif f.get('vcodec') != 'none':
            label = f"📹 {height}p | {size_mb}"
        elif f.get('acodec') != 'none':
            label = f"🔊 {abr} kbps | {size_mb}"
        else:
            continue

        buttons.append([InlineKeyboardButton(label, callback_data=f"{f_id}|{url}")])

    if not buttons:
        await update.message.reply_text("❌ No downloadable formats found.")
        return

    markup = InlineKeyboardMarkup(buttons[:30])
    await update.message.reply_text(
        f"🎬 *{title}*\nChoose a format:",
        reply_markup=markup,
        parse_mode='Markdown'
    )

# ▶️ Handle Format Button Click
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)  # Remove buttons

    fmt_id, url = query.data.split('|')
    msg = await query.message.reply_text("📥 Starting download...")

    out_path = os.path.join(TEMP_DIR, "%(title)s.%(ext)s")

    ydl_opts = {
        "format": f"{fmt_id}+bestaudio/best",
        "outtmpl": out_path,
        "merge_output_format": "mp4",
        "progress_hooks": [download_hook],
        "quiet": True,
    }

    loop = asyncio.get_event_loop()
    ydl_opts["progress_hooks"][0].__dict__["context"] = {"msg": msg, "loop": loop}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url)
        filename = ydl.prepare_filename(info)
        final_file = filename if filename.endswith(".mp4") else filename + ".mp4"

        # Download thumbnail
        thumb_path = download_thumbnail(info.get("thumbnail"), info.get("title", "thumb"))

        # Upload progress every 5 seconds (estimated)
        await msg.edit_text("📤 Uploading to Telegram: 0%")
        await context.bot.send_video(
            chat_id=query.message.chat_id,
            video=open(final_file, 'rb'),
            thumb=open(thumb_path, 'rb') if thumb_path else None,
            supports_streaming=True,
            caption=f"✅ {info['title']}"
        )

        await msg.edit_text("✅ Done!")

    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")
    finally:
        try:
            os.remove(final_file)
            if thumb_path:
                os.remove(thumb_path)
        except:
            pass

# 🚀 Run Bot
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(handle_button))
    print("🤖 Bot is running...")
    app.run_polling()
    
