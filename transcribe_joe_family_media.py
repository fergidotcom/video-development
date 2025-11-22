#!/usr/bin/env python3
"""
Transcribe first 25 audio files from Joe Ferguson Family Media folder.
Uses Whisper API to generate transcripts and stores in database.
"""

import os
import json
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime
import time

# OpenAI library
from openai import OpenAI

DB_PATH = Path(__file__).parent / "transcripts.db"
AUDIO_ROOT = Path("/Volumes/Promise Pegasus/ExtractedAudio/CKandLAFergusonFamilyArchive/Joseph Glenn Ferguson Family/Joe Ferguson Family Media")
WHISPER_COST_PER_MINUTE = 0.006
MAX_FILES = 25

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
                for line in content.split('\n'):
                    if 'export OPENAI_API_KEY=' in line and 'sk-proj-' in line:
                        api_key = line.split('=', 1)[1].strip()
                        api_key = api_key.strip('"').strip("'")
                        if api_key.startswith('sk-proj-'):
                            break

    if not api_key or api_key == "sk-REPLACE_ME" or not api_key.startswith('sk-'):
        raise ValueError("OPENAI_API_KEY not found. Please set in environment or ~/.zshrc")

    return OpenAI(api_key=api_key)

def get_audio_duration(audio_path):
    """Get audio duration in seconds using ffprobe."""
    try:
        result = subprocess.run([
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            str(audio_path)
        ], capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            data = json.loads(result.stdout)
            return float(data.get('format', {}).get('duration', 0))
        return 0
    except Exception:
        return 0

def transcribe_audio(client, audio_path):
    """Transcribe audio file using Whisper API."""
    try:
        with open(audio_path, 'rb') as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                language="en"
            )
        return transcript
    except Exception as e:
        print(f"   ❌ Whisper API error: {e}")
        return None

def get_db_connection():
    """Get database connection with timeout for locks."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn

def store_transcript(conn, audio_file_path, transcript, duration, cost):
    """Store transcript in database."""
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    # Build full text from segments
    if hasattr(transcript, 'segments') and transcript.segments:
        full_text = " ".join(seg.text.strip() for seg in transcript.segments)
    else:
        full_text = transcript.text if hasattr(transcript, 'text') else ""

    # Insert transcript record
    cursor.execute("""
        INSERT INTO transcripts (
            audio_file_path, transcript_text, language,
            duration_seconds, whisper_cost, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (audio_file_path, full_text, "en", duration, cost, now))

    transcript_id = cursor.lastrowid

    # Store segments if available
    if hasattr(transcript, 'segments') and transcript.segments:
        for seg in transcript.segments:
            cursor.execute("""
                INSERT INTO transcript_segments (
                    transcript_id, segment_index, start_time,
                    end_time, text
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                transcript_id,
                seg.id,
                seg.start,
                seg.end,
                seg.text.strip()
            ))

    conn.commit()
    return transcript_id

def ensure_transcript_tables(conn):
    """Create transcript tables if they don't exist."""
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY,
            audio_file_path TEXT UNIQUE,
            transcript_text TEXT,
            language TEXT,
            duration_seconds REAL,
            whisper_cost REAL,
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transcript_segments (
            id INTEGER PRIMARY KEY,
            transcript_id INTEGER,
            segment_index INTEGER,
            start_time REAL,
            end_time REAL,
            text TEXT,
            FOREIGN KEY (transcript_id) REFERENCES transcripts(id)
        )
    """)

    conn.commit()

def main():
    print("\n" + "="*70)
    print("TRANSCRIBE JOE FERGUSON FAMILY MEDIA (First 25 Files)")
    print("="*70)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Audio directory: {AUDIO_ROOT}")
    print("="*70 + "\n")

    if not AUDIO_ROOT.exists():
        print(f"❌ Error: Directory not found: {AUDIO_ROOT}")
        return False

    # Get OpenAI client
    try:
        client = get_openai_client()
        print("✅ OpenAI client initialized\n")
    except Exception as e:
        print(f"❌ Failed to initialize OpenAI client: {e}")
        return False

    # Connect to database
    conn = get_db_connection()
    ensure_transcript_tables(conn)
    cursor = conn.cursor()

    # Find first 25 audio files
    audio_files = sorted(AUDIO_ROOT.rglob("*_extracted.*"))[:MAX_FILES]

    if not audio_files:
        print("❌ No audio files found")
        return False

    print(f"Found {len(audio_files)} audio files to transcribe\n")

    stats = {
        'transcribed': 0,
        'skipped': 0,
        'failed': 0,
        'total_cost': 0.0,
        'total_duration': 0.0
    }

    for i, audio_path in enumerate(audio_files, 1):
        print(f"[{i}/{len(audio_files)}] {audio_path.name}")

        # Check if already transcribed
        cursor.execute("""
            SELECT id FROM transcripts WHERE audio_file_path = ?
        """, (str(audio_path),))

        if cursor.fetchone():
            print("   ⏭️  Already transcribed, skipping")
            stats['skipped'] += 1
            continue

        # Use audio path as identifier (no need to join with pegasus-survey.db)
        audio_file_id = str(audio_path)

        # Get duration
        duration = get_audio_duration(audio_path)
        if duration == 0:
            print("   ⚠️  Could not determine duration, skipping")
            stats['skipped'] += 1
            continue

        duration_min = duration / 60.0
        cost = duration_min * WHISPER_COST_PER_MINUTE

        print(f"   📊 Duration: {duration_min:.2f} min | Cost: ${cost:.4f}")

        # Transcribe
        print("   🎤 Transcribing...")
        start_time = time.time()
        transcript = transcribe_audio(client, audio_path)
        elapsed = time.time() - start_time

        if transcript:
            # Store in database
            transcript_id = store_transcript(conn, audio_file_id, transcript, duration, cost)
            stats['transcribed'] += 1
            stats['total_cost'] += cost
            stats['total_duration'] += duration_min

            # Preview first 100 chars
            preview = transcript.text[:100] if hasattr(transcript, 'text') else ""
            print(f"   ✅ Transcribed in {elapsed:.1f}s (ID: {transcript_id})")
            print(f"   📝 Preview: {preview}...")
        else:
            stats['failed'] += 1
            print("   ❌ Transcription failed")

        print()

    # Summary
    print("="*70)
    print("TRANSCRIPTION COMPLETE")
    print("="*70)
    print(f"✅ Transcribed: {stats['transcribed']}")
    print(f"⏭️  Skipped: {stats['skipped']}")
    print(f"❌ Failed: {stats['failed']}")
    print(f"💰 Total cost: ${stats['total_cost']:.2f}")
    print(f"⏱️  Total duration: {stats['total_duration']:.1f} minutes")
    print("="*70 + "\n")

    conn.close()
    return True

if __name__ == "__main__":
    main()
