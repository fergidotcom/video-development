#!/usr/bin/env python3
"""
Compress videos >1080p to 1080p resolution.
Uses H.265 encoding for efficient compression.
Preserves originals until user approves deletion.
"""

import os
import subprocess
import json
import csv
from pathlib import Path
from datetime import datetime
import sys
import signal
import shutil

# Configuration
PEGASUS_PATH = "/Volumes/Promise Pegasus"
OUTPUT_DIR = "/Users/joeferguson/Library/CloudStorage/Dropbox/Fergi/VideoDev/logs"
TEMP_DIR = "/Volumes/Promise Pegasus/_compression_temp"

# Target resolution
TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080

# FFmpeg settings
CRF = 23  # Quality (lower = better quality, larger file. 23 is good default)
PRESET = "medium"  # Speed/quality tradeoff

# Graceful shutdown
shutdown_requested = False

def signal_handler(signum, frame):
    global shutdown_requested
    print("\n⏸️  Shutdown requested, finishing current file...")
    shutdown_requested = True

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def format_size(bytes_size):
    """Format bytes to human readable."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"

def format_duration(seconds):
    """Format seconds to HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def get_video_info(filepath):
    """Get video metadata using ffprobe."""
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            '-show_format',
            filepath
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)

        # Find video stream
        video_stream = None
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'video':
                video_stream = stream
                break

        if not video_stream:
            return None

        return {
            'width': video_stream.get('width', 0),
            'height': video_stream.get('height', 0),
            'codec': video_stream.get('codec_name', 'unknown'),
            'duration': float(data.get('format', {}).get('duration', 0)),
            'bitrate': int(data.get('format', {}).get('bit_rate', 0)),
        }
    except Exception as e:
        return None

def compress_video(input_path, output_path, progress_callback=None):
    """
    Compress video to 1080p using FFmpeg.
    Returns True on success, False on failure.
    """
    try:
        # Create output directory if needed
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # FFmpeg command
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-vf', f'scale={TARGET_WIDTH}:-2',  # Scale to 1080p, maintain aspect ratio
            '-c:v', 'libx265',  # H.265 codec
            '-crf', str(CRF),
            '-preset', PRESET,
            '-c:a', 'aac',  # Re-encode audio to AAC
            '-b:a', '192k',
            '-movflags', '+faststart',  # Optimize for streaming
            '-y',  # Overwrite output
            '-progress', 'pipe:1',  # Progress output
            output_path
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        # Monitor progress
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line.startswith('out_time='):
                if progress_callback:
                    progress_callback(line.strip())

        return process.returncode == 0

    except Exception as e:
        print(f"Error compressing {input_path}: {e}")
        return False

