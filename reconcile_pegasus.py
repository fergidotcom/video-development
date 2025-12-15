#!/usr/bin/env python3
"""
Pegasus Database Reconciliation Script
Reconciles existing pegasus-survey.db with current file system state.
Identifies removed files, new files (from compression), and unusable videos.

Run with nohup for long operations:
nohup python3 reconcile_pegasus.py > logs/reconcile_$(date +%Y%m%d_%H%M%S).log 2>&1 &
"""

import os
import sys
import sqlite3
import json
import subprocess
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# Configuration
DB_PATH = "pegasus-survey.db"
PEGASUS_ROOT = "/Volumes/Promise Pegasus"
COMPRESSOR_OUTPUT = "/Volumes/Promise Pegasus/_compressor_output"

# Excluded directories (handled by other projects or old backups)
EXCLUDED_DIRS = [
    "CKandLAFergusonFamilyArchive",
    "2012 Laguna FergiDotCom Archive"
]

# Video extensions for metadata extraction
VIDEO_EXTENSIONS = {'.mp4', '.m4v', '.mov', '.avi', '.mkv', '.mts', '.m2ts', '.mpg', '.mpeg', '.wmv', '.webm'}

# Statistics tracking
stats = {
    "files_in_db": 0,
    "files_on_disk": 0,
    "files_still_present": 0,
    "files_removed": 0,
    "files_new": 0,
    "compression_outputs_found": 0,
    "unusable_files_found": 0,
    "errors": 0,
    "started_at": datetime.now().isoformat(),
    "completed_at": None
}

