#!/usr/bin/env python3
"""
FFmpeg Parallel Batch Processor
================================
Runs alongside Compressor to process videos in parallel.
Uses VideoToolbox hardware encoding (7x realtime).

Processes from smallest files first (opposite of Compressor's largest-first).
Also handles files that Compressor rejected due to metadata issues.

Usage:
    nohup python3 ffmpeg_parallel_batch.py > logs/$(date +%Y%m%d_%H%M%S)_ffmpeg_batch.log 2>&1 &
"""

import os
import sys
import csv
import json
import subprocess
import time
from pathlib import Path
from datetime import datetime

# Configuration
PEGASUS_ROOT = "/Volumes/Promise Pegasus"
OUTPUT_DIR = f"{PEGASUS_ROOT}/_compressor_output"
CSV_FILE = "logs/20251205_001737_high_res_videos.csv"
PROGRESS_FILE = "logs/compressor_cli_progress.json"
FFMPEG_PROGRESS_FILE = "logs/ffmpeg_progress.json"

# FFmpeg settings
FFMPEG_PATH = "ffmpeg"
VIDEO_BITRATE = "8M"
AUDIO_BITRATE = "192k"

def log(msg):
    """Print timestamped log message."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

def load_json(filepath):
    """Load JSON file, return empty dict if not exists."""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'completed': [], 'failed': [], 'skipped': []}

def save_json(filepath, data):
    """Save JSON file."""
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

def get_video_info(filepath):
    """Get video resolution using ffprobe."""
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'quiet',
            '-show_entries', 'stream=width,height',
            '-of', 'json', filepath
        ], capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        for stream in data.get('streams', []):
            if 'width' in stream and 'height' in stream:
                return stream['width'], stream['height']
    except:
        pass
    return None, None

def generate_output_path(input_path):
    """Generate output path preserving directory structure."""
    rel_path = input_path.replace(PEGASUS_ROOT + '/', '')
    path_parts = rel_path.split('/')

    if len(path_parts) > 1:
        subdir = '/'.join(path_parts[:-1])
    else:
        subdir = "misc"

    filename = path_parts[-1]
    base, ext = os.path.splitext(filename)
    output_filename = f"{base}_1080p.mov"

    full_output_dir = os.path.join(OUTPUT_DIR, subdir)
    os.makedirs(full_output_dir, exist_ok=True)

    return os.path.join(full_output_dir, output_filename)

def compress_video(input_path, output_path, width, height):
    """Compress video using FFmpeg with VideoToolbox."""
    # Calculate output dimensions (scale to 1080p max, preserve aspect)
    if width and height:
        if width > height:
            # Landscape
            scale = f"scale=1920:1080:force_original_aspect_ratio=decrease"
        elif height > width:
            # Portrait
            scale = f"scale=1080:1920:force_original_aspect_ratio=decrease"
        else:
            # Square
            scale = f"scale=1080:1080"
    else:
        scale = "scale='min(1920,iw)':'min(1080,ih)':force_original_aspect_ratio=decrease"

    cmd = [
        FFMPEG_PATH,
        '-i', input_path,
        '-c:v', 'hevc_videotoolbox',
        '-b:v', VIDEO_BITRATE,
        '-vf', scale,
        '-c:a', 'aac',
        '-b:a', AUDIO_BITRATE,
        '-y',
        output_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)  # 2 hour timeout
        return result.returncode == 0, result.stderr
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)

def load_video_list():
    """Load and dedupe video list from CSV."""
    videos = []
    try:
        with open(CSV_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Skip fcpbundle files
                if '.fcpbundle' in row['path']:
                    continue
                videos.append({
                    'path': row['path'],
                    'filename': row['filename'],
                    'size_bytes': int(row['size_bytes']),
                    'duration_sec': float(row.get('duration_sec', 0))
                })
    except Exception as e:
        log(f"ERROR loading CSV: {e}")

    # Dedupe by filename+size
    seen = {}
    unique = []
    for v in videos:
        key = (v['filename'].lower(), v['size_bytes'])
        if key not in seen:
            seen[key] = v['path']
            unique.append(v)

    return unique

def main():
    log("=" * 60)
    log("FFMPEG PARALLEL BATCH PROCESSOR")
    log("=" * 60)

    if not os.path.exists(PEGASUS_ROOT):
        log(f"ERROR: Pegasus drive not mounted at {PEGASUS_ROOT}")
        sys.exit(1)

    # Load video list
    videos = load_video_list()
    log(f"Loaded {len(videos)} unique non-fcpbundle videos")

    # Load both progress files
    compressor_progress = load_json(PROGRESS_FILE)
    ffmpeg_progress = load_json(FFMPEG_PROGRESS_FILE)

    # Combine all processed paths
    all_done = set(
        compressor_progress.get('completed', []) +
        compressor_progress.get('failed', []) +
        compressor_progress.get('skipped', []) +
        ffmpeg_progress.get('completed', []) +
        ffmpeg_progress.get('failed', [])
    )

    # Get remaining videos, sort by size (smallest first - opposite of Compressor)
    remaining = [v for v in videos if v['path'] not in all_done]
    remaining.sort(key=lambda x: x['size_bytes'])  # Smallest first

    log(f"Remaining to process: {len(remaining)}")

    # Also get Compressor's failed files to retry with FFmpeg
    compressor_failed = compressor_progress.get('failed', [])
    failed_videos = [v for v in videos if v['path'] in compressor_failed and v['path'] not in ffmpeg_progress.get('completed', [])]

    if failed_videos:
        log(f"Will also retry {len(failed_videos)} Compressor-failed files")
        # Add failed files to the front of the queue
        remaining = failed_videos + remaining

    if not remaining:
        log("No videos to process!")
        return

    # Process videos
    total_processed = 0
    total_failed = 0

    for i, video in enumerate(remaining):
        # Re-check progress files in case Compressor processed it
        compressor_progress = load_json(PROGRESS_FILE)
        if video['path'] in compressor_progress.get('completed', []):
            log(f"Skipping {video['filename']} - Compressor completed it")
            continue

        log(f"\n{'='*60}")
        log(f"VIDEO {i+1}/{len(remaining)}: {video['filename']}")
        log(f"Size: {video['size_bytes']/(1024**3):.2f} GB")
        log(f"Path: {video['path']}")

        # Check if source exists
        if not os.path.exists(video['path']):
            log("SKIPPING: Source file not found")
            ffmpeg_progress['failed'].append(video['path'])
            save_json(FFMPEG_PROGRESS_FILE, ffmpeg_progress)
            continue

        # Generate output path
        output_path = generate_output_path(video['path'])
        log(f"Output: {output_path}")

        # Skip if output exists
        if os.path.exists(output_path):
            log("Output already exists, marking complete")
            ffmpeg_progress['completed'].append(video['path'])
            save_json(FFMPEG_PROGRESS_FILE, ffmpeg_progress)
            continue

        # Get video dimensions
        width, height = get_video_info(video['path'])
        log(f"Dimensions: {width}x{height}")

        # Compress
        log("Starting FFmpeg compression...")
        start_time = time.time()

        success, error = compress_video(video['path'], output_path, width, height)

        elapsed = time.time() - start_time

        if success and os.path.exists(output_path):
            output_size = os.path.getsize(output_path) / (1024**3)
            input_size = video['size_bytes'] / (1024**3)
            reduction = (1 - output_size/input_size) * 100 if input_size > 0 else 0

            log(f"COMPLETE in {elapsed/60:.1f} min")
            log(f"Size: {input_size:.2f} GB -> {output_size:.2f} GB ({reduction:.1f}% reduction)")

            ffmpeg_progress['completed'].append(video['path'])
            total_processed += 1
        else:
            log(f"FAILED: {error[:200] if error else 'Unknown error'}")
            ffmpeg_progress['failed'].append(video['path'])
            total_failed += 1

            # Clean up partial output
            if os.path.exists(output_path):
                os.remove(output_path)

        save_json(FFMPEG_PROGRESS_FILE, ffmpeg_progress)

        # Brief pause
        time.sleep(1)

    log(f"\n{'='*60}")
    log("BATCH COMPLETE")
    log(f"Processed: {total_processed}")
    log(f"Failed: {total_failed}")
    log("=" * 60)

if __name__ == "__main__":
    main()
