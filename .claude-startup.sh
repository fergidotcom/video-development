#!/bin/bash
# Claude Code Project Startup Hook
# This script loads the most recent checkpoint when entering the Video Development project

# Project-specific configuration
PROJECT_NAME="VideoDev"
MAC_PERSPECTIVE_FILE="$HOME/Downloads/${PROJECT_NAME}MacPerspective.yaml"

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}📋 Claude Code Project: Video Development${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Check if checkpoint file exists
if [ -f "$MAC_PERSPECTIVE_FILE" ]; then
    echo -e "${GREEN}✅ Found checkpoint: ${MAC_PERSPECTIVE_FILE}${NC}"
    echo ""

    # Extract key information from YAML
    echo -e "${YELLOW}📊 Last Session Summary:${NC}"
    echo ""

    # Get timestamp
    TIMESTAMP=$(grep "^timestamp:" "$MAC_PERSPECTIVE_FILE" | cut -d'"' -f2)
    if [ -n "$TIMESTAMP" ]; then
        echo -e "${BLUE}⏰ Last Updated:${NC} $TIMESTAMP"
    fi

    # Get status
    STATUS=$(grep "^  status:" "$MAC_PERSPECTIVE_FILE" | sed 's/^  status: "\(.*\)"/\1/')
    if [ -n "$STATUS" ]; then
        echo -e "${BLUE}📍 Status:${NC} $STATUS"
    fi

    echo ""

    # Extract session summary
    echo -e "${YELLOW}📝 Session Summary:${NC}"
    sed -n '/^session_summary: |/,/^[^ ]/p' "$MAC_PERSPECTIVE_FILE" | \
        grep -v "^session_summary:" | \
        grep -v "^[^ ]" | \
        sed 's/^  //' | \
        sed 's/^/  /'

    echo ""

    # Extract next steps
    echo -e "${YELLOW}🎯 Next Steps:${NC}"
    sed -n '/^next_steps:/,/^[^ ]/p' "$MAC_PERSPECTIVE_FILE" | \
        grep "^  - " | \
        sed 's/^  - "\(.*\)"/  • \1/' | \
        sed 's/^  - /  • /'

    echo ""
    echo -e "${GREEN}💡 Claude will automatically load this context when you start.${NC}"
    echo ""

else
    echo -e "${YELLOW}⚠️  No checkpoint found at: ${MAC_PERSPECTIVE_FILE}${NC}"
    echo -e "${BLUE}💡 Say 'checkpoint' at the end of your session to create one.${NC}"
    echo ""
fi

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
