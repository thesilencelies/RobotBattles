#!/usr/bin/env python3
"""Publish Print and Play PDFs to Google Drive in the RobotBattles folder.

Publishes:
1. build/robot_battles_pnp_a4.pdf (10 pages A4 Landscape: cards & templates)
2. build/robot_battles_pnp_a3.pdf (8 pages A3 Landscape: chassis & automata mats)

Updates existing files in-place on Google Drive, preserving file IDs and links.
Only uploads when the file content has changed (tracks SHA-256 in build/pnp_upload_state.json).
Pass --force to override.

Usage:
    python upload_pnp.py [--force] [--dry-run] [--quiet] [--a4-only] [--a3-only]
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

# Add repo root to sys.path so we can import upload_rules
REPO_ROOT = Path(__file__).resolve().parent
if REPO_ROOT.name == "scripts":
    REPO_ROOT = REPO_ROOT.parent
sys.path.insert(0, str(REPO_ROOT))

import upload_rules

DEFAULT_FOLDER_NAME = "RobotBattles"
DEFAULT_FOLDER_ID = "1UbLJPzBeNXedYH72vMz6xlBN641UtlGY"
STATE_PATH = REPO_ROOT / "build" / "pnp_upload_state.json"


def read_pnp_state() -> dict:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"folder_name": DEFAULT_FOLDER_NAME, "folder_id": DEFAULT_FOLDER_ID, "files": {}}


def write_pnp_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Upload Print and Play PDFs to Google Drive in the RobotBattles folder."
    )
    parser.add_argument(
        "--force", action="store_true", help="Upload even if the PDF hash is unchanged"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would happen without uploading"
    )
    parser.add_argument("--quiet", action="store_true", help="Only report problems")
    parser.add_argument("--a4-only", action="store_true", help="Upload only the A4 package")
    parser.add_argument("--a3-only", action="store_true", help="Upload only the A3 package")
    parser.add_argument(
        "--folder", default=DEFAULT_FOLDER_NAME, help=f"Google Drive folder name (default: {DEFAULT_FOLDER_NAME})"
    )
    parser.add_argument(
        "--folder-id", default=None, help=f"Explicit Google Drive folder ID override (default: {DEFAULT_FOLDER_ID})"
    )
    args = parser.parse_args()

    # Determine files to process
    targets = []
    if not args.a3_only:
        targets.append(REPO_ROOT / "build" / "robot_battles_pnp_a4.pdf")
    if not args.a4_only:
        targets.append(REPO_ROOT / "build" / "robot_battles_pnp_a3.pdf")

    # Verify files exist
    for target in targets:
        if not target.is_file():
            sys.exit(
                f"Error: Missing {target}.\n"
                "Run 'python scripts/generate_print_and_play.py' first."
            )

    state = read_pnp_state()
    files_state = state.setdefault("files", {})

    items_to_upload = []
    for target in targets:
        size = target.stat().st_size
        digest = upload_rules.sha256(target)
        file_info = files_state.get(target.name, {})
        unchanged = (file_info.get("sha256") == digest)

        if not args.quiet:
            print(f"{target.name:27s}  {size / (1024 * 1024):.2f} MB  sha256 {digest[:12]}…")

        if unchanged and not args.force:
            if not args.quiet:
                print(f"  -> unchanged since last upload (skipping; pass --force to re-upload)")
                if file_info.get("web_view_link"):
                    print(f"     Link: {file_info['web_view_link']}")
        else:
            items_to_upload.append((target, digest, size, file_info))

    if not items_to_upload:
        if not args.quiet:
            folder_id = args.folder_id or state.get("folder_id") or DEFAULT_FOLDER_ID
            print(f"\nAll files are up to date in Google Drive '{args.folder}' folder.")
            print(f"Folder link: https://drive.google.com/drive/folders/{folder_id}")
        return 0

    if args.dry_run:
        folder_desc = f"folder ID {args.folder_id or state.get('folder_id') or DEFAULT_FOLDER_ID}"
        print(f"\n[dry run] Would upload {len(items_to_upload)} file(s) to Google Drive {folder_desc}:")
        for target, digest, size, file_info in items_to_upload:
            prev_id = file_info.get("file_id")
            action = f"update in-place (ID: {prev_id})" if prev_id else "upload as new file"
            print(f"  - {target.name}: {action}")
        return 0

    # Authenticate with Google Drive
    creds_path, token_path = upload_rules.find_credentials()
    if creds_path is None:
        print(upload_rules.SETUP, file=sys.stderr)
        return 2

    creds = upload_rules.build_credentials(creds_path, token_path, args.quiet)
    service = upload_rules.get_drive_service(creds)

    folder_id = args.folder_id or state.get("folder_id")
    if not folder_id:
        if not args.quiet:
            print(f"Locating '{args.folder}' folder on Google Drive…")
        folder_id = upload_rules.find_or_create_folder(service, args.folder)

    folder_link = f"https://drive.google.com/drive/folders/{folder_id}"
    state["folder_name"] = args.folder
    state["folder_id"] = folder_id
    state["folder_link"] = folder_link

    # Upload each pending item
    for target, digest, size, file_info in items_to_upload:
        cached_id = file_info.get("file_id")
        existing_file = upload_rules.resolve_remote_file(
            service, folder_id, target.name, cached_file_id=cached_id
        )

        if existing_file:
            file_id = existing_file["id"]
            if not args.quiet:
                print(f"Updating '{target.name}' in-place on Drive (ID: {file_id})…")
        else:
            file_id = None
            if not args.quiet:
                print(f"Uploading new file '{target.name}' to Drive folder '{args.folder}'…")

        response = upload_rules.upload(service, target, folder_id, file_id=file_id, quiet=args.quiet)
        res_id = response.get("id")
        web_link = response.get("webViewLink") or f"https://drive.google.com/file/d/{res_id}/view"

        files_state[target.name] = {
            "file_id": res_id,
            "sha256": digest,
            "size": size,
            "web_view_link": web_link,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        if not args.quiet:
            print(f"  ✔ Complete: {web_link}")

    write_pnp_state(state)

    if not args.quiet:
        print("\n" + "=" * 80)
        print(f"✔ All Print and Play PDFs successfully uploaded to Google Drive '{args.folder}'")
        print(f"Folder link: {folder_link}")
        print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
