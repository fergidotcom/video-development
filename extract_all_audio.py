#!/usr/bin/env python3
"""
Fault-Tolerant Audio Extraction from Video Archive
===================================================

Extracts audio from all 16,292 cataloged videos on Pegasus drive.
- Creates organized audio files in /Volumes/Promise Pegasus/ExtractedAudio/
- Mirrors original directory structure
- Preserves metadata and tracks extraction in database
- Fully resumable after interruptions
- Graceful shutdown (Ctrl+C safe)

Output naming: originalname_extracted.m4a (or .aac/.mp3 based on source)

Usage:
    python3 extract_all_audio.py

Run in a screen session for overnight operation:
    screen -S audio-extraction
    cd ~/Library/CloudStorage/Dropbox/Fergi/VideoDev
    python3 extract_all_audio.py
    # Ctrl+A, D to detach
"""

import sqlite3
import subprocess
import signal
import sys
import json
from pathlib import Path
from datetime import datetime
import time

# Configuration
DB_PATH = Path(__file__).parent / "pegasus-survey.db"
PEGASUS_ROOT = Path("/Volumes/Promise Pegasus")
AUDIO_OUTPUT_ROOT = PEGASUS_ROOT / "ExtractedAudio"
BATCH_COMMIT_SIZE = 50  # Commit every N extractions
EXTRACTION_TIMEOUT = 300  # 5 minutes max per video

