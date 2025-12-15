#!/usr/bin/env python3
"""
Narrative Intelligence Extraction Script
Analyzes directory structure, FCP bundles, and composites for narrative meaning.
"""

import os
import sys
import sqlite3
import json
import re
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import subprocess

# Configuration
DB_PATH = "pegasus-survey.db"
PEGASUS_ROOT = "/Volumes/Promise Pegasus"

# In-scope collections
IN_SCOPE_COLLECTIONS = {
    'walkabout_india': {
        'root': '/Volumes/Promise Pegasus/Walkabout2018',
        'patterns': ['Walkabout', 'India', '180'],
        'description': 'India trip footage and finished composite'
    },
    'vinny_movie': {
        'root': '/Volumes/Promise Pegasus/MyMovieWithVinny',
        'patterns': ['Vinny', 'Glenn', 'Steve', 'Jeff', 'Lew'],
        'description': 'Documentary movie project with interviews'
    },
    'peirce_gang': {
        'root': '/Volumes/Promise Pegasus/PeirceGang',
        'patterns': ['Peirce', 'Pierce', 'Philosophy'],
        'description': 'Charles Peirce philosophy discussion recordings'
    },
    'pema_mindrolling': {
        'root': '/Volumes/Promise Pegasus/Pema',
        'patterns': ['Pema', 'Mindrolling', 'Monastery'],
        'description': 'Monastery footage'
    },
    'jeffrey_pop': {
        'root': '/Volumes/Promise Pegasus/190205JeffreyAndPop',
        'patterns': ['Jeffrey', 'Pop', 'Jeff'],
        'description': 'Jeffrey and Pop life story interviews'
    }
}

# Excluded directories
EXCLUDED_DIRS = ['CKandLAFergusonFamilyArchive', '2012 Laguna FergiDotCom Archive']

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    sys.stdout.flush()

def parse_date_from_name(name):
    """Extract date from folder name (YYMMDD format)."""
    match = re.match(r'^(\d{6})', name)
    if match:
        date_str = match.group(1)
        try:
            year = int('20' + date_str[:2])
            month = int(date_str[2:4])
            day = int(date_str[4:6])
            return f"{year}-{month:02d}-{day:02d}"
        except:
            pass
    return None

def extract_semantic_from_name(name):
    """Extract semantic meaning from folder name."""
    # Remove date prefix if present
    clean_name = re.sub(r'^\d{6}', '', name)

    # Split camelCase
    words = re.findall(r'[A-Z][a-z]+|[a-z]+|[A-Z]+(?![a-z])', clean_name)

    # Identify patterns
    semantic = {
        'title': clean_name,
        'words': words,
        'is_scene': any(w.lower() in ['scene', 'take', 'shot'] for w in words),
        'is_broll': 'broll' in clean_name.lower() or 'b-roll' in clean_name.lower(),
        'is_interview': any(w.lower() in ['interview', 'chat', 'talk', 'discussion'] for w in words),
        'is_export': any(w.lower() in ['export', 'final', 'master', 'composite'] for w in words),
        'has_person': any(w.istitle() and len(w) > 2 and w.lower() not in ['the', 'and', 'with', 'from', 'for'] for w in words),
        'location_hints': [w for w in words if w.lower() in ['india', 'kerala', 'munnar', 'benares', 'haridwar', 'pondicherry', 'santa', 'barbara', 'budapest', 'hungary']]
    }
    return semantic

def analyze_collection(collection_key, collection_info):
    """Analyze a single collection for narrative structure."""
    root = collection_info['root']
    if not os.path.exists(root):
        return None

    log(f"Analyzing collection: {collection_key}")

    analysis = {
        'name': collection_key,
        'description': collection_info['description'],
        'root': root,
        'date_range': {'earliest': None, 'latest': None},
        'folder_count': 0,
        'sessions': [],
        'fcp_bundles': [],
        'composites': [],
        'persons_mentioned': set(),
        'locations_mentioned': set(),
        'narrative_phases': []
    }

    # Walk top-level folders
    for item in sorted(os.listdir(root)):
        item_path = os.path.join(root, item)
        if not os.path.isdir(item_path) or item.startswith('.'):
            continue

        analysis['folder_count'] += 1

        # Parse date
        date = parse_date_from_name(item)
        if date:
            if not analysis['date_range']['earliest'] or date < analysis['date_range']['earliest']:
                analysis['date_range']['earliest'] = date
            if not analysis['date_range']['latest'] or date > analysis['date_range']['latest']:
                analysis['date_range']['latest'] = date

        # Extract semantics
        semantic = extract_semantic_from_name(item)

        session = {
            'folder': item,
            'date': date,
            'semantic': semantic
        }

        # Look for FCP bundles in this folder
        for root_dir, dirs, files in os.walk(item_path):
            for d in dirs:
                if d.endswith('.fcpbundle') or d.endswith('.fcpproject'):
                    analysis['fcp_bundles'].append(os.path.join(root_dir, d))
            for f in files:
                if f.endswith('.m4v') or (f.endswith('.mov') and 'composite' in f.lower()):
                    analysis['composites'].append(os.path.join(root_dir, f))

        # Collect persons and locations
        if semantic.get('has_person'):
            for word in semantic['words']:
                if word.istitle() and len(word) > 2:
                    analysis['persons_mentioned'].add(word)

        for loc in semantic.get('location_hints', []):
            analysis['locations_mentioned'].add(loc)

        analysis['sessions'].append(session)

    # Convert sets to lists for JSON
    analysis['persons_mentioned'] = sorted(list(analysis['persons_mentioned']))
    analysis['locations_mentioned'] = sorted(list(analysis['locations_mentioned']))

    return analysis

