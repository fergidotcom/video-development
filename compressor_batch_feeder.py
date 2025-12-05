#!/usr/bin/env python3
"""
Compressor Batch Feeder Script
==============================
Feeds videos to Compressor watch folder in controlled batches.

Usage:
    nohup python3 compressor_batch_feeder.py > logs/$(date +%Y%m%d_%H%M%S)_compressor_batch.log 2>&1 &

Requirements:
    - Compressor app must be open with watch folder configured
    - Watch folder at: /Volumes/Promise Pegasus/_watch_input
    - Output folder at: /Volumes/Promise Pegasus/_watch_output
"""

import os
import sys
import csv
import time
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

# Configuration
PEGASUS_ROOT = "/Volumes/Promise Pegasus"
WATCH_INPUT = f"{PEGASUS_ROOT}/_watch_input"
WATCH_OUTPUT = f"{PEGASUS_ROOT}/_watch_output"
CSV_FILE = "logs/20251205_001737_high_res_videos.csv"
PROGRESS_FILE = "logs/compressor_progress.json"

# Batch settings
BATCH_SIZE_GB = 50  # Max GB to queue at once
MAX_CONCURRENT_FILES = 5  # Max files in watch folder at once
CHECK_INTERVAL_SEC = 60  # How often to check for completion
MIN_FREE_SPACE_GB = 500  # Minimum free space before pausing

