#!/usr/bin/env python3
"""
Generate Narrative Summaries for Transcripts
=============================================
Uses Claude API to create searchable narrative summaries for each transcript.
Narratives are stored in the database and indexed for full-text search.
Specifically identifies Ferguson family members in each transcript.

Run after transcriptions complete:
    python3 generate_narratives.py

Or with nohup for large batches:
    nohup python3 generate_narratives.py > logs/narratives_$(date +%Y%m%d_%H%M%S).log 2>&1 &
"""

import os
import sys
import sqlite3
import json
import time
from pathlib import Path
from datetime import datetime
from openai import OpenAI

# Configuration
TRANSCRIPT_DATABASE = "transcripts.db"
BATCH_SIZE = 10  # Process in batches to manage API costs
RATE_LIMIT_DELAY = 1  # Seconds between API calls

# Ferguson Family Members (for identification in transcripts)
FERGUSON_FAMILY = {
    "Generation 1 - Grandparents": [
        "Charles Kasreal Ferguson (CK, Charlie, Grandpa Ferguson)",
        "Lois Adelaide Ferguson (Grandma Ferguson, Lois)",
    ],
    "Generation 2 - Children": [
        "Joseph Glenn Ferguson (Joe, Joey, Pop, Pops, Dad - b. ~1940s)",
        "Michael C Ferguson (Mike, Uncle Mike)",
        "Paul Ferguson (Uncle Paul)",
        "Trudi C Ferguson (Trudi, Aunt Trudi)",
        "Susie Ferguson (Aunt Susie)",
        "Mary Pratt Ferguson (Mary, Aunt Mary)",
        "Marianne Popek Ferguson (Marianne - DECEASED 2015)",
        "Lori Ferguson (Lori)",
        "Paul Updegrove (spouse of Trudi)",
    ],
    "Generation 3 - Grandchildren": [
        "Jeff Ferguson (Jeff - son of Joe)",
        "David Ferguson (Dave, David - son of Mike)",
        "Andy Ferguson (Andy - son of Mike)",
        "Christopher Ferguson (Chris - son of Paul)",
        "Charlie Ferguson (Charlie - son of Paul)",
        "Paul Ferguson Jr (Paul - son of Susie)",
        "Sam Ferguson (Sam)",
        "David Updegrove (David - son of Trudi)",
        "Laura Updegrove (Laura - daughter of Trudi)",
        "Paul Updegrove Jr (Paul - son of Trudi)",
    ],
    "Generation 3 - Spouses": [
        "Amy Ferguson (Amy - spouse)",
        "Jen Ferguson (Jen - spouse)",
        "Katelyn Ferguson (Katelyn - spouse)",
        "Kim Ferguson (Kim - spouse)",
        "Lauren Ferguson (Lauren - spouse)",
        "Vasudha Ferguson (Vasudha - spouse of Jeff)",
        "Miles Galbraith (Miles - spouse)",
        "Paige Robinson (Paige - spouse)",
    ],
    "Generation 4 - Great-Grandchildren": [
        "Cate Ferguson (Cate - daughter of Jeff & Vasudha)",
        "Leela Ferguson (Leela - daughter of Jeff & Vasudha)",
        "Ben Ferguson (Ben)",
        "James Ferguson (James)",
        "Logan Ferguson (Logan)",
        "Mason Ferguson (Mason)",
        "Max Ferguson (Max)",
        "Romi Ferguson (Romi)",
        "Simon Ferguson (Simon)",
        "Theo Ferguson (Theo)",
        "Bodie Galbraith (Bodie)",
        "Isla Rose Galbraith (Isla)",
        "Jones Updegrove (Jones)",
        "Summerville Updegrove (Summerville)",
    ],
    "Other Notable People": [
        "Vinny (Sensei Vinny - film subject, martial arts)",
        "Pema (spiritual teacher, Mindrolling)",
        "Steve (Peirce Gang participant)",
        "Mike Macey (Peirce Gang participant)",
        "Glenn Conroy (interview subject)",
        "Lew Watts (interview subject)",
        "Shanti Gupta (interview subject)",
        "Stephen Guerin (SimTable, interview)",
        "Kjell (Santa Barbara)",
    ],
}

