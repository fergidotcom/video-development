#!/usr/bin/env python3
"""
Extract video metadata (duration, codec, resolution) using ffprobe.
Updates database with actual video properties.
"""

import json
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime

DATABASE_PATH = "video-archive.db"

def get_video_metadata(video_path):
    """Extract metadata from video file using ffprobe."""

    try:
        # Run ffprobe to get video metadata as JSON
        result = subprocess.run([
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            video_path
        ], capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return None

        metadata = json.loads(result.stdout)

        # Extract relevant information
        format_info = metadata.get('format', {})
        video_stream = next((s for s in metadata.get('streams', []) if s.get('codec_type') == 'video'), None)

        if not video_stream:
            return None

        return {
            'duration_seconds': float(format_info.get('duration', 0)),
            'format': format_info.get('format_name', '').split(',')[0],
            'codec': video_stream.get('codec_name'),
            'width': video_stream.get('width'),
            'height': video_stream.get('height'),
            'fps': eval(video_stream.get('r_frame_rate', '0/1'))  # Convert "30000/1001" to float
        }

    except Exception as e:
        print(f"   ❌ Error extracting metadata: {e}")
        return None

def extract_all_metadata():
    """Extract metadata for all Phase 1 videos."""

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # Get all Phase 1 videos (priority=high, no duration yet)
    cursor.execute("""
        SELECT id, file_path, filename, directory
        FROM videos
        WHERE priority = 'high' AND duration_seconds IS NULL
        ORDER BY directory, filename
    """)

    videos = cursor.fetchall()

    if not videos:
        print("No videos need metadata extraction.")
        return

    print(f"\n{'='*80}")
    print(f"EXTRACTING VIDEO METADATA")
    print(f"{'='*80}\n")
    print(f"Processing {len(videos)} videos...\n")

    success_count = 0
    error_count = 0
    total_duration_seconds = 0

    current_directory = None

    for video_id, file_path, filename, directory in videos:

        # Print directory header when it changes
        if directory != current_directory:
            if current_directory is not None:
                print()  # Blank line between directories
            print(f"📁 {directory}")
            current_directory = directory

        # Extract metadata
        metadata = get_video_metadata(file_path)

        if metadata:
            # Update database
            now = datetime.now().isoformat()
            cursor.execute("""
                UPDATE videos
                SET duration_seconds = ?,
                    format = ?,
                    codec = ?,
                    width = ?,
                    height = ?,
                    fps = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                metadata['duration_seconds'],
                metadata['format'],
                metadata['codec'],
                metadata['width'],
                metadata['height'],
                metadata['fps'],
                now,
                video_id
            ))

            duration_minutes = metadata['duration_seconds'] / 60
            total_duration_seconds += metadata['duration_seconds']
            success_count += 1

            print(f"   ✅ {filename[:60]:<60} {duration_minutes:>6.2f} min")

        else:
            error_count += 1
            print(f"   ❌ {filename[:60]:<60} FAILED")

    conn.commit()

    # Print summary
    print(f"\n{'='*80}")
    print(f"METADATA EXTRACTION SUMMARY")
    print(f"{'='*80}\n")

    total_minutes = total_duration_seconds / 60
    total_hours = total_minutes / 60
    estimated_cost = total_minutes * 0.006

    print(f"Videos processed: {success_count + error_count}")
    print(f"  ✅ Success: {success_count}")
    print(f"  ❌ Errors: {error_count}")

    if success_count > 0:
        print(f"\nTotal duration:")
        print(f"  - {total_duration_seconds:,.0f} seconds")
        print(f"  - {total_minutes:,.2f} minutes")
        print(f"  - {total_hours:,.2f} hours")

        print(f"\nEstimated Whisper API cost:")
        print(f"  - ${estimated_cost:,.2f} (at $0.006/minute)")

    # Get updated statistics by category
    cursor.execute("""
        SELECT category,
               COUNT(*) as count,
               SUM(duration_seconds) as total_seconds
        FROM videos
        WHERE priority = 'high' AND duration_seconds IS NOT NULL
        GROUP BY category
    """)

    print(f"\nBy category:")
    for category, count, total_seconds in cursor.fetchall():
        cat_minutes = total_seconds / 60
        cat_cost = cat_minutes * 0.006
        print(f"  - {category}: {count} videos, {cat_minutes:.2f} minutes, ${cat_cost:.2f}")

    conn.close()

    print(f"\n✅ Metadata extraction complete!\n")

if __name__ == "__main__":
    extract_all_metadata()
