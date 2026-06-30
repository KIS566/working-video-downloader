from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
import yt_dlp
import os
import re
import json
import requests
from datetime import datetime
import urllib.parse

# Flask app initialization
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB limit

# Download folder
DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# Global progress variable
download_progress = {'percent': 0, 'status': 'idle', 'speed': 'N/A', 'eta': 'N/A'}

# YouTube API Key (set this in Render environment variables)
YOUTUBE_API_KEY = os.environ.get('AIzaSyAvdprOmPNAP6AjgSPOCNYrPUc2Z7KdVno', '')

def get_video_info_with_api(video_id):
    """Fetch video info using YouTube Data API v3 - Permanent solution"""
    if not YOUTUBE_API_KEY:
        return None
    
    url = f"https://www.googleapis.com/youtube/v3/videos?id={video_id}&part=snippet,contentDetails,statistics&key={YOUTUBE_API_KEY}"
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if 'items' in data and len(data['items']) > 0:
            item = data['items'][0]
            snippet = item['snippet']
            content = item['contentDetails']
            stats = item['statistics']
            
            # Parse duration (PT1H2M3S -> seconds)
            duration_str = content['duration']
            import isodate
            duration_seconds = int(isodate.parse_duration(duration_str).total_seconds())
            
            return {
                'title': snippet['title'],
                'thumbnail': snippet['thumbnails']['high']['url'],
                'duration': duration_seconds,
                'uploader': snippet['channelTitle'],
                'views': int(stats.get('viewCount', 0)),
                'formats': [
                    {'quality': '1080p', 'format_id': 'bestvideo[height<=1080]+bestaudio/best', 'ext': 'mp4', 'filesize': 0},
                    {'quality': '720p', 'format_id': 'bestvideo[height<=720]+bestaudio/best', 'ext': 'mp4', 'filesize': 0},
                    {'quality': '480p', 'format_id': 'bestvideo[height<=480]+bestaudio/best', 'ext': 'mp4', 'filesize': 0},
                    {'quality': '360p', 'format_id': 'bestvideo[height<=360]+bestaudio/best', 'ext': 'mp4', 'filesize': 0},
                ],
                'audio_formats': [
                    {'quality': 'MP3 192kbps', 'format_id': 'bestaudio/best', 'ext': 'mp3', 'filesize': 0}
                ],
                'video_id': video_id,
                'webpage_url': f'https://www.youtube.com/watch?v={video_id}'
            }
    except Exception as e:
        print(f"API Error: {e}")
        return None
    return None

