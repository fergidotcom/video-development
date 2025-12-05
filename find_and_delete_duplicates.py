#!/usr/bin/env python3
"""
Pegasus Drive Duplicate Finder and Cleaner
Finds files in "2012 Laguna FergiDotCom Archive" that have identical copies elsewhere,
then deletes only from the archive (keeping the copy elsewhere).

Usage: python find_and_delete_duplicates.py [--dry-run]
"""

import os
import sys
import hashlib
import json
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import time

# Configuration
PEGASUS_ROOT = "/Volumes/Promise Pegasus"
ARCHIVE_DIR = "/Volumes/Promise Pegasus/2012 Laguna FergiDotCom Archive"
LOG_DIR = "/Users/joeferguson/Library/CloudStorage/Dropbox/Fergi/VideoDev/logs"

# Timestamp for this run
RUN_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# Log files
PROGRESS_LOG = os.path.join(LOG_DIR, f"{RUN_TIMESTAMP}_progress.log")
DELETION_LOG = os.path.join(LOG_DIR, f"{RUN_TIMESTAMP}_deletions.log")
DELETION_JSON = os.path.join(LOG_DIR, f"{RUN_TIMESTAMP}_deletions.json")
SUMMARY_LOG = os.path.join(LOG_DIR, f"{RUN_TIMESTAMP}_summary.txt")

# Dry run mode
DRY_RUN = "--dry-run" in sys.argv

def log_progress(message):
    """Log progress to console and file"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] {message}"
    print(log_msg)
    with open(PROGRESS_LOG, 'a') as f:
        f.write(log_msg + "\n")

def log_deletion(archive_path, external_path, file_size, checksum, deleted=True):
    """Log a deletion to the deletion log"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "DELETED" if deleted else "WOULD DELETE (dry-run)"
    log_msg = f"[{timestamp}] {status}\n  Archive: {archive_path}\n  Kept at: {external_path}\n  Size: {file_size:,} bytes\n  MD5: {checksum}\n"
    with open(DELETION_LOG, 'a') as f:
        f.write(log_msg + "\n")
    return {
        "timestamp": timestamp,
        "deleted": deleted,
        "archive_path": archive_path,
        "kept_at": external_path,
        "size": file_size,
        "md5": checksum
    }

def compute_md5(filepath, chunk_size=8192*1024):  # 8MB chunks for speed
    """Compute MD5 hash of a file"""
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()
    except (IOError, PermissionError) as e:
        log_progress(f"Error reading {filepath}: {e}")
        return None

def get_file_info(filepath):
    """Get file size and basic info"""
    try:
        stat = os.stat(filepath)
        return {
            "path": filepath,
            "size": stat.st_size,
            "name": os.path.basename(filepath)
        }
    except (IOError, PermissionError) as e:
        return None

def build_archive_index():
    """Build index of all files in the archive directory"""
    log_progress(f"Building index of files in archive: {ARCHIVE_DIR}")
    archive_files = {}  # {filename: [{path, size}, ...]}

    file_count = 0
    for root, dirs, files in os.walk(ARCHIVE_DIR):
        # Skip hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for filename in files:
            if filename.startswith('.'):
                continue

            filepath = os.path.join(root, filename)
            info = get_file_info(filepath)
            if info:
                if filename not in archive_files:
                    archive_files[filename] = []
                archive_files[filename].append(info)
                file_count += 1

                if file_count % 10000 == 0:
                    log_progress(f"  Indexed {file_count} archive files...")

    log_progress(f"Archive index complete: {file_count} files, {len(archive_files)} unique names")
    return archive_files

def find_external_matches(archive_files):
    """Find files outside the archive that match archive filenames"""
    log_progress(f"Searching for matches outside archive on {PEGASUS_ROOT}...")

    # Build set of filenames we're looking for
    target_names = set(archive_files.keys())
    matches = defaultdict(list)  # {filename: [{path, size}, ...]}

    file_count = 0
    match_count = 0

    for root, dirs, files in os.walk(PEGASUS_ROOT):
        # Skip hidden directories and the archive directory itself
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        # Skip if we're inside the archive
        if root.startswith(ARCHIVE_DIR):
            continue

        for filename in files:
            if filename.startswith('.'):
                continue

            file_count += 1
            if file_count % 50000 == 0:
                log_progress(f"  Scanned {file_count} external files, found {match_count} potential matches...")

            if filename in target_names:
                filepath = os.path.join(root, filename)
                info = get_file_info(filepath)
                if info:
                    matches[filename].append(info)
                    match_count += 1

    log_progress(f"External scan complete: {file_count} files scanned, {match_count} potential matches found")
    return matches

