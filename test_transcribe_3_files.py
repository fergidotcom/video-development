#!/usr/bin/env python3
"""
Test transcription on 3 Ferguson Family Archive files.
Validates end-to-end pipeline before full batch run.
"""

import os
import sys
import sqlite3
import signal
import time
import logging
from datetime import datetime
from pathlib import Path
from openai import OpenAI

# Configuration
SURVEY_DB = os.path.expanduser("~/Library/CloudStorage/Dropbox/Fergi/VideoDev/pegasus-survey.db")
TRANSCRIPTS_DB = os.path.expanduser("~/Library/CloudStorage/Dropbox/Fergi/VideoDev/transcripts.db")
LOG_FILE = "/tmp/transcribe-test.log"
WHISPER_COST_PER_MINUTE = 0.006
TEST_LIMIT = 3  # Only process 3 files for testing

# Global shutdown flag
shutdown_requested = False

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Signal handlers for graceful shutdown
def signal_handler(signum, frame):
    global shutdown_requested
    logger.warning(f"\n⚠️  Shutdown signal received ({signum}). Finishing current file and exiting gracefully...")
    shutdown_requested = True

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def get_test_files():
    """Get 3 small Ferguson files for testing (shortest duration first for quick test)."""
    conn = sqlite3.connect(SURVEY_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT f.id, f.file_path, af.audio_path, vm.duration_seconds
        FROM files f
        JOIN audio_files af ON f.id = af.file_id
        JOIN video_metadata vm ON f.id = vm.file_id
        WHERE f.project_assignment = 'ferguson_family'
          AND af.extraction_status = 'complete'
        ORDER BY vm.duration_seconds ASC
        LIMIT ?;
    """

    cursor.execute(query, (TEST_LIMIT,))
    files = cursor.fetchall()
    conn.close()

    logger.info(f"📋 Selected {len(files)} shortest Ferguson files for testing")
    return files


def mark_transcription_started(file_id):
    """Mark a file as transcription in progress."""
    conn = sqlite3.connect(TRANSCRIPTS_DB)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO transcription_progress
        (file_id, transcription_status, started_at)
        VALUES (?, 'in_progress', ?)
    """, (file_id, datetime.utcnow().isoformat()))

    conn.commit()
    conn.close()


def mark_transcription_complete(file_id, cost, transcript_id):
    """Mark a file as transcription complete."""
    conn = sqlite3.connect(TRANSCRIPTS_DB)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE transcription_progress
        SET transcription_status = 'complete',
            completed_at = ?,
            cost_dollars = ?,
            error_message = NULL
        WHERE file_id = ?
    """, (datetime.utcnow().isoformat(), cost, file_id))

    conn.commit()
    conn.close()


def get_openai_api_key():
    """Get OpenAI API key from environment or ~/.zshrc."""
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
        return None

    return api_key


def mark_transcription_error(file_id, error_msg):
    """Mark a file as transcription failed with error."""
    conn = sqlite3.connect(TRANSCRIPTS_DB)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO transcription_progress
        (file_id, transcription_status, started_at, completed_at, error_message)
        VALUES (?, 'error', ?, ?, ?)
    """, (file_id, datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), error_msg))

    conn.commit()
    conn.close()


def transcribe_audio_file(audio_path, file_id, duration_seconds):
    """
    Upload audio to Whisper API and get transcript.
    Returns (transcript_text, segments, cost) or (None, None, 0) on error.
    """
    try:
        # Get API key
        api_key = get_openai_api_key()
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found")

        # Initialize OpenAI client
        client = OpenAI(api_key=api_key)

        logger.info(f"📤 Uploading {os.path.basename(audio_path)} to Whisper API...")

        with open(audio_path, 'rb') as audio_file:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="en",
                response_format="verbose_json"
            )

        # Extract transcript and segments
        transcript_text = response.text
        segments = response.segments if hasattr(response, 'segments') else []

        # Calculate cost
        duration_minutes = duration_seconds / 60.0
        cost = duration_minutes * WHISPER_COST_PER_MINUTE

        logger.info(f"✅ Transcription complete: {len(transcript_text)} characters, ${cost:.4f}")

        return transcript_text, segments, cost

    except Exception as e:
        logger.error(f"❌ Whisper API error: {e}")
        return None, None, 0


