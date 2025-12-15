# FCP Bundle Parsing Report

**Date:** December 15, 2025
**Script:** `parse_fcp_bundles.py`
**Database:** `pegasus-survey.db`

## Summary

- **Total FCP bundles found:** 110
- **Successfully parsed (with timeline data):** 3
- **Empty/stripped bundles:** 107 (no project data)

## Key Findings

### FCP Bundle Structure

FCP bundles (`.fcpbundle`) are directories containing:
1. **Project data:** SQLite databases (`.fcpevent` files) with project structure
2. **Media files:** Rendered media, transcoded files, original media
3. **Metadata:** Binary plist files with settings and configurations

### Parsing Approach

Since FCPXML files don't exist in the bundles, we parse the internal SQLite databases:

- **Database location:** `{event_name}/CurrentVersion.fcpevent`
- **Format:** SQLite with Core Data schema (Apple's object persistence framework)
- **Key tables:**
  - `ZCOLLECTION` - Contains all project objects (clips, sequences, assets, etc.)
  - `ZCOLLECTIONMD` - Metadata in binary plist format
  - `ZCATALOGROOT` - Root catalog objects

### Extractable Metadata

From the SQLite databases, we can extract:

✅ **Clip count** - Number of `FFAnchoredClip` objects
✅ **Sequence count** - Number of `FFAnchoredSequence` objects
✅ **Asset count** - Number of `FFAsset` objects
✅ **Marker count** - Number of `FFAnchoredKeywordMarker` objects
✅ **Project name** - From bundle structure or collection data
✅ **Collection types** - All FCP object types and counts

❌ **Timeline duration** - Requires decoding binary plist time data (not implemented)
❌ **Clip timecode data** - Locked in binary plist format
❌ **Audio/video track structure** - Requires deep plist parsing

## Successfully Parsed Bundles

### 1. 190205JeffreyAndPop
- **Location:** `/Volumes/Promise Pegasus/190205JeffreyAndPop/190205JeffreyAndPop.fcpbundle`
- **Clips:** 18
- **Sequences:** 31
- **Assets:** 13
- **Markers:** 30
- **Events:** 3 (main event + 2 sub-projects)

### 2. 201223JeffFergusonLifeStory
- **Location:** `/Volumes/Promise Pegasus/201223JeffFergusonLifeStory/201223JeffFergusonLifeStory.fcpbundle`
- **Clips:** 7
- **Events:** 2

### 3. 2021 Cate Interview
- **Location:** `/Volumes/Promise Pegasus/Cate/Interview/2021 Cate Interview.fcpbundle`
- **Clips:** 2
- **Events:** 4

## Empty/Stripped Bundles

**107 bundles** contain only media files without project data:

- **Common locations:**
  - `/Volumes/Promise Pegasus/ExtractedAudio/MyMovieWithVinny/*` (majority)
  - `/Volumes/Promise Pegasus/_compressor_output/Walkabout2018/*`
  - `/Volumes/Promise Pegasus/_compressor_output/MyMovieWithVinny/*`

- **Likely cause:** Bundles were "stripped" or media was extracted, leaving only transcoded/rendered files
- **Contents:** Just media files (`.mov` files) in `Original Media/` or `Transcoded Media/` folders
- **No project data:** Missing `.fcpevent` SQLite databases

## Limitations

### What We Can't Extract Without FCPXML

1. **Precise timeline duration** - Requires exporting FCPXML from Final Cut Pro
2. **Clip in/out points** - Stored in binary plist format
3. **Time-based narrative structure** - Would need manual FCP export
4. **Audio/video track layout** - Complex binary data structures
5. **Effects and transitions** - Locked in proprietary format

### Why FCPXML Export Would Help

If you open these bundles in Final Cut Pro and export FCPXML:
- ✅ Complete timeline structure in readable XML
- ✅ Precise timecode data for all clips
- ✅ Marker positions and text
- ✅ Audio/video asset references with paths
- ✅ Effects, transitions, and color grading info
- ✅ Can be parsed with standard XML libraries

## Recommendations

### For Bundles With Project Data (3 bundles)
- ✅ Basic metadata extracted successfully
- ⚠️ Consider FCPXML export for complete timeline data
- 💾 Archive these bundles - they contain actual edit projects

### For Empty Bundles (107 bundles)
- ❌ No project data to extract
- 🎬 Only contain transcoded media files
- 🗑️ Consider if bundles are needed (media is already elsewhere)
- 📝 Mark as "media only" in database

## Database Updates

The `parse_fcp_bundles.py` script updates these fields:

```sql
UPDATE fcp_projects SET
    project_name = ?,        -- Extracted project name
    clip_count = ?,          -- Number of clips
    timeline_duration = ?,   -- NULL (can't extract)
    narrative_structure = ?, -- JSON with detailed counts
    parsed_at = ?            -- Timestamp of parsing attempt
WHERE fcp_id = ?
```

## Next Steps

### Option 1: Accept Limited Data
- Use the 3 successfully parsed bundles
- Mark remaining 107 as "media only, no project data"
- Focus transcription efforts on actual video files, not FCP projects

### Option 2: Manual FCPXML Export (if needed)
- Open the 3 parseable bundles in Final Cut Pro
- File → Export → XML (v1.9 or later)
- Re-run parser with FCPXML parsing logic added
- Get complete timeline data with timecodes

### Option 3: Focus Elsewhere
- FCP bundles are **edit projects**, not source videos
- The actual videos are already catalogued in `pegasus_videos` table
- Transcription pipeline should target source videos, not FCP projects
- FCP bundles are useful for understanding edit history, not content

## Script Usage

```bash
# Parse all unparsed bundles
python3 parse_fcp_bundles.py

# Parse with limit for testing
python3 parse_fcp_bundles.py 5

# View parsed data
sqlite3 pegasus-survey.db "SELECT * FROM fcp_projects WHERE clip_count > 0"
```

## Conclusion

**The FCP bundle parsing successfully extracts metadata from bundles with project data**, but the majority (97%) of bundles on the Pegasus drive are stripped/empty shells containing only media files.

For the **Video Development transcription pipeline**, focus on the source video files in the `pegasus_videos` table rather than FCP project bundles.

---

**Report generated:** December 15, 2025
**By:** VideoDev parse_fcp_bundles.py
