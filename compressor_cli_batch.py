#!/usr/bin/env python3
"""
Compressor CLI Batch Processing Script
=======================================
Submits videos to Compressor via command line for batch processing.

Usage:
    # First, open Compressor:
    open /Applications/Compressor.app

    # Then run this script:
    cd ~/Library/CloudStorage/Dropbox/Fergi/VideoDev
    nohup python3 compressor_cli_batch.py > logs/$(date +%Y%m%d_%H%M%S)_compressor_batch.log 2>&1 &

Tested: December 5, 2025 - 754MB file in 1m40s with M2 hardware acceleration
"""

import os
import sys
import csv
import time
import json
import subprocess
from pathlib import Path
from datetime import datetime

# Configuration
PEGASUS_ROOT = "/Volumes/Promise Pegasus"
OUTPUT_DIR = f"{PEGASUS_ROOT}/_compressor_output"
CSV_FILE = "logs/20251205_001737_high_res_videos.csv"
PROGRESS_FILE = "logs/compressor_cli_progress.json"

COMPRESSOR_PATH = "/Applications/Compressor.app/Contents/MacOS/Compressor"
PRESET_PATH = "/Applications/Compressor.app/Contents/Resources/Settings/Website Sharing/HD1080WebShareName.compressorsetting"

# Batch settings
MAX_CONCURRENT_JOBS = 3  # Compressor can handle multiple jobs
POLL_INTERVAL_SEC = 10   # How often to check for completion (reduced from 30)
JOB_TIMEOUT_MIN = 180    # Max time per job (3 hours for huge files)
MIN_FILE_SIZE_MB = 1     # Skip files smaller than this (likely not real videos)

def log(msg):
    """Print timestamped log message."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

def is_compressor_running():
    """Check if Compressor app is running."""
    result = subprocess.run(
        ["pgrep", "-f", "Compressor.app"],
        capture_output=True
    )
    return result.returncode == 0

def get_active_jobs():
    """Get count of active Compressor jobs by checking TranscoderService CPU usage."""
    result = subprocess.run(
        ["ps", "aux"],
        capture_output=True,
        text=True
    )
    # Count TranscoderService processes with >5% CPU (actively encoding)
    active = 0
    for line in result.stdout.split('\n'):
        if 'TranscoderService' in line:
            parts = line.split()
            if len(parts) > 2:
                try:
                    cpu = float(parts[2])
                    if cpu > 5:
                        active += 1
                except:
                    pass
    return active

def submit_job(input_path, output_path):
    """Submit a single job to Compressor via CLI."""
    cmd = [
        COMPRESSOR_PATH,
        "-batchname", "AutoBatch",
        "-jobpath", input_path,
        "-settingpath", PRESET_PATH,
        "-locationpath", output_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if "jobID" in result.stderr or "jobID" in result.stdout:
            return True
        log(f"Job submission output: {result.stderr}")
        return True  # Assume success if no error
    except Exception as e:
        log(f"ERROR submitting job: {e}")
        return False

def wait_for_output(output_path, input_size_mb, timeout_min=JOB_TIMEOUT_MIN):
    """Wait for output file to appear and be complete.

    Uses dynamic timeout based on input file size:
    - Files < 100MB: 5 min timeout (should complete in seconds)
    - Files 100MB-1GB: 30 min timeout
    - Files > 1GB: full timeout (180 min)
    """
    start = time.time()

    # Dynamic timeout based on input size
    if input_size_mb < 100:
        timeout_sec = 5 * 60  # 5 minutes for small files
    elif input_size_mb < 1024:
        timeout_sec = 30 * 60  # 30 minutes for medium files
    else:
        timeout_sec = timeout_min * 60  # Full timeout for large files

    log(f"Timeout set to {timeout_sec/60:.0f} min for {input_size_mb:.0f}MB file")

    while time.time() - start < timeout_sec:
        if os.path.exists(output_path):
            # Check if file is still being written (size changing)
            size1 = os.path.getsize(output_path)
            time.sleep(5)
            if os.path.exists(output_path):
                size2 = os.path.getsize(output_path)
                if size1 == size2 and size1 > 0:
                    return True
        time.sleep(POLL_INTERVAL_SEC)

    return False

def load_progress():
    """Load progress tracking file."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'completed': [], 'failed': [], 'skipped': []}

def save_progress(progress):
    """Save progress tracking file."""
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)