# Global state for graceful shutdown
shutdown_requested = False

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    global shutdown_requested
    print("\n\n⚠️  Shutdown requested. Completing current extraction and saving progress...")
    print("   Database will be saved. You can resume later.\n")
    shutdown_requested = True

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def extract_audio(video_path, audio_path, timeout=EXTRACTION_TIMEOUT):
    """
    Extract audio from video using FFmpeg
    Uses -c:a copy to avoid re-encoding (fast!)
    """
    try:
        # Ensure output directory exists
        audio_path.parent.mkdir(parents=True, exist_ok=True)

        # Extract audio without re-encoding
        cmd = [
            'ffmpeg',
            '-i', str(video_path),
            '-vn',  # No video
            '-acodec', 'copy',  # Copy audio stream (no re-encoding)
            '-y',  # Overwrite if exists
            str(audio_path)
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if result.returncode == 0 and audio_path.exists():
            return True, None
        else:
            error = result.stderr.split('\n')[-3:] if result.stderr else "Unknown error"
            return False, str(error)

    except subprocess.TimeoutExpired:
        return False, "FFmpeg timeout"
    except Exception as e:
        return False, str(e)

def get_audio_metadata(audio_path):
    """Extract metadata from audio file"""
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            '-select_streams', 'a:0',
            str(audio_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            stream = data.get('streams', [{}])[0]
            format_info = data.get('format', {})

            return {
                'codec': stream.get('codec_name'),
                'channels': stream.get('channels'),
                'sample_rate': stream.get('sample_rate'),
                'bitrate': int(format_info.get('bit_rate', 0)),
                'duration': float(format_info.get('duration', 0)),
                'size': int(format_info.get('size', 0))
            }
        return None
    except Exception:
        return None

def process_video(video_row, conn, cursor, stats):
    """Extract audio from a single video"""

    file_id, video_id, video_path, filename, relative_path = video_row

    try:
        video_path_obj = Path(video_path)
        if not video_path_obj.exists():
            stats['videos_skipped'] += 1
            return True

        # Check if already extracted
        cursor.execute("""
            SELECT id FROM audio_files
            WHERE source_video_id = ? AND extraction_status = 'complete'
        """, (video_id,))

        if cursor.fetchone():
            stats['videos_skipped'] += 1
            return True

        # Create audio filename
        audio_filename = video_path_obj.stem + "_extracted.m4a"

        # Mirror directory structure
        relative_dir = Path(relative_path).parent
        audio_dir = AUDIO_OUTPUT_ROOT / relative_dir
        audio_path = audio_dir / audio_filename

        # Extract audio
        success, error = extract_audio(video_path_obj, audio_path)

        if not success:
            stats['videos_errored'] += 1
            now = datetime.utcnow().isoformat()
            cursor.execute("""
                INSERT OR REPLACE INTO audio_files (
                    file_id, source_video_id, audio_path, audio_filename,
                    audio_directory, extraction_status, extraction_error, created_at
                ) VALUES (?, ?, ?, ?, ?, 'error', ?, ?)
            """, (file_id, video_id, str(audio_path), audio_filename,
                  str(audio_dir), error, now))
            return True

        # Get audio metadata
        audio_meta = get_audio_metadata(audio_path)

        # Insert audio file record
        now = datetime.utcnow().isoformat()
        cursor.execute("""
            INSERT INTO audio_files (
                file_id, source_video_id, audio_path, audio_filename, audio_directory,
                audio_format, audio_codec, duration_seconds, file_size_bytes,
                channels, sample_rate, bitrate,
                extraction_status, extracted_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'complete', ?, ?)
        """, (
            file_id, video_id, str(audio_path), audio_filename, str(audio_dir),
            'm4a',
            audio_meta['codec'] if audio_meta else 'aac',
            audio_meta['duration'] if audio_meta else 0,
            audio_meta['size'] if audio_meta else audio_path.stat().st_size,
            audio_meta['channels'] if audio_meta else None,
            audio_meta['sample_rate'] if audio_meta else None,
            audio_meta['bitrate'] if audio_meta else None,
            now, now
        ))

        stats['audio_files_created'] += 1
        stats['total_audio_size_bytes'] += audio_meta['size'] if audio_meta else audio_path.stat().st_size
        stats['videos_processed'] += 1

        return True

    except Exception as e:
        stats['videos_errored'] += 1
        return True

def run_extraction():
    """Main extraction function"""

    print("\n" + "="*70)
    print("AUDIO EXTRACTION FROM PEGASUS VIDEO ARCHIVE")
    print("="*70)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Output: {AUDIO_OUTPUT_ROOT}")
    print("="*70 + "\n")

    if not PEGASUS_ROOT.exists():
        print(f"❌ Error: Pegasus drive not found")
        return False

    AUDIO_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    conn = get_db_connection()
    cursor = conn.cursor()

    run_id = datetime.now().strftime('%Y%m%d_%H%M%S')

    cursor.execute("SELECT COUNT(*) FROM video_metadata")
    total_videos = cursor.fetchone()[0]

    stats = {
        'videos_processed': 0,
        'videos_skipped': 0,
        'videos_errored': 0,
        'audio_files_created': 0,
        'total_audio_size_bytes': 0
    }

    cursor.execute("""
        INSERT INTO audio_extraction_progress (
            extraction_run_id, started_at, status, total_videos
        ) VALUES (?, ?, 'running', ?)
    """, (run_id, datetime.utcnow().isoformat(), total_videos))
    progress_id = cursor.lastrowid
    conn.commit()

    print(f"Processing {total_videos:,} videos...\n")

    cursor.execute("""
        SELECT f.id, v.id, f.file_path, f.filename, f.relative_path
        FROM files f
        JOIN video_metadata v ON f.id = v.file_id
        WHERE f.file_type = 'video'
        ORDER BY
            CASE WHEN f.relative_path LIKE '%CKandLAFergusonFamilyArchive%' THEN 0 ELSE 1 END,
            f.id
    """)

    start_time = time.time()
    batch_count = 0

    for video_row in cursor.fetchall():
        if shutdown_requested:
            break

        process_video(video_row, conn, cursor, stats)

        batch_count += 1
        if batch_count >= BATCH_COMMIT_SIZE:
            conn.commit()
            batch_count = 0

            cursor.execute("""
                UPDATE audio_extraction_progress SET
                    videos_processed = ?, videos_skipped = ?,
                    videos_errored = ?, audio_files_created = ?,
                    total_audio_size_bytes = ?
                WHERE id = ?
            """, (
                stats['videos_processed'], stats['videos_skipped'],
                stats['videos_errored'], stats['audio_files_created'],
                stats['total_audio_size_bytes'], progress_id
            ))
            conn.commit()

            elapsed = time.time() - start_time
            rate = stats['videos_processed'] / elapsed if elapsed > 0 else 0
            total = stats['videos_processed'] + stats['videos_skipped'] + stats['videos_errored']
            percent = (total / total_videos * 100) if total_videos > 0 else 0

            print(f"   📊 {total:,}/{total_videos:,} ({percent:.1f}%) | "
                  f"{stats['audio_files_created']:,} extracted | "
                  f"{rate:.1f}/sec | {stats['total_audio_size_bytes']/1e9:.1f} GB")

    conn.commit()

    status = 'interrupted' if shutdown_requested else 'complete'
    cursor.execute("""
        UPDATE audio_extraction_progress SET
            completed_at = ?, status = ?, videos_processed = ?,
            videos_skipped = ?, videos_errored = ?,
            audio_files_created = ?, total_audio_size_bytes = ?
        WHERE id = ?
    """, (
        datetime.utcnow().isoformat(), status,
        stats['videos_processed'], stats['videos_skipped'],
        stats['videos_errored'], stats['audio_files_created'],
        stats['total_audio_size_bytes'], progress_id
    ))
    conn.commit()
    conn.close()

    print("\n" + "="*70)
    print(f"EXTRACTION {status.upper()}")
    print("="*70)
    print(f"Processed: {stats['videos_processed']:,}")
    print(f"Skipped: {stats['videos_skipped']:,}")
    print(f"Errors: {stats['videos_errored']:,}")
    print(f"Created: {stats['audio_files_created']:,}")
    print(f"Size: {stats['total_audio_size_bytes']/1e9:.2f} GB")
    print("="*70)

    return True

if __name__ == "__main__":
    try:
        run_extraction()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