def log(msg):
    """Print timestamped message."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    sys.stdout.flush()

def get_openai_client():
    """Get OpenAI client with API key."""
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        # Try reading from .zshrc
        zshrc_path = Path.home() / ".zshrc"
        if zshrc_path.exists():
            with open(zshrc_path) as f:
                for line in f:
                    if 'export OPENAI_API_KEY=' in line and 'sk-' in line:
                        api_key = line.split('=', 1)[1].strip().strip('"').strip("'")
                        break

    if not api_key or not api_key.startswith('sk-'):
        raise ValueError("OPENAI_API_KEY not found. Set in environment or ~/.zshrc")

    return OpenAI(api_key=api_key)

def setup_database(conn):
    """Add narrative column and FTS table if they don't exist."""
    cursor = conn.cursor()

    # Add narrative column if it doesn't exist
    cursor.execute("PRAGMA table_info(transcripts)")
    columns = [col[1] for col in cursor.fetchall()]

    if 'narrative' not in columns:
        log("Adding 'narrative' column to transcripts table...")
        cursor.execute("ALTER TABLE transcripts ADD COLUMN narrative TEXT")
        conn.commit()

    if 'narrative_generated_at' not in columns:
        cursor.execute("ALTER TABLE transcripts ADD COLUMN narrative_generated_at TEXT")
        conn.commit()

    if 'family_members' not in columns:
        log("Adding 'family_members' column to transcripts table...")
        cursor.execute("ALTER TABLE transcripts ADD COLUMN family_members TEXT")
        conn.commit()

    if 'other_people' not in columns:
        log("Adding 'other_people' column to transcripts table...")
        cursor.execute("ALTER TABLE transcripts ADD COLUMN other_people TEXT")
        conn.commit()

    # Create FTS5 virtual table for full-text search
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='transcripts_fts'
    """)

    if not cursor.fetchone():
        log("Creating full-text search index...")
        cursor.execute("""
            CREATE VIRTUAL TABLE transcripts_fts USING fts5(
                audio_file_path,
                transcript_text,
                narrative,
                family_members,
                other_people,
                content='transcripts',
                content_rowid='id'
            )
        """)

        # Create triggers to keep FTS in sync
        cursor.execute("""
            CREATE TRIGGER transcripts_ai AFTER INSERT ON transcripts BEGIN
                INSERT INTO transcripts_fts(rowid, audio_file_path, transcript_text, narrative, family_members, other_people)
                VALUES (new.id, new.audio_file_path, new.transcript_text, new.narrative, new.family_members, new.other_people);
            END
        """)

        cursor.execute("""
            CREATE TRIGGER transcripts_ad AFTER DELETE ON transcripts BEGIN
                INSERT INTO transcripts_fts(transcripts_fts, rowid, audio_file_path, transcript_text, narrative, family_members, other_people)
                VALUES ('delete', old.id, old.audio_file_path, old.transcript_text, old.narrative, old.family_members, old.other_people);
            END
        """)

        cursor.execute("""
            CREATE TRIGGER transcripts_au AFTER UPDATE ON transcripts BEGIN
                INSERT INTO transcripts_fts(transcripts_fts, rowid, audio_file_path, transcript_text, narrative, family_members, other_people)
                VALUES ('delete', old.id, old.audio_file_path, old.transcript_text, old.narrative, old.family_members, old.other_people);
                INSERT INTO transcripts_fts(rowid, audio_file_path, transcript_text, narrative, family_members, other_people)
                VALUES (new.id, new.audio_file_path, new.transcript_text, new.narrative, new.family_members, new.other_people);
            END
        """)

        # Populate FTS with existing data
        log("Populating full-text search index with existing transcripts...")
        cursor.execute("""
            INSERT INTO transcripts_fts(rowid, audio_file_path, transcript_text, narrative, family_members, other_people)
            SELECT id, audio_file_path, transcript_text, narrative, family_members, other_people FROM transcripts
        """)

        conn.commit()

    log("Database schema ready.")

def extract_filename_context(file_path):
    """Extract contextual information from filename."""
    path = Path(file_path)
    filename = path.stem

    # Extract date patterns (YYMMDD or YYYYMMDD)
    import re
    date_match = re.search(r'(\d{6}|\d{8})', filename)
    date_hint = ""
    if date_match:
        d = date_match.group(1)
        if len(d) == 6:
            date_hint = f"Date hint: 20{d[:2]}-{d[2:4]}-{d[4:6]}"
        else:
            date_hint = f"Date hint: {d[:4]}-{d[4:6]}-{d[6:8]}"

    # Extract folder context
    parts = path.parts
    folder_context = " > ".join(parts[-4:-1]) if len(parts) > 3 else ""

    return {
        'filename': filename,
        'folder_context': folder_context,
        'date_hint': date_hint
    }

def get_family_reference():
    """Format family members for prompt."""
    lines = []
    for gen, members in FERGUSON_FAMILY.items():
        lines.append(f"{gen}:")
        for m in members:
            lines.append(f"  - {m}")
    return "\n".join(lines)

def generate_narrative(client, transcript_text, file_path, word_count):
    """Generate a narrative summary using Claude."""

    context = extract_filename_context(file_path)

    # Truncate very long transcripts to manage token usage
    max_chars = 15000  # ~3750 tokens
    truncated = transcript_text[:max_chars] if len(transcript_text) > max_chars else transcript_text
    was_truncated = len(transcript_text) > max_chars

    family_ref = get_family_reference()

    prompt = f"""Analyze this transcript and create a concise, searchable narrative summary.
