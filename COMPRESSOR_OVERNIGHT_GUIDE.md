# Compressor Overnight Batch Processing Guide

**Created:** December 5, 2025
**Purpose:** Compress high-resolution videos to 1080p using Apple Compressor with M2 hardware acceleration
**Test Verified:** December 5, 2025 - 754MB file compressed in 1m40s

---

## Test Results (December 5, 2025)

| Test File | Original | Compressed | Time | Speed |
|-----------|----------|------------|------|-------|
| LetterWritingWide.mov | 754 MB (4K) | 182 MB (1080p) | 1m 40s | ~1x realtime |

**Compression ratio:** 76% size reduction
**Hardware acceleration:** M2 Media Engine working perfectly

---

## Overview - IMPORTANT DUPLICATE FINDING

| Metric | All Files | Unique Only |
|--------|-----------|-------------|
| **Total Videos** | 10,526 | **2,122** |
| **Video Duration** | 2,186 hrs | **631 hrs** |
| **Current Size** | 43.9 TB | TBD |
| **Processing Time** | 91 days | **~26 days** |

**8,404 files are duplicates** (same filename + size in different locations like FCP bundles).

**Recommended Strategy:**
1. **Phase A:** Delete duplicates first (instant space savings)
2. **Phase B:** Compress the 2,122 unique videos (~26 days at 1x realtime)

---

## Quick Math

At overnight processing (12 hrs/night):
- **26 days / 12 hrs = ~53 nights** for all unique videos
- But many videos are short, so actual throughput will be faster
- Expect **3-4 weeks** of overnight processing

---

## Method 1: Command Line (RECOMMENDED)

The command-line approach was tested and works. No watch folder setup needed.

### 1.1 Open Compressor
```bash
open /Applications/Compressor.app
```
Compressor must be running (can be in background).

### 1.2 Submit Jobs via Command Line
```bash
# Single file example:
/Applications/Compressor.app/Contents/MacOS/Compressor \
  -batchname "Overnight Batch" \
  -jobpath "/path/to/source/video.mp4" \
  -settingpath "/Applications/Compressor.app/Contents/Resources/Settings/Website Sharing/HD1080WebShareName.compressorsetting" \
  -locationpath "/Volumes/Promise Pegasus/_watch_output/video_1080p.mov"
```

### 1.3 Run Batch Script
```bash
cd ~/Library/CloudStorage/Dropbox/Fergi/VideoDev
nohup python3 compressor_cli_batch.py > logs/$(date +%Y%m%d_%H%M%S)_compressor_batch.log 2>&1 &
```

---

## Method 2: Watch Folder (Alternative)

### 2.1 Open Compressor
```bash
open /Applications/Compressor.app
```

### 2.2 Create Watch Folder
1. In Compressor, click **"Watch Folders"** in the left sidebar (bottom section)
2. Click the **"+"** button to add a new watch folder
3. Navigate to: `/Volumes/Promise Pegasus/_watch_input`
4. Click **"Choose"**

### 2.3 Configure Watch Folder Settings
1. Click on the newly added watch folder
2. Click **"Add Output"** (or drag a preset to it)
3. Select preset: **"HD 1080p"** from "Publish to Web" category
   - OR: "Apple Devices HD (Best Quality)" for slightly better quality
4. Set output location:
   - Click the output destination
   - Choose: `/Volumes/Promise Pegasus/_watch_output`