def log(msg):
    """Print timestamped log message."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    sys.stdout.flush()

def is_excluded(path):
    """Check if path is in excluded directory."""
    for excluded in EXCLUDED_DIRS:
        if excluded in path:
            return True
    return False

def get_rotation_metadata(file_path):
    """Extract rotation/display metadata from video file using ffprobe."""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_streams', '-show_format', file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None, None

        data = json.loads(result.stdout)

        # Look for rotation in streams
        rotation = None
        display_matrix = None
        unusual_dimensions = False

        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'video':
                # Check for rotation tag
                tags = stream.get('tags', {})
                if 'rotate' in tags:
                    rotation = tags['rotate']

                # Check for display matrix in side_data
                for side_data in stream.get('side_data_list', []):
                    if side_data.get('side_data_type') == 'Display Matrix':
                        display_matrix = side_data.get('rotation')

                # Check for unusual dimensions (potential 3D)
                width = stream.get('width', 0)
                height = stream.get('height', 0)
                if width > 0 and height > 0:
                    ratio = width / height
                    # Side-by-side 3D often has 2:1 or close ratio
                    if ratio > 1.9 and ratio < 2.1:
                        unusual_dimensions = "possible_3d_sbs"
                    elif ratio > 0.45 and ratio < 0.55:
                        unusual_dimensions = "possible_3d_over_under"

        issues = []
        if rotation and rotation not in ['0', '360']:
            issues.append(f"rotation={rotation}")
        if display_matrix and display_matrix not in [0.0, 360.0]:
            issues.append(f"display_matrix={display_matrix}")
        if unusual_dimensions:
            issues.append(unusual_dimensions)

        return {
            'rotation': rotation,
            'display_matrix': display_matrix,
            'dimensions': unusual_dimensions
        }, issues if issues else None

    except subprocess.TimeoutExpired:
        return None, ["ffprobe_timeout"]
    except Exception as e:
        return None, [f"ffprobe_error: {str(e)}"]

def scan_filesystem():
    """Walk filesystem and return set of all file paths."""
    log("Starting filesystem scan (excluding: " + ", ".join(EXCLUDED_DIRS) + ")")
    files_on_disk = set()
    dir_count = 0

    for root, dirs, files in os.walk(PEGASUS_ROOT):
        # Skip excluded directories
        if is_excluded(root):
            dirs.clear()  # Don't recurse into excluded dirs
            continue

        dir_count += 1
        if dir_count % 1000 == 0:
            log(f"  Scanned {dir_count} directories, {len(files_on_disk)} files...")

        for filename in files:
            # Skip hidden files
            if filename.startswith('.'):
                continue
            file_path = os.path.join(root, filename)
            files_on_disk.add(file_path)

    log(f"Filesystem scan complete: {len(files_on_disk)} files in {dir_count} directories")
    return files_on_disk

def get_db_files(conn):
    """Get all file paths from database (excluding excluded dirs)."""
    cursor = conn.cursor()

    # Build exclusion clause
    exclusion_clauses = " AND ".join([f"file_path NOT LIKE '%{d}%'" for d in EXCLUDED_DIRS])

    cursor.execute(f"""
        SELECT id, file_path FROM files
        WHERE {exclusion_clauses}
    """)

    db_files = {row[1]: row[0] for row in cursor.fetchall()}
    return db_files

def reconcile(conn, db_files, disk_files):
    """Reconcile database with filesystem."""
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    db_paths = set(db_files.keys())

    # Files that were removed
    removed = db_paths - disk_files
    log(f"Files removed since survey: {len(removed)}")

    # Files that are new (on disk but not in DB)
    new_files = disk_files - db_paths
    log(f"New files since survey: {len(new_files)}")

    # Files still present
    still_present = db_paths & disk_files
    log(f"Files still present: {len(still_present)}")

    # Update stats
    stats["files_in_db"] = len(db_paths)
    stats["files_on_disk"] = len(disk_files)
    stats["files_still_present"] = len(still_present)
    stats["files_removed"] = len(removed)
    stats["files_new"] = len(new_files)

    # Mark removed files
    log("Marking removed files in database...")
    batch_size = 1000
    removed_list = list(removed)
    for i in range(0, len(removed_list), batch_size):
        batch = removed_list[i:i+batch_size]
        placeholders = ','.join(['?' for _ in batch])
        cursor.execute(f"""
            UPDATE files
            SET file_status = 'removed', reconciled_at = ?
            WHERE file_path IN ({placeholders})
        """, [now] + batch)
        if (i + batch_size) % 5000 == 0:
            log(f"  Marked {min(i + batch_size, len(removed_list))} removed files...")

    # Mark present files
    log("Marking present files in database...")
    present_list = list(still_present)
    for i in range(0, len(present_list), batch_size):
        batch = present_list[i:i+batch_size]
        placeholders = ','.join(['?' for _ in batch])
        cursor.execute(f"""
            UPDATE files
            SET file_status = 'present', reconciled_at = ?
            WHERE file_path IN ({placeholders})
        """, [now] + batch)
        if (i + batch_size) % 50000 == 0:
            log(f"  Marked {min(i + batch_size, len(present_list))} present files...")

    conn.commit()
    log("File status reconciliation complete")

    return removed, new_files, still_present

def add_new_files(conn, new_files):
    """Add new files to database (likely compression outputs)."""
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    log(f"Adding {len(new_files)} new files to database...")

    compression_outputs = 0
    other_new = 0

    for i, file_path in enumerate(new_files):
        if i % 500 == 0 and i > 0:
            log(f"  Processed {i} new files...")
            conn.commit()

        try:
            filename = os.path.basename(file_path)
            directory = os.path.dirname(file_path)
            relative_path = file_path.replace(PEGASUS_ROOT + "/", "")

            # Determine file type
            ext = os.path.splitext(filename)[1].lower()
            if ext in VIDEO_EXTENSIONS:
                file_type = 'video'
            elif ext in {'.jpg', '.jpeg', '.png', '.gif', '.tiff', '.heic', '.raw'}:
                file_type = 'photo'
            elif ext in {'.pdf', '.doc', '.docx', '.txt', '.rtf'}:
                file_type = 'document'
            else:
                file_type = 'other'

            # Get file stats
            try:
                stat = os.stat(file_path)
                file_size = stat.st_size
                mod_date = datetime.fromtimestamp(stat.st_mtime).isoformat()
            except:
                file_size = None
                mod_date = None

            # Check if compression output
            is_compression = COMPRESSOR_OUTPUT in file_path
            if is_compression:
                compression_outputs += 1
            else:
                other_new += 1

            # Insert new file
            cursor.execute("""
                INSERT OR IGNORE INTO files (
                    file_path, filename, directory, relative_path, file_type,
                    file_format, file_size_bytes, modification_date, project_assignment,
                    file_status, reconciled_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'general', 'present', ?, ?, ?)
            """, (file_path, filename, directory, relative_path, file_type,
                  ext.lstrip('.'), file_size, mod_date, now, now, now))

        except Exception as e:
            stats["errors"] += 1
            log(f"  Error adding {file_path}: {e}")

    conn.commit()
    stats["compression_outputs_found"] = compression_outputs
    log(f"Added new files: {compression_outputs} compression outputs, {other_new} other")

def analyze_failed_compressions(conn):
    """Analyze files that failed compression for rotation/tilt issues."""
    log("Analyzing failed compression files for rotation/tilt issues...")

    # Load failed files from compression progress
    progress_file = "logs/compressor_cli_progress.json"
    failed_files = []

    if os.path.exists(progress_file):
        with open(progress_file) as f:
            progress = json.load(f)
            failed_files = progress.get('failed', [])

    log(f"Found {len(failed_files)} failed compression files")

    cursor = conn.cursor()
    unusable_count = 0

    for file_path in failed_files:
        if not os.path.exists(file_path):
            continue

        # Get rotation metadata
        metadata, issues = get_rotation_metadata(file_path)

        if metadata or issues:
            # Get file ID if exists
            cursor.execute("SELECT id FROM files WHERE file_path = ?", (file_path,))
            row = cursor.fetchone()
            file_id = row[0] if row else None

            # Get file size
            try:
                file_size = os.path.getsize(file_path)
            except:
                file_size = None

            # Determine issue type
            issue_type = "compression_failure"
            issue_details = json.dumps(issues) if issues else json.dumps(metadata)

            # Insert into unusable_files
            cursor.execute("""
                INSERT OR REPLACE INTO unusable_files (
                    file_id, file_path, issue_type, issue_details, file_size
                ) VALUES (?, ?, ?, ?, ?)
            """, (file_id, file_path, issue_type, issue_details, file_size))

            # Update files table
            if file_id:
                cursor.execute("""
                    UPDATE files SET
                        usability_status = 'unusable',
                        usability_issue = ?,
                        rotation_metadata = ?
                    WHERE id = ?
                """, (issue_type, json.dumps(metadata), file_id))

            unusable_count += 1

    conn.commit()
    stats["unusable_files_found"] = unusable_count
    log(f"Identified {unusable_count} potentially unusable files")

def generate_report(removed, new_files):
    """Generate reconciliation report."""
    log("Generating reconciliation report...")

    stats["completed_at"] = datetime.now().isoformat()

    report = f"""# Pegasus Reconciliation Report

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary

