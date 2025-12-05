#!/usr/bin/env python3
"""
Survey Pegasus drive for videos >1080p resolution.
Generates report of files that would benefit from compression.
"""

import os
import subprocess
import json
import csv
from pathlib import Path
from datetime import datetime
import sys

# Configuration
PEGASUS_PATH = "/Volumes/Promise Pegasus"
OUTPUT_DIR = "/Users/joeferguson/Library/CloudStorage/Dropbox/Fergi/VideoDev/logs"
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.m4v', '.wmv', '.flv', '.webm', '.mpeg', '.mpg', '.3gp', '.mts', '.m2ts'}

# Resolution threshold (anything larger than 1080p)
MAX_WIDTH = 1920
MAX_HEIGHT = 1080

def get_video_info(filepath):
    """Get video resolution and size using ffprobe."""
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            '-select_streams', 'v:0',
            filepath
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)
        if not data.get('streams'):
            return None

        stream = data['streams'][0]
        return {
            'width': stream.get('width', 0),
            'height': stream.get('height', 0),
            'codec': stream.get('codec_name', 'unknown'),
            'duration': float(stream.get('duration', 0)) if stream.get('duration') else 0
        }
    except Exception as e:
        return None

def estimate_compressed_size(original_size, original_res, target_res=(1920, 1080)):
    """Estimate compressed file size based on resolution reduction and H.265 efficiency."""
    orig_pixels = original_res[0] * original_res[1]
    target_pixels = target_res[0] * target_res[1]

    # Resolution reduction factor
    res_factor = target_pixels / orig_pixels if orig_pixels > 0 else 1

    # H.265 compression factor (typically 30-50% smaller than H.264)
    codec_factor = 0.5

    # Combined estimate
    estimated_size = original_size * res_factor * codec_factor
    return int(estimated_size)