def find_all_fcp_bundles():
    """Find all FCP bundles on Pegasus."""
    log("Finding all FCP bundles...")
    bundles = []

    for root, dirs, files in os.walk(PEGASUS_ROOT):
        # Skip excluded
        if any(ex in root for ex in EXCLUDED_DIRS):
            continue

        for d in list(dirs):
            if d.endswith('.fcpbundle') or d.endswith('.fcpproject'):
                bundle_path = os.path.join(root, d)
                bundles.append({
                    'path': bundle_path,
                    'name': d,
                    'parent': os.path.dirname(bundle_path),
                    'size': get_dir_size(bundle_path)
                })

    log(f"Found {len(bundles)} FCP bundles")
    return bundles

def get_dir_size(path):
    """Get total size of directory."""
    total = 0
    try:
        for root, dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except:
                    pass
    except:
        pass
    return total

def find_all_composites():
    """Find all finished composite videos."""
    log("Finding finished composites...")
    composites = []

    # Look for .m4v files and specific patterns
    for root, dirs, files in os.walk(PEGASUS_ROOT):
        if any(ex in root for ex in EXCLUDED_DIRS):
            continue

        for f in files:
            file_path = os.path.join(root, f)
            is_composite = False

            # M4V files are often exports
            if f.endswith('.m4v'):
                is_composite = True

            # MOV files with composite indicators
            elif f.endswith('.mov'):
                lower = f.lower()
                if any(kw in lower for kw in ['composite', 'final', 'master', 'export']):
                    is_composite = True

            if is_composite:
                try:
                    size = os.path.getsize(file_path)
                    composites.append({
                        'path': file_path,
                        'name': f,
                        'directory': root,
                        'size': size,
                        'size_mb': round(size / (1024*1024), 1)
                    })
                except:
                    pass

    log(f"Found {len(composites)} composite/exported videos")
    return composites

