#!/usr/bin/env python3
"""
Analyze survey data to identify Phase 1 videos and calculate costs.
Phase 1 focus: Life stories and family events
"""

import json
import sys
from pathlib import Path

def main():
    # Load survey data
    survey_path = Path("survey_data/survey_full_20251120_100132.json")
    metadata_path = Path("survey_data/metadata_sample_20251120_100242.json")

    print("Loading survey data...")
    with open(survey_path) as f:
        survey = json.load(f)

    with open(metadata_path) as f:
        metadata = json.load(f)

    # Extract directory information
    directories = survey["videos_by_directory"]

    print(f"\n{'='*80}")
    print(f"VIDEO ARCHIVE SURVEY - TOP LEVEL DIRECTORIES")
    print(f"{'='*80}\n")

    # List all directories with counts
    print(f"Total top-level directories: {len(directories)}\n")

    dir_stats = []
    for dir_name, videos in directories.items():
        count = len(videos)
        # Handle missing size_bytes gracefully
        total_size = sum(v.get("size_bytes", 0) for v in videos)
        total_gb = total_size / (1024**3)
        dir_stats.append({
            "name": dir_name,
            "count": count,
            "size_gb": total_gb
        })

    # Sort by video count descending
    dir_stats.sort(key=lambda x: x["count"], reverse=True)

    print(f"{'Directory':<50} {'Videos':>10} {'Size (GB)':>12}")
    print(f"{'-'*50} {'-'*10} {'-'*12}")
    for stat in dir_stats:
        print(f"{stat['name']:<50} {stat['count']:>10,} {stat['size_gb']:>12,.2f}")

    # Identify Phase 1 candidates
    print(f"\n{'='*80}")
    print(f"PHASE 1 DIRECTORY IDENTIFICATION")
    print(f"{'='*80}\n")

    print("Looking for directories matching Phase 1 criteria:")
    print("  - Life stories (Joe Ferguson, Jeff Ferguson)")
    print("  - Family events (Jeffrey and Pop)\n")

    # Keywords to look for
    life_story_keywords = ["joe", "jeff", "ferguson", "life", "story"]
    family_event_keywords = ["jeffrey", "pop", "family"]

    phase1_candidates = []

    for dir_name in directories.keys():
        dir_lower = dir_name.lower()

        # Check for matches
        is_life_story = any(kw in dir_lower for kw in life_story_keywords)
        is_family_event = any(kw in dir_lower for kw in family_event_keywords)

        if is_life_story or is_family_event:
            category = []
            if is_life_story:
                category.append("life_story")
            if is_family_event:
                category.append("family_event")

            phase1_candidates.append({
                "directory": dir_name,
                "category": category,
                "video_count": len(directories[dir_name]),
                "videos": directories[dir_name]
            })

    if phase1_candidates:
        print(f"Found {len(phase1_candidates)} potential Phase 1 directories:\n")
        for candidate in phase1_candidates:
            print(f"  📁 {candidate['directory']}")
            print(f"     Categories: {', '.join(candidate['category'])}")
            print(f"     Videos: {candidate['video_count']}")
            print()
    else:
        print("No obvious Phase 1 directories found by keyword matching.")
        print("\nShowing all directories for manual review:")
        for dir_name in sorted(directories.keys()):
            print(f"  📁 {dir_name} ({len(directories[dir_name])} videos)")

    # Estimate costs using metadata sample average
    print(f"\n{'='*80}")
    print(f"PHASE 1 COST ESTIMATION")
    print(f"{'='*80}\n")

    avg_duration_minutes = metadata["average_duration_minutes"]
    cost_per_minute = metadata["whisper_cost_per_minute"]

    print(f"Using metadata sample statistics:")
    print(f"  - Average video duration: {avg_duration_minutes:.2f} minutes")
    print(f"  - Whisper API cost: ${cost_per_minute}/minute\n")

    if phase1_candidates:
        total_phase1_videos = sum(c["video_count"] for c in phase1_candidates)
        estimated_minutes = total_phase1_videos * avg_duration_minutes
        estimated_cost = estimated_minutes * cost_per_minute

        print(f"Phase 1 Estimate (based on averages):")
        print(f"  - Total videos: {total_phase1_videos:,}")
        print(f"  - Estimated duration: {estimated_minutes:,.2f} minutes ({estimated_minutes/60:.2f} hours)")
        print(f"  - Estimated cost: ${estimated_cost:,.2f}\n")

        print("⚠️  Note: This is an ESTIMATE based on average duration.")
        print("   Actual cost requires extracting metadata from Phase 1 videos.")
        print("   Next step: Extract actual durations for Phase 1 videos only.\n")

    # Save Phase 1 candidate list
    if phase1_candidates:
        output_path = "phase1_candidates.json"
        with open(output_path, "w") as f:
            json.dump({
                "analysis_date": metadata["sample_date"],
                "candidates": phase1_candidates,
                "estimation_method": "metadata_sample_average",
                "average_duration_minutes": avg_duration_minutes,
                "cost_per_minute": cost_per_minute
            }, f, indent=2)
        print(f"✅ Phase 1 candidates saved to: {output_path}\n")

if __name__ == "__main__":
    main()