def get_video_info_ytdlp(url):
    """Fetch video metadata using yt-dlp (fallback method)"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'extract_flat': False,
        'headers': headers,
        'cookiefile': None,
        'geo_bypass': True,
        'geo_bypass_country': 'US',
        'extractor_args': {
            'youtube': {
                'skip': ['hls', 'dash'],
                'player_client': ['android', 'web', 'ios'],
                'player_skip': ['webpage', 'configs'],
            }
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None

            formats = []
            seen = set()
            
            for f in info.get('formats', []):
                if f.get('vcodec') == 'none':
                    continue
                
                height = f.get('height')
                if height:
                    label = f'{height}p'
                else:
                    label = f.get('format_note')
                    if not label:
                        label = f.get('resolution')
                    if not label:
                        label = f'ID {f["format_id"]}'
                
                filesize = f.get('filesize') or f.get('filesize_approx', 0)
                
                if label not in seen:
                    seen.add(label)
                    formats.append({
                        'quality': label,
                        'format_id': f['format_id'],
                        'ext': f['ext'],
                        'filesize': filesize or 0
                    })
            
            if not formats:
                formats = [
                    {'quality': '1080p', 'format_id': 'bestvideo[height<=1080]+bestaudio/best', 'ext': 'mp4', 'filesize': 0},
                    {'quality': '720p', 'format_id': 'bestvideo[height<=720]+bestaudio/best', 'ext': 'mp4', 'filesize': 0},
                    {'quality': '480p', 'format_id': 'bestvideo[height<=480]+bestaudio/best', 'ext': 'mp4', 'filesize': 0},
                ]
            
            audio_formats = []
            for f in info.get('formats', []):
                if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                    bitrate = f.get('abr', 128)
                    audio_formats.append({
                        'quality': f'{bitrate} kbps',
                        'format_id': f['format_id'],
                        'ext': 'mp3',
                        'filesize': f.get('filesize', 0)
                    })
            
            if not audio_formats:
                audio_formats.append({
                    'quality': 'MP3 192kbps',
                    'format_id': 'bestaudio/best',
                    'ext': 'mp3',
                    'filesize': 0
                })

            return {
                'title': info.get('title', 'Unknown Title'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'views': info.get('view_count', 0),
                'formats': formats[:10],
                'audio_formats': audio_formats[:5],
                'video_id': info.get('id', ''),
                'webpage_url': info.get('webpage_url', url)
            }
    except Exception as e:
        print(f"yt-dlp Error: {e}")
        return None

def get_video_info(url):
    """Main function to fetch video info - tries API first, then yt-dlp"""
    # Extract video ID
    video_id = None
    if 'youtu.be' in url:
        video_id = url.split('/')[-1].split('?')[0]
    elif 'youtube.com' in url:
        match = re.search(r'v=([a-zA-Z0-9_-]+)', url)
        if match:
            video_id = match.group(1)
    
    # Try API first (permanent solution)
    if video_id and YOUTUBE_API_KEY:
        print(f"Trying YouTube API for video: {video_id}")
        result = get_video_info_with_api(video_id)
        if result:
            print("✅ YouTube API success")
            return result
        print("⚠️ YouTube API failed, falling back to yt-dlp")
    
    # Fallback to yt-dlp
    return get_video_info_ytdlp(url)

def progress_hook(d):
    """Progress hook for yt-dlp"""
    if d['status'] == 'downloading':
        download_progress['percent'] = d.get('_percent_str', '0%').replace('%', '').strip()
        download_progress['speed'] = d.get('_speed_str', 'N/A')
        download_progress['eta'] = d.get('_eta_str', 'N/A')
        download_progress['status'] = 'downloading'
    elif d['status'] == 'finished':
        download_progress['status'] = 'processing'
        download_progress['percent'] = '100'

def download_video(url, format_id, quality_type='video'):
    """Download video/audio with given format"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    ydl_opts = {
        'format': format_id,
        'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
        'quiet': False,
        'no_warnings': False,
        'ignoreerrors': True,
        'progress_hooks': [progress_hook],
        'headers': headers,
        'geo_bypass': True,
        'geo_bypass_country': 'US',
        'extractor_args': {
            'youtube': {
                'skip': ['hls', 'dash'],
                'player_client': ['android', 'web', 'ios'],
            }
        }
    }
    
    if 'instagram.com' in url:
        ydl_opts['format'] = format_id if format_id != 'direct' else 'bestvideo+bestaudio/best'
        ydl_opts['headers']['Referer'] = 'https://www.instagram.com/'
    
    if quality_type == 'audio':
        ydl_opts.update({
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'format': 'bestaudio/best',
        })
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if quality_type == 'audio':
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            download_progress['status'] = 'completed'
            return filename
    except Exception as e:
        download_progress['status'] = 'error'
        download_progress['error'] = str(e)
        return None

# ----- Routes -----

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video/<video_id>')
def video_page(video_id):
    """Video page with 3 dots menu"""
    return render_template('video.html', video_id=video_id)

@app.route('/get_info', methods=['POST'])
def get_info():
    url = request.json.get('url', '').strip()
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    # If it's a YouTube short URL, convert to full URL
    if 'youtu.be' in url:
        video_id = url.split('/')[-1].split('?')[0]
        url = f'https://www.youtube.com/watch?v={video_id}'
    
    info = get_video_info(url)
    if not info:
        return jsonify({'error': 'Could not fetch video info. Make sure URL is correct and video is public.'}), 400
    
    return jsonify(info)

@app.route('/download', methods=['POST'])
def download():
    url = request.json.get('url', '').strip()
    format_id = request.json.get('format_id', 'best')
    quality_type = request.json.get('quality_type', 'video')
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    filename = download_video(url, format_id, quality_type)
    if not filename:
        return jsonify({'error': 'Download failed. Please try again.'}), 400
    
    return jsonify({'success': True, 'filename': os.path.basename(filename)})

@app.route('/download_file/<path:filename>')
def download_file(filename):
    from urllib.parse import unquote
    import re
    
    filename = unquote(filename)
    safe_filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filepath = os.path.join(DOWNLOAD_FOLDER, safe_filename)
    
    if not os.path.exists(filepath):
        filepath = os.path.join(DOWNLOAD_FOLDER, filename)
    
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True, download_name=filename)
    
    files = os.listdir(DOWNLOAD_FOLDER) if os.path.exists(DOWNLOAD_FOLDER) else []
    return jsonify({
        'error': 'File not found',
        'available_files': files,
        'requested': filename
    }), 404

@app.route('/progress')
def progress():
    return jsonify(download_progress)

# ----- Run (Production Ready) -----
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
