#!/usr/bin/env python3
"""
Scan entire Pegasus drive for duplicate files.
Generates comprehensive report WITHOUT deleting anything.
"""

import os
import hashlib
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import sys

# Configuration
PEGASUS_PATH = "/Volumes/Promise Pegasus"
OUTPUT_DIR = "/Users/joeferguson/Library/CloudStorage/Dropbox/Fergi/VideoDev/logs"

# Minimum file size to consider (skip tiny files)
MIN_SIZE = 1024  # 1KB

# For checksum calculation, read in chunks
CHUNK_SIZE = 8192 * 1024  # 8MB chunks

def format_size(bytes_size):
    """Format bytes to human readable."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"

def get_file_hash(filepath, quick=True):
    """
    Get file hash.
    If quick=True, only hash first and last 1MB (fast for large files).
    If quick=False, hash entire file (accurate but slow).
    """
    try:
        file_size = os.path.getsize(filepath)

        if quick and file_size > 2 * 1024 * 1024:  # For files >2MB, use quick hash
            hasher = hashlib.md5()
            with open(filepath, 'rb') as f:
                # Hash first 1MB
                hasher.update(f.read(1024 * 1024))
                # Seek to last 1MB
                f.seek(-1024 * 1024, 2)
                hasher.update(f.read())
                # Include file size in hash for extra safety
                hasher.update(str(file_size).encode())
            return hasher.hexdigest()
        else:
            # Full hash for smaller files
            hasher = hashlib.md5()
            with open(filepath, 'rb') as f:
                while chunk := f.read(CHUNK_SIZE):
                    hasher.update(chunk)
            return hasher.hexdigest()
    except Exception as e:
        return None

def get_full_hash(filepath):
    """Get complete file hash (slower but accurate)."""
    try:
        hasher = hashlib.md5()
        with open(filepath, 'rb') as f:
            while chunk := f.read(CHUNK_SIZE):
                hasher.update(chunk)
        return hasher.hexdigest()
    except:
        return None

def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Output files
    report_path = os.path.join(OUTPUT_DIR, f"{timestamp}_duplicate_report.md")
    json_path = os.path.join(OUTPUT_DIR, f"{timestamp}_duplicates.json")
    progress_path = os.path.join(OUTPUT_DIR, f"{timestamp}_dup_progress.log")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Starting duplicate scan of {PEGASUS_PATH}")
    print(f"Progress log: {progress_path}")
    print()

    # Phase 1: Build index by size (fast)
    print("Phase 1: Indexing files by size...")

    size_index = defaultdict(list)  # size -> list of paths
    total_files = 0
    indexed_files = 0
    total_size = 0
    errors = 0

    with open(progress_path, 'w') as progress:
        progress.write(f"Duplicate scan started: {datetime.now()}\n")
        progress.write(f"Target: {PEGASUS_PATH}\n\n")
        progress.write("Phase 1: Building size index...\n")

        for root, dirs, files in os.walk(PEGASUS_PATH):
            # Skip hidden directories and system directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['.Spotlight-V100', '.fseventsd', '.Trashes']]

            for filename in files:
                if filename.startswith('.'):
                    continue

                total_files += 1

                if total_files % 10000 == 0:
                    msg = f"Phase 1: Indexed {total_files:,} files ({format_size(total_size)} total)"
                    print(msg)
                    progress.write(f"{datetime.now()}: {msg}\n")
                    progress.flush()

                filepath = os.path.join(root, filename)

                try:
                    size = os.path.getsize(filepath)
                    if size >= MIN_SIZE:
                        size_index[size].append(filepath)
                        indexed_files += 1
                        total_size += size
                except Exception as e:
                    errors += 1

        progress.write(f"\nPhase 1 complete: {indexed_files:,} files indexed\n")
        progress.write(f"Files with potential duplicates (same size): {sum(1 for s in size_index if len(size_index[s]) > 1)}\n\n")

    # Phase 2: Find duplicates by hash
    print(f"\nPhase 2: Checking {sum(len(v) for v in size_index.values() if len(v) > 1):,} files with matching sizes...")

    # Only check files that have size matches
    potential_dups = {size: paths for size, paths in size_index.items() if len(paths) > 1}

    duplicate_clusters = []  # List of duplicate groups
    total_dup_size = 0
    total_wasted_size = 0
    files_checked = 0
    total_to_check = sum(len(paths) for paths in potential_dups.values())

    with open(progress_path, 'a') as progress:
        progress.write("Phase 2: Computing hashes for duplicate candidates...\n")

        for size, paths in sorted(potential_dups.items(), key=lambda x: -x[0]):  # Process largest first
            files_checked += len(paths)

            if files_checked % 1000 == 0:
                msg = f"Phase 2: Checked {files_checked:,}/{total_to_check:,} files, found {len(duplicate_clusters):,} duplicate groups"
                print(msg)
                progress.write(f"{datetime.now()}: {msg}\n")
                progress.flush()

            # Quick hash first
            hash_groups = defaultdict(list)
            for path in paths:
                quick_hash = get_file_hash(path, quick=True)
                if quick_hash:
                    hash_groups[quick_hash].append(path)

            # For matching quick hashes, verify with full hash
            for quick_hash, matching_paths in hash_groups.items():
                if len(matching_paths) > 1:
                    # Verify with full hash (for large files)
                    if size > 10 * 1024 * 1024:  # >10MB, verify
                        full_hash_groups = defaultdict(list)
                        for path in matching_paths:
                            full_hash = get_full_hash(path)
                            if full_hash:
                                full_hash_groups[full_hash].append(path)

                        for full_hash, verified_paths in full_hash_groups.items():
                            if len(verified_paths) > 1:
                                cluster = {
                                    'hash': full_hash,
                                    'size': size,
                                    'paths': verified_paths,
                                    'count': len(verified_paths),
                                    'wasted': size * (len(verified_paths) - 1)
                                }
                                duplicate_clusters.append(cluster)
                                total_dup_size += size * len(verified_paths)
                                total_wasted_size += cluster['wasted']
                    else:
                        # For smaller files, trust quick hash
                        cluster = {
                            'hash': quick_hash,
                            'size': size,
                            'paths': matching_paths,
                            'count': len(matching_paths),
                            'wasted': size * (len(matching_paths) - 1)
                        }
                        duplicate_clusters.append(cluster)
                        total_dup_size += size * len(matching_paths)
                        total_wasted_size += cluster['wasted']

        progress.write(f"\nPhase 2 complete: {len(duplicate_clusters):,} duplicate groups found\n")
        progress.write(f"Total wasted space: {format_size(total_wasted_size)}\n")

    # Sort clusters by wasted space (largest first)
    duplicate_clusters.sort(key=lambda x: x['wasted'], reverse=True)

    # Save JSON
    print(f"\nSaving JSON: {json_path}")
    with open(json_path, 'w') as f:
        json.dump({
            'scan_date': timestamp,
            'total_files': total_files,
            'indexed_files': indexed_files,
            'duplicate_groups': len(duplicate_clusters),
            'total_wasted_space': total_wasted_size,
            'clusters': duplicate_clusters[:1000]  # Top 1000 for JSON
        }, f, indent=2)

    # Generate report
    print(f"Generating report: {report_path}")
    with open(report_path, 'w') as f:
        f.write("# Pegasus Drive - Duplicate Files Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")

        f.write("## Executive Summary\n\n")
        f.write("| Metric | Value |\n")
        f.write("|--------|-------|\n")
        f.write(f"| **Total Files Scanned** | {total_files:,} |\n")
        f.write(f"| **Files Indexed (≥1KB)** | {indexed_files:,} |\n")
        f.write(f"| **Total Data Scanned** | {format_size(total_size)} |\n")
        f.write(f"| **Duplicate Groups Found** | {len(duplicate_clusters):,} |\n")
        f.write(f"| **Total Duplicate Files** | {sum(c['count'] for c in duplicate_clusters):,} |\n")
        f.write(f"| **Space Wasted by Duplicates** | **{format_size(total_wasted_size)}** |\n")
        f.write(f"| **Errors/Skipped** | {errors:,} |\n\n")

        f.write("---\n\n")

        f.write("## ⚠️ NO FILES DELETED\n\n")
        f.write("This is a **report only**. No files have been deleted.\n")
        f.write("Review this report and decide which duplicates to remove.\n\n")

        f.write("---\n\n")

        f.write("## Top 100 Largest Duplicate Groups\n\n")
        f.write("| # | File Size | Copies | Wasted | Sample Filename |\n")
        f.write("|---|-----------|--------|--------|----------------|\n")

        for i, cluster in enumerate(duplicate_clusters[:100], 1):
            sample_name = os.path.basename(cluster['paths'][0])
            if len(sample_name) > 35:
                sample_name = sample_name[:32] + "..."
            f.write(f"| {i} | {format_size(cluster['size'])} | {cluster['count']} | {format_size(cluster['wasted'])} | {sample_name} |\n")

        f.write("\n---\n\n")

        # Group by directory
        f.write("## Duplicates by Directory\n\n")
        dir_stats = defaultdict(lambda: {'count': 0, 'wasted': 0})
        for cluster in duplicate_clusters:
            for path in cluster['paths']:
                rel_path = path.replace(PEGASUS_PATH + '/', '')
                top_dir = rel_path.split('/')[0] if '/' in rel_path else 'root'
                dir_stats[top_dir]['count'] += 1
                dir_stats[top_dir]['wasted'] += cluster['size']

        f.write("| Directory | Duplicate Files | Potential Savings |\n")
        f.write("|-----------|-----------------|------------------|\n")
        for d in sorted(dir_stats.keys(), key=lambda x: dir_stats[x]['wasted'], reverse=True)[:30]:
            stats = dir_stats[d]
            f.write(f"| {d[:40]} | {stats['count']:,} | {format_size(stats['wasted'])} |\n")

        f.write("\n---\n\n")

        f.write("## Sample Duplicate Details (Top 20)\n\n")
        for i, cluster in enumerate(duplicate_clusters[:20], 1):
            f.write(f"### Duplicate Group #{i}\n\n")
            f.write(f"- **File Size:** {format_size(cluster['size'])}\n")
            f.write(f"- **Copies:** {cluster['count']}\n")
            f.write(f"- **Wasted Space:** {format_size(cluster['wasted'])}\n")
            f.write(f"- **MD5 Hash:** `{cluster['hash']}`\n\n")
            f.write("**Locations:**\n")
            for path in cluster['paths'][:10]:  # Show max 10 paths
                rel_path = path.replace(PEGASUS_PATH + '/', '')
                f.write(f"- `{rel_path}`\n")
            if len(cluster['paths']) > 10:
                f.write(f"- ... and {len(cluster['paths']) - 10} more\n")
            f.write("\n")

        f.write("---\n\n")

        f.write("## File Type Distribution\n\n")
        ext_stats = defaultdict(lambda: {'count': 0, 'wasted': 0})
        for cluster in duplicate_clusters:
            ext = os.path.splitext(cluster['paths'][0])[1].lower() or 'no_ext'
            ext_stats[ext]['count'] += cluster['count']
            ext_stats[ext]['wasted'] += cluster['wasted']

        f.write("| Extension | Duplicate Files | Wasted Space |\n")
        f.write("|-----------|-----------------|-------------|\n")
        for ext in sorted(ext_stats.keys(), key=lambda x: ext_stats[x]['wasted'], reverse=True)[:20]:
            stats = ext_stats[ext]
            f.write(f"| {ext} | {stats['count']:,} | {format_size(stats['wasted'])} |\n")

        f.write("\n---\n\n")

        f.write("## Full Details\n\n")
        f.write(f"Complete duplicate data saved to: `{json_path}`\n\n")
        f.write(f"**Total duplicate groups:** {len(duplicate_clusters):,}\n")
        f.write(f"**Total recoverable space:** {format_size(total_wasted_size)}\n")

    # Print summary
    print("\n" + "="*60)
    print("DUPLICATE SCAN COMPLETE")
    print("="*60)
    print(f"Total files scanned:       {total_files:,}")
    print(f"Duplicate groups found:    {len(duplicate_clusters):,}")
    print(f"Total wasted space:        {format_size(total_wasted_size)}")
    print("="*60)
    print(f"\nReport: {report_path}")
    print(f"JSON:   {json_path}")
    print("\n⚠️  NO FILES WERE DELETED - Review report before taking action")

if __name__ == "__main__":
    main()
