#!/bin/bash
# Example script: Extract audio from video file using FFmpeg

# Usage: ./extract-audio-example.sh input-video.mp4

if [ $# -eq 0 ]; then
    echo "Usage: $0 <video-file>"
    echo ""
    echo "Example: $0 sample-video.mp4"
    echo ""
    echo "This will create: sample-video.mp3"
    exit 1
fi

INPUT_VIDEO="$1"
OUTPUT_AUDIO="${INPUT_VIDEO%.*}.mp3"

echo "Extracting audio from: $INPUT_VIDEO"
echo "Output will be: $OUTPUT_AUDIO"
echo ""

ffmpeg -i "$INPUT_VIDEO" -vn -acodec libmp3lame -q:a 2 "$OUTPUT_AUDIO"

echo ""
echo "Done! Audio extracted to: $OUTPUT_AUDIO"
