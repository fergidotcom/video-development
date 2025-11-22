# Audio Extraction Monitoring Guide

## Extraction Process Status

**Started:** 2025-11-21 23:58:15
**Process ID:** 60601
**Total Videos:** 16,292
**Priority:** Ferguson Family Archive first (652 videos)
**Output Directory:** `/Volumes/Promise Pegasus/ExtractedAudio/`
**Log File:** `/tmp/videodev-extract.log`
**Database:** `~/Library/CloudStorage/Dropbox/Fergi/VideoDev/pegasus-survey.db`

## Quick Status Check

```bash
# Check if extraction is still running
pgrep -lf extract_all_audio.py

# Count audio files created so far
find "/Volumes/Promise Pegasus/ExtractedAudio" -type f | wc -l

# View latest log entries
tail -20 /tmp/videodev-extract.log

# Check database progress (commits every 50 files)
sqlite3 ~/Library/CloudStorage/Dropbox/Fergi/VideoDev/pegasus-survey.db \
  "SELECT videos_processed, videos_errored, audio_files_created,
   ROUND(videos_processed * 100.0 / 16292, 2) as percent_complete
   FROM audio_extraction_progress
   WHERE status = 'running'"
```

## Monitoring Commands

### Real-time Log Monitoring
```bash
tail -f /tmp/videodev-extract.log
```

### File Creation Rate
```bash
# Run this every minute to see progress
watch -n 60 'find "/Volumes/Promise Pegasus/ExtractedAudio" -type f | wc -l'
```

### Process Details
```bash
ps aux | grep 48088
```

## Progress Estimation

Based on 16,292 videos:
- **10% complete:** 1,629 videos
- **25% complete:** 4,073 videos
- **50% complete:** 8,146 videos
- **75% complete:** 12,219 videos

Actual extraction time depends on video sizes and source codecs.

## Graceful Shutdown

If you need to stop the extraction:

```bash
# Send interrupt signal (graceful shutdown)
kill -INT 48088

# The script will:
# 1. Complete current extraction
# 2. Save progress to database
# 3. Exit cleanly
# 4. Can be resumed later (it skips already-extracted files)
```

**DO NOT USE:** `kill -9` (will corrupt database)

## Resuming After Interruption

If the process stops or you stop it manually:

```bash
cd ~/Library/CloudStorage/Dropbox/Fergi/VideoDev
python3 extract_all_audio.py
```

The script automatically:
- Detects already-extracted audio files
- Skips those videos
- Continues from where it left off
- Creates new extraction run entry in database

## Output Structure

Audio files mirror the original directory structure:

```
/Volumes/Promise Pegasus/ExtractedAudio/
├── 190205JeffreyAndPop/
│   ├── 190205JeffAndPopTalkAboutJeffsCareerSession1_extracted.m4a
│   ├── Jeff1_extracted.m4a
│   └── ...
├── Camera1/
│   └── ...
└── ...
```

## Troubleshooting

### Process Not Running
```bash
# Check if process exists
pgrep -lf extract_all_audio.py

# If not running, check log for errors
tail -50 /tmp/videodev-extract.log

# Restart if needed
cd ~/Library/CloudStorage/Dropbox/Fergi/VideoDev
nohup python3 -u extract_all_audio.py > /tmp/videodev-extract.log 2>&1 &
```

### Disk Space Issues
```bash
# Check Pegasus drive space
df -h "/Volumes/Promise Pegasus"

# Check extraction output space usage
du -sh "/Volumes/Promise Pegasus/ExtractedAudio"
```

### Database Locked
If you get "database is locked" errors:
- The extraction script holds a write lock
- Read-only queries are fine
- Wait for batch commit (every 50 files)

## Expected Completion Time

Estimated: Several hours to complete overnight

Factors affecting speed:
- Video codec types (some extract faster)
- FFmpeg processing time per file
- Pegasus drive I/O performance
- System load

## What Happens When Complete

The script will:
1. Display completion summary
2. Update database with final statistics
3. Exit cleanly
4. Leave all audio files in `/Volumes/Promise Pegasus/ExtractedAudio/`

Next step: Begin Whisper API transcription phase
