# Video Development - Survey, Transcribe & Index Archived Video Content

**Project Name:** Video Development
**Created:** November 20, 2025
**Type:** Media Archive Processing & Search
**Status:** Active - Initial Survey Phase
**Paired with:** Claude.ai Project "Video Development - Planning"

---

## Infrastructure & Standards

@~/.claude/global-infrastructure.md

**This project automatically inherits:**
- ✅ UI/UX Design System (mobile-first, accessible, performant)
- ✅ Database Architecture Patterns (SQLite, JSON, append-only)
- ✅ Testing & Development Protocols (local, staging, production)
- ✅ Code Library & Utilities (JavaScript, Python, CSS, Netlify)
- ✅ Deployment Infrastructure (Paul's Server, Netlify, GitHub, Dropbox)

---

## Purpose

Survey, transcribe, and index archived video content currently stored on Pegasus drive. Create searchable database of video metadata and AI-generated transcripts using Whisper API.

**Primary Content:**
- India trip footage
- Vinny movie project files
- Charles Pers discussion recordings
- Other archived video content

**Primary Goal:** Make video archive searchable and accessible without manual review.

---

## Two-Claude Synchronization

**YAML Naming Convention:**
- **Mac Perspective:** `VideoDevMacPerspective.yaml`
- **Claude.ai Perspective:** `VideoDevClaudePerspective.yaml`
- **Location:** `~/Downloads/` (overwrites previous version)

**Workflow:**
1. Mac handles: File operations, surveys, transcription processing, database management
2. Claude.ai handles: Planning, architecture, feature design, cost analysis
3. Perspective files communicate progress, blockers, and next steps

---

## Storage Strategy

**PRIMARY VIDEO STORAGE: Pegasus Drive (Fast, Active Storage)**
- Videos remain on Pegasus drive (DO NOT move to Seagate)
- Pegasus is fast and suitable for active processing work
- Seagate is slow cold storage, not for active operations
- Survey and processing work will run on Pegasus while idle during Seagate transfer

**Project Database & Code:**
- SQLite database: `~/Library/CloudStorage/Dropbox/Fergi/VideoDev/video-archive.db`
- Source code: `~/Library/CloudStorage/Dropbox/Fergi/VideoDev/`
- Web interface: Paul's Server deployment

**Dropbox Integration:**
- Database synced via Dropbox
- Transcripts stored in SQLite (searchable)
- Video files remain on Pegasus drive (referenced by path)

---

## Technical Approach

### Phase 1: Survey (CURRENT)
- **Goal:** Comprehensive inventory of video archive on Pegasus drive
- **Output:**
  - Complete directory structure
  - File counts and sizes
  - Video metadata (duration, format, resolution, codecs)
  - Total duration for transcription cost calculation
  - Content categorization (India/Vinny/Charles Pers/Other)

### Phase 2: Database Design
- **Goal:** Design SQLite schema for metadata and transcripts
- **Components:**
  - Video metadata table (paths, formats, durations, creation dates)
  - Transcript table (time-coded text, searchable)
  - Category/tag system
  - Full-text search indexing

### Phase 3: Transcription Pipeline
- **Goal:** Automated video-to-transcript processing
- **Technology:** Whisper API ($0.006/minute)
- **Process:**
  1. Extract audio from video
  2. Submit to Whisper API
  3. Store time-coded transcripts in SQLite
  4. Update metadata with transcription status

### Phase 4: Search Interface
- **Goal:** Web-based search and review system
- **Features:**
  - Full-text search across all transcripts
  - Filter by category, date, duration
  - View transcript with timestamp links
  - Mark favorites, add notes
  - Export capabilities

### Deferred: Visual Analysis
- Initial focus on transcription pipeline only
- Visual frame analysis postponed
- Transcripts provide primary searchable value

---

## Quick Reference

### Pegasus Drive Location
```bash
# Mount point will be determined during survey
# Typical macOS external drive: /Volumes/Pegasus
```

### Project Directory
```bash
cd ~/Library/CloudStorage/Dropbox/Fergi/VideoDev
```

### Database
```bash
# SQLite database (will be created)
~/Library/CloudStorage/Dropbox/Fergi/VideoDev/video-archive.db
```

### Perspective Files
```bash
# Mac generates after implementation work
~/Downloads/VideoDevMacPerspective.yaml

# Claude.ai generates after planning/review
~/Downloads/VideoDevClaudePerspective.yaml
```

---

## Current Status

**Active Phase:** Initial Survey of Pegasus Drive

**Next Steps:**
1. Verify Pegasus drive mount and accessibility
2. Survey complete directory tree structure
3. Count video files per directory
4. Extract video metadata (duration, format, resolution, codecs)
5. Calculate total duration for transcription costing
6. Categorize content (India trip, Vinny movie, Charles Pers, other)
7. Document organizational patterns
8. Generate VideoDevMacPerspective.yaml with survey results

**Blocked On:** None currently

**Questions:**
- None yet - survey phase will inform architecture decisions

---

## Development Patterns

### Survey Best Practices
- Non-destructive read-only operations
- Comprehensive logging of findings
- Capture organizational patterns
- Extract all available metadata
- Calculate accurate transcription costs

### Long-Running Operations Protection

**⚠️ AUTO-COMPACT PROTECTION**

Survey and transcription operations MUST use nohup protection to prevent Mac Claude Code auto-compact from terminating multi-hour processes.

**Production operations (MANDATORY nohup):**
```bash
# Pegasus drive survey (multi-hour operation)
nohup python survey_pegasus.py > logs/$(date +%Y%m%d_%H%M%S)_survey.log 2>&1 &

# Batch transcription pipeline (API costs, hours of processing)
nohup python transcribe_batch.py > logs/$(date +%Y%m%d_%H%M%S)_transcribe.log 2>&1 &

# Or use the convenience wrapper
run-protected.sh python survey_pegasus.py
```

**Monitor progress:**
```bash
tail -f logs/[latest_log]
ps aux | grep python
```

**Why this matters:**
- **Survey operations:** Multi-hour directory traversal, metadata extraction
- **Transcription pipeline:** API costs accumulate, must complete without interruption
- **Work investment:** Cannot afford mid-process interruptions
- **Rate limits:** Incomplete runs waste API quota and billing

**Development/testing (small samples):**
- Run normally for quick tests: `python survey_pegasus.py --limit 10`
- Use for testing on small directory samples
- Ctrl+C interruption is fine for development

**Decision rule:** Would losing this mid-way waste >10 minutes of work? If YES → use nohup.

### Transcription Strategy
- Batch processing to manage costs
- Priority order (user-specified categories first)
- Progress tracking in database
- Error handling and retry logic
- Quality validation of transcripts

### Database Principles
- Append-only transaction log
- Full-text search optimization
- Timestamp-based versioning
- Backup and sync via Dropbox

---

## Cost Management

**Whisper API Pricing:** $0.006/minute of audio

**Cost Calculation:**
- Total video duration: TBD (from survey)
- Estimated transcription cost: TBD
- Process in batches to control spending
- User approval before large transcription runs

---

## Deployment

**Development:** Local (Mac)
**Production:** Paul's Server
- Web interface for search and review
- Database remains synced via Dropbox
- Videos remain on Pegasus drive (not deployed)

**Infrastructure:**
- See `FERGI_INFRASTRUCTURE_GUIDE.md` for deployment patterns
- Inherits Paul's Server SSH access and deployment workflows
- Web interface follows Fergi UI/UX standards

---

## Notes

- This is the 7th project in the FergiDotCom ecosystem
- Leverages idle time during Seagate transfer
- Videos remain on Pegasus drive (fast, active storage)
- Database and code in Dropbox for sync and backup
- Uses Two-Claude workflow for planning and implementation

---

**Project Directory:** `/Users/joeferguson/Library/CloudStorage/Dropbox/Fergi/VideoDev`
**Last Updated:** November 20, 2025
**Maintained by:** FergiDotCom Video Development Team
