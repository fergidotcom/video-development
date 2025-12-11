#!/usr/bin/env python3
"""
Pegasus Drive Comprehensive Survey
===================================
Scans /Volumes/Promise Pegasus and indexes all files into pegasus_index.db

Features:
- Full directory tree traversal with progress tracking
- Video/audio metadata extraction via ffprobe
- Directory name parsing for dates, locations, cameras
- Transcript file detection and linking
- Resume capability for interrupted scans
- Fault-tolerant with per-directory commits

Usage:
    python3 survey_pegasus.py              # Full scan
    python3 survey_pegasus.py --resume     # Resume interrupted scan
    python3 survey_pegasus.py --limit 100  # Process only 100 files (testing)
"""

import os
import sys
import re
import json
import sqlite3
import hashlib
import subprocess
from datetime import datetime
from pathlib import Path
import argparse

# Configuration
PEGASUS_ROOT = "/Volumes/Promise Pegasus"
EXCLUDE_DIRS = ["2012 Laguna FergiDotCom Archive"]
DB_PATH = os.path.expanduser("~/Library/CloudStorage/Dropbox/Fergi/VideoDev/pegasus_index.db")
LOG_DIR = os.path.expanduser("~/Library/CloudStorage/Dropbox/Fergi/VideoDev/logs")

