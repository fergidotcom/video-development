#!/usr/bin/env python3
"""
Import Phase 1 videos from survey data into database.
Phase 1 directories (Option A):
  - 190205JeffreyAndPop (family events)
  - 201223JeffFergusonLifeStory (life story)
  - 201227JoeFergusonLifeStoryByJeff (life story)
  - Camera1 Joe.MP4 (life story)
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime

DATABASE_PATH = "video-archive.db"
SURVEY_PATH = "survey_data/survey_full_20251120_100132.json"

# Phase 1 directories (Option A)
PHASE1_DIRECTORIES = {
    "190205JeffreyAndPop": {
        "category": "family_event",
        "priority": "high",
        "tags": [
            ("person", "jeffrey", "confirmed", "directory"),
            ("person", "pop", "confirmed", "directory")
        ]
    },
    "201223JeffFergusonLifeStory": {
        "category": "life_story",
        "priority": "high",
        "tags": [
            ("person", "jeff_ferguson", "confirmed", "directory")
        ]
    },
    "201227JoeFergusonLifeStoryByJeff": {
        "category": "life_story",
        "priority": "high",
        "tags": [
            ("person", "joe_ferguson", "confirmed", "directory")
        ]
    },
    "Camera1 Joe.MP4": {
        "category": "life_story",
        "priority": "high",
        "tags": [
            ("person", "joe_ferguson", "inferred", "filename")
        ]
    }
}

def import_phase1_videos():
    """Import Phase 1 videos into database."""

    print(f"Loading survey data from: {SURVEY_PATH}")
    with open(SURVEY_PATH) as f:
        survey = json.load(f)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    now = datetime.utcnow().isoformat() + "Z"

    total_imported = 0
    total_size_bytes = 0

    print(f"\n{'='*80}")
    print(f"IMPORTING PHASE 1 VIDEOS")
    print(f"{'='*80}\n")

    for dir_name, config in PHASE1_DIRECTORIES.items():
        videos = survey["videos_by_directory"].get(dir_name, [])

        if not videos:
            print(f"⚠️  Directory not found: {dir_name}")
            continue

        print(f"📁 {dir_name}")
        print(f"   Category: {config['category']}")
        print(f"   Priority: {config['priority']}")
        print(f"   Videos: {len(videos)}")

        for video in videos:
            # Insert video record
            cursor.execute("""
                INSERT INTO videos (
                    file_path, filename, directory, relative_path,
                    file_size_bytes, creation_date, modification_date,
                    category, priority, transcription_status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                video["path"],
                video["filename"],
                video["directory"],
                video["relative_path"],
                video.get("size_bytes", 0),
                video.get("created"),
                video.get("modified"),
                config["category"],
                config["priority"],
                "pending",
                now,
                now
            ))

            video_id = cursor.lastrowid

            # Insert tags
            for tag_type, tag_value, confidence, source in config["tags"]:
                cursor.execute("""
                    INSERT INTO video_tags (
                        video_id, tag_type, tag_value, confidence, source
                    ) VALUES (?, ?, ?, ?, ?)
                """, (video_id, tag_type, tag_value, confidence, source))

            total_imported += 1
            total_size_bytes += video.get("size_bytes", 0)

        print(f"   ✅ Imported {len(videos)} videos\n")

    conn.commit()

    # Print summary statistics
    print(f"{'='*80}")
    print(f"IMPORT SUMMARY")
    print(f"{'='*80}\n")

    cursor.execute("SELECT COUNT(*) FROM videos")
    video_count = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(file_size_bytes) FROM videos")
    total_size = cursor.fetchone()[0] or 0

    cursor.execute("SELECT category, COUNT(*) FROM videos GROUP BY category")
    categories = cursor.fetchall()

    cursor.execute("SELECT COUNT(DISTINCT video_id) FROM video_tags WHERE tag_type = 'person'")
    videos_with_people_tags = cursor.fetchone()[0]

    cursor.execute("SELECT tag_value, COUNT(*) FROM video_tags WHERE tag_type = 'person' GROUP BY tag_value")
    people_tags = cursor.fetchall()

    print(f"Total videos imported: {video_count}")
    print(f"Total size: {total_size / (1024**3):.2f} GB")
    print(f"\nBy category:")
    for category, count in categories:
        print(f"  - {category}: {count} videos")

    print(f"\nPeople tags ({videos_with_people_tags} videos tagged):")
    for person, count in people_tags:
        print(f"  - {person}: {count} videos")

    print(f"\n✅ Phase 1 import complete!")

    conn.close()

if __name__ == "__main__":
    import_phase1_videos()
