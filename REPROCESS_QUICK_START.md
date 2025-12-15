# Quick Start: Re-Process Failed Transcriptions

**28 files failed** because audio was > 25MB. Now fixed with chunking.

---

## Before You Start

1. **Verify Pegasus is mounted:**
   ```bash
   ls /Volumes/Promise\ Pegasus/
   ```

2. **Check API key is set:**
   ```bash
   echo $OPENAI_API_KEY
   # Should show: sk-proj-...
   ```

3. **Verify database exists:**
   ```bash
   ls -lh transcripts.db
   ```

---

## Test with One File First (RECOMMENDED)

```bash
cd ~/Library/CloudStorage/Dropbox/Fergi/VideoDev

# Create a test version that only processes first file
cat > reprocess_one_test.py << 'EOF'
#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from reprocess_failed import *

# Override main to only process first file
def test_one():
    log("="*70)
    log("TEST: Re-process ONE failed file")
    log("="*70)

    with open(PROGRESS_FILE) as f:
        progress = json.load(f)

    failed_files = progress.get('failed', [])

    if not failed_files:
        log("No failed files!")
        return

    # Only first file
    test_file = failed_files[0]
    log(f"Testing with: {os.path.basename(test_file)}")
    log("")

    client = get_openai_client()
    transcript_conn = sqlite3.connect(TRANSCRIPT_DATABASE)

    cost, status = process_failed_file(client, transcript_conn, test_file)

    log(f"\nResult: {status}")
    if status == "success":
        log(f"Cost: ${cost:.2f}")
        log("\n✅ Test successful! Ready to run full batch.")
    else:
        log(f"\n❌ Test failed: {status}")
        log("Fix errors before running full batch.")

    transcript_conn.close()

if __name__ == "__main__":
    test_one()
EOF

# Run test
python3 reprocess_one_test.py
```

**If test succeeds**, proceed to full batch below.

---

## Run Full Batch (All 28 Files)

```bash
cd ~/Library/CloudStorage/Dropbox/Fergi/VideoDev

# Run with nohup protection (recommended)
nohup python3 reprocess_failed.py > logs/reprocess_$(date +%Y%m%d_%H%M%S).log 2>&1 &

# Save the PID for monitoring
echo $! > logs/reprocess_pid.txt
```

---

## Monitor Progress

```bash
# Watch the log file in real-time
tail -f logs/reprocess_*.log

# Check if process is still running
ps aux | grep reprocess_failed | grep -v grep

# Or check the PID
ps -p $(cat logs/reprocess_pid.txt)
```

---

## Check Results

```bash
# After completion, check progress file
cat logs/transcription_progress.json | jq '.failed | length'
# Should show 0 (all moved to completed)

cat logs/transcription_progress.json | jq '.completed | length'
# Should show original count + 28

# Check database
sqlite3 transcripts.db "SELECT COUNT(*) FROM transcripts;"
# Should match completed count

# Check total cost
cat logs/transcription_progress.json | jq '.total_cost'
```

---

## Verify Transcript Quality

```bash
# Check a sample transcript from a re-processed file
sqlite3 transcripts.db << 'EOF'
SELECT
    audio_file_path,
    duration_seconds / 60 as duration_min,
    word_count,
    cost_dollars,
    substr(transcript_text, 1, 200) as preview
FROM transcripts
WHERE audio_file_path LIKE '%Walkabout%'
ORDER BY id DESC
LIMIT 3;
EOF
```

---

## Expected Results

- **Processing time:** 1-3 hours (depending on total duration)
- **Cost:** $5-15 (varies by duration)
- **Files processed:** 28
- **Success rate:** Should be 100% (all files work with chunking)

---

## If Something Goes Wrong

**Process stuck?**
```bash
# Check if it's actually stuck or just processing a large file
tail -20 logs/reprocess_*.log

# Kill if truly stuck (will resume later)
kill $(cat logs/reprocess_pid.txt)
```

**Errors in log?**
```bash
# View errors
grep "❌" logs/reprocess_*.log

# Check specific error details
grep -A 5 "Failed:" logs/reprocess_*.log
```

**Re-run after fixes:**
```bash
# Script is safe to re-run - skips already-completed files
python3 reprocess_failed.py
```

---

## After Completion

1. **Verify all 28 files succeeded:**
   ```bash
   cat logs/transcription_progress.json | jq '.failed'
   # Should be []
   ```

2. **Check database stats:**
   ```bash
   sqlite3 transcripts.db << 'EOF'
   SELECT
       COUNT(*) as total_transcripts,
       SUM(word_count) as total_words,
       SUM(duration_seconds)/3600 as total_hours,
       SUM(cost_dollars) as total_cost
   FROM transcripts;
   EOF
   ```

3. **Test search functionality:**
   ```bash
   sqlite3 transcripts.db << 'EOF'
   SELECT
       audio_file_path,
       substr(transcript_text, 1, 100) as preview
   FROM transcripts
   WHERE transcript_text LIKE '%India%'
   LIMIT 3;
   EOF
   ```

4. **Archive the test script:**
   ```bash
   rm reprocess_one_test.py  # No longer needed
   ```

---

## Next Steps After Re-Processing

1. Run main pipeline to catch any new large files:
   ```bash
   nohup python3 transcribe_composites.py > logs/transcribe_$(date +%Y%m%d_%H%M%S).log 2>&1 &
   ```

2. Build search interface (web UI)

3. Test search across all transcripts

---

**Questions?** See `AUDIO_CHUNKING_IMPLEMENTATION.md` for technical details.