# File extensions
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.mts', '.m2ts', '.mpg', '.mpeg'}
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.aac', '.m4a', '.flac', '.aiff', '.ogg', '.wma'}
TRANSCRIPT_EXTENSIONS = {'.txt', '.srt', '.vtt', '.json'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.tiff', '.heic', '.raw', '.cr2', '.nef'}

# Known project patterns
PROJECT_PATTERNS = {
    'walkabout_india': {
        'patterns': [r'walkabout.*2018', r'india', r'^18\d{4}'],
        'description': 'India trip footage 2018'
    },
    'vinny_movie': {
        'patterns': [r'mymoviewithvinny', r'vinny', r'glenn.*steve', r'steve.*jeff'],
        'description': 'My Movie With Vinny project'
    },
    'pierce_gang': {
        'patterns': [r'pierce', r'charles.*pers', r'pers.*charles'],
        'description': 'Pierce Gang / Charles Pers discussions'
    },
    'pema_mindrolling': {
        'patterns': [r'pema', r'mindrolling', r'monastery'],
        'description': 'Pema Mindrolling Monastery footage'
    },
    'ferguson_family': {
        'patterns': [r'ferguson.*family', r'family.*archive', r'life.*story'],
        'description': 'Ferguson Family videos'
    },
    'christmas': {
        'patterns': [r'christmas', r'\d{6}christmas'],
        'description': 'Christmas celebrations'
    }
}

class PegasusSurvey:
    def __init__(self, db_path, resume=False, limit=None):
        self.db_path = db_path
        self.resume = resume
        self.limit = limit
        self.conn = None
        self.stats = {
            'directories_scanned': 0,
            'files_scanned': 0,
            'video_files': 0,
            'audio_files': 0,
            'image_files': 0,
            'transcript_files': 0,
            'other_files': 0,
            'total_size': 0,
            'total_duration': 0,
            'errors': 0
        }
        self.start_time = datetime.now()

    def connect(self):
        """Connect to database"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()

    def log(self, msg, level='INFO'):
        """Log message with timestamp"""
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{ts}] [{level}] {msg}")

    def parse_directory_name(self, dirname):
        """Parse semantic information from directory name"""
        result = {
            'date': None,
            'location': None,
            'camera': None,
            'description': None
        }

        # Try to extract date patterns
        # Format: YYMMDD or YYYYMMDD at start
        date_match = re.match(r'^(\d{6})(\d{2})?', dirname)
        if date_match:
            try:
                date_str = date_match.group(1)
                year = int(date_str[:2])
                month = int(date_str[2:4])
                day = int(date_str[4:6])
                # Assume 20xx for years 00-30, 19xx for 31-99
                year = 2000 + year if year <= 30 else 1900 + year
                if 1 <= month <= 12 and 1 <= day <= 31:
                    result['date'] = f"{year}-{month:02d}-{day:02d}"
                    # Rest is description
                    remaining = dirname[6:].strip()
                    if remaining:
                        result['description'] = remaining
            except:
                pass

        # Camera patterns
        camera_patterns = [
            r'(camera\s*\d+)', r'(cam\s*\d+)', r'(sony\s*4k)', r'(gh\d)', r'(a7\w*)',
            r'(iphone)', r'(gopro)', r'(dji)', r'(drone)', r'(osmo)'
        ]
        for pattern in camera_patterns:
            match = re.search(pattern, dirname, re.IGNORECASE)
            if match:
                result['camera'] = match.group(1)
                break

        # Location extraction (common locations in Ferguson archive)
        location_patterns = [
            r'(laguna)', r'(india)', r'(newhall)', r'(mammoth)', r'(hawaii)',
            r'(rome)', r'(italy)', r'(france)', r'(japan)', r'(mexico)'
        ]
        for pattern in location_patterns:
            match = re.search(pattern, dirname, re.IGNORECASE)
            if match:
                result['location'] = match.group(1).title()
                break

        return result

    def get_file_metadata(self, filepath):
        """Extract metadata from a media file using ffprobe"""
        metadata = {
            'duration_seconds': None,
            'width': None,
            'height': None,
            'frame_rate': None,
            'video_codec': None,
            'audio_codec': None,
            'audio_sample_rate': None,
            'audio_channels': None
        }

        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', filepath
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return metadata

            data = json.loads(result.stdout)

            # Duration from format
            if 'format' in data and 'duration' in data['format']:
                try:
                    metadata['duration_seconds'] = float(data['format']['duration'])
                except:
                    pass

            # Stream details
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video' and not metadata['video_codec']:
                    metadata['video_codec'] = stream.get('codec_name')
                    metadata['width'] = stream.get('width')
                    metadata['height'] = stream.get('height')
                    # Frame rate
                    if 'r_frame_rate' in stream:
                        try:
                            num, den = map(int, stream['r_frame_rate'].split('/'))
                            if den > 0:
                                metadata['frame_rate'] = round(num / den, 2)
                        except:
                            pass
                elif stream.get('codec_type') == 'audio' and not metadata['audio_codec']:
                    metadata['audio_codec'] = stream.get('codec_name')
                    metadata['audio_sample_rate'] = stream.get('sample_rate')
                    metadata['audio_channels'] = stream.get('channels')

        except subprocess.TimeoutExpired:
            self.log(f"Timeout reading: {filepath}", 'WARN')
        except Exception as e:
            self.log(f"Error reading {filepath}: {e}", 'WARN')

        return metadata

    def get_or_create_directory(self, dirpath, parent_id=None):
        """Get or create directory record"""
        cursor = self.conn.cursor()

        # Check if exists
        cursor.execute("SELECT id FROM directories WHERE path = ?", (dirpath,))
        row = cursor.fetchone()
        if row:
            return row[0]

        # Parse directory name
        dirname = os.path.basename(dirpath)
        parsed = self.parse_directory_name(dirname)
        depth = dirpath.count(os.sep) - PEGASUS_ROOT.count(os.sep)

        cursor.execute("""
            INSERT INTO directories (path, name, parent_id, depth, parsed_date,
                                     parsed_location, parsed_camera, parsed_description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            dirpath, dirname, parent_id, depth,
            parsed['date'], parsed['location'], parsed['camera'], parsed['description']
        ))

        return cursor.lastrowid

    def detect_project(self, filepath):
        """Detect which project a file belongs to based on path"""
        path_lower = filepath.lower()

        for project_name, config in PROJECT_PATTERNS.items():
            for pattern in config['patterns']:
                if re.search(pattern, path_lower, re.IGNORECASE):
                    return project_name
        return None

    def get_or_create_project(self, project_name):
        """Get or create project record"""
        cursor = self.conn.cursor()

        cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
        row = cursor.fetchone()
        if row:
            return row[0]

        config = PROJECT_PATTERNS.get(project_name, {})
        cursor.execute("""
            INSERT INTO projects (name, description)
            VALUES (?, ?)
        """, (project_name, config.get('description', '')))

        return cursor.lastrowid

    def scan_file(self, filepath, directory_id):
        """Scan a single file and add to database"""
        try:
            stat = os.stat(filepath)
            filename = os.path.basename(filepath)
            ext = os.path.splitext(filename)[1].lower()

            # Basic metadata
            size_bytes = stat.st_size
            creation_date = datetime.fromtimestamp(stat.st_birthtime) if hasattr(stat, 'st_birthtime') else None
            modification_date = datetime.fromtimestamp(stat.st_mtime)

            # Categorize file
            is_video = ext in VIDEO_EXTENSIONS
            is_audio = ext in AUDIO_EXTENSIONS
            is_image = ext in IMAGE_EXTENSIONS
            is_transcript = ext in TRANSCRIPT_EXTENSIONS

            # Get media metadata for video/audio
            media_meta = {}
            if is_video or is_audio:
                media_meta = self.get_file_metadata(filepath)

            # Detect project
            project_name = self.detect_project(filepath)
            project_id = self.get_or_create_project(project_name) if project_name else None

            # Insert file record
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO files (
                    path, filename, extension, size_bytes, duration_seconds,
                    width, height, frame_rate, video_codec, audio_codec,
                    audio_sample_rate, audio_channels, creation_date, modification_date,
                    directory_id, project_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                filepath, filename, ext, size_bytes,
                media_meta.get('duration_seconds'),
                media_meta.get('width'),
                media_meta.get('height'),
                media_meta.get('frame_rate'),
                media_meta.get('video_codec'),
                media_meta.get('audio_codec'),
                media_meta.get('audio_sample_rate'),
                media_meta.get('audio_channels'),
                creation_date, modification_date,
                directory_id, project_id
            ))

            # Update stats
            self.stats['files_scanned'] += 1
            self.stats['total_size'] += size_bytes

            if is_video:
                self.stats['video_files'] += 1
                if media_meta.get('duration_seconds'):
                    self.stats['total_duration'] += media_meta['duration_seconds']
            elif is_audio:
                self.stats['audio_files'] += 1
                if media_meta.get('duration_seconds'):
                    self.stats['total_duration'] += media_meta['duration_seconds']
            elif is_image:
                self.stats['image_files'] += 1
            elif is_transcript:
                self.stats['transcript_files'] += 1
            else:
                self.stats['other_files'] += 1

            return True

        except Exception as e:
            self.log(f"Error scanning {filepath}: {e}", 'ERROR')
            self.stats['errors'] += 1
            return False

    def update_directory_stats(self, directory_id):
        """Update aggregated stats for a directory"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE directories SET
                file_count = (SELECT COUNT(*) FROM files WHERE directory_id = ?),
                total_size_bytes = (SELECT COALESCE(SUM(size_bytes), 0) FROM files WHERE directory_id = ?),
                total_duration_seconds = (SELECT COALESCE(SUM(duration_seconds), 0) FROM files WHERE directory_id = ?)
            WHERE id = ?
        """, (directory_id, directory_id, directory_id, directory_id))

    def scan_directory(self, dirpath, parent_id=None):
        """Recursively scan a directory"""
        dirname = os.path.basename(dirpath)

        # Check exclusions
        if dirname in EXCLUDE_DIRS:
            self.log(f"Skipping excluded directory: {dirpath}")
            return

        # Skip hidden directories
        if dirname.startswith('.') and dirname != '.':
            return

        try:
            directory_id = self.get_or_create_directory(dirpath, parent_id)

            entries = os.listdir(dirpath)
            files = []
            subdirs = []

            for entry in entries:
                full_path = os.path.join(dirpath, entry)
                if os.path.isfile(full_path):
                    files.append(full_path)
                elif os.path.isdir(full_path) and not entry.startswith('.'):
                    subdirs.append(full_path)

            # Scan files in this directory
            for filepath in files:
                if self.limit and self.stats['files_scanned'] >= self.limit:
                    self.log(f"Reached file limit ({self.limit})")
                    return
                self.scan_file(filepath, directory_id)

                # Progress logging every 100 files
                if self.stats['files_scanned'] % 100 == 0:
                    self.log(f"Progress: {self.stats['files_scanned']} files, "
                            f"{self.stats['video_files']} videos, "
                            f"{self.format_size(self.stats['total_size'])}")

            # Update directory stats
            self.update_directory_stats(directory_id)
            self.stats['directories_scanned'] += 1

            # Commit after each directory
            self.conn.commit()

            # Recurse into subdirectories
            for subdir in sorted(subdirs):
                if self.limit and self.stats['files_scanned'] >= self.limit:
                    return
                self.scan_directory(subdir, directory_id)

        except PermissionError:
            self.log(f"Permission denied: {dirpath}", 'WARN')
            self.stats['errors'] += 1
        except Exception as e:
            self.log(f"Error scanning directory {dirpath}: {e}", 'ERROR')
            self.stats['errors'] += 1

    def format_size(self, bytes):
        """Format bytes to human readable"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes < 1024:
                return f"{bytes:.1f} {unit}"
            bytes /= 1024
        return f"{bytes:.1f} PB"

    def format_duration(self, seconds):
        """Format seconds to human readable"""
        if not seconds:
            return "0:00:00"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"

    def link_transcripts(self):
        """Find transcript files and link them to their source videos"""
        self.log("Linking transcript files to videos...")
        cursor = self.conn.cursor()

        # Find all transcript files
        cursor.execute("""
            SELECT id, path, filename, directory_id FROM files
            WHERE extension IN ('.txt', '.srt', '.vtt', '.json')
        """)
        transcripts = cursor.fetchall()

        linked = 0
        for t in transcripts:
            # Try to find matching video
            base_name = os.path.splitext(t['filename'])[0]
            cursor.execute("""
                SELECT id FROM files
                WHERE directory_id = ? AND extension IN (?, ?, ?, ?, ?)
                AND filename LIKE ?
            """, (t['directory_id'], '.mp4', '.mov', '.m4v', '.avi', '.mkv', base_name + '%'))

            video = cursor.fetchone()
            if video:
                # Read transcript content
                try:
                    with open(t['path'], 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    word_count = len(content.split())

                    cursor.execute("""
                        INSERT INTO transcripts (file_id, transcript_path, content, format, word_count, source)
                        VALUES (?, ?, ?, ?, ?, 'existing')
                    """, (video['id'], t['path'], content, os.path.splitext(t['filename'])[1], word_count))

                    cursor.execute("UPDATE files SET has_transcript = 1 WHERE id = ?", (video['id'],))
                    linked += 1
                except Exception as e:
                    self.log(f"Error reading transcript {t['path']}: {e}", 'WARN')

        self.conn.commit()
        self.log(f"Linked {linked} transcript files to videos")

    def update_project_stats(self):
        """Update aggregated stats for all projects"""
        self.log("Updating project statistics...")
        cursor = self.conn.cursor()

        cursor.execute("""
            UPDATE projects SET
                file_count = (SELECT COUNT(*) FROM files WHERE project_id = projects.id),
                total_size_bytes = (SELECT COALESCE(SUM(size_bytes), 0) FROM files WHERE project_id = projects.id),
                total_duration_seconds = (SELECT COALESCE(SUM(duration_seconds), 0) FROM files WHERE project_id = projects.id),
                date_range_start = (SELECT MIN(creation_date) FROM files WHERE project_id = projects.id),
                date_range_end = (SELECT MAX(creation_date) FROM files WHERE project_id = projects.id)
        """)
        self.conn.commit()

    def generate_report(self):
        """Generate summary report"""
        cursor = self.conn.cursor()
        elapsed = (datetime.now() - self.start_time).total_seconds()

        report = []
        report.append("=" * 70)
        report.append("PEGASUS DRIVE SURVEY REPORT")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Scan Duration: {self.format_duration(elapsed)}")
        report.append("=" * 70)
        report.append("")

        # Overall stats
        report.append("OVERALL STATISTICS")
        report.append("-" * 40)
        report.append(f"Directories scanned: {self.stats['directories_scanned']:,}")
        report.append(f"Files scanned: {self.stats['files_scanned']:,}")
        report.append(f"  - Video files: {self.stats['video_files']:,}")
        report.append(f"  - Audio files: {self.stats['audio_files']:,}")
        report.append(f"  - Image files: {self.stats['image_files']:,}")
        report.append(f"  - Transcript files: {self.stats['transcript_files']:,}")
        report.append(f"  - Other files: {self.stats['other_files']:,}")
        report.append(f"Total size: {self.format_size(self.stats['total_size'])}")
        report.append(f"Total duration: {self.format_duration(self.stats['total_duration'])}")
        report.append(f"Errors: {self.stats['errors']}")
        report.append("")

        # Projects summary
        report.append("DETECTED PROJECTS")
        report.append("-" * 40)
        cursor.execute("""
            SELECT name, description, file_count, total_size_bytes, total_duration_seconds
            FROM projects ORDER BY file_count DESC
        """)
        for row in cursor.fetchall():
            report.append(f"\n{row['name']}")
            report.append(f"  Description: {row['description']}")
            report.append(f"  Files: {row['file_count']:,}")
            report.append(f"  Size: {self.format_size(row['total_size_bytes'] or 0)}")
            report.append(f"  Duration: {self.format_duration(row['total_duration_seconds'] or 0)}")

        report.append("")

        # Top directories by size
        report.append("TOP 20 DIRECTORIES BY SIZE")
        report.append("-" * 40)
        cursor.execute("""
            SELECT path, file_count, total_size_bytes, total_duration_seconds
            FROM directories ORDER BY total_size_bytes DESC LIMIT 20
        """)
        for row in cursor.fetchall():
            short_path = row['path'].replace(PEGASUS_ROOT, '')
            report.append(f"{short_path[:50]:50} | {row['file_count']:5} files | {self.format_size(row['total_size_bytes'] or 0):>10}")

        report.append("")

        # Files without transcripts (needing transcription)
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM files
            WHERE extension IN ('.mp4', '.mov', '.m4v', '.avi', '.mkv') AND has_transcript = 0
        """)
        untranscribed = cursor.fetchone()['cnt']

        cursor.execute("""
            SELECT COALESCE(SUM(duration_seconds), 0) as dur FROM files
            WHERE extension IN ('.mp4', '.mov', '.m4v', '.avi', '.mkv') AND has_transcript = 0
        """)
        untranscribed_dur = cursor.fetchone()['dur']

        report.append("TRANSCRIPTION STATUS")
        report.append("-" * 40)
        report.append(f"Videos without transcripts: {untranscribed:,}")
        report.append(f"Duration needing transcription: {self.format_duration(untranscribed_dur)}")
        report.append(f"Estimated Whisper API cost: ${untranscribed_dur / 60 * 0.006:,.2f}")

        report.append("")
        report.append("=" * 70)
        report.append("END OF REPORT")
        report.append("=" * 70)

        # Write report
        report_text = "\n".join(report)
        report_path = os.path.join(LOG_DIR, f"pegasus_survey_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(report_path, 'w') as f:
            f.write(report_text)

        self.log(f"Report saved to: {report_path}")
        print("\n" + report_text)

    def run(self):
        """Run the survey"""
        self.log(f"Starting Pegasus Drive Survey")
        self.log(f"Database: {self.db_path}")
        self.log(f"Root: {PEGASUS_ROOT}")
        self.log(f"Excluding: {EXCLUDE_DIRS}")
        if self.limit:
            self.log(f"File limit: {self.limit}")

        # Verify drive is mounted
        if not os.path.exists(PEGASUS_ROOT):
            self.log(f"ERROR: Pegasus drive not mounted at {PEGASUS_ROOT}", 'ERROR')
            sys.exit(1)

        self.connect()

        try:
            # Phase 1 & 2: Scan directories and files
            self.log("Phase 1-2: Scanning directories and files...")
            self.scan_directory(PEGASUS_ROOT)

            # Phase 3: Link transcripts
            self.log("Phase 3: Linking transcripts...")
            self.link_transcripts()

            # Phase 4: Update project stats
            self.log("Phase 4: Updating project statistics...")
            self.update_project_stats()

            # Phase 5: Generate report
            self.log("Phase 5: Generating report...")
            self.generate_report()

            self.log("Survey complete!")

        finally:
            self.close()


def main():
    parser = argparse.ArgumentParser(description='Survey Pegasus drive and index all files')
    parser.add_argument('--resume', action='store_true', help='Resume interrupted scan')
    parser.add_argument('--limit', type=int, help='Limit number of files to process (for testing)')
    args = parser.parse_args()

    survey = PegasusSurvey(DB_PATH, resume=args.resume, limit=args.limit)
    survey.run()


if __name__ == '__main__':
    main()
