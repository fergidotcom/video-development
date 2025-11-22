#!/usr/bin/env python3
"""
FastAPI backend for Video Archive search and browsing.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
from pathlib import Path
from datetime import datetime

app = FastAPI(title="Video Archive API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_PATH = "video-archive.db"

# =============================================================================
# Database Helper
# =============================================================================

def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# =============================================================================
# Response Models
# =============================================================================

class VideoSummary(BaseModel):
    id: int
    filename: str
    directory: str
    category: Optional[str]
    priority: Optional[str]
    duration_seconds: Optional[int]
    transcription_status: str
    creation_date: Optional[str]

class VideoDetail(BaseModel):
    id: int
    file_path: str
    filename: str
    directory: str
    relative_path: str
    format: Optional[str]
    codec: Optional[str]
    duration_seconds: Optional[int]
    file_size_bytes: Optional[int]
    width: Optional[int]
    height: Optional[int]
    fps: Optional[float]
    creation_date: Optional[str]
    modification_date: Optional[str]
    category: Optional[str]
    priority: Optional[str]
    transcription_status: str
    transcription_cost: Optional[float]
    transcribed_at: Optional[str]
    notes: Optional[str]

class TranscriptSegment(BaseModel):
    start_time: float
    end_time: float
    text: str

class Transcript(BaseModel):
    video_id: int
    transcript_text: str
    language: Optional[str]
    word_count: Optional[int]
    segments: List[TranscriptSegment]

class SearchResult(BaseModel):
    video_id: int
    filename: str
    directory: str
    category: Optional[str]
    duration_seconds: Optional[int]
    excerpt: str
    rank: float

class Stats(BaseModel):
    total_videos: int
    transcribed_videos: int
    total_duration_hours: float
    total_cost: float
    by_category: dict
    by_status: dict

# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/")
async def root():
    """Serve the web interface."""
    return FileResponse("web/index.html")

@app.get("/api/stats", response_model=Stats)
async def get_stats():
    """Get overall statistics."""
    conn = get_db()
    cursor = conn.cursor()

    # Total videos
    cursor.execute("SELECT COUNT(*) FROM videos WHERE priority = 'high'")
    total_videos = cursor.fetchone()[0]

    # Transcribed videos
    cursor.execute("SELECT COUNT(*) FROM videos WHERE transcription_status = 'complete'")
    transcribed_videos = cursor.fetchone()[0]

    # Total duration and cost
    cursor.execute("""
        SELECT COALESCE(SUM(duration_seconds), 0), COALESCE(SUM(transcription_cost), 0)
        FROM videos
        WHERE transcription_status = 'complete'
    """)
    total_seconds, total_cost = cursor.fetchone()
    total_hours = total_seconds / 3600

    # By category
    cursor.execute("""
        SELECT category, COUNT(*), COALESCE(SUM(duration_seconds), 0)
        FROM videos
        WHERE priority = 'high'
        GROUP BY category
    """)
    by_category = {row[0]: {"count": row[1], "hours": row[2] / 3600} for row in cursor.fetchall()}

    # By status
    cursor.execute("""
        SELECT transcription_status, COUNT(*)
        FROM videos
        WHERE priority = 'high'
        GROUP BY transcription_status
    """)
    by_status = {row[0]: row[1] for row in cursor.fetchall()}

    conn.close()

    return Stats(
        total_videos=total_videos,
        transcribed_videos=transcribed_videos,
        total_duration_hours=total_hours,
        total_cost=total_cost or 0,
        by_category=by_category,
        by_status=by_status
    )

@app.get("/api/videos", response_model=List[VideoSummary])
async def list_videos(
    category: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, le=200)
):
    """List videos with optional filtering."""
    conn = get_db()
    cursor = conn.cursor()

    query = """
        SELECT id, filename, directory, category, priority,
               duration_seconds, transcription_status, creation_date
        FROM videos
        WHERE priority = 'high'
    """
    params = []

    if category:
        query += " AND category = ?"
        params.append(category)

    if status:
        query += " AND transcription_status = ?"
        params.append(status)

    query += " ORDER BY directory, filename LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    videos = cursor.fetchall()

    conn.close()

    return [VideoSummary(**dict(row)) for row in videos]

@app.get("/api/videos/{video_id}", response_model=VideoDetail)
async def get_video(video_id: int):
    """Get detailed video information."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
    video = cursor.fetchone()

    conn.close()

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    return VideoDetail(**dict(video))

@app.get("/api/transcripts/{video_id}", response_model=Transcript)
async def get_transcript(video_id: int):
    """Get transcript for a video."""
    conn = get_db()
    cursor = conn.cursor()

    # Get transcript
    cursor.execute("""
        SELECT video_id, transcript_text, language, word_count
        FROM transcripts
        WHERE video_id = ?
    """, (video_id,))
    transcript = cursor.fetchone()

    if not transcript:
        conn.close()
        raise HTTPException(status_code=404, detail="Transcript not found")

    # Get segments
    cursor.execute("""
        SELECT ts.start_time, ts.end_time, ts.text
        FROM transcript_segments ts
        JOIN transcripts t ON t.id = ts.transcript_id
        WHERE t.video_id = ?
        ORDER BY ts.start_time
    """, (video_id,))
    segments = cursor.fetchall()

    conn.close()

    return Transcript(
        video_id=transcript['video_id'],
        transcript_text=transcript['transcript_text'],
        language=transcript['language'],
        word_count=transcript['word_count'],
        segments=[TranscriptSegment(**dict(s)) for s in segments]
    )

@app.get("/api/search", response_model=List[SearchResult])
async def search_transcripts(
    q: str = Query(..., min_length=2),
    category: Optional[str] = None,
    limit: int = Query(20, le=100)
):
    """Full-text search across all transcripts."""
    conn = get_db()
    cursor = conn.cursor()

    query = """
        SELECT v.id, v.filename, v.directory, v.category, v.duration_seconds,
               snippet(transcripts_fts, 0, '<mark>', '</mark>', '...', 32) as excerpt,
               rank
        FROM transcripts_fts
        JOIN transcripts t ON t.id = transcripts_fts.rowid
        JOIN videos v ON v.id = t.video_id
        WHERE transcripts_fts MATCH ?
    """
    params = [q]

    if category:
        query += " AND v.category = ?"
        params.append(category)

    query += " ORDER BY rank LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    results = cursor.fetchall()

    conn.close()

    return [SearchResult(**dict(row)) for row in results]

@app.get("/api/categories")
async def get_categories():
    """List all categories with counts."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT category, COUNT(*) as count
        FROM videos
        WHERE priority = 'high'
        GROUP BY category
        ORDER BY count DESC
    """)
    categories = cursor.fetchall()

    conn.close()

    return [{"name": row[0], "count": row[1]} for row in categories]

# =============================================================================
# Serve Static Files
# =============================================================================

# Mount static files directory
app.mount("/web", StaticFiles(directory="web"), name="web")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3003)
