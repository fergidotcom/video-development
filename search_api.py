#!/usr/bin/env python3
"""
FastAPI backend for Video Archive Transcript Search.
Works with transcripts.db containing FTS5 full-text search.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
from pathlib import Path
import os
import time
import re

app = FastAPI(title="Video Archive Search API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database path - look for transcripts.db in same directory as script
SCRIPT_DIR = Path(__file__).parent
DATABASE_PATH = SCRIPT_DIR / "transcripts.db"

# =============================================================================
# Database Helper
# =============================================================================

def get_db():
    """Get database connection."""
    if not DATABASE_PATH.exists():
        raise HTTPException(status_code=500, detail=f"Database not found: {DATABASE_PATH}")
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    return conn

# =============================================================================
# Response Models
# =============================================================================

class SearchResult(BaseModel):
    id: int
    video_filename: str
    video_path: str
    match_snippet: str
    narrative_summary: Optional[str]
    family_members: Optional[str]
    other_people: Optional[str]
    word_count: Optional[int]
    duration_seconds: Optional[float]

class VideoDetail(BaseModel):
    id: int
    video_filename: str
    video_path: str
    transcript_text: str
    narrative: Optional[str]
    family_members: Optional[str]
    other_people: Optional[str]
    word_count: Optional[int]
    duration_seconds: Optional[float]
    language: Optional[str]
    segments: List[dict]

class Stats(BaseModel):
    total_videos: int
    total_words: int
    total_duration_hours: float
    total_cost: float
    unique_family_members: List[str]

class SearchResponse(BaseModel):
    results: List[SearchResult]
    total_results: int
    query_time_ms: int

# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/api/search", response_model=SearchResponse)
async def search_transcripts(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(50, le=200, description="Max results")
):
    """Full-text search across all transcripts using FTS5."""
    start_time = time.time()
    conn = get_db()
    cursor = conn.cursor()

    try:
        # FTS5 search with snippet highlighting
        cursor.execute("""
            SELECT
                t.id,
                t.audio_file_path,
                snippet(transcripts_fts, 1, '<mark>', '</mark>', '...', 40) as match_snippet,
                t.narrative,
                t.family_members,
                t.other_people,
                t.word_count,
                t.duration_seconds
            FROM transcripts_fts
            JOIN transcripts t ON t.id = transcripts_fts.rowid
            WHERE transcripts_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (q, limit))

        rows = cursor.fetchall()

        results = []
        for row in rows:
            # Extract filename from path
            path = row['audio_file_path'] or ''
            filename = Path(path).stem.replace('_extracted', '')

            results.append(SearchResult(
                id=row['id'],
                video_filename=filename,
                video_path=path.replace('/ExtractedAudio/', '/'),  # Convert audio path back to video path
                match_snippet=row['match_snippet'] or '',
                narrative_summary=row['narrative'][:500] + '...' if row['narrative'] and len(row['narrative']) > 500 else row['narrative'],
                family_members=row['family_members'],
                other_people=row['other_people'],
                word_count=row['word_count'],
                duration_seconds=row['duration_seconds']
            ))

        query_time_ms = int((time.time() - start_time) * 1000)

        return SearchResponse(
            results=results,
            total_results=len(results),
            query_time_ms=query_time_ms
        )
    finally:
        conn.close()