def save_to_database(conn, collections, fcp_bundles, composites):
    """Save analysis results to database."""
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    # Save projects
    for key, analysis in collections.items():
        if analysis:
            cursor.execute("""
                INSERT OR REPLACE INTO projects_narrative (
                    project_name, project_type, narrative_summary,
                    has_fcp_project, has_finished_composite, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                key,
                'video_collection',
                json.dumps(analysis, default=str),
                len(analysis['fcp_bundles']) > 0,
                len(analysis['composites']) > 0,
                now
            ))

    # Save FCP bundles
    for bundle in fcp_bundles:
        cursor.execute("""
            INSERT OR REPLACE INTO fcp_projects (
                bundle_path, project_name, still_exists, created_at
            ) VALUES (?, ?, 1, ?)
        """, (bundle['path'], bundle['name'], now))

    # Save composites
    for comp in composites:
        cursor.execute("""
            INSERT OR REPLACE INTO composites (
                file_path, duration, transcription_status, created_at
            ) VALUES (?, NULL, 'pending', ?)
        """, (comp['path'], now))

    conn.commit()
    log("Saved analysis to database")

def generate_narrative_report(collections, fcp_bundles, composites):
    """Generate comprehensive narrative analysis report."""
    report = f"""# Pegasus Archive Narrative Analysis

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Executive Summary

The Pegasus archive contains **{sum(1 for c in collections.values() if c)}** major narrative collections
with **{len(fcp_bundles)}** Final Cut Pro project bundles and **{len(composites)}** finished/exported videos.

---

## Collection Summaries

"""

    for key, analysis in collections.items():
        if not analysis:
            continue

        report += f"""### {analysis['name'].replace('_', ' ').title()}

**Description:** {analysis['description']}

**Root:** `{analysis['root']}`

**Date Range:** {analysis['date_range']['earliest'] or 'Unknown'} to {analysis['date_range']['latest'] or 'Unknown'}

**Statistics:**
- Sessions/Folders: {analysis['folder_count']}
- FCP Projects: {len(analysis['fcp_bundles'])}
- Finished Composites: {len(analysis['composites'])}

**Key People Mentioned:** {', '.join(analysis['persons_mentioned'][:10]) if analysis['persons_mentioned'] else 'None identified'}

**Locations Mentioned:** {', '.join(analysis['locations_mentioned']) if analysis['locations_mentioned'] else 'None identified'}

---

"""

    report += f"""## FCP Project Bundles ({len(fcp_bundles)} total)

These Final Cut Pro projects contain editorial decisions, timeline structures, and narrative organization.

| Project Name | Location | Size |
|-------------|----------|------|
"""

    for bundle in sorted(fcp_bundles, key=lambda x: x['name'])[:30]:
        size_mb = round(bundle['size'] / (1024*1024), 1)
        report += f"| {bundle['name']} | {bundle['parent'].replace(PEGASUS_ROOT+'/', '')} | {size_mb} MB |\n"

    if len(fcp_bundles) > 30:
        report += f"\n... and {len(fcp_bundles) - 30} more\n"

    report += f"""

## Finished Composites ({len(composites)} total)

These are exported/finished videos ready for viewing or transcription.

**HIGH VALUE for transcription** - these represent completed editorial work.

| File | Directory | Size |
|------|-----------|------|
"""

    for comp in sorted(composites, key=lambda x: x['size'], reverse=True)[:30]:
        report += f"| {comp['name']} | {comp['directory'].replace(PEGASUS_ROOT+'/', '')} | {comp['size_mb']} MB |\n"

    if len(composites) > 30:
        report += f"\n... and {len(composites) - 30} more\n"

    report += """

## Narrative Structure Patterns

### Folder Naming Conventions
- **Date Prefix (YYMMDD):** Most folders use YYMMDD format (e.g., 180302 = March 2, 2018)
- **Event Description:** CamelCase descriptions follow dates
- **Special Indicators:**
  - "BRoll" / "B-Roll" - Supplementary footage
  - "Take" / "Scene" - Multiple versions
  - "Final" / "Export" / "Composite" - Finished work

### Project Organization Patterns
- **Walkabout 2018:** Chronological India trip documentation with location-based organization
- **My Movie With Vinny:** Session-based interview recordings with participant names
- **Peirce Gang:** Topic-based philosophy discussions with date prefixes

## Recommendations for Transcription Priority

1. **Highest Priority - Finished Composites:**
   - These represent completed editorial work
   - Already condensed to key content
   - Estimated: 50-100 files

2. **High Priority - Interview Sessions:**
   - Folders with people names
   - PeirceGang discussion recordings
   - Vinny project interviews

3. **Medium Priority - Raw Footage:**
   - Daily recordings
   - B-Roll (for content indexing only)

## Next Steps

1. Review this report and identify specific composites for transcription
2. Parse FCP bundles for timeline structure (Phase 2 complete)
3. Begin Whisper transcription pipeline on approved composites
"""

    with open("narrative_analysis_report.md", "w") as f:
        f.write(report)

    log("Report saved to narrative_analysis_report.md")

def generate_transcription_priority_list(composites):
    """Generate prioritized list for transcription."""
    # Sort by likely importance
    prioritized = []

    for comp in composites:
        priority = 3  # Default medium

        path_lower = comp['path'].lower()

        # High priority indicators
        if any(kw in path_lower for kw in ['final', 'master', 'composite', 'export']):
            priority = 1
        elif 'life story' in path_lower or 'interview' in path_lower:
            priority = 1
        elif comp['name'].endswith('.m4v'):
            priority = 2

        prioritized.append({**comp, 'priority': priority})

    # Sort by priority, then size
    prioritized.sort(key=lambda x: (x['priority'], -x['size']))

    with open("finished_composites_for_transcription.txt", "w") as f:
        f.write("# Finished Composites for Transcription\n")
        f.write(f"# Generated: {datetime.now().isoformat()}\n")
        f.write(f"# Total: {len(prioritized)} files\n")
        f.write("#\n")
        f.write("# Priority Levels:\n")
        f.write("#   1 = High (Final/Master composites, Life stories)\n")
        f.write("#   2 = Medium (M4V exports)\n")
        f.write("#   3 = Lower (Other exports)\n")
        f.write("#" + "="*80 + "\n\n")

        current_priority = 0
        for comp in prioritized:
            if comp['priority'] != current_priority:
                current_priority = comp['priority']
                f.write(f"\n## PRIORITY {current_priority}\n\n")

            f.write(f"{comp['path']}\n")
            f.write(f"  Size: {comp['size_mb']} MB\n")
            f.write(f"  Directory: {comp['directory'].replace(PEGASUS_ROOT+'/', '')}\n\n")

    log(f"Saved {len(prioritized)} composites to finished_composites_for_transcription.txt")

def main():
    log("="*60)
    log("Narrative Intelligence Extraction")
    log("="*60)

    # Check Pegasus
    if not os.path.exists(PEGASUS_ROOT):
        log(f"ERROR: Pegasus not mounted at {PEGASUS_ROOT}")
        sys.exit(1)

    # Connect to database
    conn = sqlite3.connect(DB_PATH)

    try:
        # Analyze each collection
        collections = {}
        for key, info in IN_SCOPE_COLLECTIONS.items():
            collections[key] = analyze_collection(key, info)

        # Find all FCP bundles
        fcp_bundles = find_all_fcp_bundles()

        # Find all composites
        composites = find_all_composites()

        # Save to database
        save_to_database(conn, collections, fcp_bundles, composites)

        # Generate reports
        generate_narrative_report(collections, fcp_bundles, composites)
        generate_transcription_priority_list(composites)

        log("="*60)
        log("Narrative analysis complete!")
        log("="*60)

    finally:
        conn.close()

if __name__ == "__main__":
    main()
