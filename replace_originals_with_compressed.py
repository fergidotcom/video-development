#!/usr/bin/env python3
"""
Replace original video files with their compressed versions.

For each compressed file in _compressor_output:
1. Find the original file
2. Move compressed file to original's directory with "Compressed" suffix
3. Delete the original file
4. Track statistics

Output naming: originalName.MP4 -> originalNameCompressed.mov
"""

import os
import json
import shutil
from datetime import datetime
from pathlib import Path

PEGASUS_ROOT = "/Volumes/Promise Pegasus"
OUTPUT_DIR = f"{PEGASUS_ROOT}/_compressor_output"
PROGRESS_FILE = "logs/compressor_cli_progress.json"
REPLACEMENT_LOG = "logs/replacement_log.json"

def log(msg):
    """Print timestamped log message."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

def find_compressed_files():
    """Find all compressed files in output directory."""
    compressed = []
    for root, dirs, files in os.walk(OUTPUT_DIR):
        for f in files:
            if f.endswith('_1080p.mov'):
                compressed.append(os.path.join(root, f))
    return compressed

def get_original_path(compressed_path):
    """
    Map compressed file path back to original file path.

    Compressed: /Volumes/Promise Pegasus/_compressor_output/Walkabout2018/dir/file_1080p.mov
    Original could be: /Volumes/Promise Pegasus/Walkabout2018/dir/file.MP4 or .mp4 or .MOV etc.
    """
    # Remove _compressor_output from path
    rel_path = compressed_path.replace(OUTPUT_DIR + "/", "")

    # Remove _1080p.mov suffix to get base name
    base_path = rel_path.replace("_1080p.mov", "")

    # Try common video extensions
    extensions = ['.MP4', '.mp4', '.MOV', '.mov', '.m4v', '.M4V']

    for ext in extensions:
        original = f"{PEGASUS_ROOT}/{base_path}{ext}"
        if os.path.exists(original):
            return original

    return None

def get_new_filename(original_path):
    """
    Generate new filename with 'Compressed' suffix.

    originalName.MP4 -> originalNameCompressed.mov
    """
    dirname = os.path.dirname(original_path)
    basename = os.path.basename(original_path)
    name_without_ext = os.path.splitext(basename)[0]
    new_name = f"{name_without_ext}Compressed.mov"
    return os.path.join(dirname, new_name)

def main():
    log("=" * 60)
    log("REPLACING ORIGINALS WITH COMPRESSED VERSIONS")
    log("=" * 60)

    # Find all compressed files
    log("Finding compressed files...")
    compressed_files = find_compressed_files()
    log(f"Found {len(compressed_files)} compressed files")

    # Statistics
    stats = {
        'total_compressed': len(compressed_files),
        'successful_replacements': 0,
        'original_not_found': 0,
        'errors': 0,
        'space_saved_bytes': 0,
        'original_size_bytes': 0,
        'compressed_size_bytes': 0,
        'files_processed': [],
        'errors_list': [],
        'originals_not_found': []
    }

    # Process each compressed file
    for i, compressed_path in enumerate(compressed_files):
        if (i + 1) % 50 == 0:
            log(f"Progress: {i + 1}/{len(compressed_files)}")

        try:
            # Find original
            original_path = get_original_path(compressed_path)

            if original_path is None:
                stats['original_not_found'] += 1
                stats['originals_not_found'].append(compressed_path)
                continue

            # Get sizes
            original_size = os.path.getsize(original_path)
            compressed_size = os.path.getsize(compressed_path)

            # Generate new path
            new_path = get_new_filename(original_path)

            # Check if target already exists
            if os.path.exists(new_path):
                log(f"WARNING: Target already exists, skipping: {new_path}")
                stats['errors'] += 1
                stats['errors_list'].append(f"Target exists: {new_path}")
                continue

            # Move compressed file to new location
            shutil.move(compressed_path, new_path)

            # Delete original
            os.remove(original_path)

            # Update stats
            stats['successful_replacements'] += 1
            stats['original_size_bytes'] += original_size
            stats['compressed_size_bytes'] += compressed_size
            stats['space_saved_bytes'] += (original_size - compressed_size)

            stats['files_processed'].append({
                'original': original_path,
                'new': new_path,
                'original_size': original_size,
                'compressed_size': compressed_size,
                'saved': original_size - compressed_size
            })

        except Exception as e:
            stats['errors'] += 1
            stats['errors_list'].append(f"{compressed_path}: {str(e)}")
            log(f"ERROR processing {compressed_path}: {e}")

    # Save detailed log
    log_data = {
        'timestamp': datetime.now().isoformat(),
        'stats': {
            'total_compressed': stats['total_compressed'],
            'successful_replacements': stats['successful_replacements'],
            'original_not_found': stats['original_not_found'],
            'errors': stats['errors'],
            'original_size_gb': stats['original_size_bytes'] / (1024**3),
            'compressed_size_gb': stats['compressed_size_bytes'] / (1024**3),
            'space_saved_gb': stats['space_saved_bytes'] / (1024**3)
        },
        'originals_not_found': stats['originals_not_found'][:50],  # First 50 for log
        'errors_list': stats['errors_list']
    }

    with open(REPLACEMENT_LOG, 'w') as f:
        json.dump(log_data, f, indent=2)

    # Print summary
    log("")
    log("=" * 60)
    log("REPLACEMENT COMPLETE - SUMMARY")
    log("=" * 60)
    log(f"Total compressed files found:  {stats['total_compressed']}")
    log(f"Successful replacements:       {stats['successful_replacements']}")
    log(f"Originals not found:           {stats['original_not_found']}")
    log(f"Errors:                        {stats['errors']}")
    log("")
    log(f"Original files total size:     {stats['original_size_bytes'] / (1024**3):.2f} GB")
    log(f"Compressed files total size:   {stats['compressed_size_bytes'] / (1024**3):.2f} GB")
    log(f"SPACE SAVED:                   {stats['space_saved_bytes'] / (1024**3):.2f} GB")
    log(f"Compression ratio:             {stats['compressed_size_bytes'] / max(stats['original_size_bytes'], 1) * 100:.1f}%")
    log("")
    log(f"Detailed log saved to: {REPLACEMENT_LOG}")

if __name__ == "__main__":
    main()