@app.get("/api/video/{video_id}", response_model=VideoDetail)
async def get_video(video_id: int):
    """Get full details for a single video transcript."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        # Get transcript
        cursor.execute("""
            SELECT id, audio_file_path, transcript_text, narrative,
                   family_members, other_people, word_count,
                   duration_seconds, language
            FROM transcripts
            WHERE id = ?
        """, (video_id,))

        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Video not found")

        # Get segments
        cursor.execute("""
            SELECT segment_index, start_time, end_time, text
            FROM transcript_segments
            WHERE transcript_id = ?
            ORDER BY segment_index
        """, (video_id,))

        segments = [dict(s) for s in cursor.fetchall()]

        path = row['audio_file_path'] or ''
        filename = Path(path).stem.replace('_extracted', '')

        return VideoDetail(
            id=row['id'],
            video_filename=filename,
            video_path=path.replace('/ExtractedAudio/', '/'),
            transcript_text=row['transcript_text'] or '',
            narrative=row['narrative'],
            family_members=row['family_members'],
            other_people=row['other_people'],
            word_count=row['word_count'],
            duration_seconds=row['duration_seconds'],
            language=row['language'],
            segments=segments
        )
    finally:
        conn.close()

@app.get("/api/stats", response_model=Stats)
async def get_stats():
    """Get overall statistics about the transcript database."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        # Total videos and words
        cursor.execute("""
            SELECT COUNT(*) as total,
                   COALESCE(SUM(word_count), 0) as total_words,
                   COALESCE(SUM(duration_seconds), 0) as total_duration,
                   COALESCE(SUM(cost_dollars), 0) as total_cost
            FROM transcripts
        """)
        row = cursor.fetchone()

        # Get unique family members
        cursor.execute("SELECT family_members FROM transcripts WHERE family_members IS NOT NULL")
        all_members = set()
        for r in cursor.fetchall():
            if r['family_members']:
                # Parse comma-separated list
                members = [m.strip() for m in r['family_members'].split(',')]
                all_members.update(members)

        # Clean up member names (remove parenthetical notes)
        clean_members = set()
        for m in all_members:
            # Extract just the name without parenthetical
            name = re.sub(r'\s*\([^)]*\)', '', m).strip()
            if name and len(name) > 2:
                clean_members.add(name)

        return Stats(
            total_videos=row['total'],
            total_words=row['total_words'],
            total_duration_hours=row['total_duration'] / 3600 if row['total_duration'] else 0,
            total_cost=row['total_cost'] or 0,
            unique_family_members=sorted(list(clean_members))[:50]  # Top 50
        )
    finally:
        conn.close()

@app.get("/api/people")
async def get_people():
    """Get list of all mentioned people with counts."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT family_members, other_people FROM transcripts")

        people_count = {}
        for row in cursor.fetchall():
            for field in ['family_members', 'other_people']:
                if row[field]:
                    for person in row[field].split(','):
                        name = re.sub(r'\s*\([^)]*\)', '', person).strip()
                        if name and len(name) > 2:
                            people_count[name] = people_count.get(name, 0) + 1

        # Sort by count
        sorted_people = sorted(people_count.items(), key=lambda x: -x[1])

        return [{"name": name, "count": count} for name, count in sorted_people[:100]]
    finally:
        conn.close()

@app.get("/api/recent")
async def get_recent(limit: int = Query(20, le=100)):
    """Get most recently transcribed videos."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id, audio_file_path, narrative, family_members,
                   word_count, duration_seconds, transcribed_at
            FROM transcripts
            WHERE transcribed_at IS NOT NULL
            ORDER BY transcribed_at DESC
            LIMIT ?
        """, (limit,))

        results = []
        for row in cursor.fetchall():
            path = row['audio_file_path'] or ''
            filename = Path(path).stem.replace('_extracted', '')
            results.append({
                "id": row['id'],
                "video_filename": filename,
                "narrative_preview": row['narrative'][:200] + '...' if row['narrative'] and len(row['narrative']) > 200 else row['narrative'],
                "family_members": row['family_members'],
                "word_count": row['word_count'],
                "duration_seconds": row['duration_seconds'],
                "transcribed_at": row['transcribed_at']
            })

        return results
    finally:
        conn.close()

# =============================================================================
# Serve Frontend
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the search interface."""
    html_path = SCRIPT_DIR / "search.html"
    if html_path.exists():
        return FileResponse(html_path)
    return HTMLResponse("<h1>Video Archive Search</h1><p>Frontend not found. Use /api/search?q=query to search.</p>")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
