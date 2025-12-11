#!/usr/bin/env python3 -u
"""
Transcribe large CKFergusonProfessionalMedia files
Compresses audio to under 25MB before sending to Whisper API.
"""

import sys
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

import os
import sqlite3
import signal
import time
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from openai import OpenAI

# Configuration
PROFESSIONAL_MEDIA_DIR = "/Volumes/Promise Pegasus/ExtractedAudio/CKandLAFergusonFamilyArchive/Charles Kasreal and Lois Adelaid Ferguson/CKFergusonProfessionalMedia"
TRANSCRIPTS_DB = os.path.expanduser("~/Library/CloudStorage/Dropbox/Fergi/VideoDev/transcripts.db")
WHISPER_COST_PER_MINUTE = 0.006
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB

# Files that failed due to size
LARGE_FILES = [
    "Sensitivity Training and Encounter Groups on Public TV in 1969 - Charles K Ferguson_extracted.m4a",
    "V0402 R5 Constructive Use of the Emotions - Sherman Kingsbury_extracted.m4a",
    "V0403 R5 Organization Development Seminar at UCLA  - Charles K Ferguson - Part 1_extracted.m4a",
    "V0404 R5 Organization Development Seminar at UCLA  - Charles K Ferguson - Part 2_extracted.m4a",
    "V0405 R5 Organization Development Seminar at UCLA  - Charles K Ferguson - Part 3_extracted.m4a",
    "V0408 R5 Leadership Lab General Session - Sheldon Davis_extracted.m4a",
    "V0409 R5 Overview of OD Tony Raia_extracted.m4a",
    "V0410 R5 Organization Development at Saga - William J. Crockett and Sherman Moore - Part 1_extracted.m4a",
    "V0411 R5 Organization Development at Saga - William J. Crockett  and Sherman Moore - Part 2_extracted.m4a",
    "V0552 F2 Leadership Laboratory - George H. Lainer_extracted.m4a",
]

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
    api_key = None
    zshrc_path = Path.home() / ".zshrc"
    if zshrc_path.exists():
        with open(zshrc_path) as f:
            for line in f:
                if 'export OPENAI_API_KEY=' in line and 'sk-proj-' in line:
                    candidate = line.split('=', 1)[1].strip().strip('"').strip("'")
                    if candidate.startswith('sk-proj-'):
                        api_key = candidate

    if not api_key:
        raise ValueError("OPENAI_API_KEY not found")
    return OpenAI(api_key=api_key)


