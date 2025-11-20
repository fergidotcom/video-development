#!/usr/bin/env python3
"""
Audio Extraction Module - FFmpeg Integration
Extracts audio from video files for Whisper API transcription
"""

import os
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Optional
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('audio_extraction.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class AudioExtractor:
    """Extract audio from video files using FFmpeg"""

    def __init__(self, output_dir: str = "./audio_extracts"):
        """
        Initialize audio extractor

        Args:
            output_dir: Directory to store extracted audio files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.extraction_log = []

    def check_ffmpeg(self) -> bool:
        """Verify FFmpeg is installed and accessible"""
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                text=True
            )
            logger.info(f"FFmpeg found: {result.stdout.split()[2]}")
            return True
        except FileNotFoundError:
            logger.error("FFmpeg not found. Please install FFmpeg.")
            return False

    def extract_audio(
        self,
        video_path: str,
        output_format: str = 'mp3',
        quality: int = 2,
        overwrite: bool = False
    ) -> Optional[Dict]:
        """
        Extract audio from a single video file

        Args:
            video_path: Path to video file
            output_format: Audio format (mp3, wav, m4a)
            quality: Audio quality (0-9, 2=high quality ~190kbps)
            overwrite: Overwrite existing audio file

        Returns:
            Dict with extraction results or None if failed
        """
        video_path = Path(video_path)

        if not video_path.exists():
            logger.error(f"Video file not found: {video_path}")
            return None

        # Create output filename
        output_filename = f"{video_path.stem}.{output_format}"
        output_path = self.output_dir / output_filename

        # Check if already extracted
        if output_path.exists() and not overwrite:
            logger.info(f"Audio already extracted: {output_path}")
            return {
                'video_path': str(video_path),
                'audio_path': str(output_path),
                'status': 'already_exists',
                'file_size': output_path.stat().st_size
            }

        # Build FFmpeg command
        cmd = [
            'ffmpeg',
            '-i', str(video_path),
            '-vn',  # No video
            '-acodec', 'libmp3lame' if output_format == 'mp3' else 'aac',
            '-q:a', str(quality),
            '-y' if overwrite else '-n',  # Overwrite or skip if exists
            str(output_path)
        ]

        logger.info(f"Extracting audio: {video_path.name} → {output_filename}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout for large files
            )

            if result.returncode == 0:
                file_size = output_path.stat().st_size
                logger.info(f"✓ Extracted: {output_filename} ({file_size:,} bytes)")

                extraction_result = {
                    'video_path': str(video_path),
                    'audio_path': str(output_path),
                    'status': 'success',
                    'file_size': file_size,
                    'format': output_format
                }
                self.extraction_log.append(extraction_result)
                return extraction_result
            else:
                logger.error(f"✗ FFmpeg error: {result.stderr}")
                return {
                    'video_path': str(video_path),
                    'status': 'error',
                    'error': result.stderr
                }

        except subprocess.TimeoutExpired:
            logger.error(f"✗ Timeout extracting: {video_path.name}")
            return {
                'video_path': str(video_path),
                'status': 'timeout'
            }
        except Exception as e:
            logger.error(f"✗ Exception: {e}")
            return {
                'video_path': str(video_path),
                'status': 'error',
                'error': str(e)
            }

    def batch_extract(
        self,
        video_paths: List[str],
        output_format: str = 'mp3',
        quality: int = 2,
        overwrite: bool = False
    ) -> Dict:
        """
        Extract audio from multiple video files

        Args:
            video_paths: List of video file paths
            output_format: Audio format (mp3, wav, m4a)
            quality: Audio quality (0-9)
            overwrite: Overwrite existing audio files

        Returns:
            Dict with batch extraction summary
        """
        logger.info(f"Starting batch extraction of {len(video_paths)} videos")

        results = {
            'total': len(video_paths),
            'success': 0,
            'already_exists': 0,
            'failed': 0,
            'extractions': []
        }

        for idx, video_path in enumerate(video_paths, 1):
            logger.info(f"Processing {idx}/{len(video_paths)}: {Path(video_path).name}")

            result = self.extract_audio(video_path, output_format, quality, overwrite)

            if result:
                results['extractions'].append(result)

                if result['status'] == 'success':
                    results['success'] += 1
                elif result['status'] == 'already_exists':
                    results['already_exists'] += 1
                else:
                    results['failed'] += 1
            else:
                results['failed'] += 1

        logger.info(f"Batch extraction complete:")
        logger.info(f"  Success: {results['success']}")
        logger.info(f"  Already exists: {results['already_exists']}")
        logger.info(f"  Failed: {results['failed']}")

        return results

    def save_extraction_log(self, output_file: str = "extraction_log.json"):
        """Save extraction log to JSON file"""
        log_path = self.output_dir / output_file
        with open(log_path, 'w') as f:
            json.dump(self.extraction_log, f, indent=2)
        logger.info(f"Extraction log saved to: {log_path}")


def main():
    """Example usage"""
    extractor = AudioExtractor(output_dir="./audio_extracts")

    # Check FFmpeg
    if not extractor.check_ffmpeg():
        return

    # Example: Extract single file
    # result = extractor.extract_audio("/path/to/video.mp4")
    # print(json.dumps(result, indent=2))

    # Example: Batch extract
    # video_files = ["/path/to/video1.mp4", "/path/to/video2.mp4"]
    # results = extractor.batch_extract(video_files)
    # extractor.save_extraction_log()

    print("AudioExtractor module ready. Import and use in your pipeline.")


if __name__ == "__main__":
    main()