| Metric | Count |
|--------|-------|
| Files in Database (before) | {stats['files_in_db']:,} |
| Files on Disk (current) | {stats['files_on_disk']:,} |
| Files Still Present | {stats['files_still_present']:,} |
| Files Removed | {stats['files_removed']:,} |
| New Files Added | {stats['files_new']:,} |
| Compression Outputs | {stats['compression_outputs_found']:,} |
| Unusable Files Identified | {stats['unusable_files_found']:,} |
| Errors | {stats['errors']:,} |

## Files Removed Since Survey

These files were in the original survey but no longer exist on disk:

"""

    # Sample of removed files (first 50)
    removed_sample = sorted(list(removed))[:50]
    for f in removed_sample:
        report += f"- `{f.replace(PEGASUS_ROOT + '/', '')}`\n"

    if len(removed) > 50:
        report += f"\n... and {len(removed) - 50} more\n"

    report += """

## New Files Since Survey

These files are new on disk (likely compression outputs or additions):

"""

    # Sample of new files (first 50)
    new_sample = sorted(list(new_files))[:50]
    for f in new_sample:
        report += f"- `{f.replace(PEGASUS_ROOT + '/', '')}`\n"

    if len(new_files) > 50:
        report += f"\n... and {len(new_files) - 50} more\n"

    report += """