IMPORTANT: Identify any Ferguson family members who appear to be speaking or are mentioned.

FILE CONTEXT:
- Filename: {context['filename']}
- Location: {context['folder_context']}
- {context['date_hint']}
- Word count: {word_count}
{"- Note: Transcript truncated for analysis" if was_truncated else ""}

FERGUSON FAMILY REFERENCE (identify anyone mentioned or speaking):
{family_ref}

TRANSCRIPT:
{truncated}

Create a narrative summary (150-300 words) that includes:

1. FAMILY MEMBERS IDENTIFIED: List any Ferguson family members who are speaking or mentioned.
   Use full names when possible. Note relationships (e.g., "Joe Ferguson (father)" or "Jeff Ferguson (son of Joe)").

2. OTHER PEOPLE: Non-family members mentioned (friends, colleagues, historical figures)

3. WHAT: Main topics, events, stories, or activities discussed

4. WHERE: Locations mentioned (cities, countries, homes, venues)

5. WHEN: Time period, dates, or era being discussed

6. KEY CONTENT: Important stories, memories, quotes, or information shared

Format your response as:
FAMILY MEMBERS: [list anyone identified from the Ferguson family]
OTHERS: [non-family people mentioned]
SUMMARY: [the narrative summary paragraph]

Be specific with names. If someone says "Pop" or "Dad", identify them as "Joseph Glenn Ferguson (Pop/Dad)".
If the speaker can be identified, note who is speaking."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Fast and cost-effective
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log(f"  OpenAI API error: {e}")
        return None

def get_pending_transcripts(conn, limit=None):
    """Get transcripts that need narratives generated."""
    cursor = conn.cursor()

    query = """
        SELECT id, audio_file_path, transcript_text, word_count
        FROM transcripts
        WHERE narrative IS NULL
          AND transcript_text IS NOT NULL
          AND LENGTH(transcript_text) > 50
        ORDER BY word_count ASC
    """

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query)
    return cursor.fetchall()

def parse_narrative_response(response):
    """Parse the structured response to extract family members, others, and summary."""
    family_members = ""
    other_people = ""
    summary = response

    lines = response.split('\n')
    current_section = None
    summary_lines = []

    for line in lines:
        line_upper = line.upper().strip()
        if line_upper.startswith('FAMILY MEMBERS:'):
            current_section = 'family'
            family_members = line.split(':', 1)[1].strip() if ':' in line else ""
        elif line_upper.startswith('OTHERS:'):
            current_section = 'others'
            other_people = line.split(':', 1)[1].strip() if ':' in line else ""
        elif line_upper.startswith('SUMMARY:'):
            current_section = 'summary'
            rest = line.split(':', 1)[1].strip() if ':' in line else ""
            if rest:
                summary_lines.append(rest)
        elif current_section == 'family' and line.strip() and not line_upper.startswith(('OTHERS:', 'SUMMARY:')):
            family_members += " " + line.strip()
        elif current_section == 'others' and line.strip() and not line_upper.startswith(('FAMILY', 'SUMMARY:')):
            other_people += " " + line.strip()
        elif current_section == 'summary' and line.strip():
            summary_lines.append(line.strip())

    if summary_lines:
        summary = ' '.join(summary_lines)

    return family_members.strip(), other_people.strip(), summary.strip()

