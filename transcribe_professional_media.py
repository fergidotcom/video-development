#!/usr/bin/env python3 -u
"""
Transcribe CKFergusonProfessionalMedia files
OD lectures, UCLA seminars, and professional development content from Charles Ferguson.
"""

import sys
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

import os
import sys
import sqlite3
import signal
import time
from datetime import datetime
from pathlib import Path
from openai import OpenAI

# Configuration
PROFESSIONAL_MEDIA_DIR = "/Volumes/Promise Pegasus/ExtractedAudio/CKandLAFergusonFamilyArchive/Charles Kasreal and Lois Adelaid Ferguson/CKFergusonProfessionalMedia"
TRANSCRIPTS_DB = os.path.expanduser("~/Library/CloudStorage/Dropbox/Fergi/VideoDev/transcripts.db")
WHISPER_COST_PER_MINUTE = 0.006

# Global shutdown flag
shutdown_requested = False

def signal_handler(signum, frame):
    global shutdown_requested
    print(f"\n⚠️  Shutdown signal received. Finishing current file...")
    shutdown_requested = True

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def get_openai_client():
    """Get OpenAI client with API key."""
    api_key = os.environ.get("OPENAI_API_KEY")

    # Always try to get from ~/.zshrc to find the LAST (most recent) key
    zshrc_path = Path.home() / ".zshrc"
    if zshrc_path.exists():
        with open(zshrc_path) as f:
            for line in f:
                if 'export OPENAI_API_KEY=' in line and 'sk-proj-' in line:
                    candidate = line.split('=', 1)[1].strip().strip('"').strip("'")
                    if candidate.startswith('sk-proj-'):
                        api_key = candidate  # Keep updating to get LAST match

    if not api_key or api_key == "sk-REPLACE_ME" or not api_key.startswith('sk-'):
        raise ValueError("OPENAI_API_KEY not found. Set in environment or ~/.zshrc")

    return OpenAI(api_key=api_key)


def get_audio_files():
    """Get all .m4a files from the Professional Media directory."""
    path = Path(PROFESSIONAL_MEDIA_DIR)
    if not path.exists():
        print(f"❌ Directory not found: {PROFESSIONAL_MEDIA_DIR}")
        print("   Make sure Promise Pegasus drive is connected.")
        return []

    files = sorted(path.glob("*.m4a"))
    print(f"📋 Found {len(files)} audio files in CKFergusonProfessionalMedia")
    return files


def get_already_transcribed():
    """Get set of audio paths already in database."""
    conn = sqlite3.connect(TRANSCRIPTS_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT audio_file_path FROM transcripts")
    completed = {row[0] for row in cursor.fetchall()}
    conn.close()
    return completed


def get_audio_duration(file_path):
    """Get audio duration using ffprobe."""
    import subprocess
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', str(file_path)
        ], capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except:
        return 0


def transcribe_file(client, audio_path):
    """Transcribe a single audio file using Whisper API."""
    print(f"   🎤 Calling Whisper API...")
    start_time = time.time()

    with open(audio_path, 'rb') as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
            language="en"
        )

    elapsed = time.time() - start_time
    print(f"   ✅ Transcribed in {elapsed:.1f}s")
    return transcript


def store_transcript(audio_path, transcript, duration_seconds):
    """Store transcript and segments in database."""
    conn = sqlite3.connect(TRANSCRIPTS_DB)
    cursor = conn.cursor()

    # Build full text from segments
    if hasattr(transcript, 'segments') and transcript.segments:
        full_text = " ".join(seg.text.strip() for seg in transcript.segments)
    else:
        full_text = transcript.text if hasattr(transcript, 'text') else ""

    word_count = len(full_text.split())
    cost = (duration_seconds / 60) * WHISPER_COST_PER_MINUTE

    # Insert transcript
    cursor.execute("""
        INSERT INTO transcripts
        (audio_file_path, transcript_text, language, duration_seconds,
         whisper_cost, created_at, word_count, character_count, whisper_model, cost_dollars)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(audio_path),
        full_text,
        'en',
        duration_seconds,
        cost,
        datetime.now().isoformat(),
        word_count,
        len(full_text),
        'whisper-1',
        cost
    ))

    transcript_id = cursor.lastrowid

    # Insert segments with timestamps
    if hasattr(transcript, 'segments') and transcript.segments:
        for i, seg in enumerate(transcript.segments):
            cursor.execute("""
                INSERT INTO transcript_segments
                (transcript_id, segment_index, start_time, end_time, text)
                VALUES (?, ?, ?, ?, ?)
            """, (
                transcript_id,
                i,
                seg.start,
                seg.end,
                seg.text.strip()
            ))

    conn.commit()
    conn.close()

    return transcript_id, word_count, cost


def main():
    global shutdown_requested

    print("="*70)
    print("CKFergusonProfessionalMedia Transcription")
    print("OD Lectures, UCLA Seminars, and Professional Content")
    print("="*70)
    print()

    # Get OpenAI client
    print("Initializing OpenAI client...")
    try:
        client = get_openai_client()
        print("✅ OpenAI client ready\n")
    except Exception as e:
        print(f"❌ Failed to initialize OpenAI: {e}")
        return

    # Get audio files
    audio_files = get_audio_files()
    if not audio_files:
        return

    # Get already transcribed
    already_done = get_already_transcribed()

    # Filter to files needing transcription
    to_transcribe = [f for f in audio_files if str(f) not in already_done]
    print(f"📊 Already transcribed: {len(already_done)}")
    print(f"📋 To transcribe: {len(to_transcribe)}")
    print()

    if not to_transcribe:
        print("✅ All files already transcribed!")
        return

    # Process files
    total_cost = 0
    total_words = 0

    for i, audio_path in enumerate(to_transcribe):
        if shutdown_requested:
            print("\n⚠️  Shutdown requested. Exiting gracefully.")
            break

        filename = audio_path.name
        print(f"\n[{i+1}/{len(to_transcribe)}] {filename}")

        # Get duration
        duration = get_audio_duration(audio_path)
        est_cost = (duration / 60) * WHISPER_COST_PER_MINUTE
        print(f"   📏 Duration: {duration/60:.1f} min | Est. cost: ${est_cost:.3f}")

        try:
            # Transcribe
            transcript = transcribe_file(client, audio_path)

            # Store
            transcript_id, word_count, cost = store_transcript(audio_path, transcript, duration)

            total_cost += cost
            total_words += word_count

            print(f"   💾 Stored: {word_count} words | ${cost:.3f}")

        except Exception as e:
            print(f"   ❌ Error: {e}")
            continue

    # Summary
    print("\n" + "="*70)
    print("TRANSCRIPTION COMPLETE")
    print("="*70)
    print(f"Files transcribed: {len(to_transcribe) - (1 if shutdown_requested else 0)}")
    print(f"Total words: {total_words:,}")
    print(f"Total cost: ${total_cost:.2f}")
    print()


if __name__ == "__main__":
    main()
