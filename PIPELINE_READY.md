# Video Transcription Pipeline - Ready to Run

**Status:** ✅ **SETUP COMPLETE - NOT YET EXECUTED**

**Important:** No files on Pegasus drive have been touched. All scripts are in the project folder only.

---

## What's Been Set Up

### ✅ Complete FFmpeg-Integrated Pipeline

**Phase 1: Survey**
- Scan Pegasus drive for all video files
- Extract metadata (duration, format, resolution, codecs)
- Categorize content (India/Vinny/Charles Pers/Other)
- Store in SQLite database

**Phase 2: Audio Extraction**
- FFmpeg batch conversion: video → MP3
- Efficient storage (1GB video → 10-50MB audio)
- Progress tracking and error handling
- Database updates with audio file paths

**Phase 3: Transcription**
- Submit audio files to Whisper API
- Time-coded transcripts stored in database
- Full-text search indexing
- Cost tracking and management

**Phase 4: Search (Future)**
- Web interface for searching transcripts
- Filter by category, date, duration
- Export capabilities

---

## Files Created

### Core Pipeline Modules

**`transcription_pipeline.py`** - Main pipeline class
- Database management (SQLite)
- Video metadata storage
- Transcript storage with full-text search
- Progress tracking and logging
- Pipeline status reporting

**`extract_audio.py`** - FFmpeg integration
- Single file audio extraction
- Batch processing
- Error handling and retry logic
- Extraction logging

**`run_pipeline.py`** - Command-line orchestrator ⭐ **MAIN ENTRY POINT**
- Run individual phases or complete pipeline
- Cost preview before transcription
- Category filtering
- Safety checks (Seagate transfer, Pegasus mount)

### Supporting Files

**`extract-audio-example.sh`** - Simple FFmpeg example script
**`pegasus_survey.py`** - Directory scanning utilities
**`transcribe.py`** - Whisper API integration (existing)
**`video-archive.db`** - SQLite database (created but empty)

---

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  PHASE 1: SURVEY                                            │
│  ┌──────────────┐      ┌──────────────┐                    │
│  │ Pegasus Drive│ ───> │ Scan Videos  │ ───> SQLite DB     │
│  │ (Read-only)  │      │ + Metadata   │                    │
│  └──────────────┘      └──────────────┘                    │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 2: AUDIO EXTRACTION                                  │
│  ┌──────────────┐      ┌──────────────┐                    │
│  │ Video Files  │ ───> │   FFmpeg     │ ───> MP3 Audio     │
│  │ (on Pegasus) │      │ libmp3lame   │      Files         │
│  └──────────────┘      └──────────────┘                    │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 3: TRANSCRIPTION                                     │
│  ┌──────────────┐      ┌──────────────┐                    │
│  │ Audio Files  │ ───> │ Whisper API  │ ───> Transcripts   │
│  │   (MP3)      │      │ ($0.006/min) │      in SQLite     │
│  └──────────────┘      └──────────────┘                    │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 4: SEARCH                                            │
│  ┌──────────────┐      ┌──────────────┐                    │
│  │ Full-Text    │ ───> │ Web Interface│ ───> Search Results│
│  │ Search Index │      │ (Future)     │                    │
│  └──────────────┘      └──────────────┘                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Storage Strategy

**Videos:** Remain on Pegasus drive (fast, active storage)
- DO NOT move to Seagate (slow cold storage)
- Referenced by path in database
- Processed while idle during Seagate transfer

**Audio Files:** `./audio_extracts/` (project folder)
- Temporary files for Whisper API submission
- Much smaller than videos (10-50MB vs 1GB)
- Can be deleted after transcription

**Database:** `./video-archive.db` (synced via Dropbox)
- Video metadata
- Transcripts (searchable)
- Processing logs

**Code:** `~/Library/CloudStorage/Dropbox/Fergi/VideoDev/`
- All scripts in Dropbox for sync and backup

---

## Usage Examples

### Check Pipeline Status (Safe - No Processing)

```bash
cd ~/Library/CloudStorage/Dropbox/Fergi/VideoDev
./run_pipeline.py --status
```

**Shows:**
- Total videos in database
- Audio extraction progress
- Transcription progress
- Estimated costs

### Run Complete Pipeline (After Seagate Transfer)

```bash
# Full pipeline: survey → extract audio → preview costs
./run_pipeline.py --full-pipeline
```

