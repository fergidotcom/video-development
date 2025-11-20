# Video Development - Technical Reference

**Last Updated:** November 20, 2025

This document contains technical specifications, database schema, API references, and implementation details for the Video Development project.

---

## Table of Contents

1. [Database Schema](#database-schema)
2. [API Specifications](#api-specifications)
3. [File Processing Pipeline](#file-processing-pipeline)
4. [Search Implementation](#search-implementation)
5. [Web Interface](#web-interface)
6. [Deployment](#deployment)

---

## Database Schema

### SQLite Database: `video-archive.db`

**Location:** `~/Library/CloudStorage/Dropbox/Fergi/VideoDev/video-archive.db`

#### Table: `videos`

Primary table for video file metadata.

```sql
CREATE TABLE videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    duration_seconds REAL,
    format TEXT,
    codec TEXT,
    resolution TEXT,
    frame_rate REAL,
    creation_date TEXT,
    modification_date TEXT,
    category TEXT,
    tags TEXT,
    transcription_status TEXT DEFAULT 'pending',
    transcription_date TEXT,
    transcription_cost REAL,
    notes TEXT,
    favorite INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_videos_category ON videos(category);
CREATE INDEX idx_videos_status ON videos(transcription_status);
CREATE INDEX idx_videos_favorite ON videos(favorite);
CREATE INDEX idx_videos_created ON videos(creation_date);
```

**Fields:**
- `id`: Unique identifier
- `file_path`: Absolute path on Pegasus drive
- `filename`: File name only
- `file_size_bytes`: File size in bytes
- `duration_seconds`: Video duration in seconds
- `format`: Container format (mp4, mov, avi, etc.)
- `codec`: Video codec (H.264, HEVC, etc.)
- `resolution`: Video resolution (1920x1080, etc.)
- `frame_rate`: Frames per second
- `creation_date`: File creation date (ISO 8601)
- `modification_date`: Last modified date (ISO 8601)
- `category`: Content category (India/Vinny/Charles Pers/Other)
- `tags`: JSON array of tags
- `transcription_status`: pending/processing/completed/failed
- `transcription_date`: When transcription was completed
- `transcription_cost`: Whisper API cost for this video
- `notes`: User notes
- `favorite`: Boolean flag (0/1)
- `created_at`: Record creation timestamp
- `updated_at`: Record last updated timestamp

#### Table: `transcripts`

Stores time-coded transcripts from Whisper API.

```sql
CREATE TABLE transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    segment_start REAL NOT NULL,
    segment_end REAL NOT NULL,
    text TEXT NOT NULL,
    confidence REAL,
    speaker TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
);

CREATE INDEX idx_transcripts_video ON transcripts(video_id);
CREATE INDEX idx_transcripts_time ON transcripts(segment_start, segment_end);

-- Full-text search virtual table
CREATE VIRTUAL TABLE transcripts_fts USING fts5(
    text,
    content=transcripts,
    content_rowid=id
);

-- Triggers to keep FTS table in sync
CREATE TRIGGER transcripts_ai AFTER INSERT ON transcripts BEGIN
    INSERT INTO transcripts_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER transcripts_ad AFTER DELETE ON transcripts BEGIN
    DELETE FROM transcripts_fts WHERE rowid = old.id;
END;

CREATE TRIGGER transcripts_au AFTER UPDATE ON transcripts BEGIN
    UPDATE transcripts_fts SET text = new.text WHERE rowid = old.id;
END;
```

**Fields:**
- `id`: Unique identifier
- `video_id`: Foreign key to videos table
- `segment_start`: Segment start time in seconds
- `segment_end`: Segment end time in seconds
- `text`: Transcript text for this segment
- `confidence`: Whisper API confidence score (0-1)
- `speaker`: Speaker identification (future feature)
- `created_at`: Record creation timestamp

#### Table: `categories`

Predefined and custom categories for organizing videos.

```sql
CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    color TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Seed data
INSERT INTO categories (name, description, color) VALUES
    ('India Trip', 'India trip footage', '#3b82f6'),
    ('Vinny Movie', 'Vinny movie project files', '#8b5cf6'),
    ('Charles Pers', 'Charles Pers discussion recordings', '#10b981'),
    ('Other', 'Uncategorized video content', '#6b7280');
```

#### Table: `processing_log`

Append-only log of all processing operations.

```sql
CREATE TABLE processing_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER,
    operation TEXT NOT NULL,
    status TEXT NOT NULL,
    details TEXT,
    error_message TEXT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE SET NULL
);

CREATE INDEX idx_log_video ON processing_log(video_id);
CREATE INDEX idx_log_timestamp ON processing_log(timestamp);
```

**Operations:**
- `survey`: Initial file discovery
- `metadata_extract`: Video metadata extraction
- `audio_extract`: Audio extraction for transcription
- `transcribe`: Whisper API transcription
- `import`: Manual import

---

## API Specifications

### Whisper API Integration

**Provider:** OpenAI Whisper API
**Cost:** $0.006/minute of audio
**Documentation:** https://platform.openai.com/docs/guides/speech-to-text

**Python Implementation:**

```python
import openai
from pathlib import Path

def transcribe_video(video_path: str, api_key: str) -> dict:
    """
    Transcribe video using Whisper API.

    Args:
        video_path: Path to video file on Pegasus drive
        api_key: OpenAI API key

    Returns:
        Dict with transcript segments and metadata
    """
    openai.api_key = api_key

    # Extract audio to temporary file
    audio_path = extract_audio(video_path)

    try:
        with open(audio_path, 'rb') as audio_file:
            response = openai.Audio.transcribe(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["segment"]
            )

        return {
            'text': response['text'],
            'segments': response['segments'],
            'duration': response['duration'],
            'language': response['language']
        }
    finally:
        # Clean up temporary audio file
        audio_path.unlink(missing_ok=True)
```

**Response Format:**

```json
{
  "text": "Complete transcript text...",
  "segments": [
    {
      "start": 0.0,
      "end": 5.2,
      "text": "First segment text...",
      "confidence": 0.95
    },
    {
      "start": 5.2,
      "end": 10.8,
      "text": "Second segment text...",
      "confidence": 0.92
    }
  ],
  "duration": 320.5,
  "language": "en"
}
```

### Video Metadata Extraction

**Tool:** ffprobe (part of ffmpeg)

**Python Implementation:**

```python
import subprocess
import json

def extract_video_metadata(video_path: str) -> dict:
    """
    Extract video metadata using ffprobe.

    Args:
        video_path: Path to video file

    Returns:
        Dict with video metadata
    """
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        video_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)

    # Extract video stream info
    video_stream = next(
        (s for s in data['streams'] if s['codec_type'] == 'video'),
        None
    )

    return {
        'duration': float(data['format']['duration']),
        'size': int(data['format']['size']),
        'format': data['format']['format_name'],
        'codec': video_stream['codec_name'] if video_stream else None,
        'resolution': f"{video_stream['width']}x{video_stream['height']}" if video_stream else None,
        'frame_rate': eval(video_stream['r_frame_rate']) if video_stream else None
    }
```

---

## File Processing Pipeline

### 1. Survey Phase

**Goal:** Discover and catalog all video files on Pegasus drive.

**Process:**
1. Recursively scan Pegasus drive directory tree
2. Identify video files by extension (.mp4, .mov, .avi, .m4v, .mkv, .flv, .wmv)
3. Extract basic file metadata (size, dates)
4. Insert records into `videos` table
5. Log operation in `processing_log`

**Python Implementation:**

```python
from pathlib import Path
import sqlite3
from datetime import datetime

def survey_directory(base_path: Path, db_path: str):
    """Survey directory and insert video records."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    video_extensions = {'.mp4', '.mov', '.avi', '.m4v', '.mkv', '.flv', '.wmv'}

    for video_file in base_path.rglob('*'):
        if video_file.suffix.lower() in video_extensions:
            stat = video_file.stat()

            cursor.execute('''
                INSERT OR IGNORE INTO videos
                (file_path, filename, file_size_bytes, creation_date, modification_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                str(video_file),
                video_file.name,
                stat.st_size,
                datetime.fromtimestamp(stat.st_birthtime).isoformat(),
                datetime.fromtimestamp(stat.st_mtime).isoformat()
            ))

            video_id = cursor.lastrowid

            cursor.execute('''
                INSERT INTO processing_log (video_id, operation, status, details)
                VALUES (?, 'survey', 'completed', 'File discovered during initial survey')
            ''', (video_id,))

    conn.commit()
    conn.close()
```

### 2. Metadata Extraction Phase

**Goal:** Extract detailed video metadata for all surveyed files.

**Process:**
1. Query all videos with `duration_seconds IS NULL`
2. For each video, run ffprobe to extract metadata
3. Update `videos` table with metadata
4. Log operation in `processing_log`
5. Handle errors gracefully (corrupted files, unsupported formats)

### 3. Transcription Phase

**Goal:** Generate searchable transcripts for all videos.

**Process:**
1. Query videos with `transcription_status = 'pending'`
2. For each video:
   - Extract audio track
   - Submit to Whisper API
   - Parse response and insert segments into `transcripts` table
   - Update `transcription_status = 'completed'`
   - Record cost in `transcription_cost` field
   - Log operation
3. Batch processing with progress tracking
4. User approval for cost before processing

---

## Search Implementation

### Full-Text Search

Uses SQLite FTS5 (Full-Text Search) for efficient transcript search.

**Query Examples:**

```sql
-- Basic search
SELECT v.id, v.filename, t.segment_start, t.text
FROM transcripts_fts fts
JOIN transcripts t ON fts.rowid = t.id
JOIN videos v ON t.video_id = v.id
WHERE transcripts_fts MATCH 'india trip'
ORDER BY rank;

-- Search with category filter
SELECT v.id, v.filename, t.segment_start, t.text
FROM transcripts_fts fts
JOIN transcripts t ON fts.rowid = t.id
JOIN videos v ON t.video_id = v.id
WHERE transcripts_fts MATCH 'discussion'
  AND v.category = 'Charles Pers'
ORDER BY rank;

-- Phrase search
SELECT v.id, v.filename, t.segment_start, t.text
FROM transcripts_fts fts
JOIN transcripts t ON fts.rowid = t.id
JOIN videos v ON t.video_id = v.id
WHERE transcripts_fts MATCH '"charles pers"'
ORDER BY rank;
```

### Python Search API

```python
def search_transcripts(query: str, category: str = None, limit: int = 50) -> list:
    """
    Search transcripts with optional category filter.

    Args:
        query: Search query
        category: Optional category filter
        limit: Max results to return

    Returns:
        List of search results with video and segment info
    """
    conn = sqlite3.connect('video-archive.db')
    cursor = conn.cursor()

    if category:
        cursor.execute('''
            SELECT v.id, v.filename, v.file_path, t.segment_start, t.segment_end, t.text
            FROM transcripts_fts fts
            JOIN transcripts t ON fts.rowid = t.id
            JOIN videos v ON t.video_id = v.id
            WHERE transcripts_fts MATCH ?
              AND v.category = ?
            ORDER BY rank
            LIMIT ?
        ''', (query, category, limit))
    else:
        cursor.execute('''
            SELECT v.id, v.filename, v.file_path, t.segment_start, t.segment_end, t.text
            FROM transcripts_fts fts
            JOIN transcripts t ON fts.rowid = t.id
            JOIN videos v ON t.video_id = v.id
            WHERE transcripts_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        ''', (query, limit))

    results = cursor.fetchall()
    conn.close()

    return [
        {
            'video_id': r[0],
            'filename': r[1],
            'file_path': r[2],
            'timestamp': r[3],
            'timestamp_end': r[4],
            'text': r[5]
        }
        for r in results
    ]
```

---

## Web Interface

### Technology Stack

- **Backend:** Python Flask or FastAPI
- **Frontend:** Vanilla JavaScript + Fergi UI/UX standards
- **Styling:** TailwindCSS
- **Database:** SQLite (via Python sqlite3)

### Key Features

1. **Search Page**
   - Full-text search input
   - Category filter dropdown
   - Results with video thumbnail, filename, timestamp, excerpt
   - Click to jump to video at specific timestamp

2. **Video Detail Page**
   - Video metadata display
   - Complete transcript with timestamps
   - Search within transcript
   - Edit category/tags
   - Add notes
   - Mark as favorite

3. **Browse Page**
   - Grid view of all videos
   - Filter by category, date, transcription status
   - Sort by name, date, duration, size
   - Batch operations (transcribe selected, categorize, etc.)

4. **Statistics Dashboard**
   - Total videos, total duration, total size
   - Transcription progress (completed vs pending)
   - Total transcription cost
   - Videos by category (pie chart)
   - Recent activity timeline

---

## Deployment

### Development Environment

```bash
# Run Flask development server locally
cd ~/Library/CloudStorage/Dropbox/Fergi/VideoDev
python app.py

# Access at http://localhost:5000
```

### Production Deployment (Paul's Server)

**Prerequisites:**
- Paul's server configured (see FERGI_INFRASTRUCTURE_GUIDE.md)
- Database synced via Dropbox
- Videos remain on Pegasus drive (not deployed)

**Deployment Steps:**

```bash
# 1. Build production assets
npm run build

# 2. Deploy to Paul's server
scp -P 5023 -r dist/* paul@104.172.165.209:/var/www/fergi.com/video/

# 3. Deploy Python API (if using server-side rendering)
scp -P 5023 app.py paul@104.172.165.209:/var/www/fergi.com/video/
```

**Note:** Web interface runs on Paul's server, but video files remain on Pegasus drive on local Mac. Interface provides search and metadata browsing only. Actual video playback requires local access.

---

## Environment Variables

```bash
# OpenAI API key for Whisper
OPENAI_API_KEY=sk-...

# Database path
VIDEO_DB_PATH=~/Library/CloudStorage/Dropbox/Fergi/VideoDev/video-archive.db

# Pegasus drive mount point
PEGASUS_MOUNT=/Volumes/Pegasus

# Production deployment
DEPLOY_USER=paul
DEPLOY_HOST=104.172.165.209
DEPLOY_PORT=5023
DEPLOY_PATH=/var/www/fergi.com/video/
```

---

## Cost Tracking

### Transcription Cost Formula

```
Total Cost = (Total Duration in Minutes) × $0.006
```

### Example Costs

| Duration | Cost |
|----------|------|
| 1 hour   | $0.36 |
| 10 hours | $3.60 |
| 100 hours| $36.00 |
| 1000 hours| $360.00 |

### Cost Management Strategy

1. Survey provides accurate duration totals before any spending
2. User approval required before batch transcription
3. Process in controllable batches (e.g., 10 hours at a time)
4. Track costs in database for budget monitoring
5. Prioritize high-value content first

---

## Notes

- All video files remain on Pegasus drive (fast, active storage)
- Database syncs via Dropbox for backup and access
- Web interface provides search and metadata browsing
- Actual video playback requires local Pegasus drive access
- Transcription is one-time cost per video
- Full-text search provides instant results once transcribed

---

**Last Updated:** November 20, 2025
**Maintained by:** FergiDotCom Video Development Team
