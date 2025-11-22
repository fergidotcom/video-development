#!/usr/bin/env python3
"""
Pegasus Survey Database Initialization
Creates comprehensive SQLite database schema for video/photo/document metadata survey
Based on Claude.ai VideoDevClaudePerspective.yaml specification
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "pegasus-survey.db"

def create_database():
    """Create SQLite database with complete schema for Pegasus survey"""

    print(f"Creating database: {DB_PATH}")

    # Delete existing database if present
    if DB_PATH.exists():
        print(f"  ⚠️  Existing database found, removing...")
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Enable WAL mode for better concurrent performance
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")

    print("  Creating tables...")

    # ===== TABLE 1: files (master inventory) =====
    cursor.execute("""
        CREATE TABLE files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL UNIQUE,
            filename TEXT NOT NULL,
            filename_original TEXT,
            filename_proposed TEXT,
            filename_context TEXT,
            rename_status TEXT,
            rename_batch_id INTEGER,
            directory TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            file_type TEXT,
            file_format TEXT,
            file_size_bytes INTEGER,
            project_assignment TEXT,
            creation_date TEXT,
            modification_date TEXT,
            scan_status TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    print("    ✓ files table created")

    # ===== TABLE 2: video_metadata =====
    cursor.execute("""
        CREATE TABLE video_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL UNIQUE,
            duration_seconds REAL,
            width INTEGER,
            height INTEGER,
            resolution_category TEXT,
            compression_candidate BOOLEAN,
            estimated_1024p_size_bytes INTEGER,
            codec TEXT,
            frame_rate REAL,
            bitrate INTEGER,
            audio_codec TEXT,
            audio_channels INTEGER,
            color_space TEXT,
            has_embedded_metadata BOOLEAN,
            metadata_json TEXT,
            FOREIGN KEY (file_id) REFERENCES files(id)
        )
    """)
    print("    ✓ video_metadata table created")

    # ===== TABLE 3: photo_metadata =====
    cursor.execute("""
        CREATE TABLE photo_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL UNIQUE,
            width INTEGER,
            height INTEGER,
            color_space TEXT,
            camera_make TEXT,
            camera_model TEXT,
            lens_model TEXT,
            iso INTEGER,
            aperture REAL,
            shutter_speed TEXT,
            focal_length REAL,
            gps_latitude REAL,
            gps_longitude REAL,
            gps_altitude REAL,
            date_taken TEXT,
            caption TEXT,
            keywords TEXT,
            copyright TEXT,
            has_xmp_metadata BOOLEAN,
            metadata_json TEXT,
            FOREIGN KEY (file_id) REFERENCES files(id)
        )
    """)
    print("    ✓ photo_metadata table created")

    # ===== TABLE 4: document_metadata =====
    cursor.execute("""
        CREATE TABLE document_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL UNIQUE,
            document_type TEXT,
            page_count INTEGER,
            author TEXT,
            title TEXT,
            subject TEXT,
            creation_tool TEXT,
            has_extractable_text BOOLEAN,
            metadata_json TEXT,
            FOREIGN KEY (file_id) REFERENCES files(id)
        )
    """)
    print("    ✓ document_metadata table created")

    # ===== TABLE 5: directory_analysis =====
    cursor.execute("""
        CREATE TABLE directory_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            directory_path TEXT NOT NULL UNIQUE,
            directory_name TEXT NOT NULL,
            parent_directory TEXT,
            depth_level INTEGER,
            file_count INTEGER,
            total_size_bytes INTEGER,
            video_count INTEGER,
            photo_count INTEGER,
            document_count INTEGER,
            other_count INTEGER,
            predominant_type TEXT,
            inferred_purpose TEXT,
            date_pattern TEXT,
            person_names TEXT,
            event_indicators TEXT,
            project_assignment TEXT,
            subdivision_recommendation TEXT,
            scan_status TEXT,
            created_at TEXT NOT NULL
        )
    """)
    print("    ✓ directory_analysis table created")

    # ===== TABLE 6: scan_progress (fault tolerance) =====
    cursor.execute("""
        CREATE TABLE scan_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            directory_path TEXT NOT NULL UNIQUE,
            scan_status TEXT,
            files_total INTEGER,
            files_processed INTEGER,
            files_skipped INTEGER,
            files_errored INTEGER,
            started_at TEXT,
            completed_at TEXT,
            error_summary TEXT,
            last_file_processed TEXT
        )
    """)
    print("    ✓ scan_progress table created")

    # ===== TABLE 7: survey_statistics =====
    cursor.execute("""
        CREATE TABLE survey_statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_run_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT,
            total_files INTEGER,
            files_processed INTEGER,
            files_skipped INTEGER,
            files_errored INTEGER,
            total_size_bytes INTEGER,
            total_duration_seconds REAL,
            video_count INTEGER,
            photo_count INTEGER,
            document_count INTEGER,
            other_count INTEGER,
            ferguson_family_files INTEGER,
            general_archive_files INTEGER,
            unassigned_files INTEGER,
            compression_candidates_count INTEGER,
            compression_potential_savings_bytes INTEGER,
            directories_scanned INTEGER,
            error_summary TEXT
        )
    """)
    print("    ✓ survey_statistics table created")

    print("  Creating indexes...")

    # Files table indexes
    cursor.execute("CREATE INDEX idx_files_project ON files(project_assignment)")
    cursor.execute("CREATE INDEX idx_files_type ON files(file_type)")
    cursor.execute("CREATE INDEX idx_files_directory ON files(directory)")
    cursor.execute("CREATE INDEX idx_files_scan_status ON files(scan_status)")
    cursor.execute("CREATE UNIQUE INDEX idx_files_path ON files(file_path)")
    print("    ✓ files indexes created")

    # Video metadata indexes
    cursor.execute("CREATE INDEX idx_video_resolution ON video_metadata(resolution_category)")
    cursor.execute("CREATE INDEX idx_video_compression ON video_metadata(compression_candidate)")
    cursor.execute("CREATE INDEX idx_video_file_id ON video_metadata(file_id)")
    print("    ✓ video_metadata indexes created")

    # Photo metadata indexes
    cursor.execute("CREATE INDEX idx_photo_date ON photo_metadata(date_taken)")
    cursor.execute("CREATE INDEX idx_photo_camera ON photo_metadata(camera_model)")
    cursor.execute("CREATE INDEX idx_photo_file_id ON photo_metadata(file_id)")
    print("    ✓ photo_metadata indexes created")

    # Document metadata indexes
    cursor.execute("CREATE INDEX idx_document_type ON document_metadata(document_type)")
    cursor.execute("CREATE INDEX idx_document_file_id ON document_metadata(file_id)")
    print("    ✓ document_metadata indexes created")

    # Directory analysis indexes
    cursor.execute("CREATE INDEX idx_dir_project ON directory_analysis(project_assignment)")
    cursor.execute("CREATE INDEX idx_dir_parent ON directory_analysis(parent_directory)")
    cursor.execute("CREATE INDEX idx_dir_type ON directory_analysis(predominant_type)")
    print("    ✓ directory_analysis indexes created")

    # Scan progress indexes
    cursor.execute("CREATE INDEX idx_progress_status ON scan_progress(scan_status)")
    cursor.execute("CREATE UNIQUE INDEX idx_progress_dir ON scan_progress(directory_path)")
    print("    ✓ scan_progress indexes created")

    # Survey statistics indexes
    cursor.execute("CREATE INDEX idx_stats_run_id ON survey_statistics(survey_run_id)")
    print("    ✓ survey_statistics indexes created")

    conn.commit()
    conn.close()

    print(f"\n✅ Database created successfully: {DB_PATH}")
    print(f"   Size: {DB_PATH.stat().st_size:,} bytes")
    print(f"   Tables: 7")
    print(f"   Indexes: 21")

    return DB_PATH

def verify_database(db_path):
    """Verify database schema is correct"""

    print(f"\nVerifying database schema...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]

    expected_tables = [
        'directory_analysis',
        'document_metadata',
        'files',
        'photo_metadata',
        'scan_progress',
        'survey_statistics',
        'video_metadata'
    ]

    print(f"  Tables found: {len(tables)}")
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"    ✓ {table} ({count} rows)")

    # Verify all expected tables exist
    missing_tables = set(expected_tables) - set(tables)
    if missing_tables:
        print(f"\n  ⚠️  Missing tables: {missing_tables}")
        return False

    # Get all indexes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")
    indexes = cursor.fetchall()
    print(f"  Indexes: {len(indexes)}")

    conn.close()

    print(f"\n✅ Database schema verified successfully")
    return True

if __name__ == "__main__":
    try:
        db_path = create_database()
        verify_database(db_path)

        print("\n" + "="*60)
        print("DATABASE READY FOR PEGASUS SURVEY")
        print("="*60)
        print(f"Database: {db_path}")
        print(f"Status: Initialized and ready")
        print(f"Next step: Run survey script (to be created)")
        print("="*60)

        sys.exit(0)

    except Exception as e:
        print(f"\n❌ Error creating database: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
