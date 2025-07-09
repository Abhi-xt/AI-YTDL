import os
import re
import aiohttp
import asyncio
import yt_dlp
import tempfile
from ffmpeg import input as ffmpeg_input, output as ffmpeg_output, run

def sanitize_title(title: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '', title).strip()

def parse_range_string(range_str):
    indices = set()
    for part in range_str.split(','):
        if '-' in part:
            start, end = map(int, part.split('-'))
            indices.update(range(start, end + 1))
        elif part.isdigit():
            indices.add(int(part))
    return sorted(indices)

def get_temp_dir():
    return tempfile.mkdtemp(prefix="yt_dl_")

async def extract_info(url: str) -> dict:
    loop = asyncio.get_event_loop()
    ydl_opts = {'quiet': True, 'skip_download': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))

def get_best_formats(info, media_type):
    formats = []
    for f in info.get("formats", []):
        if media_type == "video" and f.get("vcodec") != "none" and f.get("acodec") == "none":
            label = f"🎥 {f.get('height', '?')}p | {f.get('ext', 'na')} | {readable_size(f.get('filesize') or f.get('filesize_approx'))}"
            formats.append({"format_id": f["format_id"], "label": label})
        elif media_type == "audio" and f.get("vcodec") == "none":
            label = f"🎧 {int(f.get('abr', 0))}kbps | {f.get('ext', 'na')} | {readable_size(f.get('filesize') or f.get('filesize_approx'))}"
            formats.append({"format_id": f["format_id"], "label": label})
    return formats

def readable_size(size):
    if not size: return "?"
    size = int(size)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024

def get_clean_caption(filename, quality):
    return f"📄 Filename: {os.path.basename(filename)}\n📺 Quality: {quality}" if "p" in quality else f"📄 Filename: {os.path.basename(filename)}\n🔊 Quality: {quality}"

async def download_video_audio(url, fmt_id, media_type, temp_dir, status_msg, chat_id):
    output_path = os.path.join(temp_dir, "download.%(ext)s")
    format_string = fmt_id if fmt_id != "best" else ("bestvideo+bestaudio/best" if media_type == "video" else "bestaudio/best")

    ydl_opts = {
        'format': format_string,
        'outtmpl': output_path,
        'merge_output_format': 'mp4',
        'quiet': True,
        'progress_hooks': [gen_progress_hook(status_msg)],
        'noplaylist': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url)
        filepath = ydl.prepare_filename(info)
        if info.get("ext") != "mp4" and media_type == "audio":
            filepath = filepath.rsplit(".", 1)[0] + ".mp3"
        playlist_index = info.get("playlist_index")
        prefix = f"{playlist_index}. " if playlist_index else ""
        filename = prefix + sanitize_title(info['title']) + (".mp4" if media_type == "video" else ".mp3")
        quality = f"{info.get('height')}p" if media_type == "video" else f"{int(info.get('abr', 128))}kbps"

    return {
        "filepath": filepath,
        "filename": filename,
        "quality": quality,
        "filesize": info.get('filesize', 0),
        "thumbnail_url": info.get('thumbnail')
    }

def gen_progress_hook(message):
    last = {'time': 0}

    def hook(d):
        if d['status'] == 'downloading':
            percent = d.get("_percent_str", "0%").strip()
            now = asyncio.get_event_loop().time()
            if now - last['time'] > 6:
                last['time'] = now
                asyncio.ensure_future(message.edit(f"⬇️ Downloading: {percent}"))
        elif d['status'] == 'finished':
            asyncio.ensure_future(message.edit("🛠 Merging..."))
    return hook

async def generate_thumbnail(thumbnail_url, fallback_path):
    thumb_path = fallback_path.rsplit('.', 1)[0] + "_thumb.jpg"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail_url) as resp:
                if resp.status == 200:
                    with open(thumb_path, "wb") as f:
                        f.write(await resp.read())
                    return thumb_path
    except:
        pass
    try:
        ffmpeg_input(fallback_path, ss=1).output(thumb_path, vframes=1).run(quiet=True, overwrite_output=True)
        return thumb_path
    except:
        return None
                         
