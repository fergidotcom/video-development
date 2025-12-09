#!/usr/bin/env python3
"""
Replace Original Videos with Compressed Versions
=================================================
Uses progress file to map compressed outputs back to originals.

Safety features:
- Only replaces files that are SMALLER after compression
- Verifies compressed file exists and has size > 0
- Verifies original exists before replacing
- Logs all operations
- Dry-run mode by default

Usage:
    python3 replace_with_compressed.py --dry-run    # Preview changes
    python3 replace_with_compressed.py --execute    # Actually replace files
"""

import os
import sys
import json
import shutil
import argparse
from datetime import datetime

PEGASUS_ROOT = "/Volumes/Promise Pegasus"
OUTPUT_DIR = f"{PEGASUS_ROOT}/_compressor_output"
PROGRESS_FILE = "logs/compressor_cli_progress.json"
LOG_FILE = "logs/replacement_log.json"

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")

def find_compressed_output(original_path):
    """Find the compressed output file for a given original."""
    # Original: /Volumes/Promise Pegasus/MyMovieWithVinny/.../Corner.MP4
    # Output:   /Volumes/Promise Pegasus/_compressor_output/MyMovieWithVinny/Corner_1080p.mov

    # Get filename without extension
    filename = os.path.basename(original_path)
    base, ext = os.path.splitext(filename)

    # Get first-level subdirectory
    rel_path = original_path.replace(PEGASUS_ROOT + '/', '')
    parts = rel_path.split('/')
    subdir = parts[0] if parts else 'misc'

    # Expected output path
    output_path = os.path.join(OUTPUT_DIR, subdir, f"{base}_1080p.mov")

    if os.path.exists(output_path):
        return output_path

    return None

def main():
    parser = argparse.ArgumentParser(description='Replace originals with compressed versions')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without executing')
    parser.add_argument('--execute', action='store_true', help='Actually replace files')
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("ERROR: Must specify --dry-run or --execute")
        print("  --dry-run  Preview changes without executing")
        print("  --execute  Actually replace files")
        sys.exit(1)

    if not os.path.exists(PEGASUS_ROOT):
        log(f"ERROR: Pegasus drive not mounted at {PEGASUS_ROOT}")
        sys.exit(1)

    # Load progress file to get list of completed originals
    log("Loading progress file...")
    with open(PROGRESS_FILE, 'r') as f:
        progress = json.load(f)

    completed = progress.get('completed', [])
    log(f"Found {len(completed)} completed compressions")

    # Find replacements
    replacements = []
    skipped_no_output = []
    skipped_bigger = []

    for original_path in completed:
        if not os.path.exists(original_path):
            continue

        compressed_path = find_compressed_output(original_path)
        if not compressed_path:
            skipped_no_output.append(original_path)
            continue

        original_size = os.path.getsize(original_path)
        compressed_size = os.path.getsize(compressed_path)

        # Skip if compressed file is too small (likely failed/corrupted)
        min_size = 10 * 1024 * 1024  # 10MB minimum
        if compressed_size < min_size:
            skipped_bigger.append({
                'original': original_path,
                'original_size': original_size,
                'compressed_size': compressed_size,
                'reason': 'compressed too small (likely failed)'
            })
            continue

        # Skip if compressed is bigger or equal
        if compressed_size >= original_size:
            skipped_bigger.append({
                'original': original_path,
                'original_size': original_size,
                'compressed_size': compressed_size
            })
            continue

        savings_pct = (1 - compressed_size / original_size) * 100
        savings_gb = (original_size - compressed_size) / (1024**3)

        replacements.append({
            'original': original_path,
            'compressed': compressed_path,
            'original_size_gb': original_size / (1024**3),
            'compressed_size_gb': compressed_size / (1024**3),
            'savings_pct': savings_pct,
            'savings_gb': savings_gb
        })

    # Summary
    total_savings_gb = sum(r['savings_gb'] for r in replacements)
    log(f"\n{'='*60}")
    log(f"REPLACEMENT SUMMARY")
    log(f"{'='*60}")
    log(f"Files to replace: {len(replacements)}")
    log(f"Skipped (no output found): {len(skipped_no_output)}")
    log(f"Skipped (compressed bigger): {len(skipped_bigger)}")
    log(f"Total space savings: {total_savings_gb:.1f} GB")

    if args.dry_run:
        log(f"\n--- DRY RUN MODE - No changes made ---\n")
        for r in replacements:
            log(f"{r['original_size_gb']:.1f}GB -> {r['compressed_size_gb']:.1f}GB ({r['savings_pct']:.0f}% smaller)")
            log(f"  {os.path.basename(r['original'])}")
        if skipped_bigger:
            log(f"\nSkipped (would be bigger):")
            for s in skipped_bigger[:5]:
                log(f"  {os.path.basename(s['original'])}: {s['original_size']/(1024**3):.2f}GB -> {s['compressed_size']/(1024**3):.2f}GB")
        log(f"\nRun with --execute to perform replacements")
        return

    # Execute replacements
    log(f"\n--- EXECUTING REPLACEMENTS ---\n")
    success_count = 0
    fail_count = 0
    results = []

    for r in replacements:
        original = r['original']
        compressed = r['compressed']

        try:
            log(f"Replacing: {os.path.basename(original)}")

            # New path: same directory, same base name, .mov extension
            orig_base = os.path.splitext(original)[0]
            new_path = orig_base + '.mov'

            # Copy compressed to new location
            shutil.copy2(compressed, new_path)

            # Verify copy
            if os.path.exists(new_path) and os.path.getsize(new_path) == os.path.getsize(compressed):
                # Delete original if it's different from new_path
                if original.lower() != new_path.lower() and os.path.exists(original):
                    os.remove(original)

                success_count += 1
                results.append({
                    'status': 'success',
                    'original': original,
                    'new_path': new_path,
                    'savings_gb': r['savings_gb']
                })
                log(f"  Saved {r['savings_gb']:.1f} GB")
            else:
                raise Exception("Copy verification failed")

        except Exception as e:
            log(f"  ERROR: {e}")
            fail_count += 1
            results.append({
                'status': 'failed',
                'original': original,
                'error': str(e)
            })

    # Save results
    with open(LOG_FILE, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'success_count': success_count,
            'fail_count': fail_count,
            'total_savings_gb': total_savings_gb,
            'results': results
        }, f, indent=2)

    log(f"\n{'='*60}")
    log(f"COMPLETE")
    log(f"{'='*60}")
    log(f"Successful: {success_count}")
    log(f"Failed: {fail_count}")
    log(f"Space saved: {total_savings_gb:.1f} GB")
    log(f"Log saved to: {LOG_FILE}")

if __name__ == "__main__":
    main()
