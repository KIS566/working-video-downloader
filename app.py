from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
import yt_dlp
import os
import re
import json
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

download_progress = {'percent': 0, 'status': 'idle', 'speed': 'N/A', 'eta': 'N/A'}

def get_video_info(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    }
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'extract_flat': False,
        'headers': headers,
        'geo_bypass': True,
    }
    
    if 'instagram.com' in url:
        ydl_opts['format'] = 'bestvideo+bestaudio/best'
        ydl_opts['headers']['Referer'] = 'https://www.instagram.com/'
    
    if 'youtube.com' in url or 'youtu.be' in url:
        ydl_opts['extractor_args'] = {
            'youtube': {
                'skip': ['hls', 'dash'],
                'player_client': ['android', 'web'],
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
        print(f"Error: {e}")
        if 'instagram.com' in url:
            return {
                'title': 'Instagram Video',
                'thumbnail': 'https://via.placeholder.com/480x360?text=Instagram',
                'duration': 0,
                'uploader': 'Instagram User',
                'views': 0,
                'formats': [
                    {'quality': 'Best', 'format_id': 'bestvideo+bestaudio/best', 'ext': 'mp4', 'filesize': 0},
                ],
                'audio_formats': [{'quality': 'MP3', 'format_id': 'bestaudio/best', 'ext': 'mp3', 'filesize': 0}],
                'webpage_url': url
            }
        return None

def download_video(url, format_id, quality_type='video'):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    ydl_opts = {
        'format': format_id,
        'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
        'quiet': False,
        'no_warnings': False,
        'ignoreerrors': True,
        'progress_hooks': [lambda d: None],
        'headers': headers,
        'geo_bypass': True,
    }
    
    if 'youtube.com' in url or 'youtu.be' in url:
        ydl_opts['extractor_args'] = {
            'youtube': {
                'skip': ['hls', 'dash'],
                'player_client': ['android', 'web'],
            }
        }
    
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
            return filename
    except Exception as e:
        print(f"Download error: {e}")
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
    
    if 'youtu.be' in url:
        video_id = url.split('/')[-1].split('?')[0]
        url = f'https://www.youtube.com/watch?v={video_id}'
    
    info = get_video_info(url)
    if not info:
        return jsonify({'error': 'Could not fetch video info.'}), 400
    
    # Add video_id to response
    if 'youtube.com' in url or 'youtu.be' in url:
        video_id = re.search(r'v=([a-zA-Z0-9_-]+)', url)
        if video_id:
            info['video_id'] = video_id.group(1)
        else:
            info['video_id'] = url.split('/')[-1].split('?')[0]
    
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
        return jsonify({'error': 'Download failed.'}), 400
    
    return jsonify({'success': True, 'filename': os.path.basename(filename)})

@app.route('/download_file/<filename>')
def download_file(filename):
    filepath = os.path.join(DOWNLOAD_FOLDER, filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return jsonify({'error': 'File not found'}), 404

@app.route('/progress')
def progress():
    return jsonify(download_progress)

# ----- Run -----
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)