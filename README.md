# Video Development - Ferguson Family Archive Transcription Pipeline

**AI-powered video transcription and searchable archive system**

## Current Status

**✅ Phase 1: Ferguson Family Archive Transcription**

- **319 videos transcribed** with time-coded segments  
- **Cost:** $6.74 (133 files remaining, ~$2.50)
- **Database:** 1.4MB SQLite with full-text search
- **Local copy:** `~/Documents/VideoTranscripts/transcripts.db`

**Special transcript:** 1955 Art Linkletter "People Are Funny" - 4-year-old Joey Ferguson

## Quick Start

### Resume Transcription (after adding OpenAI credits)
```bash
cd ~/Library/CloudStorage/Dropbox/Fergi/VideoDev
nohup python3 transcribe_ferguson_archive.py > logs/transcribe.log 2>&1 &
tail -f /tmp/transcribe-ferguson.log
```

### Query Transcripts
```bash
# Search for keywords
sqlite3 ~/Documents/VideoTranscripts/transcripts.db "
SELECT file_id, SUBSTR(transcript_text, 1, 100) 
FROM transcripts 
WHERE transcript_text LIKE '%keyword%';"

# Get timestamps for navigation
sqlite3 transcripts.db "
SELECT PRINTF('%02d:%02d', CAST(start_time/60 AS INT), CAST(start_time%60 AS INT)) as time, text
FROM transcript_segments WHERE transcript_id = 30;"
```

## Database Schema

- **transcripts**: Full text, word counts, costs
- **transcript_segments**: Time-coded segments (start_time, end_time)
- **transcription_progress**: Status tracking, resumability

## Features

✅ Time-coded segments (jump to specific moments)
✅ Fault-tolerant & resumable
✅ Cost tracking ($0.006/minute)
✅ Progress monitoring
✅ Parallel-safe execution

⏳ Full-text search interface (Phase 2)
⏳ Audio chunking for large files
⏳ Web-based navigation UI

## Technical Details

- **API:** OpenAI Whisper (whisper-1 model)
- **Cost:** $0.02/file average
- **Throughput:** ~300 files/30 min
- **File Limit:** 25MB (35 min videos)

## Repository

**Local:** `~/Library/CloudStorage/Dropbox/Fergi/VideoDev`
**Backup:** Dropbox automatic sync
**Created:** November 22, 2025
