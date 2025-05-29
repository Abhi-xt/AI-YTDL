import os
import time
import asyncio
import requests
from yt_dlp import YoutubeDL

progress_data = {}

def humanbytes(size):
    if not size:
        return ""
    power = 1024
    t_n = 0
    power_dict = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        t_n += 1
    return "{:.2f} {}B".format(size, power_dict[t_n])

def TimeFormatter(seconds: float) -> str:
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = ((str(days) + "d, ") if days else "") +           ((str(hours) + "h, ") if hours else "") +           ((str(minutes) + "m, ") if minutes else "") +           ((str(seconds) + "s, ") if seconds else "")
    return tmp[:-2]

def progress(current, total, message, type):
    now = time.time()
    key = f"{message.id}_{type}"
    if key not in progress_data:
        progress_data[key] = now
    start = progress_data[key]
    elapsed = now - start
    speed = current / elapsed if elapsed > 0 else 0
    percent = current * 100 / total
    eta = TimeFormatter((total - current) / speed) if speed > 0 else "Calculating"
    speed_str = humanbytes(speed) + "/s"
    action = "Downloading ..." if type == "down" else "Uploading ..."
    formatted = (
        f"**{action}** \n\n"
        f"**✅ Completed** : **{percent:.1f}%**\n\n"
        f"**⏳ Processed** : **{humanbytes(current)}** - **{humanbytes(total)}**\n\n"
        f"**🚀 Speed** : **{speed_str}**\n\n"
        f"**⏰ ETA** : **{eta}**\n"
    )
    with open(f"{message.id}{type}status.txt", "w") as fileup:
        fileup.write(formatted)

async def downstatus(client, statusfile, message, chat):
    while not os.path.exists(statusfile):
        await asyncio.sleep(3)
    while os.path.exists(statusfile):
        with open(statusfile, "r") as f:
            txt = f.read()
        try:
            await client.edit_message_text(chat, message.id, txt)
            await asyncio.sleep(6)
        except:
            await asyncio.sleep(3)

async def upstatus(client, statusfile, message, chat):
    while not os.path.exists(statusfile):
        await asyncio.sleep(3)
    while os.path.exists(statusfile):
        with open(statusfile, "r") as f:
            txt = f.read()
        try:
            await client.edit_message_text(chat, message.id, txt)
            await asyncio.sleep(6)
        except:
            await asyncio.sleep(3)

async def download_video(url, resolution, message):
    ydl_opts = {
        'format': f'bestvideo[height={resolution[:-1]}]+bestaudio/best[height={resolution[:-1]}]',
        'outtmpl': '%(title)s.%(ext)s',
        'merge_output_format': 'mp4',
        'quiet': True,
        'progress_hooks': [lambda d: progress_hook(d, message)]
    }
    if os.path.exists("cookies.txt"):
        ydl_opts["cookiefile"] = "cookies.txt"
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename, info.get("title", "Video")

async def generate_thumbnail(url):
    with YoutubeDL({'quiet': True}) as ydl:
        info = ydl.extract_info(url, download=False)
        thumbnail_url = info.get('thumbnail')
        if not thumbnail_url:
            return None
        response = requests.get(thumbnail_url)
        if response.status_code == 200:
            thumb_path = f"{info['id']}_thumb.jpg"
            with open(thumb_path, 'wb') as f:
                f.write(response.content)
            return thumb_path
        return None

def progress_hook(d, message):
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate')
        downloaded = d.get('downloaded_bytes', 0)
        progress(downloaded, total, message, "down")