## Database Updates Applied

1. Added columns to `files` table:
   - `file_status` - 'present' or 'removed'
   - `compressed_version_path` - path to compressed version if exists
   - `original_file_path` - path to original if this is compressed version
   - `reconciled_at` - timestamp of reconciliation
   - `usability_status` - 'usable' or 'unusable'
   - `usability_issue` - description of issue if unusable
   - `rotation_metadata` - rotation/display metadata JSON

2. Created new tables:
   - `projects_narrative` - for narrative project metadata
   - `fcp_projects` - for Final Cut Pro project tracking
   - `composites` - for finished video composites
   - `unusable_files` - for tracking problem files

## Next Steps

1. Review `unusable_video_files.txt` for files with rotation/tilt issues
2. Proceed with Phase 1: Directory narrative analysis
3. Proceed with Phase 2: FCP bundle discovery and parsing

"""

    with open("reconciliation_report.md", "w") as f:
        f.write(report)

    log("Report saved to reconciliation_report.md")

def generate_unusable_list(conn):
    """Generate separate list of unusable video files."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT file_path, issue_type, issue_details, file_size
        FROM unusable_files
        ORDER BY file_path
    """)

    rows = cursor.fetchall()

    with open("unusable_video_files.txt", "w") as f:
        f.write("# Unusable Video Files\n")
        f.write(f"# Generated: {datetime.now().isoformat()}\n")
        f.write(f"# Total: {len(rows)} files\n")
        f.write("#\n")
        f.write("# Format: PATH | ISSUE_TYPE | DETAILS | SIZE_MB\n")
        f.write("#" + "="*80 + "\n\n")

        for file_path, issue_type, issue_details, file_size in rows:
            size_mb = f"{file_size / (1024*1024):.1f}MB" if file_size else "unknown"
            f.write(f"{file_path}\n")
            f.write(f"  Issue: {issue_type}\n")
            f.write(f"  Details: {issue_details}\n")
            f.write(f"  Size: {size_mb}\n")
            f.write("\n")

    log(f"Saved {len(rows)} unusable files to unusable_video_files.txt")

def main():
    log("="*60)
    log("Pegasus Database Reconciliation")
    log("="*60)

    # Check Pegasus mount
    if not os.path.exists(PEGASUS_ROOT):
        log(f"ERROR: Pegasus drive not mounted at {PEGASUS_ROOT}")
        sys.exit(1)

    # Connect to database
    conn = sqlite3.connect(DB_PATH)

    try:
        # Get current DB state
        log("Loading database files...")
        db_files = get_db_files(conn)
        log(f"Database contains {len(db_files)} files (excluding excluded dirs)")

        # Scan filesystem
        disk_files = scan_filesystem()

        # Reconcile
        removed, new_files, still_present = reconcile(conn, db_files, disk_files)

        # Add new files to database
        if new_files:
            add_new_files(conn, new_files)

        # Analyze failed compressions for rotation issues
        analyze_failed_compressions(conn)

        # Generate reports
        generate_report(removed, new_files)
        generate_unusable_list(conn)

        log("="*60)
        log("Reconciliation complete!")
        log("="*60)

    finally:
        conn.close()

if __name__ == "__main__":
    main()
