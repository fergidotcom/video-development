#!/usr/bin/env python3
"""
Repair NULL audio_file_path in transcripts.db by looking up file_id in pegasus-survey.db

The file_id column references pegasus-survey.db files table.
This script:
1. Finds all transcripts with NULL audio_file_path
2. Looks up the video path from pegasus-survey.db using file_id
3. Updates the audio_file_path in transcripts.db with the video path
4. Reports statistics
"""

import sqlite3

TRANSCRIPTS_DB = "/Users/joeferguson/Library/CloudStorage/Dropbox/Fergi/VideoDev/transcripts.db"
SURVEY_DB = "/Users/joeferguson/Library/CloudStorage/Dropbox/Fergi/VideoDev/pegasus-survey.db"

def main():
    print("=" * 60)
    print("Repairing Transcript Links")
    print("=" * 60)

    # Connect to databases
    trans_conn = sqlite3.connect(TRANSCRIPTS_DB)
    trans_cursor = trans_conn.cursor()

    survey_conn = sqlite3.connect(SURVEY_DB)
    survey_cursor = survey_conn.cursor()

    # Get all transcripts with NULL audio_file_path but with file_id
    trans_cursor.execute("""
        SELECT id, file_id
        FROM transcripts
        WHERE audio_file_path IS NULL AND file_id IS NOT NULL
    """)
    null_transcripts = trans_cursor.fetchall()
    print(f"\nFound {len(null_transcripts)} transcripts with NULL path but valid file_id")

    # Build lookup of file_id -> file_path from survey db
    survey_cursor.execute("SELECT id, file_path FROM files")
    file_lookup = {row[0]: row[1] for row in survey_cursor.fetchall()}
    print(f"Loaded {len(file_lookup)} files from pegasus-survey.db")

    # Repair links
    repaired = 0
    not_found = []
    repaired_details = []

    for trans_id, file_id in null_transcripts:
        if file_id in file_lookup:
            video_path = file_lookup[file_id]
            # Store the video path directly (not extracted audio path)
            trans_cursor.execute(
                "UPDATE transcripts SET audio_file_path = ? WHERE id = ?",
                (video_path, trans_id)
            )
            repaired += 1
            if len(repaired_details) < 10:
                repaired_details.append((trans_id, file_id, video_path))
        else:
            not_found.append((trans_id, file_id))

    trans_conn.commit()

    # Report results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"\nRepaired: {repaired}")
    print(f"File ID not found: {len(not_found)}")

    if repaired_details:
        print("\nSample repaired transcripts:")
        for trans_id, file_id, path in repaired_details:
            print(f"  transcript {trans_id} -> file_id {file_id}")
            print(f"    Path: ...{path[-70:]}")

    if not_found:
        print(f"\nFile IDs not found in survey db (first 10):")
        for trans_id, file_id in not_found[:10]:
            print(f"  transcript {trans_id} -> file_id {file_id} (missing)")

    # Close connections
    survey_conn.close()
    trans_conn.close()

    print("\n" + "=" * 60)
    print("Done! audio_file_path repaired in transcripts.db")
    print("=" * 60)

if __name__ == "__main__":
    main()
