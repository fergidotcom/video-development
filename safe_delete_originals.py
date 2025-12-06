#!/usr/bin/env python3
"""
Safe Original File Deletion Script
===================================
Deletes original video files ONLY after verifying compressed versions are valid.

Safety checks:
1. Compressed file must exist
2. Compressed file must be > 1MB (not a stub/failure)
3. Compressed file must be playable (ffprobe verification)
4. Original path must match progress tracking
5. All deletions logged for audit trail

Usage:
    # Dry run (show what would be deleted, no actual deletion)
    python3 safe_delete_originals.py --dry-run

    # Actually delete (requires confirmation)
    python3 safe_delete_originals.py --delete

    # Delete specific size range (e.g., originals > 5GB)
    python3 safe_delete_originals.py --delete --min-size-gb 5
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path

# Configuration
PEGASUS_ROOT = "/Volumes/Promise Pegasus"
OUTPUT_DIR = f"{PEGASUS_ROOT}/_compressor_output"
PROGRESS_FILE = "logs/compressor_cli_progress.json"
DELETION_LOG = "logs/deletion_audit.json"

# Safety thresholds
MIN_COMPRESSED_SIZE_MB = 1  # Reject outputs smaller than this
MAX_SIZE_RATIO = 0.95  # Compressed must be at least 5% smaller
MIN_SIZE_RATIO = 0.01  # Compressed shouldn't be less than 1% of original (likely corrupt)

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

def verify_video_playable(filepath):
    """Use ffprobe to verify video is playable."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', filepath],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            duration = float(result.stdout.strip())
            return duration > 0
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
    """Load completed files from progress tracking."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {'completed': [], 'failed': []}

def load_deletion_log():
    """Load existing deletion audit log."""
    if os.path.exists(DELETION_LOG):
        with open(DELETION_LOG, 'r') as f:
            return json.load(f)
    return {'deleted': [], 'skipped': [], 'failed_verification': []}

def save_deletion_log(log_data):
    """Save deletion audit log."""
    with open(DELETION_LOG, 'w') as f:
        json.dump(log_data, f, indent=2)

def format_size(bytes_size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"

def verify_and_delete(original_path, dry_run=True, verify_playable=True):
    """Verify compressed file and optionally delete original."""
    result = {
        'original': original_path,
        'status': 'unknown',
        'reason': '',
        'original_size': 0,
        'compressed_size': 0,
        'savings': 0
    }

    # Check original exists
    if not os.path.exists(original_path):
        result['status'] = 'skipped'
        result['reason'] = 'Original not found (already deleted?)'
        return result

    original_size = os.path.getsize(original_path)
    result['original_size'] = original_size

    # Get expected compressed path
    compressed_path = get_compressed_path(original_path)

    # Check compressed exists
    if not os.path.exists(compressed_path):
        result['status'] = 'skipped'
        result['reason'] = f'Compressed not found: {compressed_path}'
        return result

    compressed_size = os.path.getsize(compressed_path)
    result['compressed_size'] = compressed_size
    result['compressed_path'] = compressed_path

    # Size validation
    min_size = MIN_COMPRESSED_SIZE_MB * 1024 * 1024
    if compressed_size < min_size:
        result['status'] = 'failed_verification'
        result['reason'] = f'Compressed too small ({format_size(compressed_size)} < {MIN_COMPRESSED_SIZE_MB}MB)'
        return result

    # Ratio validation
    ratio = compressed_size / original_size if original_size > 0 else 0
    if ratio > MAX_SIZE_RATIO:
        result['status'] = 'skipped'
        result['reason'] = f'Compression ratio too high ({ratio:.1%}) - not worth deleting'
        return result

    if ratio < MIN_SIZE_RATIO:
        result['status'] = 'failed_verification'
        result['reason'] = f'Suspicious ratio ({ratio:.3%}) - compressed may be corrupt'
        return result

    # Playability verification (optional, slow)
    if verify_playable:
        if not verify_video_playable(compressed_path):
            result['status'] = 'failed_verification'
            result['reason'] = 'Compressed file not playable (ffprobe failed)'
            return result

    # All checks passed
    result['savings'] = original_size - compressed_size

    if dry_run:
        result['status'] = 'would_delete'
        result['reason'] = f'Verified OK. Would save {format_size(result["savings"])}'
    else:
        try:
            os.remove(original_path)
            result['status'] = 'deleted'
            result['reason'] = f'Deleted. Saved {format_size(result["savings"])}'
        except Exception as e:
            result['status'] = 'delete_failed'
            result['reason'] = f'Delete error: {e}'

    return result

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Safely delete original videos after compression')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without deleting')
    parser.add_argument('--delete', action='store_true', help='Actually delete files')
    parser.add_argument('--min-size-gb', type=float, default=0, help='Only delete originals larger than this (GB)')
    parser.add_argument('--skip-playable-check', action='store_true', help='Skip ffprobe verification (faster)')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of files to process')
    args = parser.parse_args()

    if not args.dry_run and not args.delete:
        print("ERROR: Must specify --dry-run or --delete")
        print("Run with --dry-run first to see what would be deleted")
        sys.exit(1)

    if args.delete and not args.dry_run:
        print("=" * 60)
        print("WARNING: This will PERMANENTLY DELETE original video files!")
        print("=" * 60)
        confirm = input("Type 'DELETE' to confirm: ")
        if confirm != 'DELETE':
            print("Aborted.")
            sys.exit(0)

    log("=" * 60)
    log("SAFE DELETION SCRIPT")
    log(f"Mode: {'DRY RUN' if args.dry_run else 'DELETE'}")
    log(f"Min size filter: {args.min_size_gb} GB")
    log("=" * 60)

    # Load progress
    progress = load_progress()
    completed = progress.get('completed', [])
    log(f"Completed files in progress: {len(completed)}")

    # Load existing deletion log
    deletion_log = load_deletion_log()
    already_deleted = set(d['original'] for d in deletion_log.get('deleted', []))

    # Filter by size if specified
    min_size_bytes = args.min_size_gb * 1024 * 1024 * 1024

    # Process files
    stats = {'would_delete': 0, 'deleted': 0, 'skipped': 0, 'failed': 0, 'total_savings': 0}

    for i, original_path in enumerate(completed):
        if args.limit and i >= args.limit:
            break

        if original_path in already_deleted:
            continue

        # Size filter
        if min_size_bytes > 0:
            try:
                if os.path.getsize(original_path) < min_size_bytes:
                    continue
            except:
                continue

        result = verify_and_delete(
            original_path,
            dry_run=args.dry_run,
            verify_playable=not args.skip_playable_check
        )

        # Log result
        if result['status'] in ['deleted', 'would_delete']:
            stats['total_savings'] += result.get('savings', 0)
            if result['status'] == 'deleted':
                stats['deleted'] += 1
                deletion_log['deleted'].append(result)
            else:
                stats['would_delete'] += 1
            log(f"✓ {os.path.basename(original_path)}: {result['reason']}")
        elif result['status'] == 'failed_verification':
            stats['failed'] += 1
            deletion_log['failed_verification'].append(result)
            log(f"✗ {os.path.basename(original_path)}: {result['reason']}")
        else:
            stats['skipped'] += 1
            if 'not found' not in result['reason'].lower():
                log(f"- {os.path.basename(original_path)}: {result['reason']}")

    # Save deletion log
    save_deletion_log(deletion_log)

    # Summary
    log("")
    log("=" * 60)
    log("SUMMARY")
    log("=" * 60)
    if args.dry_run:
        log(f"Would delete: {stats['would_delete']} files")
    else:
        log(f"Deleted: {stats['deleted']} files")
    log(f"Skipped: {stats['skipped']} files")
    log(f"Failed verification: {stats['failed']} files")
    log(f"Total space savings: {format_size(stats['total_savings'])}")
    log("")
    log(f"Audit log saved to: {DELETION_LOG}")

if __name__ == "__main__":
    main()
