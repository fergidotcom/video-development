# Audio Chunking Implementation for Large File Transcription

**Created:** December 15, 2025
**Purpose:** Handle audio files > 25MB that exceed Whisper API limits

---

## Problem

28 files failed transcription with status "audio_too_large" because their extracted audio exceeded Whisper's 25MB limit. The original code at line 185-189 of `transcribe_composites.py` just skipped these files.

---

## Solution

Implemented automatic audio chunking with the following strategy:

### 1. Dynamic Chunk Calculation

Function: `calculate_chunk_duration(audio_size_mb, total_duration_seconds)`

- Calculates bytes per second based on audio size and duration
- Targets chunks at 95% of max size (24MB) for safety margin
- Rounds down to whole minutes for clean boundaries
- Ensures minimum 5-minute chunks
- Returns optimal chunk duration in seconds

### 2. Chunk Extraction

Function: `extract_audio_chunk(video_path, output_path, start_time, duration)`

- Uses ffmpeg with `-ss` (start time) and `-t` (duration) flags
- Extracts audio directly from original video (not from full audio file)
- Same audio settings as main extraction: 16kHz mono MP3, 32kbps
- Timeout protection (600s per chunk)

### 3. Chunked Transcription Pipeline

Function: `transcribe_chunked_audio(client, audio_path, video_path, total_duration)`

**Process:**
1. Calculate optimal chunk duration based on audio size
2. Determine number of chunks needed
3. For each chunk:
   - Extract audio segment from video
   - Verify chunk size < 24MB
   - Transcribe via Whisper API
   - Adjust segment timestamps by adding chunk start offset
   - Accumulate segments and text
4. Combine all chunks into single transcript object
5. Return combined transcript with properly offset timestamps

**Key Features:**
- Preserves segment-level timestamps (adjusted for chunk position)
- Handles both segmented and non-segmented transcripts
- Safety checks for chunk size
- Progress logging for each chunk
- Rate limiting delay between chunks (1 second)

### 4. Integration

Modified `process_composite()` function:
- Check audio size after extraction
- If > 24MB → call `transcribe_chunked_audio()`
- If ≤ 24MB → call standard `transcribe_audio()`
- Rest of pipeline unchanged (same database storage)

---

## Data Structures

### TranscriptSegment Class
```python
class TranscriptSegment:
    def __init__(self, start, end, text):
        self.start = start   # Adjusted timestamp
        self.end = end       # Adjusted timestamp
        self.text = text     # Transcript text
```

### CombinedTranscript Class
```python
class CombinedTranscript:
    def __init__(self):
        self.text = ""           # Full combined text
        self.segments = []       # List of TranscriptSegment objects
        self.language = "en"     # Language code
```

This matches the structure returned by Whisper API's `verbose_json` format.

---

## Example Chunking Strategy

**File:** 50-minute video, 30MB audio

1. Calculate: 30MB / 50min = 0.6MB/min
2. Target chunk: 24MB * 0.95 = 22.8MB
3. Chunk duration: 22.8MB / 0.6MB/min = 38 minutes
4. Number of chunks: ceil(50 / 38) = 2 chunks

**Chunk 1:** 0:00-38:00 (38 minutes)
**Chunk 2:** 38:00-50:00 (12 minutes)

**Timestamp Adjustment:**
- Chunk 1 segments: timestamps as-is (0-38min)
- Chunk 2 segments: add 38min offset to all timestamps

---

## Cost Impact

Chunking does NOT increase transcription cost:
- Whisper charges $0.006 per minute of audio
- Total cost = total audio duration × $0.006
- Chunking just splits the work, same total duration

**Example:**
- 50-minute file = $0.30 (whether 1 file or 2 chunks)

---

## The 28 Failed Files

All 28 files are stored in `logs/transcription_progress.json` under the "failed" array.

**Locations:**
- Most in `/Volumes/Promise Pegasus/Walkabout2018/WalkaboutDailies/`
- Some in `/Volumes/Promise Pegasus/MyMovieWithVinny/MyMovieWithVinnyDailies/`
- Some in `/Volumes/Promise Pegasus/190205JeffreyAndPop/`
- Some in `/Volumes/Promise Pegasus/201223JeffFergusonLifeStory/`
- Some in `/Volumes/Promise Pegasus/PeirceGang/PeirceGangDailies/`