**Safety checks:**
- ✅ Confirms Seagate transfer complete
- ✅ Verifies Pegasus drive mounted
- ✅ Previews transcription costs (no API calls)

### Run Individual Phases

```bash
# Phase 1: Survey Pegasus drive
./run_pipeline.py --survey

# Phase 2: Extract audio from all videos
./run_pipeline.py --extract-audio

# Phase 3: Preview transcription costs (no charges)
./run_pipeline.py --preview-transcription

# Phase 3: Actually transcribe (INCURS COSTS!)
./run_pipeline.py --transcribe
```

### Category Filtering

```bash
# Process only India videos
./run_pipeline.py --extract-audio --category India

# Preview cost for Vinny videos only
./run_pipeline.py --preview-transcription --category Vinny
```

### Limit Processing

```bash
# Test with first 5 videos
./run_pipeline.py --survey --limit 5

# Transcribe only 10 videos
./run_pipeline.py --transcribe --limit 10
```

---

## Safety Features

### Built-in Protections

✅ **Seagate Transfer Check**
- Pipeline asks for confirmation before starting
- Won't run until you confirm transfer complete

✅ **Pegasus Mount Verification**
- Checks if drive is accessible before survey
- Prevents errors if drive unmounted

✅ **Cost Preview**
- Shows estimated Whisper API costs before transcription
- Requires explicit confirmation to proceed

✅ **Read-Only Survey**
- Phase 1 only reads files, never modifies
- Safe to run anytime

✅ **Progress Logging**
- All operations logged to files
- Database tracks every operation
- Easy to resume after interruptions