def format_size(bytes_size):
    """Format bytes to human readable."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"

def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Output files
    csv_path = os.path.join(OUTPUT_DIR, f"{timestamp}_high_res_videos.csv")
    report_path = os.path.join(OUTPUT_DIR, f"{timestamp}_compression_report.md")
    progress_path = os.path.join(OUTPUT_DIR, f"{timestamp}_survey_progress.log")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Starting survey of {PEGASUS_PATH}")
    print(f"Looking for videos larger than {MAX_WIDTH}x{MAX_HEIGHT}")
    print(f"Progress log: {progress_path}")
    print()

    # Statistics
    total_files = 0
    video_files = 0
    high_res_files = 0
    total_high_res_size = 0
    total_estimated_compressed = 0
    errors = 0

    high_res_videos = []

    # Walk the drive
    with open(progress_path, 'w') as progress:
        progress.write(f"Survey started: {datetime.now()}\n")
        progress.write(f"Target: {PEGASUS_PATH}\n")
        progress.write(f"Threshold: >{MAX_WIDTH}x{MAX_HEIGHT}\n\n")

        for root, dirs, files in os.walk(PEGASUS_PATH):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]

            for filename in files:
                total_files += 1

                # Progress update every 1000 files
                if total_files % 1000 == 0:
                    msg = f"Scanned {total_files:,} files, found {video_files:,} videos, {high_res_files:,} high-res"
                    print(msg)
                    progress.write(f"{datetime.now()}: {msg}\n")
                    progress.flush()

                # Check if video file
                ext = os.path.splitext(filename)[1].lower()
                if ext not in VIDEO_EXTENSIONS:
                    continue

                video_files += 1
                filepath = os.path.join(root, filename)

                # Get file size
                try:
                    file_size = os.path.getsize(filepath)
                except:
                    errors += 1
                    continue

                # Get video info
                info = get_video_info(filepath)
                if not info:
                    errors += 1
                    continue

                width = info['width']
                height = info['height']

                # Check if >1080p
                if width > MAX_WIDTH or height > MAX_HEIGHT:
                    high_res_files += 1
                    total_high_res_size += file_size

                    # Estimate compressed size
                    estimated = estimate_compressed_size(file_size, (width, height))
                    total_estimated_compressed += estimated
                    savings = file_size - estimated

                    video_data = {
                        'path': filepath,
                        'filename': filename,
                        'width': width,
                        'height': height,
                        'resolution': f"{width}x{height}",
                        'codec': info['codec'],
                        'duration_sec': info['duration'],
                        'size_bytes': file_size,
                        'size_human': format_size(file_size),
                        'estimated_compressed': estimated,
                        'estimated_savings': savings,
                        'savings_percent': (savings / file_size * 100) if file_size > 0 else 0
                    }
                    high_res_videos.append(video_data)

                    # Log significant files (>1GB)
                    if file_size > 1_000_000_000:
                        progress.write(f"FOUND: {filename} - {video_data['resolution']} - {video_data['size_human']}\n")
                        progress.flush()

        progress.write(f"\nSurvey completed: {datetime.now()}\n")

    # Sort by size (largest first)
    high_res_videos.sort(key=lambda x: x['size_bytes'], reverse=True)

    # Write CSV
    print(f"\nWriting CSV: {csv_path}")
    with open(csv_path, 'w', newline='') as f:
        if high_res_videos:
            writer = csv.DictWriter(f, fieldnames=high_res_videos[0].keys())
            writer.writeheader()
            writer.writerows(high_res_videos)

    # Calculate totals
    total_savings = total_high_res_size - total_estimated_compressed

    # Write report
    print(f"Writing report: {report_path}")
    with open(report_path, 'w') as f:
        f.write("# Pegasus Drive - High Resolution Video Survey\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")

        f.write("## Executive Summary\n\n")
        f.write(f"| Metric | Value |\n")
        f.write(f"|--------|-------|\n")
        f.write(f"| **Total Files Scanned** | {total_files:,} |\n")
        f.write(f"| **Video Files Found** | {video_files:,} |\n")
        f.write(f"| **Videos >1080p** | {high_res_files:,} |\n")
        f.write(f"| **Total Size (>1080p)** | {format_size(total_high_res_size)} |\n")
        f.write(f"| **Est. Compressed Size** | {format_size(total_estimated_compressed)} |\n")
        f.write(f"| **Est. Space Savings** | **{format_size(total_savings)}** |\n")
        f.write(f"| **Errors/Skipped** | {errors:,} |\n\n")

        f.write("---\n\n")

        f.write("## Resolution Distribution\n\n")
        # Group by resolution
        res_groups = {}
        for v in high_res_videos:
            res = v['resolution']
            if res not in res_groups:
                res_groups[res] = {'count': 0, 'size': 0, 'savings': 0}
            res_groups[res]['count'] += 1
            res_groups[res]['size'] += v['size_bytes']
            res_groups[res]['savings'] += v['estimated_savings']

        f.write("| Resolution | Count | Total Size | Est. Savings |\n")
        f.write("|------------|-------|------------|-------------|\n")
        for res in sorted(res_groups.keys(), key=lambda x: res_groups[x]['size'], reverse=True):
            g = res_groups[res]
            f.write(f"| {res} | {g['count']:,} | {format_size(g['size'])} | {format_size(g['savings'])} |\n")
        f.write("\n")

        f.write("---\n\n")

        f.write("## Top 50 Largest High-Res Videos\n\n")
        f.write("| # | Resolution | Size | Est. Savings | Filename |\n")
        f.write("|---|------------|------|--------------|----------|\n")
        for i, v in enumerate(high_res_videos[:50], 1):
            # Truncate filename for readability
            fname = v['filename']
            if len(fname) > 40:
                fname = fname[:37] + "..."
            f.write(f"| {i} | {v['resolution']} | {v['size_human']} | {format_size(v['estimated_savings'])} | {fname} |\n")
        f.write("\n")

        f.write("---\n\n")

        f.write("## Directory Distribution\n\n")
        # Group by top-level directory
        dir_groups = {}
        for v in high_res_videos:
            rel_path = v['path'].replace(PEGASUS_PATH + '/', '')
            top_dir = rel_path.split('/')[0] if '/' in rel_path else 'root'
            if top_dir not in dir_groups:
                dir_groups[top_dir] = {'count': 0, 'size': 0, 'savings': 0}
            dir_groups[top_dir]['count'] += 1
            dir_groups[top_dir]['size'] += v['size_bytes']
            dir_groups[top_dir]['savings'] += v['estimated_savings']

        f.write("| Directory | Video Count | Total Size | Est. Savings |\n")
        f.write("|-----------|-------------|------------|-------------|\n")
        for d in sorted(dir_groups.keys(), key=lambda x: dir_groups[x]['size'], reverse=True):
            g = dir_groups[d]
            f.write(f"| {d[:40]} | {g['count']:,} | {format_size(g['size'])} | {format_size(g['savings'])} |\n")
        f.write("\n")

        f.write("---\n\n")

        f.write("## Compression Methodology\n\n")
        f.write("**Target Resolution:** 1920x1080 (1080p)\n\n")
        f.write("**Estimated Command:**\n")
        f.write("```bash\n")
        f.write('ffmpeg -i input.mp4 -vf "scale=1920:-2" -c:v libx265 -crf 23 -c:a copy output_1080p.mp4\n')
        f.write("```\n\n")
        f.write("**Savings Estimate Methodology:**\n")
        f.write("- Resolution reduction (pixel count ratio)\n")
        f.write("- H.265 codec efficiency (~50% smaller than source)\n")
        f.write("- Conservative estimates (actual may be better)\n\n")

        f.write("---\n\n")

        f.write("## Full Video List\n\n")
        f.write(f"Complete list saved to: `{csv_path}`\n\n")
        f.write(f"**Total: {high_res_files:,} videos**\n")

    # Print summary
    print("\n" + "="*60)
    print("SURVEY COMPLETE")
    print("="*60)
    print(f"Total files scanned:     {total_files:,}")
    print(f"Video files found:       {video_files:,}")
    print(f"Videos >1080p:           {high_res_files:,}")
    print(f"Total size (>1080p):     {format_size(total_high_res_size)}")
    print(f"Estimated compressed:    {format_size(total_estimated_compressed)}")
    print(f"Estimated savings:       {format_size(total_savings)}")
    print("="*60)
    print(f"\nReport: {report_path}")
    print(f"CSV:    {csv_path}")

if __name__ == "__main__":
    main()
