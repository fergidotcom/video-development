#!/usr/bin/env python3
"""
Compressor Parallel Batch Processing Script
============================================
Submits multiple videos to Compressor in parallel for faster throughput.

Usage:
    open /Applications/Compressor.app
    cd ~/Library/CloudStorage/Dropbox/Fergi/VideoDev
    nohup python3 compressor_parallel.py > logs/$(date +%Y%m%d_%H%M%S)_parallel.log 2>&1 &

Optimized for M2 Mac with 2 concurrent encoding jobs.
"""

import os
import sys
import csv
import time
import json
import subprocess
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Configuration
PEGASUS_ROOT = "/Volumes/Promise Pegasus"
OUTPUT_DIR = f"{PEGASUS_ROOT}/_compressor_output"
CSV_FILE = "logs/20251205_001737_high_res_videos.csv"
PROGRESS_FILE = "logs/compressor_cli_progress.json"

COMPRESSOR_PATH = "/Applications/Compressor.app/Contents/MacOS/Compressor"
PRESET_PATH = "/Applications/Compressor.app/Contents/Resources/Settings/Website Sharing/HD1080WebShareName.compressorsetting"

# Parallel settings - M2 processes one encode at a time
MAX_PARALLEL_JOBS = 2
POLL_INTERVAL_SEC = 5
JOB_TIMEOUT_MIN = 300  # 5 hours - large 60-90GB files can take 2-3 hours

# Thread-safe progress tracking
progress_lock = threading.Lock()