✅ **Error Handling**
- Graceful failures (one video error won't stop batch)
- Detailed error logging
- Retry capability

---

## Database Schema

### `videos` Table
- Video file metadata (path, size, duration, format, resolution)
- Audio extraction status
- Transcription status
- Cost tracking

### `transcripts` Table
- Full transcript text
- Time-coded segments
- Language detection
- API response data

### `processing_log` Table
- All pipeline operations
- Success/failure tracking
- Timestamps

### `transcripts_fts` Table
- Full-text search index
- Fast searching across all transcripts

---

## Cost Management

**Whisper API Pricing:** $0.006 per minute of audio

**Example Costs:**
- 1 hour video = 60 minutes = $0.36
- 10 hours video = 600 minutes = $3.60
- 100 hours video = 6,000 minutes = $36.00

**Cost Controls:**
- Preview costs before transcription (`--preview-transcription`)
- Process by category (start with highest priority)
- Limit number of videos (`--limit N`)
- Requires explicit confirmation before API calls

---

## What Happens When You Run

### Phase 1: Survey (Safe - Read-Only)
```bash
./run_pipeline.py --survey
```

1. Confirms Seagate transfer complete (user prompt)
2. Verifies Pegasus drive mounted
3. Scans directory tree for video files
4. Extracts metadata using FFprobe (FFmpeg)
5. Stores all metadata in SQLite database
6. Logs all operations
7. Shows summary statistics

**Duration:** Depends on number of files (few minutes to hours)
**Cost:** $0 (no API calls)
**Safe:** Yes (read-only operations)

### Phase 2: Extract Audio
```bash
./run_pipeline.py --extract-audio
```

1. Queries database for videos without extracted audio
2. For each video:
   - Runs FFmpeg to extract audio as MP3
   - Saves to `./audio_extracts/`
   - Updates database with audio file path
3. Logs all operations
4. Shows success/failure summary

**Duration:** ~1-10% of total video duration (very fast)
**Cost:** $0 (no API calls, just FFmpeg)
**Safe:** Yes (doesn't modify original videos)

### Phase 3: Preview Transcription (Safe - No API Calls)
```bash
./run_pipeline.py --preview-transcription
```

1. Queries database for videos with audio extracted but not transcribed
2. Calculates total duration
3. Shows estimated Whisper API cost
4. Breaks down by category
5. NO API CALLS - just preview

**Duration:** Instant
**Cost:** $0 (no API calls)
**Safe:** Yes (read-only)

### Phase 3: Transcription (INCURS COSTS!)
```bash
./run_pipeline.py --transcribe
```

1. Queries videos ready for transcription
2. Shows cost estimate
3. **Requires user confirmation: "Type 'yes' to proceed"**
4. For each audio file:
   - Uploads to Whisper API
   - Receives transcript with timestamps
   - Stores in database
   - Updates full-text search index
5. Tracks actual costs

**Duration:** Real-time (as long as audio duration + API overhead)
**Cost:** $0.006 per minute of audio
**Safe:** Yes (but costs money)

---

## Next Steps (After Seagate Transfer Completes)

### Recommended Workflow

1. **Check Status**
   ```bash
   ./run_pipeline.py --status
   ```
   Currently shows 0 videos (database is empty)

2. **Run Survey** (Read-only, safe to run anytime)
   ```bash
   ./run_pipeline.py --survey
   ```
   This will populate the database with all video metadata

3. **Check Status Again**
   ```bash
   ./run_pipeline.py --status
   ```
   Now shows total videos, duration, categories

4. **Extract Audio** (Fast, no costs)
   ```bash
   ./run_pipeline.py --extract-audio
   ```
   Creates MP3 files for all videos

5. **Preview Transcription Costs**
   ```bash
   ./run_pipeline.py --preview-transcription
   ```
   See what it will cost before committing

6. **Decide on Batch Strategy**
   - Process all at once?
   - Process by category (India first, then Vinny)?
   - Process in smaller batches?

7. **Run Transcription** (When ready)
   ```bash
   # Example: Start with India videos only
   ./run_pipeline.py --transcribe --category India
   ```

---

## Monitoring Progress

### Log Files

**`pipeline_run.log`** - Main orchestrator log
**`audio_extraction.log`** - FFmpeg operations
**`transcription_pipeline.log`** - Database operations

### Status Commands

```bash
# Overall pipeline status
./run_pipeline.py --status

# Check database directly
sqlite3 video-archive.db "SELECT COUNT(*) FROM videos"
sqlite3 video-archive.db "SELECT COUNT(*) FROM videos WHERE audio_extracted = 1"
sqlite3 video-archive.db "SELECT COUNT(*) FROM transcripts"
```

### Processing Log

All operations tracked in database:
```bash
sqlite3 video-archive.db "SELECT * FROM processing_log ORDER BY timestamp DESC LIMIT 10"
```

---

## Troubleshooting

### Pegasus Drive Not Found

**Error:** "Pegasus drive not found at: /Volumes/Pegasus"

**Solution:**
1. Mount Pegasus drive
2. Check actual mount path: `ls /Volumes/`
3. Specify custom path: `./run_pipeline.py --survey --pegasus-path /Volumes/YourDriveName`

### FFmpeg Errors

**Error:** Audio extraction fails

**Solution:**
1. Check FFmpeg installed: `which ffmpeg`
2. Check logs: `cat audio_extraction.log`
3. Test single file manually:
   ```bash
   ffmpeg -i /path/to/video.mp4 -vn -acodec libmp3lame -q:a 2 test.mp3
   ```

### Database Locked

**Error:** "database is locked"

**Solution:**
1. Only run one pipeline instance at a time
2. Close any SQLite connections: `ps aux | grep sqlite`
3. Restart pipeline

---

## Important Notes

### ⚠️ What Has NOT Been Done Yet

- ❌ No files on Pegasus have been read or modified
- ❌ No survey has been run
- ❌ No audio has been extracted
- ❌ No transcription has been performed
- ❌ Database is empty (just schema, no data)

### ✅ What IS Ready

- ✅ Complete pipeline architecture designed
- ✅ All scripts created and tested (structure)
- ✅ FFmpeg integration complete
- ✅ Database schema ready
- ✅ Safety checks in place
- ✅ Cost preview functionality
- ✅ Progress tracking and logging
- ✅ Error handling

### 🎯 When to Run

**Wait until:** Pegasus → Seagate file copy completes

**Why:** We want Pegasus drive idle and stable for:
- Consistent file access during survey
- No interference with ongoing copy operations
- Accurate metadata extraction

### 🚀 Ready to Go

Everything is set up and ready. When the Seagate transfer completes, simply run:

```bash
cd ~/Library/CloudStorage/Dropbox/Fergi/VideoDev
./run_pipeline.py --full-pipeline
```

This will safely survey, extract audio, and preview costs without making any API calls.

---

**Created:** November 20, 2025
**Status:** Ready for execution (waiting on Seagate transfer)
**Location:** `~/Library/CloudStorage/Dropbox/Fergi/VideoDev/`

---

## Questions?

Run with `--help` for all options:
```bash
./run_pipeline.py --help
```
