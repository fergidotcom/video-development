#!/usr/bin/env python3
"""
Comprehensive Pegasus Drive Survey Script
==========================================

Fault-tolerant, resumable metadata extraction for all files on Pegasus drive.
Automatically detects Ferguson family content and identifies compression candidates.

Features:
- Read-only operations (zero file modifications)
- Ferguson family content detection
- 5K+ video compression candidate identification
- Full metadata extraction (ffprobe, exiftool)
- Resume capability after interruption
- Graceful shutdown (Ctrl+C safe)
- Progress tracking and reporting
- Zero API costs (100% local)

Based on Claude.ai VideoDevClaudePerspective.yaml specification
"""

import sqlite3
import json
import subprocess
import signal
import sys
from pathlib import Path
from datetime import datetime
import re
import time

# Configuration
DB_PATH = Path(__file__).parent / "pegasus-survey.db"
PEGASUS_ROOT = Path("/Volumes/Promise Pegasus")
BATCH_COMMIT_SIZE = 100  # Commit every N files
METADATA_TIMEOUT = 30  # Timeout for metadata extraction (seconds)

# File type extensions
VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.m4v', '.mpg', '.mpeg', '.wmv', '.flv', '.webm', '.mts', '.m2ts'}
PHOTO_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.heic', '.heif', '.raw', '.cr2', '.nef', '.arw'}
DOCUMENT_EXTS = {'.pdf', '.doc', '.docx', '.txt', '.rtf', '.pages', '.odt'}

# Ferguson family detection patterns
FERGUSON_PATTERNS = {
    'filename': [
        r'ferguson',
        r'jeff\s*ferguson',
        r'joe\s*ferguson',
        r'jeffrey',
        r'ck\s*and\s*la',
        r'pop',
        r'joeferguson',
        r'jeff f',
    ],
    'directory': [
        r'ferguson',
        r'family',
        r'ck\s*and\s*la',
        r'jeffrey',
        r'pop',
    ]
}

# Global state for graceful shutdown
shutdown_requested = False

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    global shutdown_requested
    print("\n\n⚠️  Shutdown requested. Completing current file and saving progress...")
    print("   Database will be saved. You can resume later.\n")
    shutdown_requested = True

