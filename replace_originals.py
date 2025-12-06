#!/usr/bin/env python3
"""
Replace Originals with Compressed Versions
===========================================
Verifies compressed files, deletes originals, and moves compressed files
back to original locations with original filenames.

Safety checks:
1. Compressed file must exist and be > 1MB
2. Compressed file must be playable (ffprobe)
3. Size ratio must be reasonable (not too small = corrupt)
4. All operations logged for audit

Usage:
    # Dry run first
    python3 replace_originals.py --dry-run

    # Actually replace
    python3 replace_originals.py --replace

    # Replace only large files (>1GB originals)
    python3 replace_originals.py --replace --min-size-gb 1
"""

import os
import sys
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

# Configuration
PEGASUS_ROOT = "/Volumes/Promise Pegasus"
OUTPUT_DIR = f"{PEGASUS_ROOT}/_compressor_output"
PROGRESS_FILE = "logs/compressor_cli_progress.json"
REPLACE_LOG = "logs/replace_audit.json"

# Safety thresholds
MIN_COMPRESSED_SIZE_MB = 1
MAX_SIZE_RATIO = 0.95  # Compressed must be smaller
MIN_SIZE_RATIO = 0.01  # Not suspiciously small

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

def format_size(bytes_size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"

def verify_video_playable(filepath):
    """Use ffprobe to verify video is playable and get duration."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', filepath],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            duration = float(result.stdout.strip())
            return duration > 1  # At least 1 second
        return False
    except:
        return False

def get_compressed_path(original_path):
    """Generate expected compressed file path from original."""
    path_parts = original_path.replace(PEGASUS_ROOT + '/', '').split('/')
    subdir = path_parts[0] if len(path_parts) > 1 else "misc"

    filename = os.path.basename(original_path)
    base, ext = os.path.splitext(filename)
    output_filename = f"{base}_1080p.mov"

    return os.path.join(OUTPUT_DIR, subdir, output_filename)

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {'completed': [], 'failed': []}

def load_replace_log():
    if os.path.exists(REPLACE_LOG):
        with open(REPLACE_LOG, 'r') as f:
            return json.load(f)
    return {'replaced': [], 'skipped': [], 'failed': []}

def save_replace_log(log_data):
    with open(REPLACE_LOG, 'w') as f:
        json.dump(log_data, f, indent=2)

def verify_and_replace(original_path, dry_run=True):
    """Verify compressed file, delete original, move compressed to original location."""
    result = {
        'original': original_path,
        'status': 'unknown',
        'reason': '',
        'original_size': 0,
        'compressed_size': 0,
        'savings': 0,
        'new_path': ''
    }

    # Check original exists
    if not os.path.exists(original_path):
        result['status'] = 'skipped'
        result['reason'] = 'Original not found'
        return result

    original_size = os.path.getsize(original_path)
    result['original_size'] = original_size

    # Get compressed path
    compressed_path = get_compressed_path(original_path)

    if not os.path.exists(compressed_path):
        result['status'] = 'skipped'
        result['reason'] = 'Compressed not found'
        return result

    compressed_size = os.path.getsize(compressed_path)
    result['compressed_size'] = compressed_size
    result['compressed_path'] = compressed_path

    # Size validation
    if compressed_size < MIN_COMPRESSED_SIZE_MB * 1024 * 1024:
        result['status'] = 'failed'
        result['reason'] = f'Compressed too small ({format_size(compressed_size)})'
        return result

    ratio = compressed_size / original_size if original_size > 0 else 0
    if ratio > MAX_SIZE_RATIO:
        result['status'] = 'skipped'
        result['reason'] = f'Not worth replacing ({ratio:.1%} of original)'
        return result

    if ratio < MIN_SIZE_RATIO:
        result['status'] = 'failed'
        result['reason'] = f'Suspicious ratio ({ratio:.3%}) - likely corrupt'
        return result

    # Playability check
    if not verify_video_playable(compressed_path):
        result['status'] = 'failed'
        result['reason'] = 'Compressed not playable'
        return result

    # Determine new path (original location, keep original extension or use .mov)
    original_dir = os.path.dirname(original_path)
    original_basename = os.path.basename(original_path)
    base, original_ext = os.path.splitext(original_basename)

    # Use .mov extension (what Compressor outputs) but could match original
    new_filename = f"{base}.mov"
    new_path = os.path.join(original_dir, new_filename)
    result['new_path'] = new_path
    result['savings'] = original_size - compressed_size

    if dry_run:
        result['status'] = 'would_replace'
        result['reason'] = f'Would save {format_size(result["savings"])}'
        return result

    # Actually perform the replacement
    try:
        # Delete original
        os.remove(original_path)

        # Move compressed to original location
        shutil.move(compressed_path, new_path)

        result['status'] = 'replaced'
        result['reason'] = f'Saved {format_size(result["savings"])}'
        return result

    except Exception as e:
        result['status'] = 'error'
        result['reason'] = str(e)
        return result

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Show what would happen')
    parser.add_argument('--replace', action='store_true', help='Actually replace files')
    parser.add_argument('--min-size-gb', type=float, default=0, help='Only process originals larger than this')
    parser.add_argument('--limit', type=int, default=0, help='Limit files to process')
    args = parser.parse_args()

    if not args.dry_run and not args.replace:
        print("ERROR: Must specify --dry-run or --replace")
        sys.exit(1)

    if args.replace:
        print("=" * 60)
        print("WARNING: This will DELETE originals and MOVE compressed files!")
        print("=" * 60)
        confirm = input("Type 'REPLACE' to confirm: ")
        if confirm != 'REPLACE':
            print("Aborted.")
            sys.exit(0)

    log("=" * 60)
    log(f"REPLACE ORIGINALS - {'DRY RUN' if args.dry_run else 'LIVE'}")
    log("=" * 60)

    progress = load_progress()
    completed = progress.get('completed', [])
    log(f"Files in progress: {len(completed)}")

    replace_log = load_replace_log()
    already_done = set(r['original'] for r in replace_log.get('replaced', []))

    min_size_bytes = args.min_size_gb * 1024 * 1024 * 1024

    stats = {'would_replace': 0, 'replaced': 0, 'skipped': 0, 'failed': 0, 'total_savings': 0}

    processed = 0
    for original_path in completed:
        if args.limit and processed >= args.limit:
            break

        if original_path in already_done:
            continue

        # Size filter
        if min_size_bytes > 0:
            try:
                if not os.path.exists(original_path):
                    continue
                if os.path.getsize(original_path) < min_size_bytes:
                    continue
            except:
                continue

        processed += 1
        result = verify_and_replace(original_path, dry_run=args.dry_run)

        if result['status'] in ['replaced', 'would_replace']:
            stats['total_savings'] += result.get('savings', 0)
            if result['status'] == 'replaced':
                stats['replaced'] += 1
                replace_log['replaced'].append(result)
            else:
                stats['would_replace'] += 1
            log(f"✓ {os.path.basename(original_path)}: {result['reason']}")
        elif result['status'] == 'failed':
            stats['failed'] += 1
            replace_log['failed'].append(result)
            log(f"✗ {os.path.basename(original_path)}: {result['reason']}")
        else:
            stats['skipped'] += 1

    save_replace_log(replace_log)

    log("")
    log("=" * 60)
    log("SUMMARY")
    log("=" * 60)
    if args.dry_run:
        log(f"Would replace: {stats['would_replace']} files")
    else:
        log(f"Replaced: {stats['replaced']} files")
    log(f"Skipped: {stats['skipped']} files")
    log(f"Failed verification: {stats['failed']} files")
    log(f"Total space savings: {format_size(stats['total_savings'])}")

if __name__ == "__main__":
    main()
