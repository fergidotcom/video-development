#!/usr/bin/env python3
"""
Find and compress the largest high-res videos first.
Doesn't need the CSV survey to be complete - does its own targeted search.
"""

import os
import subprocess
import json
from datetime import datetime
import sys
import signal

# Configuration
PEGASUS_PATH = "/Volumes/Promise Pegasus"
OUTPUT_DIR = "/Users/joeferguson/Library/CloudStorage/Dropbox/Fergi/VideoDev/logs"
COMPRESSED_DIR = "/Volumes/Promise Pegasus/_compressed_1080p"

VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.m4v', '.MP4', '.MOV', '.MKV'}

# Target resolution
TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
MIN_SIZE_GB = 1  # Only compress files >= 1GB

# FFmpeg settings
CRF = 23
PRESET = "medium"

# Graceful shutdown
shutdown_requested = False

def signal_handler(signum, frame):
    global shutdown_requested
    print("\n⏸️  Shutdown requested, will stop after current file...")
    shutdown_requested = True

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def format_size(bytes_size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"

def format_duration(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def get_video_resolution(filepath):
    """Get video resolution using ffprobe."""
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            '-select_streams', 'v:0',
            filepath
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)
        if not data.get('streams'):
            return None

        stream = data['streams'][0]
        return {
            'width': stream.get('width', 0),
            'height': stream.get('height', 0),
            'codec': stream.get('codec_name', 'unknown')
        }
    except:
        return None

def compress_video(input_path, output_path):
    """Compress video to 1080p using FFmpeg H.265."""
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-vf', f'scale={TARGET_WIDTH}:-2',
            '-c:v', 'libx265',
            '-crf', str(CRF),
            '-preset', PRESET,
            '-tag:v', 'hvc1',  # Better compatibility
            '-c:a', 'aac',
            '-b:a', '192k',
            '-movflags', '+faststart',
            '-y',
            output_path
        ]

        print(f"  Running FFmpeg...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0
    except Exception as e:
        print(f"  Error: {e}")
        return False

def find_large_high_res_videos():
    """Find large high-resolution videos on the drive."""
    print(f"Scanning {PEGASUS_PATH} for large high-res videos...")
    print(f"Looking for files >= {MIN_SIZE_GB}GB with resolution > {TARGET_WIDTH}x{TARGET_HEIGHT}")
    print()

    videos = []
    min_size_bytes = MIN_SIZE_GB * 1024 * 1024 * 1024
    files_checked = 0

    for root, dirs, files in os.walk(PEGASUS_PATH):
        # Skip hidden and special directories
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['_compressed_1080p', '_compression_temp']]

        for filename in files:
            ext = os.path.splitext(filename)[1]
            if ext not in VIDEO_EXTENSIONS:
                continue

            filepath = os.path.join(root, filename)

            try:
                size = os.path.getsize(filepath)
            except:
                continue

            # Only check large files
            if size < min_size_bytes:
                continue

            files_checked += 1
            if files_checked % 10 == 0:
                print(f"  Checked {files_checked} large videos...", end='\r')

            # Check resolution
            info = get_video_resolution(filepath)
            if not info:
                continue

            if info['width'] > TARGET_WIDTH or info['height'] > TARGET_HEIGHT:
                videos.append({
                    'path': filepath,
                    'filename': filename,
                    'width': info['width'],
                    'height': info['height'],
                    'size': size,
                    'codec': info['codec']
                })
                print(f"  FOUND: {filename} - {info['width']}x{info['height']} - {format_size(size)}")

    print(f"\nFound {len(videos)} large high-res videos")
    return videos

def main():
    global shutdown_requested

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(OUTPUT_DIR, f"{timestamp}_compression_log.txt")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(COMPRESSED_DIR, exist_ok=True)

    print("="*60)
    print("PEGASUS DRIVE - HIGH-RES VIDEO COMPRESSION")
    print("="*60)
    print()

    # Find videos
    videos = find_large_high_res_videos()

    if not videos:
        print("No large high-res videos found!")
        return

    # Sort by size (largest first)
    videos.sort(key=lambda x: x['size'], reverse=True)

    total_original = sum(v['size'] for v in videos)
    print(f"\nTotal size to compress: {format_size(total_original)}")
    print()

    # Track results
    total_saved = 0
    processed = 0
    failed = 0

    with open(log_path, 'w') as log:
        log.write(f"Compression started: {datetime.now()}\n")
        log.write(f"Videos to process: {len(videos)}\n")
        log.write(f"Total original size: {format_size(total_original)}\n\n")

        for i, video in enumerate(videos, 1):
            if shutdown_requested:
                print(f"\n⏸️  Stopping after {processed} videos (shutdown requested)")
                break

            input_path = video['path']
            filename = video['filename']

            # Create output path (same structure under _compressed_1080p)
            rel_path = input_path.replace(PEGASUS_PATH + '/', '')
            base_name = os.path.splitext(rel_path)[0]
            output_path = os.path.join(COMPRESSED_DIR, f"{base_name}_1080p.mp4")

            # Skip if already compressed
            if os.path.exists(output_path):
                print(f"\n[{i}/{len(videos)}] SKIP (already exists): {filename}")
                continue

            print(f"\n[{i}/{len(videos)}] Compressing: {filename}")
            print(f"  Resolution: {video['width']}x{video['height']}")
            print(f"  Size: {format_size(video['size'])}")

            log.write(f"\n[{i}/{len(videos)}] {filename}\n")
            log.write(f"  Original: {video['width']}x{video['height']} - {format_size(video['size'])}\n")

            start_time = datetime.now()
            success = compress_video(input_path, output_path)
            elapsed = (datetime.now() - start_time).total_seconds()

            if success and os.path.exists(output_path):
                compressed_size = os.path.getsize(output_path)
                savings = video['size'] - compressed_size
                savings_pct = (savings / video['size'] * 100) if video['size'] > 0 else 0

                total_saved += savings
                processed += 1

                print(f"  ✓ Done: {format_size(compressed_size)} (saved {format_size(savings)}, {savings_pct:.1f}%)")
                print(f"  Time: {format_duration(elapsed)}")
                print(f"  Total saved so far: {format_size(total_saved)}")

                log.write(f"  ✓ Compressed: {format_size(compressed_size)} (saved {format_size(savings)}, {savings_pct:.1f}%)\n")
                log.write(f"  Time: {format_duration(elapsed)}\n")
            else:
                failed += 1
                print(f"  ✗ FAILED")
                log.write(f"  ✗ FAILED\n")

                # Clean up failed output
                if os.path.exists(output_path):
                    os.remove(output_path)

            log.flush()

        log.write(f"\n\n{'='*60}\n")
        log.write(f"COMPLETE: {processed} videos, {format_size(total_saved)} saved\n")

    print("\n" + "="*60)
    print("COMPRESSION SUMMARY")
    print("="*60)
    print(f"Videos processed: {processed}")
    print(f"Videos failed: {failed}")
    print(f"Total space saved: {format_size(total_saved)}")
    print("="*60)
    print(f"\nCompressed files in: {COMPRESSED_DIR}")
    print("⚠️  ORIGINAL FILES PRESERVED")
    print("Delete originals after verifying compressed versions are OK")

if __name__ == "__main__":
    main()