def log(msg):
    """Print timestamped log message (thread-safe)."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

def is_compressor_running():
    """Check if Compressor app is running."""
    result = subprocess.run(["pgrep", "-x", "Compressor"], capture_output=True)
    return result.returncode == 0

def submit_job(input_path, output_path):
    """Submit a single job to Compressor via CLI."""
    cmd = [
        COMPRESSOR_PATH,
        "-batchname", f"Parallel_{os.path.basename(input_path)[:20]}",
        "-jobpath", input_path,
        "-settingpath", PRESET_PATH,
        "-locationpath", output_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stderr + result.stdout

        # Check for errors that mean job won't process
        if "Errors:" in output or "Error:" in output:
            return (False, output.strip())

        return (True, None)
    except Exception as e:
        return (False, str(e))

def wait_for_output(output_path, timeout_min=JOB_TIMEOUT_MIN):
    """Wait for output file to appear and stabilize."""
    start = time.time()
    timeout_sec = timeout_min * 60

    while time.time() - start < timeout_sec:
        if os.path.exists(output_path):
            size1 = os.path.getsize(output_path)
            time.sleep(3)
            if os.path.exists(output_path):
                size2 = os.path.getsize(output_path)
                if size1 == size2 and size1 > 0:
                    return True
        time.sleep(POLL_INTERVAL_SEC)

    return False

def process_video(video, output_dir, progress):
    """Process a single video - submit and wait for completion."""
    input_path = video['path']
    filename = video['filename']
    size_mb = video['size_bytes'] / (1024 * 1024)

    # Generate output path
    path_parts = input_path.replace(PEGASUS_ROOT + '/', '').split('/')
    subdir = path_parts[0] if len(path_parts) > 1 else "misc"
    base, ext = os.path.splitext(filename)
    output_path = os.path.join(output_dir, subdir, f"{base}_1080p.mov")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    log(f"START: {filename} ({size_mb/1024:.1f}GB)")

    # Skip if output exists
    if os.path.exists(output_path):
        log(f"SKIP (exists): {filename}")
        with progress_lock:
            progress['completed'].append(input_path)
        return ('skipped', input_path, 0)

    # Skip if source gone
    if not os.path.exists(input_path):
        log(f"SKIP (missing): {filename}")
        with progress_lock:
            progress['skipped'].append(input_path)
        return ('missing', input_path, 0)

    # Submit job
    start_time = time.time()
    success, error = submit_job(input_path, output_path)

    if not success:
        log(f"REJECTED: {filename} - {error}")
        with progress_lock:
            progress['failed'].append(input_path)
        return ('failed', input_path, 0)

    # Wait for completion
    if wait_for_output(output_path):
        elapsed = time.time() - start_time
        if os.path.exists(output_path):
            output_size = os.path.getsize(output_path) / (1024**2)
            savings = (1 - output_size/size_mb) * 100 if size_mb > 0 else 0
            log(f"DONE: {filename} in {elapsed/60:.1f}min ({savings:.0f}% smaller)")
        else:
            log(f"DONE: {filename} in {elapsed/60:.1f}min")

        with progress_lock:
            progress['completed'].append(input_path)
        return ('completed', input_path, elapsed)
    else:
        log(f"TIMEOUT: {filename}")
        with progress_lock:
            progress['failed'].append(input_path)
        return ('timeout', input_path, 0)

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
    """Save progress tracking file (thread-safe)."""
    with progress_lock:
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
                    'duration_sec': float(row.get('duration_sec', 0))
                })
    except Exception as e:
        log(f"ERROR loading CSV: {e}")
    return videos

def get_unique_videos(videos):
    """Return only unique videos (dedupe by filename+size, case-insensitive)."""
    seen = {}
    unique = []
    for v in videos:
        # Case-insensitive filename for deduplication
        key = (v['filename'].lower(), v['size_bytes'])
        if key not in seen:
            seen[key] = v['path']
            unique.append(v)
    return unique

def main():
    log("=" * 60)
    log("COMPRESSOR PARALLEL BATCH PROCESSOR")
    log(f"Running {MAX_PARALLEL_JOBS} jobs in parallel")
    log("=" * 60)

    # Check prerequisites
    if not os.path.exists(PEGASUS_ROOT):
        log(f"ERROR: Pegasus drive not mounted")
        sys.exit(1)

    if not is_compressor_running():
        log("Starting Compressor...")
        subprocess.run(["open", "/Applications/Compressor.app"])
        time.sleep(5)

    log("Compressor is running")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Load videos
    all_videos = load_video_list()
    videos = get_unique_videos(all_videos)
    log(f"Total unique videos: {len(videos)}")

    # Load progress and filter
    progress = load_progress()
    already_done = set(progress['completed']) | set(progress.get('failed', [])) | set(progress.get('skipped', []))
    remaining = [v for v in videos if v['path'] not in already_done]

    log(f"Already done: {len(progress['completed'])} completed, {len(progress.get('failed', []))} failed")
    log(f"Remaining: {len(remaining)}")

    if not remaining:
        log("All videos processed!")
        return

    # Sort by size (largest first for better parallelism)
    remaining.sort(key=lambda x: x['size_bytes'], reverse=True)

    # Process in parallel
    completed = 0
    failed = 0
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_JOBS) as executor:
        futures = {}

        for video in remaining:
            future = executor.submit(process_video, video, OUTPUT_DIR, progress)
            futures[future] = video['filename']

        for future in as_completed(futures):
            filename = futures[future]
            try:
                status, path, elapsed = future.result()
                if status == 'completed':
                    completed += 1
                elif status in ('failed', 'timeout'):
                    failed += 1

                # Save progress after each completion
                save_progress(progress)

                # Status update
                done = completed + failed
                total = len(remaining)
                elapsed_total = (time.time() - start_time) / 60
                log(f"Progress: {done}/{total} ({completed} ok, {failed} failed) - {elapsed_total:.0f}min elapsed")

            except Exception as e:
                log(f"ERROR processing {filename}: {e}")
                failed += 1

    # Final summary
    total_time = (time.time() - start_time) / 60
    log("=" * 60)
    log("BATCH COMPLETE")
    log(f"Completed: {completed}")
    log(f"Failed: {failed}")
    log(f"Total time: {total_time:.1f} minutes")
    log("=" * 60)

if __name__ == "__main__":
    main()
