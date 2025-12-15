#!/usr/bin/env python3
"""
Search Transcripts and Narratives
=================================
Full-text search across all transcripts and narrative summaries.

Usage:
    python3 search_transcripts.py "search query"
    python3 search_transcripts.py "vinny india walkabout"
    python3 search_transcripts.py "peirce gang philosophy"
"""

import sys
import sqlite3
from pathlib import Path

TRANSCRIPT_DATABASE = "transcripts.db"

def search(query, limit=20):
    """Search transcripts using FTS5."""
    conn = sqlite3.connect(TRANSCRIPT_DATABASE)
    cursor = conn.cursor()

    # Check if FTS table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='transcripts_fts'
    """)

    if cursor.fetchone():
        # Use FTS search
        cursor.execute("""
            SELECT
                t.id,
                t.audio_file_path,
                t.word_count,
                t.duration_seconds,
                t.narrative,
                snippet(transcripts_fts, 1, '>>>', '<<<', '...', 40) as transcript_snippet,
                snippet(transcripts_fts, 2, '>>>', '<<<', '...', 40) as narrative_snippet,
                bm25(transcripts_fts) as rank
            FROM transcripts_fts
            JOIN transcripts t ON transcripts_fts.rowid = t.id
            WHERE transcripts_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit))
    else:
        # Fallback to LIKE search
        like_query = f"%{query}%"
        cursor.execute("""
            SELECT
                id,
                audio_file_path,
                word_count,
                duration_seconds,
                narrative,
                substr(transcript_text, 1, 200) as transcript_snippet,
                NULL as narrative_snippet,
                0 as rank
            FROM transcripts
            WHERE transcript_text LIKE ? OR narrative LIKE ? OR audio_file_path LIKE ?
            LIMIT ?
        """, (like_query, like_query, like_query, limit))

    results = cursor.fetchall()
    conn.close()
    return results

def format_duration(seconds):
    """Format duration as MM:SS or HH:MM:SS."""
    if not seconds:
        return "?"
    seconds = int(seconds)
    if seconds < 3600:
        return f"{seconds // 60}:{seconds % 60:02d}"
    else:
        return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 search_transcripts.py 'search query'")
        print("\nExamples:")
        print("  python3 search_transcripts.py 'vinny'")
        print("  python3 search_transcripts.py 'india walkabout'")
        print("  python3 search_transcripts.py 'peirce philosophy'")
        sys.exit(1)

    query = sys.argv[1]
    results = search(query)

    print(f"\n🔍 Search: '{query}'")
    print(f"   Found: {len(results)} results")
    print("=" * 70)

    if not results:
        print("\nNo results found. Try different search terms.")
        return

    for i, r in enumerate(results, 1):
        tid, path, words, duration, narrative, t_snip, n_snip, rank = r
        filename = Path(path).name
        folder = Path(path).parent.name

        print(f"\n[{i}] 📄 {filename}")
        print(f"    📁 {folder}")
        print(f"    ⏱️  {format_duration(duration)} | {words or '?'} words")

        if n_snip and n_snip.strip():
            print(f"    📝 {n_snip}")
        elif narrative:
            preview = narrative[:150] + "..." if len(narrative) > 150 else narrative
            print(f"    📝 {preview}")

        if t_snip and t_snip.strip():
            print(f"    💬 {t_snip}")

    print("\n" + "=" * 70)

if __name__ == "__main__":
    main()