def load_video_list():
    """Load list of videos to process from CSV."""
    videos = []
    try:
        with open(CSV_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                videos.append({
                    'path': row['path'],
                    'filename': row['filename'],
                    'size_bytes': int(row['size_bytes']),
                    'size_human': row['size_human'],
                    'resolution': row['resolution'],
                    'duration_sec': float(row.get('duration_sec', 0))
                })
    except Exception as e:
        log(f"ERROR loading CSV: {e}")
    return videos

def get_unique_videos(videos):
    """Return only unique videos (dedupe by filename+size)."""
    seen = {}
    unique = []

    for v in videos:
        key = (v['filename'], v['size_bytes'])
        if key not in seen:
            seen[key] = v['path']
            unique.append(v)

    return unique

def generate_output_path(video, output_dir):
    """Generate output path preserving some directory structure."""
    # Extract meaningful subdirectory from path
    path_parts = video['path'].replace(PEGASUS_ROOT + '/', '').split('/')

    # Use first directory level for organization
    if len(path_parts) > 1:
        subdir = path_parts[0]
    else:
        subdir = "misc"

    # Clean filename and add _1080p suffix
    base, ext = os.path.splitext(video['filename'])
    output_filename = f"{base}_1080p.mov"

    # Create subdirectory
    full_output_dir = os.path.join(output_dir, subdir)
    os.makedirs(full_output_dir, exist_ok=True)

    return os.path.join(full_output_dir, output_filename)

def main():
    log("=" * 60)
    log("COMPRESSOR CLI BATCH PROCESSOR")
    log("=" * 60)

    # Check prerequisites
    if not os.path.exists(PEGASUS_ROOT):
        log(f"ERROR: Pegasus drive not mounted at {PEGASUS_ROOT}")
        sys.exit(1)

    if not is_compressor_running():
        log("Starting Compressor...")
        subprocess.run(["open", "/Applications/Compressor.app"])
        time.sleep(5)

        if not is_compressor_running():
            log("ERROR: Could not start Compressor")
            sys.exit(1)

    log("Compressor is running")

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    log(f"Output directory: {OUTPUT_DIR}")

    # Load videos
    log(f"Loading video list from {CSV_FILE}")
    all_videos = load_video_list()
    log(f"Total videos in CSV: {len(all_videos)}")

    # Get unique videos only
    videos = get_unique_videos(all_videos)
    log(f"Unique videos: {len(videos)}")

    # Load progress
    progress = load_progress()
    completed_paths = set(progress['completed'])

    # Filter already processed
    remaining = [v for v in videos if v['path'] not in completed_paths]
    log(f"Remaining to process: {len(remaining)}")

    if not remaining:
        log("All videos have been processed!")
        return

    # Sort by size (smallest first for quick wins)
    remaining.sort(key=lambda x: x['size_bytes'])

    # Process videos
    total_processed = 0
    total_failed = 0

    for i, video in enumerate(remaining):
        log(f"\n{'='*60}")
        log(f"VIDEO {i+1}/{len(remaining)}: {video['filename']}")
        log(f"Size: {video['size_human']} | Duration: {video['duration_sec']:.0f}s")
        log(f"Path: {video['path']}")

        # Generate output path
        output_path = generate_output_path(video, OUTPUT_DIR)
        log(f"Output: {output_path}")

        # Skip if output already exists
        if os.path.exists(output_path):
            log("Output already exists, skipping")
            progress['completed'].append(video['path'])
            save_progress(progress)
            continue

        # Skip if source file no longer exists
        if not os.path.exists(video['path']):
            log(f"SKIPPING: Source file no longer exists")
            progress['skipped'].append(video['path'])
            save_progress(progress)
            continue

        # Skip files that are too small (likely not real videos)
        size_mb = video['size_bytes'] / (1024 * 1024)
        if size_mb < MIN_FILE_SIZE_MB:
            log(f"SKIPPING: File too small ({size_mb:.2f}MB < {MIN_FILE_SIZE_MB}MB minimum)")
            progress['skipped'].append(video['path'])
            save_progress(progress)
            continue

        # Submit job
        log("Submitting to Compressor...")
        start_time = time.time()

        if submit_job(video['path'], output_path):
            # Wait for completion
            log("Waiting for completion...")

            if wait_for_output(output_path, size_mb):
                elapsed = time.time() - start_time
                output_size = os.path.getsize(output_path) / (1024**2)
                input_size = video['size_bytes'] / (1024**2)
                savings = (1 - output_size/input_size) * 100

                log(f"COMPLETE in {elapsed/60:.1f} min")
                log(f"Size: {input_size:.1f}MB -> {output_size:.1f}MB ({savings:.1f}% reduction)")

                progress['completed'].append(video['path'])
                total_processed += 1
            else:
                log(f"TIMEOUT waiting for output")
                progress['failed'].append(video['path'])
                total_failed += 1
        else:
            log("Failed to submit job")
            progress['failed'].append(video['path'])
            total_failed += 1

        save_progress(progress)

        # Brief pause between jobs
        time.sleep(2)

    log(f"\n{'='*60}")
    log("BATCH COMPLETE")
    log(f"Processed: {total_processed}")
    log(f"Failed: {total_failed}")
    log(f"{'='*60}")

if __name__ == "__main__":
    main()