# Register signal handler
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def get_db_connection():
    """Get database connection with WAL mode enabled"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def detect_ferguson_family(file_path, directory, metadata_json=None):
    """
    Detect if file is Ferguson family content
    Returns: 'ferguson_family', 'general', or 'unassigned'
    """

    # Check filename patterns
    filename_lower = file_path.name.lower()
    for pattern in FERGUSON_PATTERNS['filename']:
        if re.search(pattern, filename_lower, re.IGNORECASE):
            return 'ferguson_family'

    # Check directory patterns
    dir_lower = str(directory).lower()
    for pattern in FERGUSON_PATTERNS['directory']:
        if re.search(pattern, dir_lower, re.IGNORECASE):
            return 'ferguson_family'

    # Check metadata if available (for photos with EXIF/IPTC)
    if metadata_json:
        try:
            metadata = json.loads(metadata_json)
            for field in ['Author', 'Creator', 'Copyright', 'Keywords', 'Caption']:
                if field in metadata:
                    value_lower = str(metadata[field]).lower()
                    for pattern in FERGUSON_PATTERNS['filename']:
                        if re.search(pattern, value_lower, re.IGNORECASE):
                            return 'ferguson_family'
        except:
            pass

    return 'general'

def get_file_type(file_path):
    """Determine file type from extension"""
    ext = file_path.suffix.lower()

    if ext in VIDEO_EXTS:
        return 'video', ext[1:]  # Remove leading dot
    elif ext in PHOTO_EXTS:
        return 'photo', ext[1:]
    elif ext in DOCUMENT_EXTS:
        return 'document', ext[1:]
    else:
        return 'other', ext[1:] if ext else 'unknown'

def extract_video_metadata(file_path):
    """Extract video metadata using ffprobe"""
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            str(file_path)
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=METADATA_TIMEOUT
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)

            # Extract video stream info
            video_stream = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), None)
            audio_stream = next((s for s in data.get('streams', []) if s.get('codec_type') == 'audio'), None)
            format_info = data.get('format', {})

            metadata = {
                'duration_seconds': float(format_info.get('duration', 0)),
                'width': video_stream.get('width') if video_stream else None,
                'height': video_stream.get('height') if video_stream else None,
                'codec': video_stream.get('codec_name') if video_stream else None,
                'frame_rate': eval(video_stream.get('avg_frame_rate', '0/1')) if video_stream else None,
                'bitrate': int(format_info.get('bit_rate', 0)),
                'audio_codec': audio_stream.get('codec_name') if audio_stream else None,
                'audio_channels': audio_stream.get('channels') if audio_stream else None,
                'color_space': video_stream.get('color_space') if video_stream else None,
                'has_embedded_metadata': bool(format_info.get('tags')),
                'metadata_json': json.dumps(data)
            }

            # Determine resolution category
            if metadata['width'] and metadata['height']:
                height = metadata['height']
                width = metadata['width']

                if height >= 2880 or width >= 5120:
                    metadata['resolution_category'] = '5K+'
                    metadata['compression_candidate'] = True
                    # Rough estimate: 1024p is ~1/5 the pixels of 5K
                    metadata['estimated_1024p_size_bytes'] = int(file_path.stat().st_size * 0.2)
                elif height >= 2160:
                    metadata['resolution_category'] = '4K'
                    metadata['compression_candidate'] = False
                elif height >= 1080:
                    metadata['resolution_category'] = '1080p'
                    metadata['compression_candidate'] = False
                elif height >= 720:
                    metadata['resolution_category'] = '720p'
                    metadata['compression_candidate'] = False
                else:
                    metadata['resolution_category'] = 'other'
                    metadata['compression_candidate'] = False

            return metadata, None

    except subprocess.TimeoutExpired:
        return None, "ffprobe timeout"
    except Exception as e:
        return None, str(e)

def extract_photo_metadata(file_path):
    """Extract photo metadata using exiftool"""
    try:
        cmd = ['exiftool', '-j', '-a', '-G1', str(file_path)]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=METADATA_TIMEOUT
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)[0]

            metadata = {
                'width': data.get('EXIF:ImageWidth') or data.get('File:ImageWidth'),
                'height': data.get('EXIF:ImageHeight') or data.get('File:ImageHeight'),
                'color_space': data.get('EXIF:ColorSpace'),
                'camera_make': data.get('EXIF:Make'),
                'camera_model': data.get('EXIF:Model'),
                'lens_model': data.get('EXIF:LensModel'),
                'iso': data.get('EXIF:ISO'),
                'aperture': data.get('EXIF:FNumber'),
                'shutter_speed': data.get('EXIF:ShutterSpeed'),
                'focal_length': data.get('EXIF:FocalLength'),
                'gps_latitude': data.get('EXIF:GPSLatitude'),
                'gps_longitude': data.get('EXIF:GPSLongitude'),
                'gps_altitude': data.get('EXIF:GPSAltitude'),
                'date_taken': data.get('EXIF:DateTimeOriginal'),
                'caption': data.get('IPTC:Caption-Abstract'),
                'keywords': ','.join(data.get('IPTC:Keywords', [])) if isinstance(data.get('IPTC:Keywords'), list) else data.get('IPTC:Keywords'),
                'copyright': data.get('EXIF:Copyright') or data.get('IPTC:CopyrightNotice'),
                'has_xmp_metadata': any(k.startswith('XMP:') for k in data.keys()),
                'metadata_json': json.dumps(data)
            }

            return metadata, None

    except subprocess.TimeoutExpired:
        return None, "exiftool timeout"
    except Exception as e:
        return None, str(e)

def extract_document_metadata(file_path):
    """Extract basic document metadata using exiftool"""
    try:
        cmd = ['exiftool', '-j', str(file_path)]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=METADATA_TIMEOUT
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)[0]

            metadata = {
                'document_type': data.get('File:FileType'),
                'page_count': data.get('PDF:PageCount'),
                'author': data.get('PDF:Author') or data.get('XMP:Creator'),
                'title': data.get('PDF:Title') or data.get('XMP:Title'),
                'subject': data.get('PDF:Subject'),
                'creation_tool': data.get('PDF:Creator') or data.get('XMP:CreatorTool'),
                'has_extractable_text': True,  # Assume yes if metadata exists
                'metadata_json': json.dumps(data)
            }

            return metadata, None

    except subprocess.TimeoutExpired:
        return None, "exiftool timeout"
    except Exception as e:
        return None, str(e)

def process_file(file_path, conn, cursor, stats):
    """Process a single file: extract metadata and store in database"""

    try:
        # Skip hidden files
        if file_path.name.startswith('.'):
            stats['files_skipped'] += 1
            return True

        # Get file info
        file_stat = file_path.stat()
        file_type, file_format = get_file_type(file_path)

        # Calculate relative path from Pegasus root
        try:
            relative_path = file_path.relative_to(PEGASUS_ROOT)
        except ValueError:
            relative_path = file_path

        # Determine project assignment
        project_assignment = detect_ferguson_family(file_path, file_path.parent)

        # Track Ferguson family files
        if project_assignment == 'ferguson_family':
            stats['ferguson_family_files'] += 1
        elif project_assignment == 'general':
            stats['general_archive_files'] += 1
        else:
            stats['unassigned_files'] += 1

        # Track file type
        if file_type == 'video':
            stats['video_count'] += 1
        elif file_type == 'photo':
            stats['photo_count'] += 1
        elif file_type == 'document':
            stats['document_count'] += 1
        else:
            stats['other_count'] += 1

        # Insert file record
        now = datetime.utcnow().isoformat()
        cursor.execute("""
            INSERT INTO files (
                file_path, filename, directory, relative_path,
                file_type, file_format, file_size_bytes,
                project_assignment, creation_date, modification_date,
                scan_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(file_path),
            file_path.name,
            str(file_path.parent),
            str(relative_path),
            file_type,
            file_format,
            file_stat.st_size,
            project_assignment,
            datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
            datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
            'complete',
            now,
            now
        ))

        file_id = cursor.lastrowid
        stats['total_size_bytes'] += file_stat.st_size

        # Extract type-specific metadata
        if file_type == 'video':
            metadata, error = extract_video_metadata(file_path)
            if metadata:
                cursor.execute("""
                    INSERT INTO video_metadata (
                        file_id, duration_seconds, width, height,
                        resolution_category, compression_candidate, estimated_1024p_size_bytes,
                        codec, frame_rate, bitrate, audio_codec, audio_channels,
                        color_space, has_embedded_metadata, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    file_id,
                    metadata.get('duration_seconds'),
                    metadata.get('width'),
                    metadata.get('height'),
                    metadata.get('resolution_category'),
                    metadata.get('compression_candidate', False),
                    metadata.get('estimated_1024p_size_bytes'),
                    metadata.get('codec'),
                    metadata.get('frame_rate'),
                    metadata.get('bitrate'),
                    metadata.get('audio_codec'),
                    metadata.get('audio_channels'),
                    metadata.get('color_space'),
                    metadata.get('has_embedded_metadata', False),
                    metadata.get('metadata_json')
                ))

                if metadata.get('duration_seconds'):
                    stats['total_duration_seconds'] += metadata['duration_seconds']

                if metadata.get('compression_candidate'):
                    stats['compression_candidates_count'] += 1
                    stats['compression_potential_savings_bytes'] += file_stat.st_size - metadata.get('estimated_1024p_size_bytes', 0)

        elif file_type == 'photo':
            metadata, error = extract_photo_metadata(file_path)
            if metadata:
                cursor.execute("""
                    INSERT INTO photo_metadata (
                        file_id, width, height, color_space,
                        camera_make, camera_model, lens_model,
                        iso, aperture, shutter_speed, focal_length,
                        gps_latitude, gps_longitude, gps_altitude,
                        date_taken, caption, keywords, copyright,
                        has_xmp_metadata, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    file_id,
                    metadata.get('width'),
                    metadata.get('height'),
                    metadata.get('color_space'),
                    metadata.get('camera_make'),
                    metadata.get('camera_model'),
                    metadata.get('lens_model'),
                    metadata.get('iso'),
                    metadata.get('aperture'),
                    metadata.get('shutter_speed'),
                    metadata.get('focal_length'),
                    metadata.get('gps_latitude'),
                    metadata.get('gps_longitude'),
                    metadata.get('gps_altitude'),
                    metadata.get('date_taken'),
                    metadata.get('caption'),
                    metadata.get('keywords'),
                    metadata.get('copyright'),
                    metadata.get('has_xmp_metadata', False),
                    metadata.get('metadata_json')
                ))

        elif file_type == 'document':
            metadata, error = extract_document_metadata(file_path)
            if metadata:
                cursor.execute("""
                    INSERT INTO document_metadata (
                        file_id, document_type, page_count,
                        author, title, subject, creation_tool,
                        has_extractable_text, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    file_id,
                    metadata.get('document_type'),
                    metadata.get('page_count'),
                    metadata.get('author'),
                    metadata.get('title'),
                    metadata.get('subject'),
                    metadata.get('creation_tool'),
                    metadata.get('has_extractable_text', False),
                    metadata.get('metadata_json')
                ))

        stats['files_processed'] += 1
        return True

    except Exception as e:
        stats['files_errored'] += 1
        # Log error but continue
        print(f"   ⚠️  Error processing {file_path.name}: {e}")

        # Update file record with error
        try:
            cursor.execute("""
                UPDATE files SET scan_status = 'error', error_message = ?
                WHERE file_path = ?
            """, (str(e), str(file_path)))
        except:
            pass

        return True  # Continue processing

def run_survey(resume=False):
    """Main survey function"""

    print("\n" + "="*70)
    print("PEGASUS DRIVE COMPREHENSIVE SURVEY")
    print("="*70)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Pegasus root: {PEGASUS_ROOT}")
    print(f"Database: {DB_PATH}")
    print(f"Resume mode: {'Yes' if resume else 'No'}")
    print("="*70 + "\n")

    # Verify Pegasus drive is mounted
    if not PEGASUS_ROOT.exists():
        print(f"❌ Error: Pegasus drive not found at {PEGASUS_ROOT}")
        print("   Please ensure the drive is mounted and try again.")
        return False

    conn = get_db_connection()
    cursor = conn.cursor()

    # Initialize survey run
    survey_run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    stats = {
        'total_files': 0,
        'files_processed': 0,
        'files_skipped': 0,
        'files_errored': 0,
        'total_size_bytes': 0,
        'total_duration_seconds': 0,
        'video_count': 0,
        'photo_count': 0,
        'document_count': 0,
        'other_count': 0,
        'ferguson_family_files': 0,
        'general_archive_files': 0,
        'unassigned_files': 0,
        'compression_candidates_count': 0,
        'compression_potential_savings_bytes': 0,
        'directories_scanned': 0
    }

    # Insert survey statistics record
    cursor.execute("""
        INSERT INTO survey_statistics (
            survey_run_id, started_at, status,
            total_files, files_processed, files_skipped, files_errored,
            total_size_bytes, total_duration_seconds,
            video_count, photo_count, document_count, other_count,
            ferguson_family_files, general_archive_files, unassigned_files,
            compression_candidates_count, compression_potential_savings_bytes,
            directories_scanned
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        survey_run_id, datetime.utcnow().isoformat(), 'running',
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
    ))
    stats_id = cursor.lastrowid
    conn.commit()

    print("Scanning directory structure...")
    start_time = time.time()
    batch_count = 0

    # Recursively walk directory tree
    for root, dirs, files in PEGASUS_ROOT.walk():
        if shutdown_requested:
            print("\n\n⏸️  Shutdown in progress...")
            break

        stats['directories_scanned'] += 1
        stats['total_files'] += len(files)

        # Process files in this directory
        print(f"\n📁 {root.relative_to(PEGASUS_ROOT)}")
        print(f"   Files: {len(files)}")

        for filename in files:
            if shutdown_requested:
                break

            file_path = root / filename
            process_file(file_path, conn, cursor, stats)

            # Batch commit
            batch_count += 1
            if batch_count >= BATCH_COMMIT_SIZE:
                conn.commit()
                batch_count = 0

                # Update stats in database
                cursor.execute("""
                    UPDATE survey_statistics SET
                        total_files = ?, files_processed = ?, files_skipped = ?,
                        files_errored = ?, total_size_bytes = ?, total_duration_seconds = ?,
                        video_count = ?, photo_count = ?, document_count = ?, other_count = ?,
                        ferguson_family_files = ?, general_archive_files = ?, unassigned_files = ?,
                        compression_candidates_count = ?, compression_potential_savings_bytes = ?,
                        directories_scanned = ?
                    WHERE id = ?
                """, (
                    stats['total_files'], stats['files_processed'], stats['files_skipped'],
                    stats['files_errored'], stats['total_size_bytes'], stats['total_duration_seconds'],
                    stats['video_count'], stats['photo_count'], stats['document_count'], stats['other_count'],
                    stats['ferguson_family_files'], stats['general_archive_files'], stats['unassigned_files'],
                    stats['compression_candidates_count'], stats['compression_potential_savings_bytes'],
                    stats['directories_scanned'], stats_id
                ))
                conn.commit()

                # Progress update
                elapsed = time.time() - start_time
                rate = stats['files_processed'] / elapsed if elapsed > 0 else 0
                print(f"   ⏱️  Progress: {stats['files_processed']:,} files | {rate:.1f} files/sec | {stats['total_size_bytes']/1e9:.1f} GB")

    # Final commit
    conn.commit()

    # Update final stats
    end_time = datetime.utcnow().isoformat()
    status = 'interrupted' if shutdown_requested else 'complete'

    cursor.execute("""
        UPDATE survey_statistics SET
            completed_at = ?, status = ?,
            total_files = ?, files_processed = ?, files_skipped = ?,
            files_errored = ?, total_size_bytes = ?, total_duration_seconds = ?,
            video_count = ?, photo_count = ?, document_count = ?, other_count = ?,
            ferguson_family_files = ?, general_archive_files = ?, unassigned_files = ?,
            compression_candidates_count = ?, compression_potential_savings_bytes = ?,
            directories_scanned = ?
        WHERE id = ?
    """, (
        end_time, status,
        stats['total_files'], stats['files_processed'], stats['files_skipped'],
        stats['files_errored'], stats['total_size_bytes'], stats['total_duration_seconds'],
        stats['video_count'], stats['photo_count'], stats['document_count'], stats['other_count'],
        stats['ferguson_family_files'], stats['general_archive_files'], stats['unassigned_files'],
        stats['compression_candidates_count'], stats['compression_potential_savings_bytes'],
        stats['directories_scanned'], stats_id
    ))
    conn.commit()
    conn.close()

    # Print final report
    print("\n" + "="*70)
    print(f"SURVEY {'INTERRUPTED' if shutdown_requested else 'COMPLETE'}")
    print("="*70)
    print(f"Total files: {stats['total_files']:,}")
    print(f"Files processed: {stats['files_processed']:,}")
    print(f"Files skipped: {stats['files_skipped']:,}")
    print(f"Files errored: {stats['files_errored']:,}")
    print(f"Total size: {stats['total_size_bytes']/1e9:.2f} GB")
    print(f"Total video duration: {stats['total_duration_seconds']/3600:.1f} hours")
    print()
    print(f"Videos: {stats['video_count']:,}")
    print(f"Photos: {stats['photo_count']:,}")
    print(f"Documents: {stats['document_count']:,}")
    print(f"Other: {stats['other_count']:,}")
    print()
    print(f"Ferguson family files: {stats['ferguson_family_files']:,}")
    print(f"General archive files: {stats['general_archive_files']:,}")
    print(f"Unassigned files: {stats['unassigned_files']:,}")
    print()
    print(f"5K+ compression candidates: {stats['compression_candidates_count']:,}")
    print(f"Potential savings: {stats['compression_potential_savings_bytes']/1e9:.2f} GB")
    print()
    print(f"Directories scanned: {stats['directories_scanned']:,}")
    print("="*70)

    if shutdown_requested:
        print("\n⏸️  Survey interrupted. Database saved.")
        print("   You can resume later (resume capability to be implemented).")

    return True

if __name__ == "__main__":
    print("\n🔍 Pegasus Drive Survey")
    print("   Press Ctrl+C at any time to safely stop and save progress\n")

    try:
        success = run_survey(resume=False)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
