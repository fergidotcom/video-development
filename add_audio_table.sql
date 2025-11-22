-- Add audio extraction table to pegasus-survey database
-- Run with: sqlite3 pegasus-survey.db < add_audio_table.sql

CREATE TABLE IF NOT EXISTS audio_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    source_video_id INTEGER NOT NULL,
    audio_path TEXT NOT NULL UNIQUE,
    audio_filename TEXT NOT NULL,
    audio_directory TEXT NOT NULL,
    audio_format TEXT,
    audio_codec TEXT,
    duration_seconds REAL,
    file_size_bytes INTEGER,
    channels INTEGER,
    sample_rate INTEGER,
    bitrate INTEGER,
    extraction_status TEXT DEFAULT 'pending',
    extraction_error TEXT,
    extracted_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (file_id) REFERENCES files(id),
    FOREIGN KEY (source_video_id) REFERENCES video_metadata(id)
);

CREATE INDEX IF NOT EXISTS idx_audio_file_id ON audio_files(file_id);
CREATE INDEX IF NOT EXISTS idx_audio_source_video ON audio_files(source_video_id);
CREATE INDEX IF NOT EXISTS idx_audio_status ON audio_files(extraction_status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_audio_path ON audio_files(audio_path);

-- Add extraction progress tracking table
CREATE TABLE IF NOT EXISTS audio_extraction_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    extraction_run_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT DEFAULT 'running',
    total_videos INTEGER,
    videos_processed INTEGER DEFAULT 0,
    videos_skipped INTEGER DEFAULT 0,
    videos_errored INTEGER DEFAULT 0,
    audio_files_created INTEGER DEFAULT 0,
    total_audio_size_bytes INTEGER DEFAULT 0,
    total_duration_seconds REAL DEFAULT 0,
    current_video TEXT,
    error_summary TEXT
);

CREATE INDEX IF NOT EXISTS idx_extraction_run ON audio_extraction_progress(extraction_run_id);
