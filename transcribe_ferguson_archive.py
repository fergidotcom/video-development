#!/usr/bin/env python3
"""
Ferguson Family Archive Transcription Pipeline

Transcribes audio from Ferguson Family Archive videos using OpenAI Whisper API.
- Fault-tolerant: Ctrl+C safe, graceful shutdown
- Resumable: Checks transcription_progress, skips completed files
- Cost tracking: Per-file and cumulative
- Progress display: N/652 complete, $X.XX spent
- Error handling: Logs errors, continues to next file
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
LOG_FILE = "/tmp/transcribe-ferguson.log"
WHISPER_COST_PER_MINUTE = 0.006
BATCH_SIZE = 10  # Process in batches, allowing for interruption

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


def get_ferguson_files_to_transcribe():
    """Query Ferguson files with extracted audio, ordered by duration (longest first)."""
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
          AND vm.duration_seconds < 2100
          AND f.filename NOT LIKE '%Vivino%'
          AND f.filename NOT LIKE '%Vivion%'
        ORDER BY vm.duration_seconds ASC;
    """

    cursor.execute(query)
    files = cursor.fetchall()
    conn.close()

    logger.info(f"📋 Found {len(files)} Ferguson Family Archive videos with extracted audio")
    return files


def get_already_transcribed():
    """Get set of file_ids that are already transcribed or in progress."""
    conn = sqlite3.connect(TRANSCRIPTS_DB)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT file_id
        FROM transcription_progress
        WHERE transcription_status IN ('complete', 'in_progress')
    """)

    completed = {row[0] for row in cursor.fetchall()}
    conn.close()

    return completed


def get_transcription_stats():
    """Get current transcription statistics."""
    conn = sqlite3.connect(TRANSCRIPTS_DB)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) as total_count,
            COALESCE(SUM(cost_dollars), 0) as total_cost
        FROM transcription_progress
        WHERE transcription_status = 'complete'
    """)

    row = cursor.fetchone()
    conn.close()

    return {
        'completed_count': row[0],
        'total_cost': row[1]
    }


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


def display_progress(current, total, cost_this_file, cumulative_cost, elapsed_time):
    """Display progress update."""
    percent = (current / total) * 100
    avg_time_per_file = elapsed_time / current if current > 0 else 0
    remaining_files = total - current
    eta_seconds = remaining_files * avg_time_per_file
    eta_hours = eta_seconds / 3600

    logger.info(f"""
╔═══════════════════════════════════════════════════════════════════
║ 📊 PROGRESS: {current}/{total} files ({percent:.1f}%)
║ 💰 Cost this file: ${cost_this_file:.4f} | Cumulative: ${cumulative_cost:.2f}
║ ⏱️  Elapsed: {elapsed_time/3600:.2f}h | ETA: {eta_hours:.2f}h
╚═══════════════════════════════════════════════════════════════════
    """)


def main():
    logger.info("=" * 80)
    logger.info("🎬 Ferguson Family Archive Transcription Pipeline")
    logger.info("=" * 80)

    # Check for OpenAI API key
    api_key = get_openai_api_key()
    if not api_key:
        logger.error("❌ OPENAI_API_KEY not found!")
        logger.error("   Please set it in your environment or ~/.zshrc:")
        logger.error("   export OPENAI_API_KEY='sk-proj-...'")
        sys.exit(1)

    logger.info("✅ OpenAI API key found")

    # Get files to process
    all_files = get_ferguson_files_to_transcribe()
    already_done = get_already_transcribed()

    files_to_process = [f for f in all_files if f['id'] not in already_done]

    logger.info(f"📝 Total Ferguson files: {len(all_files)}")
    logger.info(f"✅ Already transcribed: {len(already_done)}")
    logger.info(f"📋 Remaining to process: {len(files_to_process)}")

    if not files_to_process:
        logger.info("🎉 All Ferguson Family Archive files already transcribed!")
        return

    # Get current stats
    stats = get_transcription_stats()
    cumulative_cost = stats['total_cost']
    completed_count = stats['completed_count']

    logger.info(f"💰 Current cumulative cost: ${cumulative_cost:.2f}")
    logger.info(f"🚀 Starting transcription of {len(files_to_process)} files...")
    logger.info("")

    start_time = time.time()
    files_processed_this_session = 0

    # Process files
    for file_record in files_to_process:
        if shutdown_requested:
            logger.warning("🛑 Shutdown requested - exiting gracefully")
            break

        file_id = file_record['id']
        audio_path = file_record['audio_path']
        video_path = file_record['file_path']
        duration = file_record['duration_seconds']

        logger.info(f"\n{'='*80}")
        logger.info(f"🎥 Processing file {completed_count + 1}/{len(all_files)}")
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
        files_processed_this_session += 1
        cumulative_cost += cost
        elapsed_time = time.time() - start_time

        # Display progress
        display_progress(completed_count, len(all_files), cost, cumulative_cost, elapsed_time)

    # Final summary
    logger.info("\n" + "=" * 80)
    logger.info("🏁 TRANSCRIPTION SESSION COMPLETE")
    logger.info("=" * 80)
    logger.info(f"✅ Files processed this session: {files_processed_this_session}")
    logger.info(f"✅ Total files completed: {completed_count}/{len(all_files)}")
    logger.info(f"💰 Total cost: ${cumulative_cost:.2f}")
    logger.info(f"⏱️  Total elapsed time: {(time.time() - start_time)/3600:.2f} hours")

    if completed_count < len(all_files):
        remaining = len(all_files) - completed_count
        logger.info(f"📋 Remaining files: {remaining}")
        logger.info(f"   Run this script again to resume transcription")
    else:
        logger.info("🎉 ALL FERGUSON FAMILY ARCHIVE FILES TRANSCRIBED!")

    logger.info("=" * 80)


if __name__ == '__main__':
    main()
