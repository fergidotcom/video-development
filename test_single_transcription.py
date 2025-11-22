#!/usr/bin/env python3
"""Test transcription on a single video."""

import sqlite3
from transcribe import get_openai_client, process_video

# Test with video ID 17 (shortest video - about 12 minutes)
VIDEO_ID = 17

def test_single():
    print("="*80)
    print("TESTING SINGLE VIDEO TRANSCRIPTION")
    print("="*80)
    print()

    # Get OpenAI client
    print("Initializing OpenAI client...")
    client = get_openai_client()
    print("✅ Client ready\n")

    # Connect to database
    conn = sqlite3.connect("video-archive.db")
    cursor = conn.cursor()

    # Get video details
    cursor.execute("""
        SELECT id, file_path, filename, duration_seconds
        FROM videos
        WHERE id = ?
    """, (VIDEO_ID,))

    video = cursor.fetchone()
    if not video:
        print(f"❌ Video ID {VIDEO_ID} not found")
        return

    video_id, file_path, filename, duration_seconds = video

    print(f"Test video:")
    print(f"  ID: {video_id}")
    print(f"  File: {filename}")
    print(f"  Duration: {duration_seconds / 60:.2f} minutes")
    print(f"  Path: {file_path}")
    print()

    # Process the video
    success = process_video(client, conn, video_id, file_path, filename)

    if success:
        # Check results
        cursor.execute("""
            SELECT transcript_text, word_count
            FROM transcripts
            WHERE video_id = ?
        """, (video_id,))

        result = cursor.fetchone()
        if result:
            transcript, word_count = result
            print()
            print("="*80)
            print("TRANSCRIPT PREVIEW")
            print("="*80)
            print(transcript[:500] + "..." if len(transcript) > 500 else transcript)
            print()
            print(f"Total words: {word_count}")

    conn.close()

if __name__ == "__main__":
    test_single()
