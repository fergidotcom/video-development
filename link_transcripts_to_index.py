#!/usr/bin/env python3
"""
Link existing transcripts to videos in pegasus_index.db

This script:
1. Reads all transcripts from transcripts.db
2. Maps audio file paths back to original video paths
3. Updates has_transcript=1 for matching videos in pegasus_index.db
4. Reports statistics on matched/unmatched transcripts
"""

import sqlite3
import os
import re
import time

# Database paths
TRANSCRIPTS_DB = "/Users/joeferguson/Library/CloudStorage/Dropbox/Fergi/VideoDev/transcripts.db"
INDEX_DB = "/Users/joeferguson/Library/CloudStorage/Dropbox/Fergi/VideoDev/pegasus_index.db"

# Video extensions to try when matching
VIDEO_EXTENSIONS = ['.mp4', '.MP4', '.mov', '.MOV', '.m4v', '.M4V', '.avi', '.AVI', '.mkv', '.MKV']

def audio_path_to_video_path(audio_path):
    """
    Convert extracted audio path OR direct video path to potential video paths.

    Handles two cases:
    1. Extracted audio: /Volumes/Promise Pegasus/ExtractedAudio/CKandLA.../video_extracted.m4a
       -> /Volumes/Promise Pegasus/CKandLA.../video.mp4
    2. Direct video: /Volumes/Promise Pegasus/CKandLA.../video.mp4
       -> Returns as-is plus variations
    """
    possible_paths = []

    # Case 1: Extracted audio path
    if '/ExtractedAudio/' in audio_path:
        video_path = audio_path.replace('/ExtractedAudio/', '/')
        video_path = re.sub(r'_extracted\.m4a$', '', video_path, flags=re.IGNORECASE)

        for ext in VIDEO_EXTENSIONS:
            possible_paths.append(video_path + ext)
        possible_paths.append(video_path)

    # Case 2: Direct video path (already has extension)
    else:
        # Add the path as-is first
        possible_paths.append(audio_path)

        # Also try case variations of the extension
        base, ext = os.path.splitext(audio_path)
        if ext:
            possible_paths.append(base + ext.lower())
            possible_paths.append(base + ext.upper())

    return possible_paths

def execute_with_retry(cursor, sql, params=None, max_retries=10, delay=1.0):
    """Execute SQL with retry on database lock."""
    for attempt in range(max_retries):
        try:
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            return True
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < max_retries - 1:
                print(f"  Database locked, retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            else:
                raise
    return False

def main():
    print("=" * 60)
    print("Linking Transcripts to Video Index")
    print("=" * 60)

    # Connect to databases with timeout
    trans_conn = sqlite3.connect(TRANSCRIPTS_DB, timeout=30)
    trans_cursor = trans_conn.cursor()

    index_conn = sqlite3.connect(INDEX_DB, timeout=30)
    index_cursor = index_conn.cursor()

    # Enable WAL mode for better concurrency
    index_cursor.execute("PRAGMA journal_mode=WAL")
    print("Enabled WAL mode for concurrent access")

    # Get all transcripts
    trans_cursor.execute("SELECT id, audio_file_path FROM transcripts")
    transcripts = trans_cursor.fetchall()
    print(f"\nFound {len(transcripts)} transcripts in transcripts.db")

    # Get all video paths from index for faster lookup
    index_cursor.execute("SELECT id, path FROM files")
    all_files = {row[1]: row[0] for row in index_cursor.fetchall()}
    print(f"Found {len(all_files)} files in pegasus_index.db")

    # Reset all has_transcript flags to 0
    print("\nResetting has_transcript flags (may retry if db is busy)...")
    execute_with_retry(index_cursor, "UPDATE files SET has_transcript = 0")
    index_conn.commit()
    print("Reset all has_transcript flags to 0")

    # Match transcripts to videos
    matched = 0
    unmatched = []
    matched_details = []

    for trans_id, audio_path in transcripts:
        if not audio_path:
            unmatched.append(f"[NULL path] transcript_id={trans_id}")
            continue
        possible_paths = audio_path_to_video_path(audio_path)
        found = False

        for video_path in possible_paths:
            if video_path in all_files:
                file_id = all_files[video_path]
                execute_with_retry(
                    index_cursor,
                    "UPDATE files SET has_transcript = 1 WHERE id = ?",
                    (file_id,)
                )
                matched += 1
                matched_details.append((audio_path, video_path))
                found = True
                break

        if not found:
            unmatched.append(audio_path)

    # Commit changes
    index_conn.commit()

    # Report results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"\nMatched transcripts: {matched}")
    print(f"Unmatched transcripts: {len(unmatched)}")

    # Count videos with/without transcripts
    index_cursor.execute("SELECT COUNT(*) FROM files WHERE has_transcript = 1")
    with_trans = index_cursor.fetchone()[0]

    index_cursor.execute("SELECT COUNT(*) FROM files WHERE has_transcript = 0")
    without_trans = index_cursor.fetchone()[0]

    index_cursor.execute("SELECT COUNT(*) FROM files WHERE duration_seconds > 0")
    video_count = index_cursor.fetchone()[0]

    print(f"\nVideos with transcripts: {with_trans}")
    print(f"Videos without transcripts: {without_trans}")
    print(f"Videos (files with duration): {video_count}")

    # Show some unmatched if any
    if unmatched:
        print(f"\nFirst 10 unmatched transcript paths:")
        for path in unmatched[:10]:
            print(f"  - {path}")

    # Show some matched examples
    if matched_details:
        print(f"\nSample matched pairs:")
        for audio, video in matched_details[:5]:
            print(f"  Audio: ...{audio[-60:]}")
            print(f"  Video: ...{video[-60:]}")
            print()

    # Close connections
    trans_conn.close()
    index_conn.close()

    print("=" * 60)
    print("Done! has_transcript flags updated in pegasus_index.db")
    print("=" * 60)

if __name__ == "__main__":
    main()