def store_transcript(file_id, transcript_text, segments, duration_seconds, cost):
    """Store transcript and segments in database."""
    conn = sqlite3.connect(TRANSCRIPTS_DB)
    cursor = conn.cursor()

    try:
        # Insert main transcript
        cursor.execute("""
            INSERT INTO transcripts
            (file_id, transcript_text, language, duration_seconds, transcribed_at,
             word_count, character_count, whisper_model, cost_dollars)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            file_id,
            transcript_text,
            'en',
            duration_seconds,
            datetime.utcnow().isoformat(),
            len(transcript_text.split()),
            len(transcript_text),
            'whisper-1',
            cost
        ))

        transcript_id = cursor.lastrowid

        # Insert segments if available
        if segments:
            for idx, segment in enumerate(segments):
                cursor.execute("""
                    INSERT INTO transcript_segments
                    (transcript_id, start_time, end_time, text, segment_index)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    transcript_id,
                    getattr(segment, 'start', 0),
                    getattr(segment, 'end', 0),
                    getattr(segment, 'text', ''),
                    idx
                ))

        conn.commit()
        logger.info(f"💾 Stored transcript (ID: {transcript_id}) with {len(segments)} segments")
        return transcript_id

    except Exception as e:
        logger.error(f"❌ Database error storing transcript: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()


def main():
    logger.info("=" * 80)
    logger.info("🧪 TEST: Ferguson Family Archive Transcription (3 files)")
    logger.info("=" * 80)

    # Check for OpenAI API key
    api_key = get_openai_api_key()
    if not api_key:
        logger.error("❌ OPENAI_API_KEY not found!")
        logger.error("   Please set it in your environment or ~/.zshrc:")
        logger.error("   export OPENAI_API_KEY='sk-proj-...'")
        sys.exit(1)

    logger.info("✅ OpenAI API key found")

    # Get test files
    test_files = get_test_files()

    if not test_files:
        logger.error("❌ No test files found!")
        return

    logger.info(f"🚀 Starting transcription of {len(test_files)} test files...")
    logger.info("")

    start_time = time.time()
    cumulative_cost = 0
    completed_count = 0

    # Process files
    for idx, file_record in enumerate(test_files, 1):
        if shutdown_requested:
            logger.warning("🛑 Shutdown requested - exiting gracefully")
            break

        file_id = file_record['id']
        audio_path = file_record['audio_path']
        video_path = file_record['file_path']
        duration = file_record['duration_seconds']

        logger.info(f"\n{'='*80}")
        logger.info(f"🎥 Test file {idx}/{len(test_files)}")
        logger.info(f"   Video: {os.path.basename(video_path)}")
        logger.info(f"   Audio: {os.path.basename(audio_path)}")
        logger.info(f"   Duration: {duration:.1f}s ({duration/60:.1f} minutes)")
        logger.info(f"{'='*80}")

        # Check if audio file exists
        if not os.path.exists(audio_path):
            logger.error(f"❌ Audio file not found: {audio_path}")
            mark_transcription_error(file_id, f"Audio file not found: {audio_path}")
            continue

        # Mark as in progress
        mark_transcription_started(file_id)

        # Transcribe
        transcript_text, segments, cost = transcribe_audio_file(audio_path, file_id, duration)

        if transcript_text is None:
            logger.error(f"❌ Transcription failed for {video_path}")
            mark_transcription_error(file_id, "Whisper API error")
            continue

        # Store transcript
        transcript_id = store_transcript(file_id, transcript_text, segments, duration, cost)

        if transcript_id is None:
            logger.error(f"❌ Failed to store transcript for {video_path}")
            mark_transcription_error(file_id, "Database storage error")
            continue

        # Mark complete
        mark_transcription_complete(file_id, cost, transcript_id)

        # Update stats
        completed_count += 1
        cumulative_cost += cost

        logger.info(f"✅ Test file {idx}/{len(test_files)} complete | Cost: ${cost:.4f} | Cumulative: ${cumulative_cost:.4f}")

        # Show a snippet of the transcript
        snippet = transcript_text[:200] + "..." if len(transcript_text) > 200 else transcript_text
        logger.info(f"📝 Transcript preview: {snippet}")

    # Final summary
    elapsed_time = time.time() - start_time
    logger.info("\n" + "=" * 80)
    logger.info("🏁 TEST COMPLETE")
    logger.info("=" * 80)
    logger.info(f"✅ Files processed: {completed_count}/{len(test_files)}")
    logger.info(f"💰 Total cost: ${cumulative_cost:.4f}")
    logger.info(f"⏱️  Elapsed time: {elapsed_time:.1f} seconds")
    logger.info("")

    if completed_count == len(test_files):
        logger.info("🎉 TEST SUCCESSFUL! Pipeline validated end-to-end.")
        logger.info("   Ready to launch full Ferguson archive transcription.")
        logger.info("   Run: nohup python3 transcribe_ferguson_archive.py > /tmp/transcribe-ferguson-run.log 2>&1 &")
    else:
        logger.warning("⚠️  Some test files failed. Review errors before full run.")

    logger.info("=" * 80)


if __name__ == '__main__':
    main()
