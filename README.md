# Video Archive Transcription System

**Automated pipeline for surveying, transcribing, and indexing archived video content using AI.**

[![Status](https://img.shields.io/badge/status-ready-green)](README.md)
[![Python](https://img.shields.io/badge/python-3.8+-blue)](https://python.org)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-7.1-orange)](https://ffmpeg.org)
[![Whisper](https://img.shields.io/badge/Whisper_API-OpenAI-purple)](https://platform.openai.com/docs/guides/speech-to-text)

---

## Overview

Transform your video archive into a searchable knowledge base. This system automatically:

1. **Surveys** your video collection and extracts metadata
2. **Extracts audio** from videos using FFmpeg
3. **Transcribes** audio using OpenAI's Whisper API
4. **Indexes** transcripts for full-text search
5. **Enables search** across all video content

**Perfect for:**
- Personal video archives (travel footage, family videos)
- Interview collections
- Lecture recordings
- Documentary research
- Any large video library you want to make searchable

---

## Features

### ✅ Comprehensive Video Survey
- Scans entire drive for video files
- Extracts metadata: duration, format, resolution, codecs
- Categorizes content automatically
- Stores everything in SQLite database

### ✅ Efficient Audio Extraction
- FFmpeg integration for fast, reliable extraction
- Batch processing of hundreds/thousands of files
- 90-95% file size reduction (1GB video → 10-50MB audio)
- Progress tracking and error recovery

### ✅ AI-Powered Transcription
- OpenAI Whisper API for accurate transcripts
- Time-coded segments for precise searching
- Language detection
- Cost estimation before processing

### ✅ Full-Text Search
- SQLite FTS5 full-text search index
- Search across all transcripts instantly
- Filter by category, date, duration
- Export search results

### ✅ Safe & Reliable
- Read-only survey (never modifies original videos)
- Comprehensive error handling
- Progress logging
- Resume capability after interruptions

---

## Quick Start

### Prerequisites

**Required:**
- Python 3.8 or higher
- FFmpeg 7.1+ (for audio extraction)
- OpenAI API key (for transcription)

**Check if installed:**
```bash
python3 --version
ffmpeg -version
```

**Install FFmpeg** (if needed):
```bash
brew install ffmpeg
```

### Installation

1. **Clone or download this repository**

2. **Verify FFmpeg is installed:**
   ```bash
   which ffmpeg
   # Should show: /opt/homebrew/bin/ffmpeg or similar
   ```

3. **Set up OpenAI API key** (for transcription phase):
   ```bash
   export OPENAI_API_KEY="your-api-key-here"
   ```

4. **You're ready to go!**

### Basic Usage

**1. Check status:**
```bash
cd ~/Library/CloudStorage/Dropbox/Fergi/VideoDev
./run_pipeline.py --status
```

**2. Survey your video archive:**
```bash
./run_pipeline.py --survey --pegasus-path /Volumes/YourDrive
```

**3. Extract audio from videos:**
```bash
./run_pipeline.py --extract-audio
```

**4. Preview transcription costs:**
```bash
./run_pipeline.py --preview-transcription
```

**5. Transcribe (when ready):**
```bash
./run_pipeline.py --transcribe
```

---

## Architecture

### Pipeline Flow

```
┌───────────────────────────────────────────────────────────────┐
│  Phase 1: SURVEY                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐ │
│  │ Video Files  │ ──> │ FFprobe      │ ──> │ SQLite DB    │ │
│  │ (on drive)   │     │ (metadata)   │     │ (videos)     │ │
│  └──────────────┘     └──────────────┘     └──────────────┘ │
└───────────────────────────────────────────────────────────────┘
                              ↓
┌───────────────────────────────────────────────────────────────┐
│  Phase 2: AUDIO EXTRACTION                                    │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐ │
│  │ Video Files  │ ──> │ FFmpeg       │ ──> │ MP3 Audio    │ │
│  │              │     │ (extract)    │     │ (on Pegasus) │ │
│  └──────────────┘     └──────────────┘     └──────────────┘ │
└───────────────────────────────────────────────────────────────┘
                              ↓
┌───────────────────────────────────────────────────────────────┐
│  Phase 3: TRANSCRIPTION                                       │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐ │
│  │ MP3 Audio    │ ──> │ Whisper API  │ ──> │ Transcripts  │ │
│  │              │     │ ($0.006/min) │     │ (in SQLite)  │ │
│  └──────────────┘     └──────────────┘     └──────────────┘ │
└───────────────────────────────────────────────────────────────┘
                              ↓
┌───────────────────────────────────────────────────────────────┐
│  Phase 4: SEARCH                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐ │
│  │ FTS5 Index   │ ──> │ Search Query │ ──> │ Results      │ │
│  │ (full-text)  │     │              │     │ (ranked)     │ │
│  └──────────────┘     └──────────────┘     └──────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

### Components

**Core Modules:**

| Module | Purpose |
|--------|---------|
| `run_pipeline.py` | Main orchestrator (start here) |
| `transcription_pipeline.py` | Database management & workflow |
| `extract_audio.py` | FFmpeg audio extraction |
| `transcribe.py` | Whisper API integration |
| `pegasus_survey.py` | Directory scanning utilities |

**Database:**
- `video-archive.db` - SQLite database
  - `videos` - Video metadata
  - `transcripts` - Full transcripts with timestamps
  - `transcripts_fts` - Full-text search index
  - `processing_log` - Operation tracking

**Storage:**
- Videos: Remain on original drive (read-only)
- Audio files: `/Volumes/Pegasus/VideoDev_Audio/` (configurable)
- Database: Project folder (synced via Dropbox)

---

## Usage Guide

### Command Reference

```bash
# Show pipeline status and statistics
./run_pipeline.py --status

# Survey video archive
./run_pipeline.py --survey --pegasus-path /Volumes/YourDrive

# Extract audio from all videos
./run_pipeline.py --extract-audio

# Preview transcription costs (no API calls)
./run_pipeline.py --preview-transcription

# Transcribe audio (INCURS COSTS - requires confirmation)
./run_pipeline.py --transcribe

# Run complete pipeline (survey + extract + preview)
./run_pipeline.py --full-pipeline

# Process specific category only
./run_pipeline.py --extract-audio --category India

# Limit processing (useful for testing)
./run_pipeline.py --transcribe --limit 10

# Custom audio output directory
./run_pipeline.py --extract-audio --audio-output-dir /path/to/audio

# Get help
./run_pipeline.py --help
```

### Workflow Examples

**Example 1: Initial Setup**
```bash
# 1. Survey your video archive
./run_pipeline.py --survey --pegasus-path /Volumes/Pegasus

# 2. Check what was found
./run_pipeline.py --status

# 3. Extract audio from all videos
./run_pipeline.py --extract-audio

# 4. Preview transcription costs
./run_pipeline.py --preview-transcription
# Shows: "100 videos, 50 hours, estimated cost: $18.00"

# 5. Transcribe all (when ready)
./run_pipeline.py --transcribe
# Prompts for confirmation before proceeding
```

**Example 2: Process by Category**
```bash
# Survey everything first
./run_pipeline.py --survey

# Process India videos only
./run_pipeline.py --extract-audio --category India
./run_pipeline.py --preview-transcription --category India
./run_pipeline.py --transcribe --category India

# Then process Vinny videos
./run_pipeline.py --extract-audio --category Vinny
./run_pipeline.py --transcribe --category Vinny
```

**Example 3: Test with Small Batch**
```bash
# Survey everything
./run_pipeline.py --survey

# Test with first 5 videos
./run_pipeline.py --extract-audio --limit 5
./run_pipeline.py --transcribe --limit 5

# Check results in database
sqlite3 video-archive.db "SELECT filename, transcription_status FROM videos LIMIT 5"

# If good, process the rest
./run_pipeline.py --extract-audio
./run_pipeline.py --transcribe
```

---

## Cost Management

### Whisper API Pricing

**Rate:** $0.006 per minute of audio

**Example Costs:**
| Duration | Cost |
|----------|------|
| 1 hour (60 min) | $0.36 |
| 10 hours (600 min) | $3.60 |
| 100 hours (6,000 min) | $36.00 |
| 1,000 hours (60,000 min) | $360.00 |

### Cost Controls

✅ **Preview before transcribing**
- `--preview-transcription` shows estimated cost
- No API calls, no charges

✅ **Process in batches**
- Use `--limit N` to process N videos at a time
- Test with small batch first

✅ **Filter by category**
- Prioritize important content
- `--category CategoryName`

✅ **Explicit confirmation required**
- Pipeline asks "Type 'yes' to proceed" before API calls
- No accidental charges

### Monitoring Costs

**Track costs in database:**
```bash
sqlite3 video-archive.db "SELECT SUM(transcription_cost) FROM videos"
```

**Check what's pending:**
```bash
./run_pipeline.py --preview-transcription
```

---

## Safety & Reliability

### Built-in Safety Features

✅ **Read-only survey** - Never modifies original video files
✅ **Confirmation prompts** - Explicit approval before transcription
✅ **Cost previews** - See estimated costs before committing
✅ **Progress logging** - All operations logged
✅ **Error recovery** - Graceful handling of failures
✅ **Resume capability** - Can restart after interruptions

### Data Integrity

- All operations logged in database (`processing_log` table)
- Atomic database transactions
- Backup database regularly
- Original videos never modified

### Error Handling

**If audio extraction fails:**
- Error logged in `audio_extraction.log`
- Processing continues with remaining videos
- Failed videos marked in database
- Can retry individually later

**If transcription fails:**
- Error logged in `transcription_pipeline.log`
- No charge for failed requests
- Can retry failed videos
- Partial results saved

### Monitoring

**Log files:**
- `pipeline_run.log` - Main orchestrator
- `audio_extraction.log` - FFmpeg operations
- `transcription_pipeline.log` - Database operations

**Database queries:**
```bash
# Recent operations
sqlite3 video-archive.db "SELECT * FROM processing_log ORDER BY timestamp DESC LIMIT 10"

# Failed extractions
sqlite3 video-archive.db "SELECT * FROM videos WHERE audio_extracted = 0"

# Transcription status
sqlite3 video-archive.db "SELECT transcription_status, COUNT(*) FROM videos GROUP BY transcription_status"
```

---

## Database Schema

### Tables

**`videos`** - Video file metadata
```sql
- id (primary key)
- file_path (unique)
- filename
- file_size
- duration_seconds
- format (mp4, mov, avi, etc.)
- width, height (resolution)
- codec
- category (India, Vinny, etc.)
- created_date
- added_date
- audio_extracted (0/1)
- audio_path
- transcription_status (pending/completed/failed)
- transcription_cost
```

**`transcripts`** - Transcription data
```sql
- id (primary key)
- video_id (foreign key)
- full_text (complete transcript)
- language (detected language)
- duration
- timestamp_data (JSON segments)
- transcribed_date
- api_response (JSON)
```

**`transcripts_fts`** - Full-text search index
```sql
- video_id
- full_text (searchable)
```

**`processing_log`** - Operation tracking
```sql
- id (primary key)
- video_id (foreign key)
- operation (survey/extract/transcribe)
- status (success/failed)
- message
- timestamp
```

### Example Queries

**Search transcripts:**
```sql
SELECT v.filename, v.category, snippet(transcripts_fts, 1, '<mark>', '</mark>', '...', 64)
FROM transcripts_fts
JOIN transcripts t ON transcripts_fts.rowid = t.id
JOIN videos v ON t.video_id = v.id
WHERE transcripts_fts MATCH 'search terms'
ORDER BY rank;
```

**Statistics by category:**
```sql
SELECT category,
       COUNT(*) as count,
       SUM(duration_seconds)/3600 as hours,
       SUM(transcription_cost) as cost
FROM videos
GROUP BY category;
```

**Find videos about topic:**
```sql
SELECT v.filename, v.file_path, t.full_text
FROM videos v
JOIN transcripts t ON v.id = t.video_id
WHERE t.full_text LIKE '%topic%';
```

---

## Configuration

### Storage Locations

**Default configuration:**
- Videos: Remain on source drive (read-only)
- Audio files: `/Volumes/Pegasus/VideoDev_Audio/`
- Database: `~/Library/CloudStorage/Dropbox/Fergi/VideoDev/video-archive.db`

**Custom audio directory:**
```bash
./run_pipeline.py --audio-output-dir /path/to/audio/folder
```

**Custom Pegasus path:**
```bash
./run_pipeline.py --pegasus-path /Volumes/YourDriveName
```

### Environment Variables

**Required for transcription:**
```bash
export OPENAI_API_KEY="sk-..."
```

**Optional:**
```bash
export FFMPEG_PATH="/custom/path/to/ffmpeg"  # If not in PATH
```

---

## Troubleshooting

### FFmpeg Not Found

**Problem:** `FFmpeg not found. Please install FFmpeg.`

**Solution:**
```bash
# Install via Homebrew
brew install ffmpeg

# Verify installation
which ffmpeg
ffmpeg -version
```

### Pegasus Drive Not Mounted

**Problem:** `Pegasus drive not found at: /Volumes/Pegasus`

**Solution:**
1. Mount the drive in Finder
2. Check actual mount path: `ls /Volumes/`
3. Use custom path: `./run_pipeline.py --survey --pegasus-path /Volumes/ActualName`

### Audio Extraction Fails

**Problem:** Audio extraction errors in log

**Solution:**
1. Check FFmpeg installation: `ffmpeg -version`
2. Test single file manually:
   ```bash
   ffmpeg -i /path/to/video.mp4 -vn -acodec libmp3lame -q:a 2 test.mp3
   ```
3. Check video file is readable
4. Check disk space on audio output drive

### Database Locked

**Problem:** `database is locked`

**Solution:**
1. Only run one pipeline instance at a time
2. Close any SQLite browser connections
3. Check for stale processes: `ps aux | grep python`

### Transcription API Errors

**Problem:** Whisper API fails

**Solution:**
1. Verify API key: `echo $OPENAI_API_KEY`
2. Check OpenAI API status
3. Verify audio file format (should be MP3)
4. Check audio file size (max 25MB per file)

---

## Development

### Project Structure

```
VideoDev/
├── README.md                       # This file
├── PIPELINE_READY.md              # Detailed setup guide
├── CLAUDE.md                       # Project documentation
├── run_pipeline.py                 # Main orchestrator ⭐
├── transcription_pipeline.py       # Core pipeline logic
├── extract_audio.py                # FFmpeg integration
├── transcribe.py                   # Whisper API client
├── pegasus_survey.py              # Directory scanning
├── video-archive.db               # SQLite database
├── pipeline_run.log               # Main log file
├── audio_extraction.log           # FFmpeg log
└── transcription_pipeline.log     # Database log
```

### Adding Features

**Custom metadata extraction:**
- Edit `pegasus_survey.py`
- Add fields to `videos` table schema
- Update `extract_video_metadata()` function

**Custom categorization:**
- Edit `run_survey()` in `run_pipeline.py`
- Add logic to determine category from path/filename
- Update category field when adding to database

**Web interface:**
- Create Flask/FastAPI app
- Use `TranscriptionPipeline.search_transcripts()` for queries
- Display results with video links

### Testing

**Test audio extraction:**
```python
from extract_audio import AudioExtractor

extractor = AudioExtractor(output_dir="/tmp/test")
result = extractor.extract_audio("/path/to/test-video.mp4")
print(result)
```

**Test database:**
```python
from transcription_pipeline import TranscriptionPipeline

pipeline = TranscriptionPipeline(db_path="test.db")
status = pipeline.get_pipeline_status()
print(status)
```

---

## FAQ

**Q: Will this modify my original video files?**
A: No. The survey phase only reads files. Audio extraction creates new MP3 files but never modifies originals.

**Q: Where are the audio files stored?**
A: By default in `/Volumes/Pegasus/VideoDev_Audio/` but you can customize with `--audio-output-dir`.

**Q: How long does transcription take?**
A: Roughly real-time. A 1-hour video takes ~60-90 minutes to transcribe (plus upload time).

**Q: Can I pause and resume?**
A: Yes. The pipeline tracks progress in the database. Just run the same command again and it will skip already-processed videos.

**Q: What video formats are supported?**
A: Any format FFmpeg can read: MP4, MOV, AVI, MKV, FLV, WMV, etc.

**Q: Can I transcribe videos without storing them?**
A: Yes. The database stores transcripts, so you can delete audio files after transcription. Keep the database for searching.

**Q: How accurate are the transcripts?**
A: Whisper is state-of-the-art. Accuracy depends on audio quality, accents, background noise. Generally 90-95%+ accurate for clear speech.

**Q: Can I edit transcripts after generation?**
A: Yes. Transcripts are stored in SQLite `transcripts` table. You can edit the `full_text` field directly.

---

## Roadmap

### Implemented ✅
- [x] Video file survey with metadata extraction
- [x] FFmpeg audio extraction
- [x] Whisper API transcription
- [x] SQLite database with full-text search
- [x] Progress tracking and logging
- [x] Cost estimation and management
- [x] Batch processing

### Planned 🎯
- [ ] Web-based search interface
- [ ] Video player with transcript sync
- [ ] Bulk transcript export (PDF, TXT, JSON)
- [ ] Speaker diarization (identify different speakers)
- [ ] Visual frame analysis (detect scenes, objects)
- [ ] Automatic chapter generation
- [ ] Tag management system
- [ ] RESTful API for integrations

---

## Contributing

This is a personal project, but suggestions and improvements are welcome!

**To contribute:**
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

---

## License

Personal project - use freely for your own video archives.

---

## Credits

**Technologies:**
- [FFmpeg](https://ffmpeg.org) - Audio/video processing
- [OpenAI Whisper](https://openai.com/research/whisper) - Speech-to-text
- [SQLite FTS5](https://www.sqlite.org/fts5.html) - Full-text search
- [Python 3](https://python.org) - Programming language

**Author:** Fergi
**Project:** Video Archive Transcription System
**Created:** November 2025

---

## Quick Links

- [Detailed Setup Guide](PIPELINE_READY.md)
- [Project Documentation](CLAUDE.md)
- [Technical Reference](TECHNICAL_REFERENCE.md)

---

**Ready to make your video archive searchable? Start with:**
```bash
./run_pipeline.py --status
```
