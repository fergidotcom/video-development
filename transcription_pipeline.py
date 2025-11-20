#!/usr/bin/env python3
"""
Video Transcription Pipeline - Complete Workflow
Survey → Extract Audio → Transcribe → Store in Database
"""

import os
import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import logging

from extract_audio import AudioExtractor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('transcription_pipeline.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TranscriptionPipeline:
    """Complete pipeline for video transcription workflow"""

    def __init__(
        self,
        db_path: str = "video-archive.db",
        audio_output_dir: str = "./audio_extracts"
    ):
        """
        Initialize transcription pipeline

        Args:
            db_path: Path to SQLite database
            audio_output_dir: Directory for extracted audio files
        """
        self.db_path = db_path
        self.audio_extractor = AudioExtractor(output_dir=audio_output_dir)
        self.conn = None
        self.init_database()

    def init_database(self):
        """Initialize SQLite database with schema"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.cursor()

        # Videos table - metadata for each video file
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                file_size INTEGER,
                duration_seconds REAL,
                format TEXT,
                width INTEGER,
                height INTEGER,
                codec TEXT,
                category TEXT,
                created_date TEXT,
                added_date TEXT DEFAULT CURRENT_TIMESTAMP,
                audio_extracted INTEGER DEFAULT 0,
                audio_path TEXT,
                transcription_status TEXT DEFAULT 'pending',
                transcription_cost REAL
            )
        ''')

        # Transcripts table - time-coded transcription data
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transcripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id INTEGER NOT NULL,
                full_text TEXT NOT NULL,
                language TEXT,
                duration REAL,
                timestamp_data TEXT,
                transcribed_date TEXT DEFAULT CURRENT_TIMESTAMP,
                api_response TEXT,
                FOREIGN KEY (video_id) REFERENCES videos (id)
            )
        ''')

        # Processing log - track all pipeline operations
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processing_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id INTEGER,
                operation TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (video_id) REFERENCES videos (id)
            )
        ''')

        # Full-text search index for transcripts
        cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts USING fts5(
                video_id,
                full_text,
                content=transcripts,
                content_rowid=id
            )
        ''')

        self.conn.commit()
        logger.info(f"Database initialized: {self.db_path}")

    def log_operation(
        self,
        operation: str,
        status: str,
        message: str = "",
        video_id: Optional[int] = None
    ):
        """Log pipeline operation to database"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO processing_log (video_id, operation, status, message)
            VALUES (?, ?, ?, ?)
        ''', (video_id, operation, status, message))
        self.conn.commit()

    def add_video_metadata(self, metadata: Dict) -> int:
        """
        Add video metadata to database

        Args:
            metadata: Dictionary with video metadata

        Returns:
            Video ID in database
        """
        cursor = self.conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO videos (
                    file_path, filename, file_size, duration_seconds,
                    format, width, height, codec, category, created_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                metadata.get('file_path'),
                metadata.get('filename'),
                metadata.get('file_size'),
                metadata.get('duration_seconds'),
                metadata.get('format'),
                metadata.get('width'),
                metadata.get('height'),
                metadata.get('codec'),
                metadata.get('category'),
                metadata.get('created_date')
            ))

            self.conn.commit()
            video_id = cursor.lastrowid

            self.log_operation(
                'add_metadata',
                'success',
                f"Added video: {metadata.get('filename')}",
                video_id
            )

            logger.info(f"Added video metadata: {metadata.get('filename')} (ID: {video_id})")
            return video_id

        except sqlite3.IntegrityError:
            logger.warning(f"Video already exists: {metadata.get('file_path')}")
            cursor.execute('SELECT id FROM videos WHERE file_path = ?', (metadata.get('file_path'),))
            return cursor.fetchone()[0]

    def extract_audio_for_video(self, video_id: int) -> bool:
        """
        Extract audio from video in database

        Args:
            video_id: Video ID in database

        Returns:
            True if successful, False otherwise
        """
        cursor = self.conn.cursor()
        cursor.execute('SELECT file_path, audio_extracted FROM videos WHERE id = ?', (video_id,))
        row = cursor.fetchone()

        if not row:
            logger.error(f"Video ID {video_id} not found in database")
            return False

        video_path = row['file_path']
        already_extracted = row['audio_extracted']

        if already_extracted:
            logger.info(f"Audio already extracted for video ID {video_id}")
            return True

        # Extract audio using FFmpeg
        result = self.audio_extractor.extract_audio(video_path)

        if result and result['status'] in ('success', 'already_exists'):
            # Update database
            cursor.execute('''
                UPDATE videos
                SET audio_extracted = 1, audio_path = ?
                WHERE id = ?
            ''', (result['audio_path'], video_id))

            self.conn.commit()

            self.log_operation(
                'extract_audio',
                'success',
                f"Audio extracted: {result['audio_path']}",
                video_id
            )

            logger.info(f"✓ Audio extraction complete for video ID {video_id}")
            return True
        else:
            self.log_operation(
                'extract_audio',
                'failed',
                f"Error: {result.get('error', 'Unknown error')}",
                video_id
            )
            logger.error(f"✗ Audio extraction failed for video ID {video_id}")
            return False

    def batch_extract_audio(self, category: Optional[str] = None) -> Dict:
        """
        Extract audio for all videos in database

        Args:
            category: Optional category filter (e.g., 'India', 'Vinny')

        Returns:
            Summary of batch extraction
        """
        cursor = self.conn.cursor()

        # Get videos that need audio extraction
        if category:
            cursor.execute('''
                SELECT id, file_path FROM videos
                WHERE audio_extracted = 0 AND category = ?
                ORDER BY id
            ''', (category,))
        else:
            cursor.execute('''
                SELECT id, file_path FROM videos
                WHERE audio_extracted = 0
                ORDER BY id
            ''')

        videos = cursor.fetchall()

        logger.info(f"Found {len(videos)} videos needing audio extraction")

        results = {
            'total': len(videos),
            'success': 0,
            'failed': 0,
            'video_ids': []
        }

        for video in videos:
            video_id = video['id']
            success = self.extract_audio_for_video(video_id)

            if success:
                results['success'] += 1
                results['video_ids'].append(video_id)
            else:
                results['failed'] += 1

        logger.info(f"Batch audio extraction complete: {results['success']}/{results['total']} successful")

        return results

    def add_transcript(
        self,
        video_id: int,
        transcript_data: Dict
    ) -> int:
        """
        Add transcription result to database

        Args:
            video_id: Video ID in database
            transcript_data: Dict with transcript text, language, etc.

        Returns:
            Transcript ID
        """
        cursor = self.conn.cursor()

        # Insert transcript
        cursor.execute('''
            INSERT INTO transcripts (
                video_id, full_text, language, duration, timestamp_data, api_response
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            video_id,
            transcript_data.get('text'),
            transcript_data.get('language'),
            transcript_data.get('duration'),
            json.dumps(transcript_data.get('segments', [])),
            json.dumps(transcript_data.get('api_response', {}))
        ))

        transcript_id = cursor.lastrowid

        # Update video status
        cursor.execute('''
            UPDATE videos
            SET transcription_status = 'completed',
                transcription_cost = ?
            WHERE id = ?
        ''', (transcript_data.get('cost', 0), video_id))

        # Update FTS index
        cursor.execute('''
            INSERT INTO transcripts_fts (video_id, full_text)
            VALUES (?, ?)
        ''', (video_id, transcript_data.get('text')))

        self.conn.commit()

        self.log_operation(
            'transcribe',
            'success',
            f"Transcript added (ID: {transcript_id})",
            video_id
        )

        logger.info(f"✓ Transcript added for video ID {video_id}")
        return transcript_id

    def get_videos_ready_for_transcription(self, category: Optional[str] = None) -> List[Dict]:
        """
        Get videos that have audio extracted but not transcribed

        Args:
            category: Optional category filter

        Returns:
            List of video records
        """
        cursor = self.conn.cursor()

        if category:
            cursor.execute('''
                SELECT id, file_path, audio_path, filename, duration_seconds, category
                FROM videos
                WHERE audio_extracted = 1
                AND transcription_status = 'pending'
                AND category = ?
                ORDER BY id
            ''', (category,))
        else:
            cursor.execute('''
                SELECT id, file_path, audio_path, filename, duration_seconds, category
                FROM videos
                WHERE audio_extracted = 1
                AND transcription_status = 'pending'
                ORDER BY id
            ''')

        return [dict(row) for row in cursor.fetchall()]

    def search_transcripts(self, query: str) -> List[Dict]:
        """
        Full-text search across all transcripts

        Args:
            query: Search query

        Returns:
            List of matching videos with transcript snippets
        """
        cursor = self.conn.cursor()

        cursor.execute('''
            SELECT
                v.id, v.filename, v.file_path, v.category,
                t.full_text,
                snippet(transcripts_fts, 1, '<mark>', '</mark>', '...', 64) as snippet
            FROM transcripts_fts
            JOIN transcripts t ON transcripts_fts.rowid = t.id
            JOIN videos v ON t.video_id = v.id
            WHERE transcripts_fts MATCH ?
            ORDER BY rank
        ''', (query,))

        return [dict(row) for row in cursor.fetchall()]

    def get_pipeline_status(self) -> Dict:
        """Get overall pipeline status and statistics"""
        cursor = self.conn.cursor()

        stats = {}

        # Total videos
        cursor.execute('SELECT COUNT(*) as count FROM videos')
        stats['total_videos'] = cursor.fetchone()['count']

        # Audio extraction status
        cursor.execute('SELECT COUNT(*) as count FROM videos WHERE audio_extracted = 1')
        stats['audio_extracted'] = cursor.fetchone()['count']

        # Transcription status
        cursor.execute('SELECT COUNT(*) as count FROM videos WHERE transcription_status = "completed"')
        stats['transcribed'] = cursor.fetchone()['count']

        # Total duration
        cursor.execute('SELECT SUM(duration_seconds) as total FROM videos')
        total_seconds = cursor.fetchone()['total'] or 0
        stats['total_duration_hours'] = round(total_seconds / 3600, 2)

        # Estimated cost (if not transcribed)
        cursor.execute('''
            SELECT SUM(duration_seconds) as total FROM videos
            WHERE transcription_status = 'pending' AND audio_extracted = 1
        ''')
        pending_seconds = cursor.fetchone()['total'] or 0
        stats['pending_transcription_minutes'] = round(pending_seconds / 60, 2)
        stats['estimated_cost'] = round((pending_seconds / 60) * 0.006, 2)

        # By category
        cursor.execute('''
            SELECT category, COUNT(*) as count, SUM(duration_seconds) as duration
            FROM videos
            GROUP BY category
        ''')
        stats['by_category'] = {
            row['category']: {
                'count': row['count'],
                'duration_hours': round(row['duration'] / 3600, 2) if row['duration'] else 0
            }
            for row in cursor.fetchall()
        }

        return stats

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")


def main():
    """Example usage"""
    pipeline = TranscriptionPipeline()

    # Get pipeline status
    status = pipeline.get_pipeline_status()
    print("\n=== Pipeline Status ===")
    print(json.dumps(status, indent=2))

    pipeline.close()


if __name__ == "__main__":
    main()
