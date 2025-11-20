#!/usr/bin/env python3
"""
Video Metadata Sampler
Extracts duration metadata from a sample of videos to estimate transcription costs
"""

import json
import subprocess
import random
from pathlib import Path
from datetime import datetime

def get_video_duration_ffprobe(file_path):
    """Extract video duration using ffprobe"""
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            str(file_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            data = json.loads(result.stdout)

            # Extract video stream info
            video_stream = next(
                (s for s in data.get('streams', []) if s.get('codec_type') == 'video'),
                None
            )

            duration = float(data['format'].get('duration', 0))

            return {
                'duration_seconds': duration,
                'duration_minutes': round(duration / 60, 2),
                'duration_hours': round(duration / 3600, 2),
                'format': data['format'].get('format_name'),
                'codec': video_stream.get('codec_name') if video_stream else None,
                'resolution': f"{video_stream.get('width')}x{video_stream.get('height')}" if video_stream else None,
                'frame_rate': video_stream.get('r_frame_rate') if video_stream else None,
                'size_bytes': int(data['format'].get('size', 0)),
            }
    except Exception as e:
        return {'error': str(e)}
    return None

def sample_videos(survey_file, sample_size=100):
    """Sample videos and extract metadata"""

    print("=" * 80)
    print("VIDEO METADATA SAMPLING")
    print("=" * 80)
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Sample size: {sample_size}")
    print("=" * 80)
    print()

    # Load survey data
    with open(survey_file, 'r') as f:
        survey_data = json.load(f)

    all_videos = survey_data['all_videos']
    print(f"Total videos in survey: {len(all_videos):,}")

    # Filter out videos with errors
    valid_videos = [v for v in all_videos if 'error' not in v and 'path' in v]
    print(f"Valid videos: {len(valid_videos):,}")
    print()

    # Random sample
    sample = random.sample(valid_videos, min(sample_size, len(valid_videos)))
    print(f"Sampling {len(sample)} videos...")
    print()

    # Extract metadata
    results = []
    total_duration = 0
    successful = 0
    failed = 0

    for i, video in enumerate(sample, 1):
        file_path = Path(video['path'])

        if not file_path.exists():
            print(f"  [{i}/{len(sample)}] SKIP: {video['filename']} (file not found)")
            failed += 1
            continue

        metadata = get_video_duration_ffprobe(file_path)

        if metadata and 'error' not in metadata:
            duration_min = metadata.get('duration_minutes', 0)
            total_duration += duration_min

            results.append({
                **video,
                **metadata
            })

            successful += 1
            print(f"  [{i}/{len(sample)}] OK: {video['filename']:50s} {duration_min:8.2f} min")
        else:
            error_msg = metadata.get('error', 'Unknown error') if metadata else 'Failed to extract'
            print(f"  [{i}/{len(sample)}] FAIL: {video['filename']} ({error_msg})")
            failed += 1

    print()
    print(f"Successfully extracted: {successful}/{len(sample)}")
    print(f"Failed: {failed}/{len(sample)}")
    print()

    # Calculate statistics
    if successful > 0:
        avg_duration_min = total_duration / successful
        avg_duration_hours = avg_duration_min / 60

        # Estimate for full archive
        total_videos = len(all_videos)
        estimated_total_duration_min = avg_duration_min * total_videos
        estimated_total_duration_hours = estimated_total_duration_min / 60

        # Transcription cost calculation
        whisper_cost_per_minute = 0.006
        estimated_transcription_cost = estimated_total_duration_min * whisper_cost_per_minute

        print("=" * 80)
        print("SAMPLE STATISTICS")
        print("=" * 80)
        print(f"Sample size: {successful} videos")
        print(f"Total sample duration: {total_duration:,.2f} minutes ({total_duration/60:.2f} hours)")
        print(f"Average duration per video: {avg_duration_min:.2f} minutes ({avg_duration_hours:.2f} hours)")
        print()

        print("=" * 80)
        print("ESTIMATED FULL ARCHIVE STATISTICS")
        print("=" * 80)
        print(f"Total videos: {total_videos:,}")
        print(f"Estimated total duration: {estimated_total_duration_min:,.0f} minutes ({estimated_total_duration_hours:,.0f} hours)")
        print(f"Estimated transcription cost: ${estimated_transcription_cost:,.2f}")
        print()

        print("COST BREAKDOWN BY DIRECTORY:")
        print("(Based on proportional video counts)")
        print()

        # Calculate per-directory estimates
        videos_by_dir = survey_data['videos_by_directory']
        for dirname in sorted(videos_by_dir.keys(), key=lambda x: len(videos_by_dir[x]), reverse=True):
            dir_video_count = len(videos_by_dir[dirname])
            dir_estimated_duration = avg_duration_min * dir_video_count
            dir_estimated_cost = dir_estimated_duration * whisper_cost_per_minute
            print(f"  {dirname:40s} {dir_video_count:5,} videos  ~{dir_estimated_duration:8,.0f} min  ~${dir_estimated_cost:8,.2f}")

        print()
        print("=" * 80)

        # Save results
        return {
            'sample_date': datetime.now().isoformat(),
            'sample_size': successful,
            'failed_count': failed,
            'total_sample_duration_minutes': total_duration,
            'average_duration_minutes': avg_duration_min,
            'average_duration_hours': avg_duration_hours,
            'total_videos': total_videos,
            'estimated_total_duration_minutes': estimated_total_duration_min,
            'estimated_total_duration_hours': estimated_total_duration_hours,
            'estimated_transcription_cost': estimated_transcription_cost,
            'whisper_cost_per_minute': whisper_cost_per_minute,
            'sample_videos': results
        }

    return None

if __name__ == '__main__':
    # Find most recent survey file
    survey_dir = Path.home() / "Library/CloudStorage/Dropbox/Fergi/VideoDev/survey_data"
    survey_files = sorted(survey_dir.glob("survey_full_*.json"), reverse=True)

    if not survey_files:
        print("ERROR: No survey files found. Run pegasus_survey.py first.")
        exit(1)

    survey_file = survey_files[0]
    print(f"Using survey file: {survey_file.name}")
    print()

    # Run sampling
    results = sample_videos(survey_file, sample_size=100)

    if results:
        # Save results
        output_file = survey_dir / f"metadata_sample_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"Metadata sample saved to: {output_file}")
