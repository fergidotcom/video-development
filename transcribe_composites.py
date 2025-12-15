#!/usr/bin/env python3
"""
Transcribe finished composites from Pegasus archive.
Uses Whisper API to transcribe the 130 identified composite videos.

Run with nohup for long operations:
nohup python3 transcribe_composites.py > logs/transcribe_$(date +%Y%m%d_%H%M%S).log 2>&1 &
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
TRANSCRIPT_DATABASE = "transcripts.db"  # Central transcript database
SURVEY_DATABASE = "pegasus-survey.db"   # For updating composite status
COST_ESTIMATE_FILE = "transcription_cost_estimate.json"
WHISPER_COST_PER_MINUTE = 0.006
MAX_AUDIO_SIZE_MB = 24  # Whisper limit is 25MB

# Progress tracking
PROGRESS_FILE = "logs/transcription_progress.json"

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

def save_progress(progress):
    """Save progress to file."""
    os.makedirs("logs", exist_ok=True)
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)

def load_progress():
    """Load progress from file."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"completed": [], "failed": [], "skipped": [], "total_cost": 0}

def get_existing_transcripts(conn):
    """Get set of already-transcribed file paths from central database."""
    cursor = conn.cursor()
    cursor.execute("SELECT audio_file_path FROM transcripts")
    return set(row[0] for row in cursor.fetchall())

def store_transcript(transcript_conn, file_path, transcript, duration_seconds, processing_time):
    """Store transcript in central transcripts.db database."""
    cursor = transcript_conn.cursor()
    now = datetime.now().isoformat()

    # Extract data from transcript
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

    # Insert into central transcripts table
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

    # Insert segments
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

def process_composite(client, transcript_conn, file_path, duration_seconds):
    """Process a single composite video."""
    filename = os.path.basename(file_path)
    log(f"  Processing: {filename[:60]}")

    if not os.path.exists(file_path):
        log(f"    File not found, skipping")
        return None, "file_not_found"

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

        if audio_size_mb > MAX_AUDIO_SIZE_MB:
            log(f"    Audio too large ({audio_size_mb:.1f}MB > {MAX_AUDIO_SIZE_MB}MB), chunking required")
            # For now, skip files that are too large
            # TODO: Implement chunking
            return None, "audio_too_large"

        # Transcribe
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
    log("COMPOSITE TRANSCRIPTION PIPELINE")
    log("Using central transcripts.db database")
    log("="*70)

    # Load cost estimate with file list
    if not os.path.exists(COST_ESTIMATE_FILE):
        log(f"ERROR: {COST_ESTIMATE_FILE} not found. Run calculate_transcription_cost.py first.")
        sys.exit(1)

    with open(COST_ESTIMATE_FILE) as f:
        cost_data = json.load(f)

    composites = cost_data['composites']
    total_hours = cost_data['total_duration_hours']
    estimated_cost = cost_data['estimated_cost_usd']

    log(f"Total composites in list: {len(composites)}")
    log(f"Total duration: {total_hours:.1f} hours")
    log(f"Estimated cost (full): ${estimated_cost:.2f}")
    log("")

    # Initialize OpenAI client
    log("Initializing OpenAI client...")
    client = get_openai_client()
    log("✅ Client ready")

    # Connect to central transcripts database
    transcript_conn = sqlite3.connect(TRANSCRIPT_DATABASE)

    # Get already-transcribed files from central database
    existing_transcripts = get_existing_transcripts(transcript_conn)
    log(f"Already transcribed in central database: {len(existing_transcripts)}")

    # Load local progress (for tracking this session)
    progress = load_progress()
    failed_paths = set(progress.get('failed', []))
    log(f"Previously failed (this pipeline): {len(failed_paths)}")
    log("")

    # Filter to only pending (not in central DB and not failed)
    pending = []
    already_done = 0
    for c in composites:
        if c['path'] in existing_transcripts:
            already_done += 1
        elif c['path'] not in failed_paths:
            pending.append(c)

    log(f"Already transcribed (skipping): {already_done}")
    log(f"Remaining to process: {len(pending)}")

    if not pending:
        log("\n✅ All composites already transcribed!")
        transcript_conn.close()
        return

    # Calculate remaining cost
    remaining_minutes = sum(c['duration_sec'] / 60 for c in pending)
    remaining_cost = remaining_minutes * WHISPER_COST_PER_MINUTE
    log(f"Remaining duration: {remaining_minutes / 60:.1f} hours")
    log(f"Remaining cost: ${remaining_cost:.2f}")
    log("="*70)

    # Process composites
    success_count = 0
    fail_count = 0
    session_cost = 0

    for i, comp in enumerate(pending):
        file_path = comp['path']
        duration = comp['duration_sec']

        log(f"\n[{i+1}/{len(pending)}] {os.path.basename(file_path)}")

        cost, status = process_composite(client, transcript_conn, file_path, duration)

        if status == "success":
            progress['completed'].append(file_path)
            success_count += 1
            session_cost += cost
            progress['total_cost'] = progress.get('total_cost', 0) + cost
        else:
            progress['failed'].append(file_path)
            fail_count += 1

        # Save progress after each file
        save_progress(progress)

        # Small delay to avoid rate limiting
        time.sleep(0.5)

    # Final summary
    log("\n" + "="*70)
    log("TRANSCRIPTION SUMMARY")
    log("="*70)
    log(f"Processed this session: {success_count + fail_count}")
    log(f"  Success: {success_count}")
    log(f"  Failed: {fail_count}")
    log(f"Session cost: ${session_cost:.2f}")

    # Get transcript stats from central database
    cursor = transcript_conn.cursor()
    cursor.execute("SELECT COUNT(*), SUM(word_count) FROM transcripts")
    transcript_count, total_words = cursor.fetchone()
    log(f"\nCentral database stats:")
    log(f"  Total transcripts: {transcript_count}")
    log(f"  Total words: {total_words or 0:,}")

    transcript_conn.close()
    log("\n✅ Transcription pipeline complete!")

if __name__ == "__main__":
    main()
