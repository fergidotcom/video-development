# Pegasus Drive Cleanup Plan

**Created:** December 4, 2025
**Status:** Plan Only - Awaiting Approval

---

## Drive Overview

- **Total Capacity:** 18TB
- **Currently Used:** 16TB (89%)
- **Available:** 2.1TB

---

## Phase 1: 2012 Laguna Archive Duplicates ✅ IN PROGRESS

**Status:** Running automated deletion script

**Target Directory:** `/Volumes/Promise Pegasus/2012 Laguna FergiDotCom Archive/` (1.3TB)

**Action:** Delete files that have identical copies (matching name, size, AND checksum) elsewhere on the drive.

**Subdirectories:**
- `170529NewCKFFamilyArchive` (240GB)
- `FergiDotComUberFullBackupBeforeSantaFeMove033015` (419GB)
- `FergiFamilyMediaArchiveUncompressedMaterial` (656GB)

**Script:** `find_and_delete_duplicates.py`
**Logs:** `logs/[timestamp]_*.log`

---

## Phase 2: 5K Video Compression (PLANNED - NOT EXECUTED)

**Problem:** Videos stored at 5K resolution are excessively large when 1080p or 4K would suffice.

**Target Resolution:** Compress to 1080p or 4K depending on source importance.

**Approach:**
1. Survey all video files on Pegasus for resolution
2. Identify 5K+ resolution videos
3. Use FFmpeg to transcode to lower resolution
4. Keep originals until verified, then delete

**Estimated FFmpeg Command:**
```bash
# For 4K output (good for archival)
ffmpeg -i input.mp4 -vf "scale=3840:-2" -c:v libx265 -crf 23 -c:a copy output_4k.mp4

# For 1080p output (significant space savings)
ffmpeg -i input.mp4 -vf "scale=1920:-2" -c:v libx265 -crf 23 -c:a copy output_1080p.mp4
```

**Space Savings Estimate:**
- 5K to 1080p: ~75-85% reduction
- 5K to 4K: ~50-60% reduction

**Directories to Survey:**
- `Camera Uploads/` (17,510 files)
- `Camera1 Joe.MP4` (32.9GB - single large file)
- `Camera2 Kjell.MP4` (32.2GB - single large file)
- `MyMovieWithVinny/` (project files)
- All other video-containing directories

---

## Phase 3: Drive-Wide Duplicate Detection (PLANNED - NOT EXECUTED)

**Approach:** Extend duplicate detection beyond just the 2012 Laguna archive.

**Strategy:**
1. Build complete file hash database for entire drive
2. Identify all duplicate clusters
3. Present for user review (which copy to keep?)
4. Delete after approval

**Potential Duplicate Hotspots:**
- `Camera Uploads/` may have duplicates with other directories
- Multiple backup directories may overlap
- Project directories may have exported/source duplicates

---

## Phase 4: Large File Analysis (PLANNED - NOT EXECUTED)

**Approach:** Identify unusually large files that may be:
- Uncompressed video exports
- Temporary/intermediate files
- Forgotten downloads

**Action:**
```bash
# Find files larger than 10GB
find "/Volumes/Promise Pegasus" -type f -size +10G -exec ls -lh {} \;
```

**Known Large Files:**
- `Camera1 Joe.MP4` - 32.9GB
- `Camera2 Kjell.MP4` - 32.2GB

---

## Phase 5: Empty Directory Cleanup (PLANNED - NOT EXECUTED)

After duplicate deletion, clean up empty directories:

```bash
# Find empty directories (dry run)
find "/Volumes/Promise Pegasus" -type d -empty

# Remove empty directories (after review)
find "/Volumes/Promise Pegasus" -type d -empty -delete
```

---

## Safety Principles

1. **Always verify checksums** before considering files duplicates
2. **Keep logs** of all deletions with full paths and checksums
3. **One source at a time** - only delete from designated directories
4. **User approval** required before bulk operations on new directories
5. **Preserve originals** when compressing until verified

---

## Next Steps After Phase 1 Completes

1. Review deletion logs from Phase 1
2. Decide on target resolution for video compression
3. Identify priority directories for compression
4. Run video resolution survey
5. Present compression plan for approval

---

**Last Updated:** December 4, 2025
