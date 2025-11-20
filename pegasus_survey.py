#!/usr/bin/env python3
"""
Pegasus Drive Video Survey Script
Scans Pegasus drive for all video files and generates comprehensive inventory
"""

import os
import json
import subprocess
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Pegasus drive mount point
PEGASUS_PATH = Path("/Volumes/Promise Pegasus")

# Video file extensions to search for
VIDEO_EXTENSIONS = {
    '.mp4', '.m4v', '.mov', '.avi', '.mkv', '.flv',
    '.wmv', '.mpg', '.mpeg', '.3gp', '.webm', '.MP4', '.MOV'
}

def get_file_metadata(file_path):
    """Extract basic file metadata"""
    try:
        stat = file_path.stat()
        return {
            'path': str(file_path),
            'filename': file_path.name,
            'size_bytes': stat.st_size,
            'size_mb': round(stat.st_size / (1024 * 1024), 2),
            'size_gb': round(stat.st_size / (1024 * 1024 * 1024), 2),
            'created': datetime.fromtimestamp(stat.st_birthtime).isoformat(),
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }
    except Exception as e:
        return {
            'path': str(file_path),
            'filename': file_path.name,
            'error': str(e)
        }

def get_video_duration(file_path):
    """Extract video duration using ffprobe if available"""
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            str(file_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            duration = float(data['format']['duration'])
            return {
                'duration_seconds': duration,
                'duration_minutes': round(duration / 60, 2),
                'duration_hours': round(duration / 3600, 2)
            }
    except Exception as e:
        pass
    return None

def survey_pegasus():
    """Perform comprehensive survey of Pegasus drive"""

    print("=" * 80)
    print("PEGASUS DRIVE VIDEO SURVEY")
    print("=" * 80)
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Scanning: {PEGASUS_PATH}")
    print("=" * 80)
    print()

    if not PEGASUS_PATH.exists():
        print(f"ERROR: Pegasus drive not found at {PEGASUS_PATH}")
        return None

    # Data structures
    all_videos = []
    videos_by_directory = defaultdict(list)
    total_size = 0
    total_duration = 0
    extension_counts = defaultdict(int)

    # Scan directories
    print("Scanning directories...")
    print()

    for root, dirs, files in os.walk(PEGASUS_PATH):
        root_path = Path(root)

        # Skip hidden directories
        if any(part.startswith('.') for part in root_path.parts):
            continue

        for filename in files:
            file_path = root_path / filename

            # Check if video file
            if file_path.suffix.lower() in VIDEO_EXTENSIONS:
                # Get metadata
                metadata = get_file_metadata(file_path)

                # Get relative path from Pegasus root
                rel_path = file_path.relative_to(PEGASUS_PATH)
                top_level_dir = str(rel_path.parts[0]) if rel_path.parts else "root"

                metadata['directory'] = top_level_dir
                metadata['relative_path'] = str(rel_path)

                # Track by extension
                extension_counts[file_path.suffix.lower()] += 1

                # Add to collections
                all_videos.append(metadata)
                videos_by_directory[top_level_dir].append(metadata)

                # Track totals
                if 'size_bytes' in metadata:
                    total_size += metadata['size_bytes']

                # Progress indicator
                if len(all_videos) % 100 == 0:
                    print(f"  Found {len(all_videos)} videos so far...")

    print()
    print(f"Scan complete! Found {len(all_videos)} videos.")
    print()

    # Calculate summary statistics
    summary = {
        'scan_date': datetime.now().isoformat(),
        'total_videos': len(all_videos),
        'total_size_bytes': total_size,
        'total_size_gb': round(total_size / (1024 ** 3), 2),
        'total_size_tb': round(total_size / (1024 ** 4), 2),
        'top_level_directories': len(videos_by_directory),
        'extensions': dict(extension_counts),
    }

    # Print summary
    print("=" * 80)
    print("SURVEY SUMMARY")
    print("=" * 80)
    print(f"Total Videos: {summary['total_videos']:,}")
    print(f"Total Size: {summary['total_size_gb']:.2f} GB ({summary['total_size_tb']:.2f} TB)")
    print(f"Top-Level Directories: {summary['top_level_directories']}")
    print()

    print("Videos by Directory:")
    for dirname in sorted(videos_by_directory.keys(), key=lambda x: len(videos_by_directory[x]), reverse=True):
        count = len(videos_by_directory[dirname])
        size_gb = sum(v.get('size_bytes', 0) for v in videos_by_directory[dirname]) / (1024 ** 3)
        print(f"  {dirname:40s} {count:5,} videos  {size_gb:8.2f} GB")
    print()

    print("Videos by Extension:")
    for ext in sorted(extension_counts.keys(), key=lambda x: extension_counts[x], reverse=True):
        print(f"  {ext:10s} {extension_counts[ext]:5,}")
    print()

    # Return comprehensive results
    return {
        'summary': summary,
        'videos_by_directory': {k: v for k, v in videos_by_directory.items()},
        'all_videos': all_videos
    }

def save_survey_results(results, output_dir):
    """Save survey results to JSON files"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Save full results
    full_path = output_path / f"survey_full_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(full_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Full survey saved to: {full_path}")

    # Save summary only
    summary_path = output_path / f"survey_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(summary_path, 'w') as f:
        json.dump(results['summary'], f, indent=2)
    print(f"Summary saved to: {summary_path}")

    return full_path, summary_path

if __name__ == '__main__':
    # Run survey
    results = survey_pegasus()

    if results:
        # Save to VideoDev directory
        output_dir = Path.home() / "Library/CloudStorage/Dropbox/Fergi/VideoDev/survey_data"
        save_survey_results(results, output_dir)

        print()
        print("=" * 80)
        print("NEXT STEPS")
        print("=" * 80)
        print("1. Review survey results in survey_data/ directory")
        print("2. Create SQLite database schema")
        print("3. Import survey data into database")
        print("4. Begin extracting video metadata (duration, codec, resolution)")
        print("5. Calculate transcription costs")
        print("=" * 80)
