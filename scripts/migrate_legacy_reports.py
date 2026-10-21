"""
Legacy report migration script.

WHAT THIS DOES
──────────────
Copies (does NOT move or delete) existing legacy reports from the flat
output/ directory into a user-owned directory (output/{user_id}/),
assigning new UUID report IDs and adding the housekeeping fields that
multi-user API endpoints require.

WHEN TO USE
───────────
Run this AFTER you have confirmed your Supabase user ID and ONLY after
reviewing the dry-run output. The originals in output/ are never modified.

SAFETY GUARANTEES
─────────────────
  --dry-run: print what would happen, make no changes (default)
  Never overwrites an existing file in the destination
  Never deletes, moves, or modifies legacy source files
  Validates the user_id as a UUID before writing anything
  Validates each legacy report against the Pydantic schema before copying
  Requires explicit --confirm flag to make any writes

HOW TO FIND YOUR USER ID
─────────────────────────
  1. Sign in to the application in the browser.
  2. Open your browser's developer tools (F12) → Application → Local Storage.
  3. Find the Supabase session: look for a key like "sb-xxxx-auth-token".
  4. The `user.id` field is your UUID (e.g. "a0b1c2d3-...").
  Alternatively, the Settings page in the app will display it once Stage 4
  connects the frontend.

USAGE
─────
  # Preview (no changes made):
  python scripts/migrate_legacy_reports.py --user-id <your-uuid>

  # Actually migrate:
  python scripts/migrate_legacy_reports.py --user-id <your-uuid> --confirm

EXAMPLE
───────
  python scripts/migrate_legacy_reports.py \\
      --user-id a0b1c2d3-e4f5-6789-abcd-ef0123456789 \\
      --confirm
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ── Allow running from project root without installing the package ───────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pydantic import ValidationError

from app.schemas import VisionExtractionReport
from config.settings import REPORTS_BASE_DIR

# Sentinel keys added by the migration
_REPORT_ID_KEY = "_report_id"
_CREATED_AT_KEY = "_created_at"
_FILENAME_KEY = "_image_filename"
_INDEX_FLAG_KEY = "_indexed"

# The legacy reports live at the root of REPORTS_BASE_DIR (flat structure).
# This migration copies them into REPORTS_BASE_DIR/{user_id}/.
LEGACY_DIR = REPORTS_BASE_DIR  # i.e. output/


def _validate_user_id(user_id: str) -> None:
    try:
        uuid.UUID(user_id)
    except ValueError:
        print(f"ERROR: '{user_id}' is not a valid UUID.", file=sys.stderr)
        sys.exit(1)


def _find_legacy_reports() -> list[Path]:
    """Find flat JSON files in the legacy output/ directory."""
    return sorted(
        p for p in LEGACY_DIR.glob("*.json")
        if p.is_file() and not p.name.endswith(".tmp")
    )


def _migrate(user_id: str, *, dry_run: bool) -> None:
    dest_dir = REPORTS_BASE_DIR / user_id
    legacy_reports = _find_legacy_reports()

    if not legacy_reports:
        print("No legacy reports found in:", LEGACY_DIR)
        return

    print(f"Found {len(legacy_reports)} legacy report(s) in {LEGACY_DIR}")
    print(f"Destination directory: {dest_dir}")
    print(f"Mode: {'DRY RUN (no changes)' if dry_run else 'LIVE WRITE'}")
    print("-" * 60)

    migrated = 0
    skipped = 0
    failed = 0

    for legacy_path in legacy_reports:
        print(f"\nSource: {legacy_path.name}")

        # Read and validate
        try:
            raw = json.loads(legacy_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  SKIP — cannot read: {exc}")
            skipped += 1
            continue

        # Skip if already migrated (has _report_id)
        if _REPORT_ID_KEY in raw:
            print("  SKIP — already has _report_id (already migrated)")
            skipped += 1
            continue

        # Validate against domain schema
        try:
            VisionExtractionReport.model_validate(raw)
        except ValidationError as exc:
            print(f"  SKIP — schema validation failed: {exc}")
            skipped += 1
            continue

        # Build the new payload
        new_report_id = str(uuid.uuid4())
        original_stem = legacy_path.stem  # e.g. "github1_report" or "spiderman profile_report"
        # Strip the _report suffix if present for a cleaner display filename
        display_name = (
            original_stem.removesuffix("_report")
            if original_stem.endswith("_report")
            else original_stem
        )
        display_name = display_name + ".jpg"  # best guess; adjust manually if needed

        new_payload = dict(raw)
        new_payload[_REPORT_ID_KEY] = new_report_id
        new_payload[_CREATED_AT_KEY] = datetime.now(timezone.utc).isoformat()
        new_payload[_FILENAME_KEY] = display_name
        new_payload[_INDEX_FLAG_KEY] = False

        dest_path = dest_dir / f"{new_report_id}.json"

        print(f"  Would create: {dest_path.relative_to(PROJECT_ROOT)}")
        print(f"  New report_id: {new_report_id}")
        print(f"  Display filename: {display_name}")

        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)
            if dest_path.exists():
                print("  SKIP — destination file already exists (unexpected UUID collision)")
                skipped += 1
                continue
            dest_path.write_text(
                json.dumps(new_payload, indent=2), encoding="utf-8"
            )
            print("  WRITTEN ✓")

        migrated += 1

    print("\n" + "=" * 60)
    print(f"{'Would migrate' if dry_run else 'Migrated'}: {migrated}")
    print(f"Skipped:   {skipped}")
    print(f"Failed:    {failed}")
    if dry_run and migrated > 0:
        print("\nThis was a DRY RUN. Add --confirm to apply changes.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--user-id",
        required=True,
        help="Your Supabase user UUID (find it in the app settings or browser session).",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Apply changes. Without this flag, only a dry run is performed.",
    )
    args = parser.parse_args()

    _validate_user_id(args.user_id)
    _migrate(args.user_id, dry_run=not args.confirm)


if __name__ == "__main__":
    main()
