#!/usr/bin/env python3
"""
Main Pipeline Orchestrator - Run Video Transcription Workflow
DO NOT RUN until Pegasus → Seagate file copy completes!
"""

import os
import sys
import argparse
import json
from pathlib import Path
from typing import Optional
import logging

from transcription_pipeline import TranscriptionPipeline
from extract_audio import AudioExtractor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('pipeline_run.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def display_banner():
    """Display pipeline banner"""
    print("""
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║         Video Archive Transcription Pipeline                  ║
║         Survey → Extract Audio → Transcribe → Store           ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
    """)


def check_pegasus_mounted(pegasus_path: str = "/Volumes/Pegasus") -> bool:
    """Check if Pegasus drive is mounted"""
    if Path(pegasus_path).exists():
        logger.info(f"✓ Pegasus drive found at: {pegasus_path}")
        return True
    else:
        logger.error(f"✗ Pegasus drive not found at: {pegasus_path}")
        logger.error("Please mount Pegasus drive before running pipeline")
        return False


def check_seagate_transfer_complete() -> bool:
    """
    Check if Seagate transfer is complete
    TODO: Implement actual check (e.g., check for marker file)
    """
    print("\n⚠️  IMPORTANT: Has the Pegasus → Seagate file copy completed?")
    response = input("Type 'yes' to confirm and continue: ").strip().lower()
    return response == 'yes'


def run_survey(pegasus_path: str, pipeline: TranscriptionPipeline):
    """
    Run Phase 1: Survey Pegasus drive
    Scan all videos and add metadata to database
    """
    logger.info("=== PHASE 1: SURVEY ===")
    logger.info(f"Scanning: {pegasus_path}")

    # Use existing pegasus_survey.py logic
    from pegasus_survey import scan_directory, extract_video_metadata

    # Scan directory structure
    video_files = scan_directory(pegasus_path)
    logger.info(f"Found {len(video_files)} video files")

    # Extract metadata and add to database
    for idx, video_path in enumerate(video_files, 1):
        logger.info(f"Processing {idx}/{len(video_files)}: {Path(video_path).name}")

        try:
            # Extract metadata using FFprobe
            metadata = extract_video_metadata(video_path)

            # Add to database
            if metadata:
                video_id = pipeline.add_video_metadata(metadata)
                logger.info(f"  Added to database (ID: {video_id})")

        except Exception as e:
            logger.error(f"  Error processing {video_path}: {e}")

    logger.info("Survey phase complete!")


def run_audio_extraction(pipeline: TranscriptionPipeline, category: Optional[str] = None):
    """
    Run Phase 2: Extract audio from all videos
    Uses FFmpeg to convert video → MP3
    """
    logger.info("=== PHASE 2: AUDIO EXTRACTION ===")

    # Get videos needing extraction
    results = pipeline.batch_extract_audio(category=category)

    logger.info(f"Audio extraction complete:")
    logger.info(f"  Success: {results['success']}")
    logger.info(f"  Failed: {results['failed']}")

    return results


def run_transcription_preview(pipeline: TranscriptionPipeline, category: Optional[str] = None):
    """
    Preview transcription costs before running
    Shows what will be transcribed and estimated cost
    """
    logger.info("=== TRANSCRIPTION PREVIEW ===")

    videos = pipeline.get_videos_ready_for_transcription(category=category)

    if not videos:
        logger.info("No videos ready for transcription")
        return

    total_duration = sum(v.get('duration_seconds', 0) for v in videos)
    total_minutes = total_duration / 60
    estimated_cost = total_minutes * 0.006

    print(f"\nReady for transcription: {len(videos)} videos")
    print(f"Total duration: {total_minutes:.1f} minutes ({total_duration/3600:.1f} hours)")
    print(f"Estimated cost: ${estimated_cost:.2f}")
    print("\nBreakdown by category:")

    by_category = {}
    for video in videos:
        cat = video.get('category', 'unknown')
        if cat not in by_category:
            by_category[cat] = {'count': 0, 'duration': 0}
        by_category[cat]['count'] += 1
        by_category[cat]['duration'] += video.get('duration_seconds', 0)

    for cat, data in by_category.items():
        minutes = data['duration'] / 60
        cost = minutes * 0.006
        print(f"  {cat}: {data['count']} videos, {minutes:.1f} min, ${cost:.2f}")


def run_transcription(pipeline: TranscriptionPipeline, category: Optional[str] = None, limit: Optional[int] = None):
    """
    Run Phase 3: Transcribe audio using Whisper API
    NOTE: This incurs costs! Preview first with --preview-transcription
    """
    logger.info("=== PHASE 3: TRANSCRIPTION ===")

    # Get videos ready for transcription
    videos = pipeline.get_videos_ready_for_transcription(category=category)

    if limit:
        videos = videos[:limit]

    if not videos:
        logger.info("No videos ready for transcription")
        return

    # Confirm before proceeding
    total_minutes = sum(v.get('duration_seconds', 0) for v in videos) / 60
    estimated_cost = total_minutes * 0.006

    print(f"\n⚠️  About to transcribe {len(videos)} videos")
    print(f"Estimated cost: ${estimated_cost:.2f}")
    response = input("Type 'yes' to confirm and proceed: ").strip().lower()

    if response != 'yes':
        logger.info("Transcription cancelled by user")
        return

    # TODO: Implement Whisper API transcription
    # This will use the transcribe.py module
    logger.warning("Whisper API transcription not yet implemented")
    logger.info("Use transcribe.py module to implement this phase")


def show_status(pipeline: TranscriptionPipeline):
    """Display current pipeline status"""
    status = pipeline.get_pipeline_status()

    print("\n" + "="*60)
    print("PIPELINE STATUS")
    print("="*60)
    print(f"Total videos: {status['total_videos']}")
    print(f"Audio extracted: {status['audio_extracted']}/{status['total_videos']}")
    print(f"Transcribed: {status['transcribed']}/{status['total_videos']}")
    print(f"Total duration: {status['total_duration_hours']} hours")
    print(f"\nPending transcription: {status['pending_transcription_minutes']} minutes")
    print(f"Estimated cost: ${status['estimated_cost']}")
    print(f"\nBy Category:")
    for cat, data in status['by_category'].items():
        print(f"  {cat}: {data['count']} videos ({data['duration_hours']} hours)")
    print("="*60 + "\n")


def main():
    """Main pipeline orchestrator"""
    parser = argparse.ArgumentParser(description="Video Archive Transcription Pipeline")

    parser.add_argument(
        '--pegasus-path',
        default='/Volumes/Pegasus',
        help='Path to Pegasus drive mount point'
    )

    parser.add_argument(
        '--audio-output-dir',
        help='Directory for extracted audio files (default: Pegasus/VideoDev_Audio)'
    )

    parser.add_argument(
        '--category',
        help='Process only specific category (e.g., India, Vinny)'
    )

    parser.add_argument(
        '--survey',
        action='store_true',
        help='Run Phase 1: Survey Pegasus drive'
    )

    parser.add_argument(
        '--extract-audio',
        action='store_true',
        help='Run Phase 2: Extract audio from videos'
    )

    parser.add_argument(
        '--preview-transcription',
        action='store_true',
        help='Preview transcription costs (no API calls)'
    )

    parser.add_argument(
        '--transcribe',
        action='store_true',
        help='Run Phase 3: Transcribe audio (INCURS COSTS!)'
    )

    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of videos to process'
    )

    parser.add_argument(
        '--status',
        action='store_true',
        help='Show pipeline status and exit'
    )

    parser.add_argument(
        '--full-pipeline',
        action='store_true',
        help='Run complete pipeline: survey → extract → preview'
    )

    args = parser.parse_args()

    display_banner()

    # Determine audio output directory
    if args.audio_output_dir:
        audio_dir = args.audio_output_dir
    else:
        # Default: VideoDev_Audio folder on Pegasus drive
        audio_dir = f"{args.pegasus_path}/VideoDev_Audio"

    logger.info(f"Audio output directory: {audio_dir}")

    # Initialize pipeline
    pipeline = TranscriptionPipeline(audio_output_dir=audio_dir)

    try:
        # Status check
        if args.status or not any([args.survey, args.extract_audio, args.preview_transcription, args.transcribe, args.full_pipeline]):
            show_status(pipeline)
            return

        # Check Seagate transfer
        if not check_seagate_transfer_complete():
            logger.error("Pipeline cancelled: Seagate transfer not complete")
            return

        # Check Pegasus mounted
        if args.survey or args.full_pipeline:
            if not check_pegasus_mounted(args.pegasus_path):
                return

        # Run requested phases
        if args.full_pipeline:
            run_survey(args.pegasus_path, pipeline)
            run_audio_extraction(pipeline, args.category)
            run_transcription_preview(pipeline, args.category)
            show_status(pipeline)

        else:
            if args.survey:
                run_survey(args.pegasus_path, pipeline)

            if args.extract_audio:
                run_audio_extraction(pipeline, args.category)

            if args.preview_transcription:
                run_transcription_preview(pipeline, args.category)

            if args.transcribe:
                run_transcription(pipeline, args.category, args.limit)

            show_status(pipeline)

    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
