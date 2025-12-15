#!/usr/bin/env python3
"""
Calculate total duration and estimated Whisper API cost for composites.
"""

import os
import subprocess
import json
from datetime import datetime

COMPOSITES_FILE = "finished_composites_for_transcription.txt"
WHISPER_COST_PER_MINUTE = 0.006  # $0.006/minute

def get_duration(file_path):
    """Get video duration in seconds using ffprobe."""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_entries', 'format=duration', file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return float(data.get('format', {}).get('duration', 0))
    except:
        pass
    return 0

def main():
    # Parse composites file
    composites = []
    with open(COMPOSITES_FILE) as f:
        current_path = None
        for line in f:
            line = line.strip()
            if line.startswith('/Volumes/'):
                current_path = line
            elif line.startswith('Size:') and current_path:
                composites.append(current_path)
                current_path = None

    print(f"Found {len(composites)} composites to analyze")
    print("="*60)

    total_duration = 0
    results = []

    for i, path in enumerate(composites):
        if i % 10 == 0:
            print(f"Processing {i+1}/{len(composites)}...")

        duration = get_duration(path)
        total_duration += duration

        results.append({
            'path': path,
            'duration_sec': duration,
            'duration_min': duration / 60,
            'exists': os.path.exists(path)
        })

    # Calculate costs
    total_minutes = total_duration / 60
    total_hours = total_minutes / 60
    estimated_cost = total_minutes * WHISPER_COST_PER_MINUTE

    print("\n" + "="*60)
    print("TRANSCRIPTION COST ESTIMATE")
    print("="*60)
    print(f"Total composites: {len(composites)}")
    print(f"Total duration: {total_hours:.1f} hours ({total_minutes:.0f} minutes)")
    print(f"Whisper API rate: ${WHISPER_COST_PER_MINUTE}/minute")
    print(f"ESTIMATED COST: ${estimated_cost:.2f}")
    print("="*60)

    # Save detailed results
    with open("transcription_cost_estimate.json", "w") as f:
        json.dump({
            'generated': datetime.now().isoformat(),
            'total_composites': len(composites),
            'total_duration_seconds': total_duration,
            'total_duration_minutes': total_minutes,
            'total_duration_hours': total_hours,
            'cost_per_minute': WHISPER_COST_PER_MINUTE,
            'estimated_cost_usd': estimated_cost,
            'composites': results
        }, f, indent=2)

    print("\nDetailed results saved to transcription_cost_estimate.json")

if __name__ == "__main__":
    main()