5. **IMPORTANT:** Check "Delete source file after successful transcode" is **OFF**
   (We'll delete manually after verification)

### 2.4 Verify Watch Folder is Active
- The watch folder should show a green indicator when active
- Compressor must remain open for watch folders to work

---

## Step 2: Prepare Directories

Run this once before starting:

```bash
# Create input and output directories
mkdir -p "/Volumes/Promise Pegasus/_watch_input"
mkdir -p "/Volumes/Promise Pegasus/_watch_output"
mkdir -p "/Volumes/Promise Pegasus/_compression_logs"

# Verify directories exist
ls -la "/Volumes/Promise Pegasus/_watch_input"
ls -la "/Volumes/Promise Pegasus/_watch_output"
```

---

## Step 3: Run Overnight Batch Script

### 3.1 Start the Batch Feeder Script

```bash
cd ~/Library/CloudStorage/Dropbox/Fergi/VideoDev
nohup python3 compressor_batch_feeder.py > logs/$(date +%Y%m%d_%H%M%S)_compressor_batch.log 2>&1 &
echo "Batch feeder started. PID: $!"
```

### 3.2 What the Script Does
1. Reads the list of high-res videos from the CSV
2. Copies files in batches to `_watch_input`
3. Waits for Compressor to process them
4. Moves processed files out of `_watch_input`
5. Logs all activity

### 3.3 Alternative: Manual Batch Copy

If you prefer manual control, copy files in batches:

```bash
# Copy first 10 large files for testing
head -11 logs/20251205_001737_high_res_videos.csv | tail -10 | cut -d',' -f1 | while read f; do
    cp "$f" "/Volumes/Promise Pegasus/_watch_input/"
done
```

---

## Step 4: Monitor Progress

### 4.1 Check Compressor Status
- Compressor GUI shows current batch progress
- Watch the "Active" section for encoding status

### 4.2 Check Output Files
```bash
# Count completed files
ls -la "/Volumes/Promise Pegasus/_watch_output/" | wc -l

# Check total size of compressed files
du -sh "/Volumes/Promise Pegasus/_watch_output/"

# View recent completions
ls -lt "/Volumes/Promise Pegasus/_watch_output/" | head -20
```

### 4.3 Check Script Logs
```bash
# Latest log
tail -f logs/*compressor_batch*.log
```

---

## Step 5: Morning Verification

### 5.1 Check Completion Status
```bash
# How many files were compressed?
find "/Volumes/Promise Pegasus/_watch_output" -type f \( -name "*.mp4" -o -name "*.m4v" \) | wc -l

# Total space used by compressed files
du -sh "/Volumes/Promise Pegasus/_watch_output"

# Check for any errors in logs
grep -i "error\|fail" logs/*compressor_batch*.log
```

### 5.2 Verify Quality (Spot Check)
```bash
# Pick a random compressed file and check its properties
ffprobe -v quiet -print_format json -show_streams "/Volumes/Promise Pegasus/_watch_output/[FILENAME].mp4" | grep -E "width|height|codec"
```

### 5.3 Compare Original vs Compressed
```bash
# Example comparison
ORIG="/Volumes/Promise Pegasus/MyMovieWithVinny/171208GlennConroy/Glenn4K.MP4"
COMP="/Volumes/Promise Pegasus/_watch_output/Glenn4K.mp4"
echo "Original: $(ls -lh "$ORIG" | awk '{print $5}')"
echo "Compressed: $(ls -lh "$COMP" | awk '{print $5}')"
```

---

## Step 6: Delete Originals (AFTER VERIFICATION ONLY)

**WARNING:** Only run after confirming compressed files are valid!

```bash
# This script will be created to safely delete originals
# after verification of compressed files
python3 verify_and_delete_originals.py
```

---

## Troubleshooting

### Compressor Stops Processing
- Ensure Compressor app is running (not just the icon)
- Check System Preferences > Energy Saver - disable sleep
- Check if Mac went to sleep (breaks watch folder)

### Watch Folder Not Active
1. Quit Compressor
2. Reopen Compressor
3. Check watch folder status (should show green)

### Files Not Being Picked Up
- Ensure files are fully copied before Compressor sees them
- Try removing and re-adding the watch folder
- Check Compressor preferences for watch folder settings

### Disk Full
```bash
# Check space
df -h "/Volumes/Promise Pegasus"

# If needed, delete verified compressed files' originals to free space
```

---

## Key Paths

| Purpose | Path |
|---------|------|
| Watch Input | `/Volumes/Promise Pegasus/_watch_input` |
| Watch Output | `/Volumes/Promise Pegasus/_watch_output` |
| Logs | `~/Library/CloudStorage/Dropbox/Fergi/VideoDev/logs/` |
| Source CSV | `logs/20251205_001737_high_res_videos.csv` |
| Batch Script | `compressor_batch_feeder.py` |

---

## Estimated Timeline

| Phase | Videos | Est. Time |
|-------|--------|-----------|
| Night 1 | ~500-1000 | 8-12 hours |
| Night 2 | ~1000-2000 | 8-12 hours |
| Night 3+ | Remaining | Continue as needed |

With M2 hardware acceleration, expect roughly:
- Small files (<5GB): 2-5 minutes each
- Medium files (5-20GB): 10-30 minutes each
- Large files (>50GB): 30-90 minutes each

---

## Pre-Flight Checklist

Before starting overnight run:

- [ ] Pegasus drive mounted at `/Volumes/Promise Pegasus`
- [ ] Directories created (`_watch_input`, `_watch_output`)
- [ ] Compressor open and watch folder configured
- [ ] Watch folder shows green/active status
- [ ] Mac set to NOT sleep (Energy Saver settings)
- [ ] Batch feeder script started
- [ ] Logs directory exists

---

**Last Updated:** December 5, 2025