def update_narrative(conn, transcript_id, narrative_response):
    """Store the generated narrative and parsed fields."""
    family_members, other_people, summary = parse_narrative_response(narrative_response)

    cursor = conn.cursor()
    cursor.execute("""
        UPDATE transcripts
        SET narrative = ?, family_members = ?, other_people = ?, narrative_generated_at = ?
        WHERE id = ?
    """, (summary, family_members, other_people, datetime.now().isoformat(), transcript_id))
    conn.commit()

    return family_members, other_people

def main():
    log("=" * 60)
    log("NARRATIVE GENERATOR FOR TRANSCRIPTS")
    log("=" * 60)

    # Connect to database
    if not os.path.exists(TRANSCRIPT_DATABASE):
        log(f"ERROR: Database {TRANSCRIPT_DATABASE} not found")
        sys.exit(1)

    conn = sqlite3.connect(TRANSCRIPT_DATABASE)

    # Setup database schema
    setup_database(conn)

    # Get OpenAI client
    try:
        client = get_openai_client()
        log("OpenAI client initialized (using gpt-4o-mini)")
    except Exception as e:
        log(f"ERROR: {e}")
        sys.exit(1)

    # Get pending transcripts
    pending = get_pending_transcripts(conn)
    log(f"Found {len(pending)} transcripts needing narratives")

    if not pending:
        log("All transcripts have narratives. Nothing to do.")
        return

    # Process transcripts
    processed = 0
    failed = 0
    total_cost = 0  # Rough estimate: ~$0.003 per narrative with Sonnet

    for i, (tid, file_path, transcript_text, word_count) in enumerate(pending):
        filename = Path(file_path).name
        log(f"\n[{i+1}/{len(pending)}] {filename}")
        log(f"  Words: {word_count}")

        # Generate narrative
        narrative = generate_narrative(client, transcript_text, file_path, word_count or 0)

        if narrative:
            family_members, other_people = update_narrative(conn, tid, narrative)
            processed += 1
            total_cost += 0.003  # Rough estimate
            log(f"  ✅ Generated ({len(narrative)} chars)")

            # Show family members identified
            if family_members:
                log(f"  👨‍👩‍👧‍👦 Family: {family_members[:100]}{'...' if len(family_members) > 100 else ''}")
            if other_people:
                log(f"  👥 Others: {other_people[:80]}{'...' if len(other_people) > 80 else ''}")
        else:
            failed += 1
            log(f"  ❌ Failed to generate narrative")

        # Rate limiting
        time.sleep(RATE_LIMIT_DELAY)

    # Summary
    log(f"\n{'=' * 60}")
    log("COMPLETE")
    log(f"Processed: {processed}")
    log(f"Failed: {failed}")
    log(f"Est. cost: ${total_cost:.2f}")
    log("=" * 60)

    conn.close()

def search_transcripts(query, limit=10):
    """Search transcripts and narratives using full-text search."""
    conn = sqlite3.connect(TRANSCRIPT_DATABASE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            t.id,
            t.audio_file_path,
            t.word_count,
            t.narrative,
            snippet(transcripts_fts, 1, '<mark>', '</mark>', '...', 32) as transcript_match,
            snippet(transcripts_fts, 2, '<mark>', '</mark>', '...', 32) as narrative_match,
            bm25(transcripts_fts) as rank
        FROM transcripts_fts
        JOIN transcripts t ON transcripts_fts.rowid = t.id
        WHERE transcripts_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """, (query, limit))

    results = cursor.fetchall()
    conn.close()
    return results

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        # Search mode: python3 generate_narratives.py search "query"
        if len(sys.argv) < 3:
            print("Usage: python3 generate_narratives.py search 'your query'")
            sys.exit(1)

        query = sys.argv[2]
        results = search_transcripts(query)

        print(f"\nSearch results for: '{query}'\n")
        print("=" * 60)

        for r in results:
            tid, path, words, narrative, t_match, n_match, rank = r
            filename = Path(path).name
            print(f"\n📄 {filename} ({words} words)")
            print(f"   Path: {path}")
            if t_match:
                print(f"   Transcript: {t_match}")
            if n_match:
                print(f"   Narrative: {n_match}")
            print()
    else:
        main()