def find_duplicates(archive_files, external_matches):
    """Compare archive files with external matches to find true duplicates"""
    log_progress("Comparing files to find true duplicates (matching name, size, and checksum)...")

    duplicates = []  # List of (archive_path, external_path, size, md5)
    compared = 0

    for filename, archive_list in archive_files.items():
        if filename not in external_matches:
            continue

        external_list = external_matches[filename]

        for archive_info in archive_list:
            archive_path = archive_info['path']
            archive_size = archive_info['size']

            # Find external files with matching size
            size_matches = [e for e in external_list if e['size'] == archive_size]

            if not size_matches:
                continue

            compared += 1
            if compared % 100 == 0:
                log_progress(f"  Compared {compared} potential duplicates, found {len(duplicates)} confirmed...")

            # Compute archive file checksum
            archive_md5 = compute_md5(archive_path)
            if not archive_md5:
                continue

            # Check each size match for checksum match
            for external_info in size_matches:
                external_path = external_info['path']
                external_md5 = compute_md5(external_path)

                if external_md5 and archive_md5 == external_md5:
                    log_progress(f"  DUPLICATE FOUND: {filename} ({archive_size:,} bytes)")
                    duplicates.append((archive_path, external_path, archive_size, archive_md5))
                    break  # Found a match, no need to check other externals

    log_progress(f"Duplicate detection complete: {len(duplicates)} confirmed duplicates")
    return duplicates

def delete_duplicates(duplicates):
    """Delete duplicate files from the archive (keeping external copies)"""
    log_progress(f"{'DRY RUN - ' if DRY_RUN else ''}Deleting {len(duplicates)} duplicate files from archive...")

    deleted_files = []
    total_freed = 0

    for archive_path, external_path, size, md5 in duplicates:
        try:
            if not DRY_RUN:
                os.remove(archive_path)

            deleted_info = log_deletion(archive_path, external_path, size, md5, deleted=not DRY_RUN)
            deleted_files.append(deleted_info)
            total_freed += size

            log_progress(f"  {'[DRY-RUN] Would delete' if DRY_RUN else 'Deleted'}: {os.path.basename(archive_path)} ({size:,} bytes)")

        except (IOError, PermissionError) as e:
            log_progress(f"  ERROR deleting {archive_path}: {e}")

    log_progress(f"Deletion complete: {len(deleted_files)} files, {total_freed / (1024**3):.2f} GB freed")
    return deleted_files, total_freed

def write_summary(duplicates, deleted_files, total_freed, start_time):
    """Write a summary report"""
    end_time = time.time()
    duration = end_time - start_time

    summary = f"""
================================================================================
PEGASUS DUPLICATE CLEANUP SUMMARY
Run: {RUN_TIMESTAMP}
Mode: {'DRY RUN' if DRY_RUN else 'LIVE DELETION'}
================================================================================

RESULTS:
- Duplicates found: {len(duplicates)}
- Files deleted: {len(deleted_files)}
- Space freed: {total_freed / (1024**3):.2f} GB ({total_freed:,} bytes)
- Duration: {duration / 60:.1f} minutes

SOURCE DIRECTORY (files deleted from here):
{ARCHIVE_DIR}

FILES DELETED:
"""

    for f in deleted_files:
        summary += f"\n  {f['archive_path']}"
        summary += f"\n    Size: {f['size']:,} bytes"
        summary += f"\n    Kept at: {f['kept_at']}"
        summary += f"\n    MD5: {f['md5']}\n"

    summary += f"""
================================================================================
Log files:
- Progress: {PROGRESS_LOG}
- Deletions: {DELETION_LOG}
- JSON: {DELETION_JSON}
================================================================================
"""

    with open(SUMMARY_LOG, 'w') as f:
        f.write(summary)

    # Also save as JSON for programmatic access
    with open(DELETION_JSON, 'w') as f:
        json.dump({
            "run_timestamp": RUN_TIMESTAMP,
            "dry_run": DRY_RUN,
            "duplicates_found": len(duplicates),
            "files_deleted": len(deleted_files),
            "bytes_freed": total_freed,
            "duration_seconds": duration,
            "deletions": deleted_files
        }, f, indent=2)

    log_progress(f"Summary written to {SUMMARY_LOG}")
    return summary

def main():
    start_time = time.time()

    log_progress("=" * 70)
    log_progress("PEGASUS DUPLICATE FINDER AND CLEANER")
    log_progress(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE - FILES WILL BE DELETED'}")
    log_progress("=" * 70)

    # Verify directories exist
    if not os.path.exists(PEGASUS_ROOT):
        log_progress(f"ERROR: Pegasus drive not found at {PEGASUS_ROOT}")
        sys.exit(1)

    if not os.path.exists(ARCHIVE_DIR):
        log_progress(f"ERROR: Archive directory not found at {ARCHIVE_DIR}")
        sys.exit(1)

    # Step 1: Build archive index
    archive_files = build_archive_index()

    # Step 2: Find external matches
    external_matches = find_external_matches(archive_files)

    # Step 3: Find true duplicates (matching checksum)
    duplicates = find_duplicates(archive_files, external_matches)

    # Step 4: Delete duplicates from archive
    deleted_files, total_freed = delete_duplicates(duplicates)

    # Step 5: Write summary
    summary = write_summary(duplicates, deleted_files, total_freed, start_time)

    print("\n" + summary)

    log_progress("CLEANUP COMPLETE")

if __name__ == "__main__":
    main()