def main():
    global shutdown_requested

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Output files
    log_path = os.path.join(OUTPUT_DIR, f"{timestamp}_compression.log")
    results_path = os.path.join(OUTPUT_DIR, f"{timestamp}_compression_results.json")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)

    # Find the most recent high-res video survey
    csv_files = sorted([f for f in os.listdir(OUTPUT_DIR) if f.endswith('_high_res_videos.csv')], reverse=True)

    if not csv_files:
        print("ERROR: No high-res video survey found!")
        print("Please run survey_high_res_videos.py first.")
        sys.exit(1)

    csv_path = os.path.join(OUTPUT_DIR, csv_files[0])
    print(f"Loading video list from: {csv_path}")

    # Load videos to compress
    videos = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            videos.append({
                'path': row['path'],
                'width': int(row['width']),
                'height': int(row['height']),
                'size': int(row['size_bytes']),
                'duration': float(row.get('duration_sec', 0))
            })

    print(f"Found {len(videos)} videos to compress")
    print(f"Total original size: {format_size(sum(v['size'] for v in videos))}")
    print()

    # Sort by size (largest first)
    videos.sort(key=lambda x: x['size'], reverse=True)

    # Track results
    results = {
        'started': timestamp,
        'videos_processed': 0,
        'videos_failed': 0,
        'original_size': 0,
        'compressed_size': 0,
        'space_saved': 0,
        'files': []
    }

    with open(log_path, 'w') as log:
        log.write(f"Compression started: {datetime.now()}\n")
        log.write(f"Videos to process: {len(videos)}\n\n")

        for i, video in enumerate(videos, 1):
            if shutdown_requested:
                log.write(f"\nShutdown requested after {i-1} videos\n")
                break

            input_path = video['path']
            filename = os.path.basename(input_path)

            # Create output path (same name, in temp dir, with .mp4 extension)
            base_name = os.path.splitext(filename)[0]
            output_path = os.path.join(TEMP_DIR, f"{base_name}_1080p.mp4")

            print(f"\n[{i}/{len(videos)}] Processing: {filename}")
            print(f"  Original: {video['width']}x{video['height']} - {format_size(video['size'])}")

            log.write(f"\n[{i}/{len(videos)}] {filename}\n")
            log.write(f"  Original: {video['width']}x{video['height']} - {format_size(video['size'])}\n")
            log.flush()

            # Compress
            start_time = datetime.now()

            def progress_cb(line):
                # Extract time from progress line
                pass  # Could show progress bar here

            success = compress_video(input_path, output_path, progress_cb)

            elapsed = (datetime.now() - start_time).total_seconds()

            if success and os.path.exists(output_path):
                compressed_size = os.path.getsize(output_path)
                savings = video['size'] - compressed_size
                savings_pct = (savings / video['size'] * 100) if video['size'] > 0 else 0

                results['videos_processed'] += 1
                results['original_size'] += video['size']
                results['compressed_size'] += compressed_size
                results['space_saved'] += savings

                result_info = {
                    'input': input_path,
                    'output': output_path,
                    'original_size': video['size'],
                    'compressed_size': compressed_size,
                    'savings': savings,
                    'savings_pct': savings_pct,
                    'elapsed_sec': elapsed,
                    'status': 'success'
                }
                results['files'].append(result_info)

                print(f"  ✓ Compressed: {format_size(compressed_size)} (saved {format_size(savings)}, {savings_pct:.1f}%)")
                print(f"  Time: {format_duration(elapsed)}")

                log.write(f"  ✓ Compressed: {format_size(compressed_size)} (saved {format_size(savings)}, {savings_pct:.1f}%)\n")
                log.write(f"  Time: {format_duration(elapsed)}\n")
            else:
                results['videos_failed'] += 1
                results['files'].append({
                    'input': input_path,
                    'status': 'failed',
                    'elapsed_sec': elapsed
                })

                print(f"  ✗ FAILED after {format_duration(elapsed)}")
                log.write(f"  ✗ FAILED after {format_duration(elapsed)}\n")

            log.flush()

            # Save intermediate results
            with open(results_path, 'w') as f:
                json.dump(results, f, indent=2)

        # Final summary
        log.write(f"\n\n{'='*60}\n")
        log.write("COMPRESSION COMPLETE\n")
        log.write(f"{'='*60}\n")
        log.write(f"Videos processed: {results['videos_processed']}\n")
        log.write(f"Videos failed: {results['videos_failed']}\n")
        log.write(f"Original size: {format_size(results['original_size'])}\n")
        log.write(f"Compressed size: {format_size(results['compressed_size'])}\n")
        log.write(f"Space saved: {format_size(results['space_saved'])}\n")

    # Print summary
    print("\n" + "="*60)
    print("COMPRESSION COMPLETE")
    print("="*60)
    print(f"Videos processed:   {results['videos_processed']}")
    print(f"Videos failed:      {results['videos_failed']}")
    print(f"Original size:      {format_size(results['original_size'])}")
    print(f"Compressed size:    {format_size(results['compressed_size'])}")
    print(f"Space saved:        {format_size(results['space_saved'])}")
    print("="*60)
    print(f"\nCompressed files in: {TEMP_DIR}")
    print("⚠️  ORIGINAL FILES NOT DELETED")
    print("Review compressed files, then delete originals if satisfactory")

if __name__ == "__main__":
    main()
