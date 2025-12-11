-- Pegasus Drive Index Database Schema
-- Created: 2025-12-11
-- Purpose: Comprehensive index of all media files on Pegasus drive

-- Projects table (must exist before files for FK)
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    root_directory TEXT,
    file_count INTEGER DEFAULT 0,
    total_size_bytes INTEGER DEFAULT 0,
    total_duration_seconds REAL DEFAULT 0,
    date_range_start DATE,
    date_range_end DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Directories table
CREATE TABLE IF NOT EXISTS directories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    parent_id INTEGER,
    depth INTEGER,
    parsed_date DATE,
    parsed_location TEXT,
    parsed_camera TEXT,
    parsed_description TEXT,
    file_count INTEGER DEFAULT 0,
    total_size_bytes INTEGER DEFAULT 0,
    total_duration_seconds REAL DEFAULT 0,
    scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_id) REFERENCES directories(id)
);

-- Files table
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    extension TEXT,
    size_bytes INTEGER,
    duration_seconds REAL,
    width INTEGER,
    height INTEGER,
    frame_rate REAL,
    video_codec TEXT,
    audio_codec TEXT,
    audio_sample_rate INTEGER,
    audio_channels INTEGER,
    creation_date TIMESTAMP,
    modification_date TIMESTAMP,
    camera_model TEXT,
    gps_lat REAL,
    gps_lon REAL,
    file_hash TEXT,
    directory_id INTEGER,
    project_id INTEGER,
    has_transcript BOOLEAN DEFAULT 0,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (directory_id) REFERENCES directories(id),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- Transcripts table
CREATE TABLE IF NOT EXISTS transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    transcript_path TEXT,
    content TEXT,
    format TEXT,
    word_count INTEGER,
    language TEXT DEFAULT 'en',
    source TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id)
);

-- Scan progress table (for resume capability)
CREATE TABLE IF NOT EXISTS scan_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    directory_path TEXT NOT NULL,
    status TEXT DEFAULT 'pending',  -- pending, in_progress, completed, error
    files_scanned INTEGER DEFAULT 0,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_files_directory ON files(directory_id);
CREATE INDEX IF NOT EXISTS idx_files_project ON files(project_id);
CREATE INDEX IF NOT EXISTS idx_files_extension ON files(extension);
CREATE INDEX IF NOT EXISTS idx_files_date ON files(creation_date);
CREATE INDEX IF NOT EXISTS idx_directories_parent ON directories(parent_id);
CREATE INDEX IF NOT EXISTS idx_directories_path ON directories(path);
CREATE INDEX IF NOT EXISTS idx_transcripts_file ON transcripts(file_id);
CREATE INDEX IF NOT EXISTS idx_scan_progress_status ON scan_progress(status);

-- Full-text search for transcripts
CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts USING fts5(
    content,
    content=transcripts,
    content_rowid=id
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS transcripts_ai AFTER INSERT ON transcripts BEGIN
    INSERT INTO transcripts_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS transcripts_ad AFTER DELETE ON transcripts BEGIN
    INSERT INTO transcripts_fts(transcripts_fts, rowid, content) VALUES('delete', old.id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS transcripts_au AFTER UPDATE ON transcripts BEGIN
    INSERT INTO transcripts_fts(transcripts_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO transcripts_fts(rowid, content) VALUES (new.id, new.content);
END;