def log(msg):
    """Print timestamped log message."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

def get_free_space_gb(path):
    """Get free space in GB for the given path."""
    try:
        stat = os.statvfs(path)
        return (stat.f_frsize * stat.f_bavail) / (1024**3)
    except:
        return 0

def is_compressor_running():
    """Check if Compressor app is running."""
    result = subprocess.run(
        ["pgrep", "-f", "Compressor.app"],
        capture_output=True
    )
    return result.returncode == 0

def get_watch_folder_files():
    """Get list of files currently in watch input folder."""
    if not os.path.exists(WATCH_INPUT):
        return []
    return [f for f in os.listdir(WATCH_INPUT)
            if f.endswith(('.mp4', '.MP4', '.mov', '.MOV', '.m4v'))]

def get_output_files():
    """Get list of files in output folder."""
    if not os.path.exists(WATCH_OUTPUT):
        return []
    return [f for f in os.listdir(WATCH_OUTPUT)
            if f.endswith(('.mp4', '.MP4', '.mov', '.MOV', '.m4v'))]

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
                    'resolution': row['resolution']
                })
    except Exception as e:
        log(f"ERROR loading CSV: {e}")
    return videos

def load_progress():
    """Load progress tracking file."""
    import json
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'processed': [], 'skipped': [], 'failed': []}

def save_progress(progress):
    """Save progress tracking file."""
    import json
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)

def copy_to_watch_folder(video):
    """Copy a video file to the watch folder."""
    src = video['path']
    filename = video['filename']
    dst = os.path.join(WATCH_INPUT, filename)

    # Handle duplicate filenames by adding hash
    if os.path.exists(dst):
        base, ext = os.path.splitext(filename)
        # Use part of path hash to make unique
        path_hash = str(abs(hash(src)))[:6]
        filename = f"{base}_{path_hash}{ext}"
        dst = os.path.join(WATCH_INPUT, filename)

    try:
        log(f"Copying: {src} -> {dst}")
        shutil.copy2(src, dst)
        return filename
    except Exception as e:
        log(f"ERROR copying {src}: {e}")
        return None

def wait_for_processing(expected_files, timeout_hours=4):
    """Wait for files to be processed by Compressor."""
    start_time = time.time()
    timeout_sec = timeout_hours * 3600

    while time.time() - start_time < timeout_sec:
        # Check what's still in input folder
        remaining = get_watch_folder_files()
        processed_count = len(expected_files) - len([f for f in expected_files if f in remaining])

        if len(remaining) == 0 or not any(f in remaining for f in expected_files):
            log(f"Batch complete! {processed_count} files processed.")
            return True

        log(f"Waiting... {len(remaining)} files still processing")

        # Check if Compressor is still running
        if not is_compressor_running():
            log("WARNING: Compressor not running! Waiting for restart...")

        time.sleep(CHECK_INTERVAL_SEC)

    log(f"TIMEOUT waiting for batch after {timeout_hours} hours")
    return False

def filter_duplicates(videos):
    """Remove duplicate files (same name+size in different locations)."""
    seen = {}
    unique = []
    duplicates = []

    for v in videos:
        key = (v['filename'], v['size_bytes'])
        if key not in seen:
            seen[key] = v['path']
            unique.append(v)
        else:
            duplicates.append(v)

    log(f"Found {len(unique)} unique videos, {len(duplicates)} duplicates (same name+size)")
    return unique, duplicates

def main():
    log("=" * 60)
    log("COMPRESSOR BATCH FEEDER STARTING")
    log("=" * 60)

    # Verify prerequisites
    if not os.path.exists(PEGASUS_ROOT):
        log(f"ERROR: Pegasus drive not mounted at {PEGASUS_ROOT}")
        sys.exit(1)

    if not os.path.exists(WATCH_INPUT):
        log(f"Creating watch input folder: {WATCH_INPUT}")
        os.makedirs(WATCH_INPUT)

    if not os.path.exists(WATCH_OUTPUT):
        log(f"Creating watch output folder: {WATCH_OUTPUT}")
        os.makedirs(WATCH_OUTPUT)

    # Check Compressor
    if not is_compressor_running():
        log("WARNING: Compressor is not running!")
        log("Please open Compressor and configure watch folder, then restart this script.")
        sys.exit(1)

    # Load video list
    log(f"Loading video list from {CSV_FILE}")
    all_videos = load_video_list()
    log(f"Found {len(all_videos)} videos in CSV")

    # Filter duplicates
    videos, duplicates = filter_duplicates(all_videos)

    # Load progress
    progress = load_progress()
    processed_paths = set(progress['processed'])

    # Filter already processed
    remaining = [v for v in videos if v['path'] not in processed_paths]
    log(f"Remaining to process: {len(remaining)} videos")

    if len(remaining) == 0:
        log("All videos have been processed!")
        return

    # Sort by size (smallest first for quick wins)
    remaining.sort(key=lambda x: x['size_bytes'])

    # Process in batches
    batch_num = 0
    total_processed = 0

    while remaining:
        batch_num += 1
        log(f"\n{'='*60}")
        log(f"BATCH {batch_num}")
        log(f"{'='*60}")

        # Check free space
        free_gb = get_free_space_gb(PEGASUS_ROOT)
        log(f"Free space: {free_gb:.1f} GB")

        if free_gb < MIN_FREE_SPACE_GB:
            log(f"WARNING: Low disk space ({free_gb:.1f} GB < {MIN_FREE_SPACE_GB} GB)")
            log("Pausing until space is freed. Delete verified originals to continue.")
            while get_free_space_gb(PEGASUS_ROOT) < MIN_FREE_SPACE_GB:
                time.sleep(300)  # Check every 5 minutes

        # Select batch (up to BATCH_SIZE_GB or MAX_CONCURRENT_FILES)
        batch = []
        batch_size = 0

        for v in remaining[:]:
            if len(batch) >= MAX_CONCURRENT_FILES:
                break
            if batch_size + v['size_bytes'] > BATCH_SIZE_GB * (1024**3):
                if len(batch) > 0:  # Already have some files
                    break
            batch.append(v)
            batch_size += v['size_bytes']
            remaining.remove(v)

        log(f"Batch size: {len(batch)} files, {batch_size/(1024**3):.2f} GB")

        # Copy files to watch folder
        batch_files = []
        for v in batch:
            copied_name = copy_to_watch_folder(v)
            if copied_name:
                batch_files.append(copied_name)
                progress['processed'].append(v['path'])

        save_progress(progress)

        # Wait for Compressor to process
        if batch_files:
            log(f"Waiting for Compressor to process {len(batch_files)} files...")
            success = wait_for_processing(batch_files)

            if success:
                total_processed += len(batch_files)
                log(f"Total processed so far: {total_processed}")
            else:
                log("Batch did not complete in time. Check Compressor status.")
                # Put failed files back for retry
                for v in batch:
                    if v['path'] in progress['processed']:
                        progress['processed'].remove(v['path'])
                        progress['failed'].append(v['path'])
                save_progress(progress)

        # Small delay between batches
        time.sleep(10)

    log(f"\n{'='*60}")
    log(f"ALL BATCHES COMPLETE")
    log(f"Total processed: {total_processed}")
    log(f"{'='*60}")

if __name__ == "__main__":
    main()
