#!/usr/bin/env python3
"""
Transcription pipeline for video archive.
Processes videos through Whisper API and stores transcripts in database.
"""

import os
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
import time

# OpenAI library
from openai import OpenAI

DATABASE_PATH = "video-archive.db"
WHISPER_COST_PER_MINUTE = 0.006

# Initialize OpenAI client
def get_openai_client():
    """Get OpenAI client with API key from environment."""
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key or api_key == "sk-REPLACE_ME":
        # Try loading from ~/.zshrc if not in environment
        zshrc_path = Path.home() / ".zshrc"
        if zshrc_path.exists():
            with open(zshrc_path) as f:
                content = f.read()
                # Find all OPENAI_API_KEY exports
                for line in content.split('\n'):
                    if 'export OPENAI_API_KEY=' in line and 'sk-proj-' in line:
                        # Extract the key (handle quotes)
                        api_key = line.split('=', 1)[1].strip()
                        api_key = api_key.strip('"').strip("'")
                        if api_key.startswith('sk-proj-'):
                            break

    if not api_key or api_key == "sk-REPLACE_ME" or not api_key.startswith('sk-'):
        raise ValueError("OPENAI_API_KEY not found or invalid. Please set it in your environment or ~/.zshrc")

    return OpenAI(api_key=api_key)

def extract_audio(video_path, output_path):
    """Extract audio from video file to temporary file."""

    try:
        result = subprocess.run([
            'ffmpeg',
            '-i', video_path,
            '-vn',  # No video
            '-acodec', 'libmp3lame',  # MP3 codec
            '-ar', '16000',  # 16kHz sample rate (Whisper recommendation)
            '-ac', '1',  # Mono
            '-b:a', '32k',  # 32kbps bitrate (sufficient for speech)
            '-y',  # Overwrite
            output_path
        ], capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            print(f"      ffmpeg error: {result.stderr[:200]}")
            return False

        return True

    except Exception as e:
        print(f"      Exception during audio extraction: {e}")
        return False

def transcribe_audio(client, audio_path):
    """Transcribe audio file using Whisper API."""

    try:
        with open(audio_path, 'rb') as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",  # Includes segments with timestamps
                language="en"  # Assume English for now
            )

        return transcript

    except Exception as e:
        print(f"      Whisper API error: {e}")
        return None