def compress_audio(input_path, max_size=MAX_FILE_SIZE):
    """Compress audio file to be under max_size using ffmpeg."""
    input_size = os.path.getsize(input_path)

    if input_size <= max_size:
        return input_path, False  # No compression needed

    # Get duration
    result = subprocess.run([
        'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', str(input_path)
    ], capture_output=True, text=True, timeout=30)
    duration = float(result.stdout.strip())

    # Calculate target bitrate (aim for 22MB to have margin)
    target_size = 22 * 1024 * 1024  # 22MB
    target_bitrate = int((target_size * 8) / duration)  # bits per second
    target_kbps = max(16, min(target_bitrate // 1000, 64))  # 16-64 kbps range

    print(f"   🗜️  Compressing: {input_size/1024/1024:.1f}MB → target {target_kbps}kbps")

    # Create temp file
    temp_file = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
    temp_path = temp_file.name
    temp_file.close()

    # Compress with ffmpeg
    result = subprocess.run([
        'ffmpeg', '-y', '-i', str(input_path),
        '-vn',  # No video
        '-acodec', 'libmp3lame',
        '-ar', '16000',  # 16kHz (Whisper optimal)
        '-ac', '1',  # Mono
        '-b:a', f'{target_kbps}k',
        temp_path
    ], capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        print(f"   ❌ Compression failed: {result.stderr[:200]}")
        os.unlink(temp_path)
        return None, False

    compressed_size = os.path.getsize(temp_path)
    print(f"   ✅ Compressed to {compressed_size/1024/1024:.1f}MB")

    return temp_path, True


def get_audio_duration(file_path):
    """Get audio duration using ffprobe."""
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', str(file_path)
        ], capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except:
        return 0


def get_already_transcribed():
    """Get set of audio paths already in database."""
    conn = sqlite3.connect(TRANSCRIPTS_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT audio_file_path FROM transcripts")
    completed = {row[0] for row in cursor.fetchall()}
    conn.close()
    return completed


def transcribe_file(client, audio_path):
    """Transcribe audio file using Whisper API."""
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


def store_transcript(original_path, transcript, duration_seconds):
    """Store transcript in database."""
    conn = sqlite3.connect(TRANSCRIPTS_DB)
    cursor = conn.cursor()

    if hasattr(transcript, 'segments') and transcript.segments:
        full_text = " ".join(seg.text.strip() for seg in transcript.segments)
    else:
        full_text = transcript.text if hasattr(transcript, 'text') else ""

    word_count = len(full_text.split())
    cost = (duration_seconds / 60) * WHISPER_COST_PER_MINUTE

    cursor.execute("""
        INSERT INTO transcripts
        (audio_file_path, transcript_text, language, duration_seconds,
         whisper_cost, created_at, word_count, character_count, whisper_model, cost_dollars)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(original_path),
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

    # Store segments
    if hasattr(transcript, 'segments') and transcript.segments:
        for i, seg in enumerate(transcript.segments):
            cursor.execute("""
                INSERT INTO transcript_segments
                (transcript_id, segment_index, start_time, end_time, text)
                VALUES (?, ?, ?, ?, ?)
            """, (transcript_id, i, seg.start, seg.end, seg.text.strip()))

    conn.commit()
    conn.close()

    return transcript_id, word_count, cost


def main():
    global shutdown_requested

    print("="*70)
    print("Large Professional Media Transcription (with compression)")
    print("="*70)
    print()

    # Get OpenAI client
    print("Initializing OpenAI client...")
    try:
        client = get_openai_client()
        print("✅ OpenAI client ready\n")
    except Exception as e:
        print(f"❌ Failed: {e}")
        return

    # Get already transcribed
    already_done = get_already_transcribed()

    # Filter to files needing transcription
    base_path = Path(PROFESSIONAL_MEDIA_DIR)
    to_transcribe = []
    for filename in LARGE_FILES:
        full_path = base_path / filename
        if full_path.exists() and str(full_path) not in already_done:
            to_transcribe.append(full_path)

    print(f"📋 Large files to transcribe: {len(to_transcribe)}")
    print()

    if not to_transcribe:
        print("✅ All large files already transcribed!")
        return

    total_cost = 0
    total_words = 0

    for i, audio_path in enumerate(to_transcribe):
        if shutdown_requested:
            print("\n⚠️  Shutdown requested. Exiting.")
            break

        filename = audio_path.name
        print(f"\n[{i+1}/{len(to_transcribe)}] {filename}")

        duration = get_audio_duration(audio_path)
        print(f"   📏 Duration: {duration/60:.1f} min")

        try:
            # Compress if needed
            compressed_path, was_compressed = compress_audio(audio_path)
            if compressed_path is None:
                continue

            # Transcribe
            transcript = transcribe_file(client, compressed_path)

            # Store (with original path as reference)
            transcript_id, word_count, cost = store_transcript(audio_path, transcript, duration)

            total_cost += cost
            total_words += word_count

            print(f"   💾 Stored: {word_count} words | ${cost:.3f}")

            # Clean up temp file
            if was_compressed and os.path.exists(compressed_path):
                os.unlink(compressed_path)

        except Exception as e:
            print(f"   ❌ Error: {e}")
            continue

    print("\n" + "="*70)
    print("TRANSCRIPTION COMPLETE")
    print("="*70)
    print(f"Files transcribed: {len(to_transcribe)}")
    print(f"Total words: {total_words:,}")
    print(f"Total cost: ${total_cost:.2f}")


if __name__ == "__main__":
    main()
