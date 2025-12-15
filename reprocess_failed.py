#!/usr/bin/env python3
"""
Re-process failed transcription files (those that were audio_too_large).
Now that chunking is implemented, this will retry all 28 failed files.

Run with nohup for long operations:
nohup python3 reprocess_failed.py > logs/reprocess_$(date +%Y%m%d_%H%M%S).log 2>&1 &
"""

import os
import sys
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
import time

from openai import OpenAI

# Configuration
TRANSCRIPT_DATABASE = "transcripts.db"
COST_ESTIMATE_FILE = "transcription_cost_estimate.json"
PROGRESS_FILE = "logs/transcription_progress.json"
WHISPER_COST_PER_MINUTE = 0.006
MAX_AUDIO_SIZE_MB = 24

def log(msg):
    """Print timestamped message."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    sys.stdout.flush()

def get_openai_client():
    """Get OpenAI client with API key."""
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        zshrc_path = Path.home() / ".zshrc"
        if zshrc_path.exists():
            with open(zshrc_path) as f:
                for line in f:
                    if 'export OPENAI_API_KEY=' in line and 'sk-proj-' in line:
                        api_key = line.split('=', 1)[1].strip().strip('"').strip("'")
                        break

    if not api_key or not api_key.startswith('sk-'):
        raise ValueError("OPENAI_API_KEY not found. Set in environment or ~/.zshrc")

    return OpenAI(api_key=api_key)

def extract_audio(video_path, output_path, max_duration=None):
    """Extract audio from video file."""
    cmd = [
        'ffmpeg', '-y',
        '-i', video_path,
        '-vn',
        '-acodec', 'libmp3lame',
        '-ar', '16000',
        '-ac', '1',
        '-b:a', '32k'
    ]

    if max_duration:
        cmd.extend(['-t', str(max_duration)])

    cmd.append(output_path)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return result.returncode == 0
    except Exception as e:
        log(f"  Error extracting audio: {e}")
        return False

def transcribe_audio(client, audio_path):
    """Transcribe audio file using Whisper API."""
    try:
        with open(audio_path, 'rb') as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
                language="en"
            )
        return transcript
    except Exception as e:
        log(f"  Whisper API error: {e}")
        return None

def calculate_chunk_duration(audio_size_mb, total_duration_seconds):
    """Calculate optimal chunk duration to stay under MAX_AUDIO_SIZE_MB."""
    bytes_per_second = (audio_size_mb * 1024 * 1024) / total_duration_seconds
    target_chunk_mb = MAX_AUDIO_SIZE_MB * 0.95
    target_chunk_bytes = target_chunk_mb * 1024 * 1024
    chunk_duration = target_chunk_bytes / bytes_per_second
    chunk_duration = int(chunk_duration / 60) * 60
    chunk_duration = max(chunk_duration, 300)
    return chunk_duration

def extract_audio_chunk(video_path, output_path, start_time, duration):
    """Extract a specific chunk of audio from video file."""
    cmd = [
        'ffmpeg', '-y',
        '-ss', str(start_time),
        '-i', video_path,
        '-t', str(duration),
        '-vn',
        '-acodec', 'libmp3lame',
        '-ar', '16000',
        '-ac', '1',
        '-b:a', '32k',
        output_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return result.returncode == 0
    except Exception as e:
        log(f"  Error extracting audio chunk: {e}")
        return False

class TranscriptSegment:
    """Simple class to hold segment data."""
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text

class CombinedTranscript:
    """Combined transcript from multiple chunks."""
    def __init__(self):
        self.text = ""
        self.segments = []
        self.language = "en"

def transcribe_chunked_audio(client, audio_path, video_path, total_duration):
    """Transcribe large audio files by splitting into chunks."""
    audio_size_mb = Path(audio_path).stat().st_size / (1024 * 1024)
    chunk_duration = calculate_chunk_duration(audio_size_mb, total_duration)
    num_chunks = int((total_duration + chunk_duration - 1) / chunk_duration)

    log(f"    Chunking strategy: {num_chunks} chunks of ~{chunk_duration/60:.1f} minutes each")

    combined = CombinedTranscript()
    chunk_texts = []

    for chunk_idx in range(num_chunks):
        start_time = chunk_idx * chunk_duration
        duration = min(chunk_duration, total_duration - start_time)

        log(f"    Chunk {chunk_idx+1}/{num_chunks}: {start_time/60:.1f}-{(start_time+duration)/60:.1f} min")

        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_chunk:
            chunk_path = temp_chunk.name

        try:
            if not extract_audio_chunk(video_path, chunk_path, start_time, duration):
                raise Exception(f"Failed to extract chunk {chunk_idx+1}")

            chunk_size_mb = Path(chunk_path).stat().st_size / (1024 * 1024)
            log(f"      Chunk size: {chunk_size_mb:.1f} MB")

            if chunk_size_mb > MAX_AUDIO_SIZE_MB:
                raise Exception(f"Chunk {chunk_idx+1} still too large: {chunk_size_mb:.1f}MB")

            chunk_transcript = transcribe_audio(client, chunk_path)

            if not chunk_transcript:
                raise Exception(f"Failed to transcribe chunk {chunk_idx+1}")

            if hasattr(chunk_transcript, 'segments') and chunk_transcript.segments:
                for seg in chunk_transcript.segments:
                    adjusted_segment = TranscriptSegment(
                        start=seg.start + start_time,
                        end=seg.end + start_time,
                        text=seg.text
                    )
                    combined.segments.append(adjusted_segment)
                    chunk_texts.append(seg.text.strip())
            else:
                chunk_texts.append(chunk_transcript.text.strip())

            log(f"      ✅ Chunk {chunk_idx+1} transcribed")

        finally:
            if Path(chunk_path).exists():
                Path(chunk_path).unlink()

        time.sleep(1)

    combined.text = " ".join(chunk_texts)
    log(f"    ✅ Combined {num_chunks} chunks: {len(combined.segments)} segments, {len(combined.text.split())} words")

    return combined

def store_transcript(transcript_conn, file_path, transcript, duration_seconds, processing_time):
    """Store transcript in central transcripts.db database."""
    cursor = transcript_conn.cursor()
    now = datetime.now().isoformat()

    if hasattr(transcript, 'segments') and transcript.segments:
        full_text = " ".join(seg.text.strip() for seg in transcript.segments)
        segments = transcript.segments
        segment_count = len(segments)
    else:
        full_text = transcript.text
        segments = []
        segment_count = 0

    word_count = len(full_text.split())
    character_count = len(full_text)
    cost = (duration_seconds / 60) * WHISPER_COST_PER_MINUTE

    cursor.execute("""
        INSERT OR REPLACE INTO transcripts (
            audio_file_path, transcript_text, language, duration_seconds,
            whisper_cost, created_at, word_count, character_count,
            whisper_model, transcribed_at, cost_dollars
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        file_path, full_text, 'en', duration_seconds,
        cost, now, word_count, character_count,
        'whisper-1', now, cost
    ))

    transcript_id = cursor.lastrowid

    for i, segment in enumerate(segments):
        cursor.execute("""
            INSERT INTO transcript_segments (
                transcript_id, segment_index, start_time, end_time, text
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            transcript_id, i, segment.start, segment.end, segment.text.strip()
        ))

    transcript_conn.commit()

    return word_count, segment_count, cost

def get_file_duration(file_path):
    """Get video duration using ffprobe."""
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        file_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception as e:
        log(f"  Error getting duration: {e}")

    return None

def process_failed_file(client, transcript_conn, file_path):
    """Re-process a single failed file."""
    filename = os.path.basename(file_path)
    log(f"  Processing: {filename[:60]}")

    if not os.path.exists(file_path):
        log(f"    File not found, skipping")
        return None, "file_not_found"

    # Get duration
    duration_seconds = get_file_duration(file_path)
    if not duration_seconds:
        log(f"    Could not determine duration, skipping")
        return None, "no_duration"

    start_time = time.time()

    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
        temp_audio_path = temp_file.name

    try:
        # Extract audio
        log(f"    Extracting audio...")
        if not extract_audio(file_path, temp_audio_path):
            raise Exception("Audio extraction failed")

        # Check audio file size
        audio_size_mb = Path(temp_audio_path).stat().st_size / (1024 * 1024)
        log(f"    Audio size: {audio_size_mb:.1f} MB")

        # Transcribe (with chunking if needed)
        if audio_size_mb > MAX_AUDIO_SIZE_MB:
            log(f"    Audio too large ({audio_size_mb:.1f}MB > {MAX_AUDIO_SIZE_MB}MB), using chunked transcription")
            transcript = transcribe_chunked_audio(client, temp_audio_path, file_path, duration_seconds)
        else:
            log(f"    Transcribing with Whisper API...")
            transcript = transcribe_audio(client, temp_audio_path)

        if not transcript:
            raise Exception("Whisper API failed")

        # Store in central transcripts.db
        log(f"    Storing transcript in central database...")
        processing_time = time.time() - start_time
        word_count, segment_count, cost = store_transcript(
            transcript_conn, file_path, transcript, duration_seconds, processing_time
        )

        log(f"    ✅ {word_count} words, {segment_count} segments, ${cost:.3f}, {processing_time:.1f}s")

        return cost, "success"

    except Exception as e:
        log(f"    ❌ Failed: {e}")
        return None, str(e)

    finally:
        if Path(temp_audio_path).exists():
            Path(temp_audio_path).unlink()

def main():
    log("="*70)
    log("RE-PROCESS FAILED TRANSCRIPTIONS (CHUNKING ENABLED)")
    log("="*70)

    # Load progress file with failed list
    if not os.path.exists(PROGRESS_FILE):
        log(f"ERROR: {PROGRESS_FILE} not found.")
        sys.exit(1)

    with open(PROGRESS_FILE) as f:
        progress = json.load(f)

    failed_files = progress.get('failed', [])

    if not failed_files:
        log("No failed files to re-process!")
        return

    log(f"Found {len(failed_files)} failed files to re-process")
    log("")

    # Initialize OpenAI client
    log("Initializing OpenAI client...")
    client = get_openai_client()
    log("✅ Client ready")

    # Connect to central transcripts database
    transcript_conn = sqlite3.connect(TRANSCRIPT_DATABASE)

    # Process each failed file
    success_count = 0
    still_failed = []
    session_cost = 0

    for i, file_path in enumerate(failed_files):
        log(f"\n[{i+1}/{len(failed_files)}] {os.path.basename(file_path)}")

        cost, status = process_failed_file(client, transcript_conn, file_path)

        if status == "success":
            success_count += 1
            session_cost += cost
            # Add to completed list
            if file_path not in progress['completed']:
                progress['completed'].append(file_path)
        else:
            # Still failed
            still_failed.append(file_path)
            log(f"    Still failed: {status}")

        # Small delay to avoid rate limiting
        time.sleep(0.5)

    # Update progress file
    progress['failed'] = still_failed
    progress['total_cost'] = progress.get('total_cost', 0) + session_cost

    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)

    # Final summary
    log("\n" + "="*70)
    log("RE-PROCESSING SUMMARY")
    log("="*70)
    log(f"Attempted: {len(failed_files)}")
    log(f"  Success: {success_count}")
    log(f"  Still failed: {len(still_failed)}")
    log(f"Session cost: ${session_cost:.2f}")

    # Get transcript stats from central database
    cursor = transcript_conn.cursor()
    cursor.execute("SELECT COUNT(*), SUM(word_count) FROM transcripts")
    transcript_count, total_words = cursor.fetchone()
    log(f"\nCentral database stats:")
    log(f"  Total transcripts: {transcript_count}")
    log(f"  Total words: {total_words or 0:,}")

    transcript_conn.close()
    log("\n✅ Re-processing complete!")

if __name__ == "__main__":
    main()
