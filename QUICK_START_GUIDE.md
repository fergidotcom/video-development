# Speaker Recognition Pipeline - Quick Start Guide

**For:** Running the complete pipeline on Ferguson Family Archive videos

---

## Prerequisites

1. **Python Environment Setup**
```bash
cd ~/Documents/VideoTranscripts
python3 -m venv venv
source venv/bin/activate
pip install pyannote.audio librosa scikit-learn openai omegaconf
```

2. **Environment Variables**
```bash
# Add to ~/.zshrc
export HF_TOKEN="your_huggingface_token_here"  # Get from https://huggingface.co/settings/tokens
export OPENAI_API_KEY="your_openai_key_here"

# Reload shell
source ~/.zshrc
```

3. **HuggingFace License Acceptance**
Visit and accept all licenses:
- https://huggingface.co/pyannote/speaker-diarization-3.1
- https://huggingface.co/pyannote/segmentation-3.0
- https://huggingface.co/pyannote/speaker-diarization-community-1
- https://huggingface.co/pyannote/embedding

---

## Running the Pipeline

### Phase 2: Speaker Diarization

**Pilot (25 files):**
```bash
cd ~/Documents/VideoTranscripts
source venv/bin/activate
export HF_TOKEN="$HF_TOKEN"  # Or set in ~/.zshrc
python diarize_videos.py
```

**Full Production (434 files):**
```bash
# 1. Edit diarize_videos.py line 260:
#    Change: files = get_transcribed_files(limit=25)
#    To:     files = get_transcribed_files(limit=None)

# 2. Run with nohup protection
nohup bash -c 'source venv/bin/activate && export HF_TOKEN="$HF_TOKEN" && python diarize_videos.py' > logs/$(date +%Y%m%d_%H%M%S)_diarize_full.log 2>&1 &

# 3. Monitor progress
tail -f logs/*_diarize_full.log

# Estimated time: 12-24 hours
```

### Phase 3: Voice Embeddings

**Pilot (1000 segments):**
```bash
cd ~/Documents/VideoTranscripts
source venv/bin/activate
export HF_TOKEN="$HF_TOKEN"
python extract_speaker_embeddings.py
```

**Full Production (all segments):**
```bash
# 1. Edit extract_speaker_embeddings.py line 242:
#    Change: segments = get_segments_needing_embeddings(limit=1000)
#    To:     segments = get_segments_needing_embeddings(limit=None)

# 2. Run with nohup protection
nohup bash -c 'source venv/bin/activate && export HF_TOKEN="$HF_TOKEN" && python extract_speaker_embeddings.py' > logs/$(date +%Y%m%d_%H%M%S)_embeddings_full.log 2>&1 &

# 3. Monitor progress
tail -f logs/*_embeddings_full.log

# Estimated time: 2-4 hours
```

### Phase 4: Speaker Clustering

**Run (fast, no limits needed):**
```bash
cd ~/Documents/VideoTranscripts
source venv/bin/activate
python cluster_speakers.py

# Estimated time: Minutes
# Expected output: 20-50 unique speaker clusters
```

---

## Checking Results

### Database Queries

```bash
cd ~/Documents/VideoTranscripts
source venv/bin/activate
python -c "
import sqlite3
conn = sqlite3.connect('transcripts.db')
cursor = conn.cursor()

# Check progress
cursor.execute('SELECT COUNT(*) FROM transcripts')
print(f'Transcripts: {cursor.fetchone()[0]}')

cursor.execute('SELECT COUNT(*) FROM speaker_segments')
print(f'Speaker segments: {cursor.fetchone()[0]}')

cursor.execute('SELECT COUNT(*) FROM speaker_embeddings')
print(f'Embeddings: {cursor.fetchone()[0]}')

cursor.execute('SELECT COUNT(*) FROM unknown_clusters')
print(f'Clusters: {cursor.fetchone()[0]}')

conn.close()
"
```

### View Cluster Details

```bash
python -c "
import sqlite3
conn = sqlite3.connect('transcripts.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT cluster_label, sample_count, total_duration
    FROM unknown_clusters
    ORDER BY sample_count DESC
''')

print('Discovered Speaker Clusters:')
for row in cursor.fetchall():
    print(f'  {row[0]}: {row[1]} segments, {row[2]:.1f}s total')

conn.close()
"
```

---

## Monitoring Long Operations

### Check if Process is Running
```bash
ps aux | grep python | grep -E "diarize|embedding|cluster"
```

### View Live Logs
```bash
# Latest diarization log
tail -f ~/Documents/VideoTranscripts/logs/*_diarize_full.log

# Latest embeddings log
tail -f ~/Documents/VideoTranscripts/logs/*_embeddings_full.log
```

### Kill Stuck Process
```bash
# Find PID
ps aux | grep python | grep diarize

# Kill it
kill [PID]
```

---

## Troubleshooting

### Error: "HF_TOKEN not set"
```bash
export HF_TOKEN="$HF_TOKEN"
```

### Error: "403 Forbidden" from HuggingFace
- Go to https://huggingface.co/pyannote/[model-name]
- Click "Agree and access repository"
- Wait 1-2 minutes, try again

### Error: "AudioDecoder is not defined"
- This is already fixed in the scripts
- We use librosa instead of pyannote's built-in audio loading

### Error: "Format not recognised"
- Make sure librosa is installed: `pip install librosa`
- M4A files require audioread backend (installed with librosa)

### Low Success Rate in Phase 3
- Normal: Many segments are < 1 second and get filtered
- Typical success rate: 25-35%
- All good segments still get processed

### High Noise Rate in Clustering
- Normal: 20-40% noise points expected
- Noise = segments that don't fit well into clusters
- Often means rare speakers or poor audio quality

---

## Performance Tips

### Use screen/tmux for Long Operations
```bash
# Start protected session
screen -S videodevel

# Run pipeline
cd ~/Documents/VideoTranscripts
source venv/bin/activate
export HF_TOKEN="..."
python diarize_videos.py

# Detach: Ctrl+A, D
# Reattach later: screen -r videodevel
```

### Monitor GPU Usage
```bash
# Check MPS utilization
python -c "
import torch
print(f'MPS available: {torch.backends.mps.is_available()}')
print(f'MPS built: {torch.backends.mps.is_built()}')
"
```

### Free Up Disk Space
```bash
# Remove old log files (optional)
rm ~/Documents/VideoTranscripts/logs/*_pilot*.log

# Keep only the latest full run logs
```

---

## Next Steps After Clustering

1. Review cluster composition (see SPEAKER_RECOGNITION_PIPELINE_COMPLETE.md)
2. Build Phase 5 web UI for human identification
3. Identify speakers by listening to cluster samples
4. Link identified persons to transcript search

---

**Questions?** See full documentation in `SPEAKER_RECOGNITION_PIPELINE_COMPLETE.md`