def store_transcript(conn, video_id, transcript, processing_time):
    """Store transcript and segments in database."""

    cursor = conn.cursor()
    now = datetime.now().isoformat()

    # Build full transcript text from segments
    # The Whisper API returns objects, not dicts
    if hasattr(transcript, 'segments') and transcript.segments:
        full_text = " ".join(seg.text.strip() for seg in transcript.segments)
        segments = transcript.segments
    else:
        full_text = transcript.text
        segments = []

    # Calculate statistics
    word_count = len(full_text.split())
    character_count = len(full_text)

    # Get video duration for cost calculation
    cursor.execute("SELECT duration_seconds FROM videos WHERE id = ?", (video_id,))
    duration_seconds = cursor.fetchone()[0]
    cost = (duration_seconds / 60) * WHISPER_COST_PER_MINUTE

    # Insert transcript
    cursor.execute("""
        INSERT INTO transcripts (
            video_id, transcript_text, language,
            whisper_model, word_count, character_count,
            processing_duration_seconds, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        video_id, full_text, 'en',
        'whisper-1', word_count, character_count,
        processing_time, now
    ))

    transcript_id = cursor.lastrowid

    # Insert segments (if available)
    if segments:
        for segment in segments:
            cursor.execute("""
                INSERT INTO transcript_segments (
                    transcript_id, start_time, end_time, text
                ) VALUES (?, ?, ?, ?)
            """, (
                transcript_id,
                segment.start,
                segment.end,
                segment.text.strip()
            ))

    # Update video status
    cursor.execute("""
        UPDATE videos
        SET transcription_status = 'complete',
            transcription_cost = ?,
            transcribed_at = ?,
            updated_at = ?
        WHERE id = ?
    """, (cost, now, now, video_id))

    conn.commit()

    return word_count, len(segments)

def process_video(client, conn, video_id, file_path, filename):
    """Process a single video through the transcription pipeline."""

    print(f"   🎬 {filename[:60]}")

    start_time = time.time()

    # Create temporary file for audio
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
        temp_audio_path = temp_file.name

    try:
        # Step 1: Extract audio
        print(f"      Extracting audio...")
        if not extract_audio(file_path, temp_audio_path):
            raise Exception("Audio extraction failed")

        # Check file size (Whisper API limit is 25MB)
        audio_size_mb = Path(temp_audio_path).stat().st_size / (1024 * 1024)
        if audio_size_mb > 24:
            print(f"      ⚠️  Audio file is {audio_size_mb:.2f} MB (may need chunking)")
            # For now, proceed anyway - Whisper often accepts slightly larger files
            # TODO: Implement chunking for very large files

        # Step 2: Transcribe with Whisper API
        print(f"      Transcribing with Whisper API...")
        transcript = transcribe_audio(client, temp_audio_path)

        if not transcript:
            raise Exception("Whisper API failed")

        # Step 3: Store in database
        print(f"      Storing transcript...")
        processing_time = time.time() - start_time
        word_count, segment_count = store_transcript(conn, video_id, transcript, processing_time)

        print(f"      ✅ Complete! {word_count} words, {segment_count} segments, {processing_time:.1f}s")

        return True

    except Exception as e:
        print(f"      ❌ Failed: {e}")

        # Update video status as failed
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute("""
            UPDATE videos
            SET transcription_status = 'failed',
                notes = ?,
                updated_at = ?
            WHERE id = ?
        """, (str(e), now, video_id))
        conn.commit()

        return False

    finally:
        # Clean up temporary file
        if Path(temp_audio_path).exists():
            Path(temp_audio_path).unlink()

def transcribe_all():
    """Transcribe all pending Phase 1 videos."""

    print(f"\n{'='*80}")
    print(f"VIDEO TRANSCRIPTION PIPELINE")
    print(f"{'='*80}\n")

    # Initialize OpenAI client
    print("Initializing OpenAI client...")
    client = get_openai_client()
    print("✅ OpenAI client ready\n")

    # Connect to database
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # Get all videos ready for transcription (have duration, not yet transcribed)
    cursor.execute("""
        SELECT id, file_path, filename, directory, duration_seconds
        FROM videos
        WHERE priority = 'high'
          AND duration_seconds IS NOT NULL
          AND transcription_status IN ('pending', 'failed')
        ORDER BY directory, filename
    """)

    videos = cursor.fetchall()

    if not videos:
        print("No videos need transcription.")
        conn.close()
        return

    total_duration = sum(v[4] for v in videos)
    estimated_cost = (total_duration / 60) * WHISPER_COST_PER_MINUTE

    print(f"Videos to process: {len(videos)}")
    print(f"Total duration: {total_duration / 60:.2f} minutes ({total_duration / 3600:.2f} hours)")
    print(f"Estimated cost: ${estimated_cost:.2f}\n")

    # Process videos
    success_count = 0
    error_count = 0
    current_directory = None

    for video_id, file_path, filename, directory, duration_seconds in videos:

        # Print directory header when it changes
        if directory != current_directory:
            if current_directory is not None:
                print()
            print(f"📁 {directory}")
            current_directory = directory

        # Process video
        if process_video(client, conn, video_id, file_path, filename):
            success_count += 1
        else:
            error_count += 1

    # Print summary
    print(f"\n{'='*80}")
    print(f"TRANSCRIPTION SUMMARY")
    print(f"{'='*80}\n")

    # Get final statistics
    cursor.execute("""
        SELECT COUNT(*), SUM(transcription_cost)
        FROM videos
        WHERE transcription_status = 'complete'
    """)
    complete_count, total_cost = cursor.fetchone()

    cursor.execute("""
        SELECT SUM(word_count), COUNT(*)
        FROM transcripts
    """)
    total_words, transcript_count = cursor.fetchone()

    print(f"Processing complete:")
    print(f"  ✅ Success: {success_count}")
    print(f"  ❌ Errors: {error_count}")

    if complete_count:
        print(f"\nOverall statistics:")
        print(f"  - Videos transcribed: {complete_count}")
        print(f"  - Total words: {total_words:,}")
        print(f"  - Total cost: ${total_cost:.2f}")

    conn.close()

    print(f"\n✅ Transcription pipeline complete!\n")

if __name__ == "__main__":
    transcribe_all()
