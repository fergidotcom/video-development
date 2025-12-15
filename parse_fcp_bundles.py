#!/usr/bin/env python3
"""
Parse Final Cut Pro bundles to extract timeline information.

FCP bundles (.fcpbundle) contain SQLite databases with binary plist data.
This script extracts available metadata without requiring FCPXML export.
"""

import sqlite3
import os
import json
import sys
from pathlib import Path
from datetime import datetime
import plistlib
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FCPBundleParser:
    """Parser for Final Cut Pro bundle files."""

    def __init__(self, db_path):
        """Initialize parser with database path."""
        self.db_path = db_path
        self.survey_db = None

    def connect_db(self):
        """Connect to the survey database."""
        self.survey_db = sqlite3.connect(self.db_path)
        self.survey_db.row_factory = sqlite3.Row

    def close_db(self):
        """Close database connection."""
        if self.survey_db:
            self.survey_db.close()

    def get_unparsed_bundles(self):
        """Get list of FCP bundles that haven't been parsed yet."""
        cursor = self.survey_db.cursor()
        cursor.execute("""
            SELECT fcp_id, bundle_path, project_name
            FROM fcp_projects
            WHERE parsed_at IS NULL AND still_exists = 1
            ORDER BY bundle_path
        """)
        return cursor.fetchall()

    def find_fcpevent_files(self, bundle_path):
        """Find all .fcpevent files in a bundle."""
        fcpevent_files = []
        try:
            for root, dirs, files in os.walk(bundle_path):
                # Look for CurrentVersion.fcpevent files
                if 'CurrentVersion.fcpevent' in files:
                    fcpevent_path = os.path.join(root, 'CurrentVersion.fcpevent')
                    # Skip if it's directly in the bundle root (library file)
                    if os.path.dirname(fcpevent_path) != bundle_path:
                        fcpevent_files.append(fcpevent_path)
        except Exception as e:
            logger.error(f"Error walking bundle {bundle_path}: {e}")
        return fcpevent_files

    def parse_fcpevent_db(self, fcpevent_path):
        """Parse an fcpevent SQLite database."""
        try:
            conn = sqlite3.connect(fcpevent_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get project information
            project_info = {}

            # Try to find project name and type
            cursor.execute("""
                SELECT ZNAME, ZTYPE, ZIDENTIFIER
                FROM ZCOLLECTION
                WHERE ZTYPE IN ('FFMediaEventProject', 'FFMediaEventFolder')
                LIMIT 10
            """)
            collections = cursor.fetchall()

            # Get project name from collections
            for col in collections:
                if col['ZNAME']:
                    project_info['project_name'] = col['ZNAME']
                    break

            # Count clips (FFAnchoredClip types)
            cursor.execute("""
                SELECT COUNT(*) as clip_count
                FROM ZCOLLECTION
                WHERE ZTYPE = 'FFAnchoredClip'
            """)
            clip_result = cursor.fetchone()
            project_info['clip_count'] = clip_result['clip_count'] if clip_result else 0

            # Count sequences (FFAnchoredSequence types)
            cursor.execute("""
                SELECT COUNT(*) as sequence_count
                FROM ZCOLLECTION
                WHERE ZTYPE = 'FFAnchoredSequence'
            """)
            seq_result = cursor.fetchone()
            project_info['sequence_count'] = seq_result['sequence_count'] if seq_result else 0

            # Count assets (FFAsset types)
            cursor.execute("""
                SELECT COUNT(*) as asset_count
                FROM ZCOLLECTION
                WHERE ZTYPE = 'FFAsset'
            """)
            asset_result = cursor.fetchone()
            project_info['asset_count'] = asset_result['asset_count'] if asset_result else 0

            # Count markers (FFAnchoredKeywordMarker types)
            cursor.execute("""
                SELECT COUNT(*) as marker_count
                FROM ZCOLLECTION
                WHERE ZTYPE = 'FFAnchoredKeywordMarker'
            """)
            marker_result = cursor.fetchone()
            project_info['marker_count'] = marker_result['marker_count'] if marker_result else 0

            # Try to extract timeline data from binary plists
            # This is complex - for now we'll store counts
            cursor.execute("""
                SELECT ZTYPE, COUNT(*) as count
                FROM ZCOLLECTION
                GROUP BY ZTYPE
                ORDER BY count DESC
                LIMIT 20
            """)
            type_counts = cursor.fetchall()
            project_info['collection_types'] = {
                row['ZTYPE']: row['count']
                for row in type_counts if row['ZTYPE']
            }

            conn.close()
            return project_info

        except Exception as e:
            logger.error(f"Error parsing fcpevent {fcpevent_path}: {e}")
            return None

    def parse_bundle(self, bundle_path):
        """Parse a complete FCP bundle."""
        logger.info(f"Parsing bundle: {bundle_path}")

        if not os.path.exists(bundle_path):
            logger.warning(f"Bundle not found: {bundle_path}")
            return None

        # Find all fcpevent files
        fcpevent_files = self.find_fcpevent_files(bundle_path)

        if not fcpevent_files:
            logger.warning(f"No fcpevent files found in {bundle_path}")
            return None

        logger.info(f"Found {len(fcpevent_files)} fcpevent file(s)")

        # Parse each fcpevent file and aggregate data
        all_projects = []
        total_clips = 0
        total_sequences = 0
        total_assets = 0
        total_markers = 0

        for fcpevent_path in fcpevent_files:
            project_info = self.parse_fcpevent_db(fcpevent_path)
            if project_info:
                all_projects.append({
                    'fcpevent_path': fcpevent_path,
                    'data': project_info
                })
                total_clips += project_info.get('clip_count', 0)
                total_sequences += project_info.get('sequence_count', 0)
                total_assets += project_info.get('asset_count', 0)
                total_markers += project_info.get('marker_count', 0)

        if not all_projects:
            return None

        # Build narrative structure
        narrative_structure = {
            'fcpevent_files': len(fcpevent_files),
            'projects': all_projects,
            'totals': {
                'clips': total_clips,
                'sequences': total_sequences,
                'assets': total_assets,
                'markers': total_markers
            }
        }

        # Extract project name (use first non-empty name found)
        project_name = None
        for proj in all_projects:
            if proj['data'].get('project_name'):
                project_name = proj['data']['project_name']
                break

        if not project_name:
            # Use bundle name as fallback
            project_name = Path(bundle_path).stem.replace('.fcpbundle', '')

        return {
            'project_name': project_name,
            'clip_count': total_clips,
            'timeline_duration': None,  # Cannot determine without FCPXML
            'narrative_structure': narrative_structure
        }

    def update_database(self, fcp_id, parsed_data):
        """Update the database with parsed data."""
        cursor = self.survey_db.cursor()

        if parsed_data:
            cursor.execute("""
                UPDATE fcp_projects
                SET project_name = ?,
                    clip_count = ?,
                    timeline_duration = ?,
                    narrative_structure = ?,
                    parsed_at = ?
                WHERE fcp_id = ?
            """, (
                parsed_data['project_name'],
                parsed_data['clip_count'],
                parsed_data['timeline_duration'],
                json.dumps(parsed_data['narrative_structure'], indent=2),
                datetime.now().isoformat(),
                fcp_id
            ))
        else:
            # Mark as attempted but failed
            cursor.execute("""
                UPDATE fcp_projects
                SET parsed_at = ?
                WHERE fcp_id = ?
            """, (
                datetime.now().isoformat(),
                fcp_id
            ))

        self.survey_db.commit()

    def parse_all_bundles(self, limit=None):
        """Parse all unparsed bundles."""
        bundles = self.get_unparsed_bundles()

        if limit:
            bundles = bundles[:limit]

        total = len(bundles)
        logger.info(f"Found {total} unparsed bundle(s)")

        success_count = 0
        fail_count = 0

        for idx, bundle in enumerate(bundles, 1):
            fcp_id = bundle['fcp_id']
            bundle_path = bundle['bundle_path']

            logger.info(f"[{idx}/{total}] Processing: {bundle_path}")

            try:
                parsed_data = self.parse_bundle(bundle_path)
                self.update_database(fcp_id, parsed_data)

                if parsed_data:
                    success_count += 1
                    logger.info(f"✓ Success: {parsed_data['project_name']} "
                               f"({parsed_data['clip_count']} clips)")
                else:
                    fail_count += 1
                    logger.warning(f"✗ Failed to parse bundle")

            except Exception as e:
                fail_count += 1
                logger.error(f"✗ Error: {e}")
                # Still update database to mark as attempted
                self.update_database(fcp_id, None)

        logger.info(f"\n{'='*60}")
        logger.info(f"Parsing complete!")
        logger.info(f"Success: {success_count}")
        logger.info(f"Failed: {fail_count}")
        logger.info(f"Total: {total}")
        logger.info(f"{'='*60}")


def main():
    """Main entry point."""
    db_path = "/Users/joeferguson/Library/CloudStorage/Dropbox/Fergi/VideoDev/pegasus-survey.db"

    if not os.path.exists(db_path):
        logger.error(f"Database not found: {db_path}")
        sys.exit(1)

    parser = FCPBundleParser(db_path)

    try:
        parser.connect_db()

        # Parse with optional limit for testing
        limit = None
        if len(sys.argv) > 1:
            try:
                limit = int(sys.argv[1])
                logger.info(f"Limiting to first {limit} bundle(s) for testing")
            except ValueError:
                logger.warning(f"Invalid limit '{sys.argv[1]}', parsing all bundles")

        parser.parse_all_bundles(limit=limit)

    finally:
        parser.close_db()


if __name__ == '__main__':
    main()