**Common characteristics:**
- Long duration videos (30+ minutes typical)
- High-quality audio (resulting in larger file sizes)
- India trip dailies (verbose, multi-scene content)

---

## Re-Processing Script

**File:** `reprocess_failed.py`

### Purpose
Re-process the 28 failed files using the new chunking implementation.

### Features
- Reads failed list from `logs/transcription_progress.json`
- Re-processes each file with chunking support
- Moves successful re-processes from "failed" to "completed" array
- Updates progress.json after each file
- Tracks session cost and statistics

### Usage
```bash
# Run with nohup protection (recommended)
cd ~/Library/CloudStorage/Dropbox/Fergi/VideoDev
nohup python3 reprocess_failed.py > logs/reprocess_$(date +%Y%m%d_%H%M%S).log 2>&1 &

# Monitor progress
tail -f logs/reprocess_*.log

# Check what's running
ps aux | grep reprocess_failed
```

### Safety Features
- Non-destructive (doesn't modify original files)
- Progress saved after each file
- Can be interrupted and restarted
- Handles missing files gracefully
- Same error handling as main pipeline

---

## Testing Notes

**DO NOT run full pipeline yet.** Implementation is code-complete but untested.

**Before running:**
1. Verify Pegasus drive is mounted at `/Volumes/Promise Pegasus`
2. Check that OPENAI_API_KEY is set in environment or ~/.zshrc
3. Ensure transcripts.db exists and is accessible
4. Test with ONE file first (modify script to limit to 1 file)

**Test procedure:**
```bash
# Test with a single failed file
cd ~/Library/CloudStorage/Dropbox/Fergi/VideoDev

# Modify reprocess_failed.py to process only first file (add break after first iteration)
# Then run:
python3 reprocess_failed.py

# Check results:
sqlite3 transcripts.db "SELECT audio_file_path, word_count, duration_seconds FROM transcripts ORDER BY id DESC LIMIT 1;"
```

---

## Files Modified

1. **transcribe_composites.py** - Main transcription pipeline
   - Added `calculate_chunk_duration()` function (lines 94-112)
   - Added `extract_audio_chunk()` function (lines 114-134)
   - Added `TranscriptSegment` class (lines 136-141)
   - Added `CombinedTranscript` class (lines 143-148)
   - Added `transcribe_chunked_audio()` function (lines 150-219)
   - Modified `process_composite()` to use chunking when needed (lines 313-318)

2. **reprocess_failed.py** - NEW script for re-processing
   - Standalone script with all chunking logic
   - Reads failed list from progress.json
   - Re-processes with chunking support
   - Updates progress.json on success

---

## Expected Results

**After running reprocess_failed.py:**
- 28 files move from "failed" to "completed" in progress.json
- 28 new entries in transcripts.db
- Estimated cost: $5-15 (depending on total duration of failed files)
- Processing time: 1-3 hours (depending on file sizes and chunk counts)

**Database entries:**
- Full combined transcript text in `transcripts.text` field
- All segments with adjusted timestamps in `transcript_segments` table
- Searchable across entire archive

---

## Next Steps

1. **Test with one file first** - Modify reprocess_failed.py to process only 1 file
2. **Verify results** - Check transcript quality and timestamp accuracy
3. **Run full batch** - Process all 28 files with nohup protection
4. **Validate completion** - Ensure all files moved from failed to completed
5. **Update main pipeline** - Run transcribe_composites.py to catch any new large files

---

## Maintenance Notes

**If chunking fails:**
- Check chunk size calculation (should be < 24MB)
- Verify ffmpeg extraction with -ss and -t flags
- Check timestamp adjustment math (start_time offset)
- Review Whisper API error messages

**If timestamps are wrong:**
- Verify chunk start_time is being added to segment times
- Check that segment.start and segment.end exist
- Ensure chunks are processed in correct order

**If transcripts are incomplete:**
- Check that all chunks are being transcribed
- Verify text concatenation with proper spacing
- Ensure no chunks are being skipped on error

---

**Implementation Status:** ✅ Code Complete, Ready for Testing
**Estimated Completion Time:** 1-3 hours for all 28 files
**Estimated Cost:** $5-15 for all 28 files
