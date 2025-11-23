# Voice & Face Recognition - Video Development Integration

**Project:** Video Development
**Integration Type:** Unsupervised Clustering (Unknown Speakers)
**Created:** November 23, 2025
**Status:** Specification Complete, Ready for Implementation

---

## Table of Contents

1. [Integration Overview](#integration-overview)
2. [Database Schema](#database-schema)
3. [Clustering Pipeline](#clustering-pipeline)
4. [Cluster Review UI](#cluster-review-ui)
5. [Transcription Integration](#transcription-integration)
6. [Batch Processing](#batch-processing)
7. [Testing Strategy](#testing-strategy)

---

## Integration Overview

### Current State (November 2025)

**Video Development has:**
- ✅ 652 archived videos on Pegasus drive
- ✅ Whisper transcription pipeline planned
- ✅ SQLite database design planned
- ✅ Survey phase complete
- ⚠️ Unknown speakers in videos (no training data)

### Integration Goals

1. **Discover unknown speakers** in 652 archived videos without training data
2. **Cluster similar voices** using DBSCAN on speaker embeddings
3. **Present clusters to user** for manual identification
4. **Link transcripts to speakers** for searchable content
5. **Convert identified clusters** to supervised training data
6. **Enable future auto-identification** after initial labeling

### Use Case: India Trip Videos

**Example Scenario:**
- Video contains 3 unknown speakers
- Diarization identifies 3 distinct voice patterns
- Clustering groups all segments from each speaker
- User reviews cluster samples and identifies:
  - Speaker_0 = "Joe Ferguson"
  - Speaker_1 = "Mary Ferguson"
  - Speaker_2 = "Guide (Unknown)"
- System links all Joe's segments, creates voiceprint for future videos

---

## Database Schema

### Core Tables

```sql
-- Videos table (replaces generic media_items)
CREATE TABLE IF NOT EXISTS videos (
    video_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    file_size_bytes INTEGER,
    duration_seconds REAL,
    format TEXT,  -- mp4, mov, avi
    resolution TEXT,  -- 1920x1080, 1280x720
    codec_video TEXT,
    codec_audio TEXT,
    frame_rate REAL,
    created_date TIMESTAMP,
    modified_date TIMESTAMP,
    category TEXT,  -- 'India', 'Vinny', 'Charles', 'Other'
    processing_status TEXT DEFAULT 'pending',
    -- Values: 'pending', 'transcribing', 'diarizing', 'clustering', 'complete', 'error'
    transcription_complete BOOLEAN DEFAULT 0,
    diarization_complete BOOLEAN DEFAULT 0,
    clustering_complete BOOLEAN DEFAULT 0,
    indexed_at TIMESTAMP
);

CREATE INDEX idx_videos_category ON videos(category);
CREATE INDEX idx_videos_status ON videos(processing_status);

-- Transcripts from Whisper API
CREATE TABLE IF NOT EXISTS transcripts (
    transcript_id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    text TEXT NOT NULL,
    confidence REAL,
    language TEXT DEFAULT 'en',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (video_id) REFERENCES videos(video_id) ON DELETE CASCADE
);

CREATE INDEX idx_transcripts_video ON transcripts(video_id, start_time);

-- Full-text search for transcripts
CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts USING fts5(
    text,
    content=transcripts,
    content_rowid=transcript_id
);

-- Speaker segments from diarization
CREATE TABLE IF NOT EXISTS speaker_segments (
    segment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    speaker_label TEXT,  -- 'SPEAKER_00', 'SPEAKER_01', etc. (from Pyannote)
    cluster_id INTEGER,  -- Link to unknown_clusters
    person_id INTEGER,  -- Link to persons table (NULL until identified)
    confidence REAL,
    needs_review BOOLEAN DEFAULT 0,
    verified BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (video_id) REFERENCES videos(video_id) ON DELETE CASCADE,
    FOREIGN KEY (cluster_id) REFERENCES unknown_clusters(id) ON DELETE SET NULL,
    FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE SET NULL
);

CREATE INDEX idx_segments_video ON speaker_segments(video_id, start_time);
CREATE INDEX idx_segments_cluster ON speaker_segments(cluster_id);
CREATE INDEX idx_segments_person ON speaker_segments(person_id);

-- Speaker embeddings (one per segment)
CREATE TABLE IF NOT EXISTS speaker_embeddings (
    embedding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id INTEGER NOT NULL,
    video_id INTEGER NOT NULL,
    embedding BLOB NOT NULL,  -- 192-512D numpy array
    embedding_model TEXT DEFAULT 'ecapa-tdnn',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (segment_id) REFERENCES speaker_segments(segment_id) ON DELETE CASCADE,
    FOREIGN KEY (video_id) REFERENCES videos(video_id) ON DELETE CASCADE
);

CREATE INDEX idx_embeddings_segment ON speaker_embeddings(segment_id);
CREATE INDEX idx_embeddings_video ON speaker_embeddings(video_id);

-- Unknown speaker clusters
CREATE TABLE IF NOT EXISTS unknown_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_type TEXT NOT NULL DEFAULT 'voice',  -- 'voice' or 'face'
    cluster_label TEXT NOT NULL,  -- 'Speaker_0', 'Speaker_1', etc.
    sample_count INTEGER DEFAULT 0,
    total_duration REAL DEFAULT 0.0,  -- Total seconds of speech
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    representative_embedding BLOB,  -- Centroid embedding
    person_id INTEGER,  -- NULL until user identifies
    identification_confidence REAL,  -- User's confidence in identification
    identified_at TIMESTAMP,
    identified_by TEXT,  -- Username or 'system'
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE SET NULL
);

CREATE INDEX idx_clusters_type ON unknown_clusters(cluster_type);
CREATE INDEX idx_clusters_identified ON unknown_clusters(person_id) WHERE person_id IS NOT NULL;

-- Persons table (shared with Family Archive)
CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);

-- Face detections in videos (sampled frames)
CREATE TABLE IF NOT EXISTS face_detections (
    detection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    frame_number INTEGER NOT NULL,
    timestamp REAL NOT NULL,  -- Seconds into video
    person_id INTEGER,  -- NULL if unknown
    cluster_id INTEGER,  -- Face cluster
    confidence REAL,
    bbox_x INTEGER,
    bbox_y INTEGER,
    bbox_width INTEGER,
    bbox_height INTEGER,
    needs_review BOOLEAN DEFAULT 0,
    verified BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (video_id) REFERENCES videos(video_id) ON DELETE CASCADE,
    FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE SET NULL,
    FOREIGN KEY (cluster_id) REFERENCES unknown_clusters(id) ON DELETE SET NULL
);

CREATE INDEX idx_face_detections_video ON face_detections(video_id, timestamp);
CREATE INDEX idx_face_detections_cluster ON face_detections(cluster_id);
```

---

## Clustering Pipeline

### Pipeline Overview

```
Video File
  ↓
1. Extract Audio
  ↓
2. Whisper Transcription → transcripts table
  ↓
3. Pyannote Diarization → speaker_segments table
  ↓
4. Extract Speaker Embeddings → speaker_embeddings table
  ↓
5. Cluster Embeddings (DBSCAN) → unknown_clusters table
  ↓
6. Link Segments to Clusters
  ↓
7. Present to User for Identification
  ↓
8. User Identifies → Update cluster.person_id
  ↓
9. Convert to Supervised (future videos auto-tagged)
```

### 1. Audio Extraction

```python
import subprocess
import os

def extract_audio_from_video(video_path, output_audio_path):
    """
    Extract audio track from video and convert to 16kHz mono WAV.

    Args:
        video_path: Path to video file
        output_audio_path: Path for output WAV file

    Returns:
        Path to extracted audio file
    """
    # Use ffmpeg to extract and convert audio
    cmd = [
        'ffmpeg',
        '-i', video_path,
        '-vn',  # No video
        '-acodec', 'pcm_s16le',  # PCM 16-bit
        '-ar', '16000',  # 16kHz sample rate (required for Pyannote)
        '-ac', '1',  # Mono
        '-y',  # Overwrite output
        output_audio_path
    ]

    subprocess.run(cmd, check=True, capture_output=True)

    return output_audio_path
```

### 2. Whisper Transcription (Existing Pipeline)

```python
from openai import OpenAI

def transcribe_audio_whisper(audio_path):
    """
    Transcribe audio using OpenAI Whisper API.

    Cost: $0.006/minute
    """
    client = OpenAI()

    with open(audio_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",  # Get timestamps
            timestamp_granularity="segment"
        )

    return transcript.segments  # List of {start, end, text}
```

### 3. Speaker Diarization

```python
from pyannote.audio import Pipeline
import torch

def diarize_audio(audio_path):
    """
    Run speaker diarization to identify when each speaker talks.

    Returns: List of (speaker_label, start_time, end_time)
    """
    # Initialize pipeline
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token="YOUR_HF_TOKEN"
    )

    # Move to GPU if available
    if torch.cuda.is_available():
        pipeline.to(torch.device("cuda"))

    # Run diarization
    diarization = pipeline(audio_path)

    # Extract segments
    segments = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append({
            'speaker_label': speaker,  # 'SPEAKER_00', 'SPEAKER_01', etc.
            'start_time': turn.start,
            'end_time': turn.end,
            'duration': turn.end - turn.start
        })

    return segments
```

### 4. Extract Speaker Embeddings

```python
from pyannote.audio import Inference
from pyannote.core import Segment

def extract_speaker_embeddings(audio_path, segments):
    """
    Extract speaker embedding for each diarization segment.

    Returns: List of (segment_id, embedding) tuples
    """
    # Initialize embedding model
    model = Inference(
        "pyannote/embedding",
        device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
    )

    embeddings = []

    for segment in segments:
        # Extract embedding for this segment
        segment_obj = Segment(segment['start_time'], segment['end_time'])
        embedding = model.crop(audio_path, segment_obj)

        embeddings.append({
            'speaker_label': segment['speaker_label'],
            'start_time': segment['start_time'],
            'end_time': segment['end_time'],
            'embedding': embedding.numpy()
        })

    return embeddings
```

### 5. Cluster Embeddings (DBSCAN)

```python
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import normalize
import numpy as np

def cluster_speaker_embeddings(embeddings, epsilon=0.6, min_samples=3):
    """
    Cluster speaker embeddings to discover unique speakers across all videos.

    Args:
        embeddings: List of embedding dicts from extract_speaker_embeddings
        epsilon: DBSCAN distance threshold (tune based on data)
        min_samples: Minimum segments to form a cluster

    Returns:
        cluster_labels: Array of cluster IDs (-1 = noise)
    """
    # Stack embeddings into matrix
    X = np.vstack([e['embedding'] for e in embeddings])

    # Normalize for cosine distance
    X_normalized = normalize(X, norm='l2')

    # Run DBSCAN
    clustering = DBSCAN(
        eps=epsilon,
        min_samples=min_samples,
        metric='cosine'
    )

    cluster_labels = clustering.fit_predict(X_normalized)

    return cluster_labels

def create_cluster_records(embeddings, cluster_labels):
    """
    Create unknown_clusters records and link segments.

    Returns: Dict mapping cluster_id to cluster record
    """
    import sqlite3
    conn = sqlite3.connect('video-archive.db')
    cursor = conn.cursor()

    # Get unique clusters (excluding noise -1)
    unique_clusters = set(cluster_labels) - {-1}

    cluster_map = {}

    for cluster_num, cluster_id in enumerate(sorted(unique_clusters)):
        # Find all segments in this cluster
        cluster_mask = cluster_labels == cluster_id
        cluster_embeddings = [emb for i, emb in enumerate(embeddings) if cluster_mask[i]]

        # Calculate statistics
        sample_count = len(cluster_embeddings)
        total_duration = sum(e['end_time'] - e['start_time'] for e in cluster_embeddings)

        # Calculate representative embedding (centroid)
        centroid = np.mean([e['embedding'] for e in cluster_embeddings], axis=0)

        # Insert cluster record
        cursor.execute("""
            INSERT INTO unknown_clusters
            (cluster_type, cluster_label, sample_count, total_duration, representative_embedding, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, ('voice', f'Speaker_{cluster_num}', sample_count, total_duration, centroid.tobytes()))

        db_cluster_id = cursor.lastrowid
        cluster_map[cluster_id] = db_cluster_id

    conn.commit()
    conn.close()

    return cluster_map
```

### Complete Processing Function

```python
def process_video_full_pipeline(video_path, video_id):
    """
    Complete pipeline: transcription → diarization → clustering.
    """
    import os
    import tempfile

    # 1. Extract audio
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        audio_path = tmp.name

    extract_audio_from_video(video_path, audio_path)

    # 2. Transcribe with Whisper
    transcript_segments = transcribe_audio_whisper(audio_path)

    # Store transcripts in database
    store_transcripts(video_id, transcript_segments)

    # 3. Diarize audio (find speaker segments)
    diarization_segments = diarize_audio(audio_path)

    # Store speaker segments
    store_speaker_segments(video_id, diarization_segments)

    # 4. Extract embeddings for each segment
    embeddings_with_metadata = extract_speaker_embeddings(audio_path, diarization_segments)

    # Store embeddings
    store_speaker_embeddings(video_id, embeddings_with_metadata)

    # 5. Cluster embeddings
    embeddings_only = [e['embedding'] for e in embeddings_with_metadata]
    cluster_labels = cluster_speaker_embeddings(embeddings_with_metadata)

    # 6. Create cluster records and link segments
    cluster_map = create_cluster_records(embeddings_with_metadata, cluster_labels)

    # Link segments to clusters
    link_segments_to_clusters(video_id, cluster_labels, cluster_map)

    # Cleanup
    os.unlink(audio_path)

    return {
        'transcripts_count': len(transcript_segments),
        'speakers_detected': len(set(cluster_labels) - {-1}),
        'segments_count': len(diarization_segments)
    }
```

---

## Cluster Review UI

### Overview

The cluster review interface presents unknown speaker clusters to the user for manual identification.

### Main Cluster Review Screen

```html
<!DOCTYPE html>
<html>
<head>
    <title>Speaker Identification - Video Development</title>
    <style>
        .cluster-review-container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }

        .cluster-card {
            border: 2px solid #ddd;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            background: white;
        }

        .cluster-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }

        .cluster-label {
            font-size: 24px;
            font-weight: bold;
        }

        .cluster-stats {
            display: flex;
            gap: 20px;
            color: #666;
        }

        .audio-samples {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }

        .audio-sample {
            border: 1px solid #e0e0e0;
            border-radius: 4px;
            padding: 15px;
            background: #f9f9f9;
        }

        .sample-info {
            margin-bottom: 10px;
            font-size: 14px;
            color: #666;
        }

        .waveform-container {
            height: 60px;
            background: #e8e8e8;
            border-radius: 4px;
            margin: 10px 0;
        }

        .playback-controls {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .btn-play {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            border: none;
            background: #667eea;
            color: white;
            font-size: 16px;
            cursor: pointer;
        }

        .suggestions-section {
            background: #f0f7ff;
            padding: 15px;
            border-radius: 4px;
            margin: 20px 0;
        }

        .suggestion-item {
            display: flex;
            align-items: center;
            padding: 10px;
            margin: 5px 0;
            background: white;
            border-radius: 4px;
            cursor: pointer;
        }

        .suggestion-item:hover {
            background: #e6f2ff;
        }

        .suggestion-confidence {
            margin-left: auto;
            font-weight: bold;
            color: #667eea;
        }

        .action-buttons {
            display: flex;
            gap: 10px;
            margin-top: 20px;
        }

        .btn-primary {
            padding: 12px 24px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 4px;
            font-size: 16px;
            cursor: pointer;
        }

        .btn-secondary {
            padding: 12px 24px;
            background: white;
            color: #667eea;
            border: 2px solid #667eea;
            border-radius: 4px;
            font-size: 16px;
            cursor: pointer;
        }

        .person-search {
            width: 100%;
            padding: 12px;
            border: 2px solid #ddd;
            border-radius: 4px;
            font-size: 16px;
            margin: 10px 0;
        }
    </style>
</head>
<body>
    <div class="cluster-review-container">
        <h1>Identify Speakers (23 clusters pending)</h1>

        <!-- Cluster Card -->
        <div class="cluster-card" data-cluster-id="3">
            <div class="cluster-header">
                <div class="cluster-label">Speaker_3</div>
                <div class="cluster-stats">
                    <span>12 segments</span>
                    <span>3.4 minutes total</span>
                    <span>5 videos</span>
                </div>
            </div>

            <!-- Audio Samples -->
            <h3>Sample Clips (tap to play):</h3>
            <div class="audio-samples">
                <div class="audio-sample">
                    <div class="sample-info">
                        Video: India_Day2.mp4<br>
                        00:45 - 01:02 (17s)
                    </div>
                    <div class="waveform-container">
                        <!-- Waveform visualization canvas -->
                    </div>
                    <div class="playback-controls">
                        <button class="btn-play" data-clip-id="1">▶</button>
                        <span class="playback-time">0:00 / 0:17</span>
                    </div>
                    <audio src="/api/clips/speaker_3_clip_1.wav" hidden></audio>
                </div>

                <div class="audio-sample">
                    <div class="sample-info">
                        Video: India_Day3.mp4<br>
                        02:15 - 02:34 (19s)
                    </div>
                    <div class="waveform-container"></div>
                    <div class="playback-controls">
                        <button class="btn-play" data-clip-id="2">▶</button>
                        <span class="playback-time">0:00 / 0:19</span>
                    </div>
                    <audio src="/api/clips/speaker_3_clip_2.wav" hidden></audio>
                </div>

                <div class="audio-sample">
                    <div class="sample-info">
                        Video: India_Day5.mp4<br>
                        01:05 - 01:28 (23s)
                    </div>
                    <div class="waveform-container"></div>
                    <div class="playback-controls">
                        <button class="btn-play" data-clip-id="3">▶</button>
                        <span class="playback-time">0:00 / 0:23</span>
                    </div>
                    <audio src="/api/clips/speaker_3_clip_3.wav" hidden></audio>
                </div>
            </div>

            <!-- AI Suggestions -->
            <div class="suggestions-section">
                <h3>Best Matches:</h3>
                <div class="suggestion-item" data-person-id="5">
                    <span class="suggestion-name">Joe Ferguson</span>
                    <span class="suggestion-confidence">78%</span>
                </div>
                <div class="suggestion-item" data-person-id="12">
                    <span class="suggestion-name">Paul Ferguson</span>
                    <span class="suggestion-confidence">65%</span>
                </div>
            </div>

            <!-- Manual Selection -->
            <div class="manual-selection">
                <h3>Or Select Person:</h3>
                <input type="text"
                       class="person-search"
                       placeholder="Search family members..."
                       data-cluster-id="3">

                <div class="person-results hidden">
                    <!-- Populated by search -->
                </div>
            </div>

            <!-- Actions -->
            <div class="action-buttons">
                <button class="btn-primary" onclick="confirmIdentification(3, 5)">
                    Select Top Match (Joe Ferguson)
                </button>
                <button class="btn-secondary" onclick="createNewPerson(3)">
                    Create New Person
                </button>
                <button class="btn-secondary" onclick="skipCluster(3)">
                    Skip for Now
                </button>
                <button class="btn-secondary" onclick="nextCluster()">
                    Next Cluster →
                </button>
            </div>
        </div>

        <!-- Progress Indicator -->
        <div class="progress-bar">
            <div class="progress-fill" style="width: 13%"></div>
            <span class="progress-text">3 of 23 identified (13%)</span>
        </div>
    </div>

    <script src="cluster-review.js"></script>
</body>
</html>
```

### JavaScript Functionality

```javascript
// cluster-review.js

// Play audio clip
document.querySelectorAll('.btn-play').forEach(btn => {
    btn.addEventListener('click', (e) => {
        const clipId = e.target.dataset.clipId;
        const audioElement = e.target.closest('.audio-sample').querySelector('audio');

        if (audioElement.paused) {
            audioElement.play();
            e.target.textContent = '⏸';
        } else {
            audioElement.pause();
            e.target.textContent = '▶';
        }
    });
});

// Confirm identification
async function confirmIdentification(clusterId, personId) {
    const response = await fetch(`/api/v1/clusters/${clusterId}/identify`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            person_id: personId,
            confidence: 1.0,
            identified_by: 'user'
        })
    });

    if (response.ok) {
        // Show success message
        showNotification('Speaker identified successfully!');

        // Move to next cluster
        nextCluster();
    }
}

// Create new person
function createNewPerson(clusterId) {
    const name = prompt('Enter person name:');

    if (name) {
        fetch('/api/v1/persons', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: name})
        })
        .then(r => r.json())
        .then(data => {
            confirmIdentification(clusterId, data.id);
        });
    }
}

// Skip cluster
function skipCluster(clusterId) {
    // Mark as skipped, move to next
    nextCluster();
}

// Load next cluster
function nextCluster() {
    window.location.href = `/review/clusters?skip=${getCurrentClusterId()}`;
}

// Person search
document.querySelectorAll('.person-search').forEach(input => {
    input.addEventListener('input', async (e) => {
        const query = e.target.value;

        if (query.length < 2) return;

        const response = await fetch(`/api/v1/persons/search?q=${query}`);
        const persons = await response.json();

        // Show results
        displayPersonResults(persons, e.target.dataset.clusterId);
    });
});
```

### Mobile Optimizations

```css
/* Mobile-specific styles */
@media (max-width: 768px) {
    .audio-samples {
        grid-template-columns: 1fr;
    }

    .cluster-stats {
        flex-direction: column;
        gap: 5px;
    }

    .action-buttons {
        flex-direction: column;
    }

    .btn-primary, .btn-secondary {
        width: 100%;
    }
}

/* Touch gestures */
.cluster-card {
    touch-action: pan-y;  /* Allow vertical scrolling */
}

/* Swipe to next cluster */
let touchStartX = 0;
let touchEndX = 0;

document.addEventListener('touchstart', e => {
    touchStartX = e.changedTouches[0].screenX;
});

document.addEventListener('touchend', e => {
    touchEndX = e.changedTouches[0].screenX;
    handleSwipe();
});

function handleSwipe() {
    if (touchEndX < touchStartX - 50) {
        // Swipe left = next cluster
        nextCluster();
    }
    if (touchEndX > touchStartX + 50) {
        // Swipe right = previous cluster
        previousCluster();
    }
}
```

---

## Transcription Integration

### Link Speaker Labels to Transcripts

```python
def link_transcripts_to_speakers(video_id):
    """
    Link Whisper transcript segments to identified speakers.

    Transcripts have timestamps, speaker_segments have timestamps.
    Find overlaps and assign speaker to transcript.
    """
    conn = sqlite3.connect('video-archive.db')
    cursor = conn.cursor()

    # Get all transcripts for this video
    cursor.execute("""
        SELECT transcript_id, start_time, end_time, text
        FROM transcripts
        WHERE video_id = ?
        ORDER BY start_time
    """, (video_id,))
    transcripts = cursor.fetchall()

    # Get all speaker segments for this video
    cursor.execute("""
        SELECT segment_id, start_time, end_time, person_id, cluster_id
        FROM speaker_segments
        WHERE video_id = ?
        ORDER BY start_time
    """, (video_id,))
    segments = cursor.fetchall()

    # For each transcript, find overlapping speaker
    for trans_id, trans_start, trans_end, text in transcripts:
        best_overlap = 0
        best_speaker = None

        for seg_id, seg_start, seg_end, person_id, cluster_id in segments:
            # Calculate overlap
            overlap_start = max(trans_start, seg_start)
            overlap_end = min(trans_end, seg_end)
            overlap = max(0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = (person_id, cluster_id)

        # Update transcript with speaker info
        if best_speaker:
            person_id, cluster_id = best_speaker

            cursor.execute("""
                UPDATE transcripts
                SET person_id = ?, cluster_id = ?
                WHERE transcript_id = ?
            """, (person_id, cluster_id, trans_id))

    conn.commit()
    conn.close()
```

### Display Transcripts with Speaker Labels

```html
<div class="transcript-viewer">
    <h2>India_Day2.mp4 Transcript</h2>

    <div class="transcript-segment">
        <div class="speaker-label identified">
            <img src="/avatars/joe.jpg" class="speaker-avatar">
            <span class="speaker-name">Joe Ferguson</span>
            <span class="timestamp">00:45</span>
        </div>
        <p class="transcript-text">
            This is incredible! Look at the architecture of this temple.
        </p>
    </div>

    <div class="transcript-segment">
        <div class="speaker-label unknown" onclick="identifyCluster(8)">
            <span class="speaker-name">Speaker_8</span>
            <span class="timestamp">00:53</span>
            <button class="btn-identify">Who is this?</button>
        </div>
        <p class="transcript-text">
            It was built in the 12th century and has over 300 intricate carvings.
        </p>
    </div>

    <div class="transcript-segment">
        <div class="speaker-label identified">
            <img src="/avatars/mary.jpg" class="speaker-avatar">
            <span class="speaker-name">Mary Ferguson</span>
            <span class="timestamp">01:02</span>
        </div>
        <p class="transcript-text">
            Can we go inside?
        </p>
    </div>
</div>
```

---

## Batch Processing

### Process All 652 Videos

```python
import sqlite3
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def batch_process_all_videos(batch_size=10):
    """
    Process all videos in batches.

    Args:
        batch_size: Number of videos to process before committing
    """
    conn = sqlite3.connect('video-archive.db')
    cursor = conn.cursor()

    # Get all unprocessed videos
    cursor.execute("""
        SELECT video_id, file_path
        FROM videos
        WHERE processing_status = 'pending'
        ORDER BY video_id
    """)

    videos = cursor.fetchall()
    total = len(videos)

    logger.info(f"Processing {total} videos in batches of {batch_size}")

    for i, (video_id, file_path) in enumerate(videos):
        try:
            logger.info(f"[{i+1}/{total}] Processing {file_path}")

            # Update status
            cursor.execute("""
                UPDATE videos
                SET processing_status = 'processing'
                WHERE video_id = ?
            """, (video_id,))
            conn.commit()

            # Run full pipeline
            result = process_video_full_pipeline(file_path, video_id)

            # Update status
            cursor.execute("""
                UPDATE videos
                SET processing_status = 'complete',
                    transcription_complete = 1,
                    diarization_complete = 1
                WHERE video_id = ?
            """, (video_id,))
            conn.commit()

            logger.info(f"  ✓ Transcripts: {result['transcripts_count']}")
            logger.info(f"  ✓ Speakers: {result['speakers_detected']}")
            logger.info(f"  ✓ Segments: {result['segments_count']}")

        except Exception as e:
            logger.error(f"  ✗ Error: {e}")

            # Mark as error
            cursor.execute("""
                UPDATE videos
                SET processing_status = 'error'
                WHERE video_id = ?
            """, (video_id,))
            conn.commit()

            continue

    conn.close()

    logger.info("Batch processing complete!")

# Run batch process with nohup protection
if __name__ == '__main__':
    batch_process_all_videos()
```

### Cost Estimation

```python
def estimate_processing_costs():
    """Calculate estimated costs for processing all videos."""
    conn = sqlite3.connect('video-archive.db')
    cursor = conn.cursor()

    # Get total duration of all videos
    cursor.execute("""
        SELECT SUM(duration_seconds) / 60.0 as total_minutes
        FROM videos
        WHERE processing_status = 'pending'
    """)

    total_minutes = cursor.fetchone()[0]

    # Whisper API: $0.006/minute
    whisper_cost = total_minutes * 0.006

    print(f"Total video duration: {total_minutes:.1f} minutes")
    print(f"Estimated Whisper cost: ${whisper_cost:.2f}")
    print(f"\nDiarization & clustering: Free (local processing)")
    print(f"Total estimated cost: ${whisper_cost:.2f}")

    conn.close()
```

---

## Testing Strategy

### Unit Tests

```python
# test_clustering.py
import pytest
from clustering import cluster_speaker_embeddings

def test_clustering_creates_distinct_speakers():
    """Test that DBSCAN correctly identifies distinct speakers."""
    # Create synthetic embeddings for 3 speakers
    speaker1_embeddings = [generate_similar_embedding() for _ in range(10)]
    speaker2_embeddings = [generate_similar_embedding() for _ in range(8)]
    speaker3_embeddings = [generate_similar_embedding() for _ in range(12)]

    all_embeddings = speaker1_embeddings + speaker2_embeddings + speaker3_embeddings

    labels = cluster_speaker_embeddings(all_embeddings)

    # Should find 3 clusters (excluding noise)
    unique_clusters = set(labels) - {-1}
    assert len(unique_clusters) == 3
```

### Integration Tests

```python
# test_pipeline.py
def test_full_pipeline_on_sample_video():
    """Test complete pipeline on a short test video."""
    video_path = "test_data/sample_video.mp4"

    result = process_video_full_pipeline(video_path, video_id=999)

    assert result['transcripts_count'] > 0
    assert result['speakers_detected'] > 0
    assert result['segments_count'] > 0

    # Verify data in database
    conn = sqlite3.connect('video-archive.db')
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM transcripts WHERE video_id = 999")
    assert cursor.fetchone()[0] == result['transcripts_count']

    cursor.execute("SELECT COUNT(*) FROM speaker_segments WHERE video_id = 999")
    assert cursor.fetchone()[0] == result['segments_count']
```

---

## Implementation Checklist

### Phase 1: Database & Clustering (2 weeks)

- [ ] Create database schema (videos, transcripts, segments, clusters)
- [ ] Implement audio extraction (ffmpeg)
- [ ] Integrate Whisper transcription
- [ ] Implement Pyannote diarization
- [ ] Implement speaker embedding extraction
- [ ] Implement DBSCAN clustering
- [ ] Write batch processing script

### Phase 2: Cluster Review UI (2 weeks)

- [ ] Build cluster review page (HTML/CSS/JS)
- [ ] Implement audio clip playback
- [ ] Build person search interface
- [ ] Add identification confirmation workflow
- [ ] Implement "Create New Person" flow
- [ ] Add swipe gestures for mobile
- [ ] Build progress tracking

### Phase 3: Transcription Integration (1 week)

- [ ] Link speaker segments to transcripts
- [ ] Build transcript viewer with speaker labels
- [ ] Implement "identify from transcript" UI
- [ ] Add search by speaker functionality

### Phase 4: Production Processing (2 weeks)

- [ ] Test on 10-video sample
- [ ] Estimate costs for full 652 videos
- [ ] Run full batch processing (with nohup)
- [ ] Monitor progress and errors
- [ ] Review and identify all clusters
- [ ] Build voiceprints from identified speakers

---

## Expected Outcomes

**After Full Implementation:**

1. **All 652 videos processed** with transcripts and diarization
2. **Speaker clusters identified** (estimated 20-50 unique speakers)
3. **Searchable transcripts** with speaker attribution
4. **Unknown speakers identified** through cluster review UI
5. **Voiceprints created** for future auto-identification
6. **Cost-effective** (Whisper API only, ~$50-200 total)

**User Experience:**
- Search transcripts: "Find all videos where Joe talks about temples"
- Review clusters on mobile device (plane trip)
- Identify speakers in 2-3 hours total review time
- Future videos auto-tag known speakers

---

**Integration Complete:** Ready for implementation

**Next Steps:** Phase 1 - Database & clustering implementation

**Estimated Timeline:** 6-8 weeks total

**Deployment:** See main skill specification for deployment architecture
