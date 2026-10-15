#!/usr/bin/env python3
"""Publish rules PDF to Google Drive in the RobotBattles folder, updating in place.

The rules PDF is a build artifact that is ignored by git. It is published to
Google Drive instead.

The upload updates an existing Drive file in-place if one already exists in the
folder (or if previously uploaded), preserving revision history and keeping any
existing shared view links valid. If the file is not yet in the folder, it is created.

Nothing is uploaded when the PDF is byte-identical to the last one published
(the hash is remembered in build/), so wiring this into a rebuild is cheap --
only a genuinely changed PDF costs the transfer. Pass --force to override.

Credentials -- First match wins:
  1. $RULES_DRIVE_CREDENTIALS, if set
  2. ~/.config/combatrobotics/drive_service_account.json   (service account)
  3. ~/.config/combatrobotics/client_secret.json           (OAuth desktop app)
  4. ~/.config/mobilesuit/drive_service_account.json       (shared service account)
  5. ~/.config/mobilesuit/client_secret.json               (shared OAuth desktop app)

Tokens:
  Reuses ~/.config/combatrobotics/drive_token.json or ~/.config/mobilesuit/drive_token.json.

Run: python upload_rules.py [--force] [--dry-run] [--quiet] [--pdf PATH] [--folder NAME] [--folder-id ID]
"""

import argparse
import datetime
import hashlib
import json
import os
import sys
from pathlib import Path

DEFAULT_FOLDER_NAME = "RobotBattles"
SCOPES = ["https://www.googleapis.com/auth/drive"]

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_PATH = SCRIPT_DIR / "build" / "rules_upload_state.json"

CONFIG_DIR_COMBAT = Path.home() / ".config" / "combatrobotics"
CONFIG_DIR_MOBILE = Path.home() / ".config" / "mobilesuit"

SETUP = f"""
No Drive credentials found. One-time setup -- pick ONE:

  A. Service account (recommended: headless, never expires, no browser)
     1. https://console.cloud.google.com/ -> create/pick a project
     2. APIs & Services -> Library -> enable "Google Drive API"
     3. APIs & Services -> Credentials -> Create credentials -> Service account
     4. On the new account: Keys -> Add key -> JSON -> download
     5. Save it as {CONFIG_DIR_COMBAT / "drive_service_account.json"}
        (or {CONFIG_DIR_MOBILE / "drive_service_account.json"})
     6. Share the '{DEFAULT_FOLDER_NAME}' folder in Google Drive with the service account
        e-mail address (…@….iam.gserviceaccount.com) and grant *Editor*.

  B. Your own Google account (opens a browser once, then caches a token)
     1-2. as above
     3. APIs & Services -> Credentials -> Create credentials
        -> OAuth client ID -> Desktop app -> download the JSON
     4. Save it as {CONFIG_DIR_COMBAT / "client_secret.json"}
        (or {CONFIG_DIR_MOBILE / "client_secret.json"})
     5. If the consent screen is in "Testing", add yourself as a test user.
     The first run opens a browser; the refresh token is cached in drive_token.json.

Either file can live elsewhere -- point $RULES_DRIVE_CREDENTIALS at it.
"""


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_state():
    try:
        with open(STATE_PATH) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def write_state(data):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as fh:
        json.dump(data, fh, indent=2)


def resolve_pdf_path(cli_path=None):
    if cli_path:
        p = Path(cli_path).resolve()
        if not p.is_file():
            sys.exit(f"Specified PDF not found: {p}")
        return p

    candidates = [
        SCRIPT_DIR / "rules" / "combat_robotics_game.pdf",
        SCRIPT_DIR / "rules" / "rules.pdf",
    ]
    for c in candidates:
        if c.is_file():
            return c

    # Fallback to the primary candidate even if missing, so caller can report error
    return candidates[0]


def find_credentials():
    """Return (creds_path, token_path) or (None, None)."""
    env = os.environ.get("RULES_DRIVE_CREDENTIALS")
    if env:
        path = Path(env).expanduser()
        if not path.is_file():
            sys.exit(f"RULES_DRIVE_CREDENTIALS points at a missing file: {path}")
        token_candidate = path.parent / "drive_token.json"
        if not token_candidate.is_file():
            for fallback in (
                CONFIG_DIR_COMBAT / "drive_token.json",
                CONFIG_DIR_MOBILE / "drive_token.json",
            ):
                if fallback.is_file():
                    token_candidate = fallback
                    break
        return path, token_candidate

    for config_dir in (CONFIG_DIR_COMBAT, CONFIG_DIR_MOBILE):
        for name in ("drive_service_account.json", "client_secret.json"):
            path = config_dir / name
            if path.is_file():
                token_path = config_dir / "drive_token.json"
                if not token_path.is_file():
                    other_dir = (
                        CONFIG_DIR_MOBILE
                        if config_dir == CONFIG_DIR_COMBAT
                        else CONFIG_DIR_COMBAT
                    )
                    if (other_dir / "drive_token.json").is_file():
                        token_path = other_dir / "drive_token.json"
                return path, token_path

    return None, None


def build_credentials(path, token_path, quiet):
    """Build Drive credentials, auto-detecting service account vs OAuth client."""
    with open(path) as fh:
        blob = json.load(fh)

    if blob.get("type") == "service_account":
        from google.oauth2 import service_account

        if not quiet:
            print(f"auth: service account ({blob.get('client_email', '?')})")
        return service_account.Credentials.from_service_account_file(
            str(path), scopes=SCOPES
        )

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if token_path and token_path.is_file():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except ValueError:
            creds = None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as err:
            if not quiet:
                print(f"auth: cached token refresh failed ({err}), re-authorising…")
            creds = None

    if not (creds and creds.valid):
        if not quiet:
            print("auth: opening a browser for one-time Google authorisation…")
        flow = InstalledAppFlow.from_client_secrets_file(str(path), SCOPES)
        creds = flow.run_local_server(port=0)

        save_token_path = (
            token_path
            if (token_path and token_path.parent.exists())
            else (path.parent / "drive_token.json")
        )
        save_token_path.parent.mkdir(parents=True, exist_ok=True)
        save_token_path.write_text(creds.to_json())
        save_token_path.chmod(0o600)
        if not quiet:
            print(f"auth: user account authorised (token cached in {save_token_path})")
    else:
        if not quiet and token_path:
            print(f"auth: user account (token loaded from {token_path})")

    return creds


def get_drive_service(creds):
    from googleapiclient.discovery import build

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def find_or_create_folder(service, name: str, parent_id: str = None) -> str:
    query_parts = [
        f"name = '{name}'",
        "mimeType = 'application/vnd.google-apps.folder'",
        "trashed = false",
    ]
    if parent_id:
        query_parts.append(f"'{parent_id}' in parents")
    query = " and ".join(query_parts)

    res = (
        service.files()
        .list(
            q=query,
            fields="files(id, name, webViewLink)",
            spaces="drive",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    files = res.get("files", [])
    if files:
        return files[0]["id"]

    folder_metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        folder_metadata["parents"] = [parent_id]

    folder = (
        service.files()
        .create(
            body=folder_metadata,
            fields="id, name, webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    return folder["id"]


def resolve_remote_file(service, folder_id: str, file_name: str, cached_file_id: str = None):
    """Locate existing file in folder by cached_file_id or file_name."""
    if cached_file_id:
        try:
            item = (
                service.files()
                .get(
                    fileId=cached_file_id,
                    fields="id, name, trashed, parents, webViewLink",
                    supportsAllDrives=True,
                )
                .execute()
            )
            if not item.get("trashed") and (not folder_id or folder_id in item.get("parents", [])):
                return item
        except Exception:
            pass

    query = f"'{folder_id}' in parents and name = '{file_name}' and trashed = false"
    res = (
        service.files()
        .list(
            q=query,
            fields="files(id, name, size, modifiedTime, webViewLink)",
            spaces="drive",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    files = res.get("files", [])
    if files:
        return files[0]
    return None


def upload(service, file_path: Path, folder_id: str, file_id: str = None, quiet=False):
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(
        str(file_path),
        mimetype="application/pdf",
        resumable=True,
        chunksize=8 << 20,
    )

    if file_id:
        request = service.files().update(
            fileId=file_id,
            media_body=media,
            keepRevisionForever=False,
            supportsAllDrives=True,
            fields="id,name,size,modifiedTime,webViewLink",
        )
    else:
        file_metadata = {
            "name": file_path.name,
            "parents": [folder_id],
        }
        request = service.files().create(
            body=file_metadata,
            media_body=media,
            supportsAllDrives=True,
            fields="id,name,size,modifiedTime,webViewLink",
        )

    try:
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status and not quiet:
                print(f"  …{int(status.progress() * 100)}%", end="\r", flush=True)
        if not quiet:
            print("  …100%")
        return response
    except HttpError as err:
        if err.resp.status == 404:
            sys.exit(
                f"\nDrive returned 404.\n"
                "The credentials are valid but cannot see the destination. If you are "
                "using a service account, share the folder with its e-mail address "
                "and give it Editor."
            )
        if err.resp.status == 403:
            sys.exit(
                f"\nDrive returned 403.\n"
                "The account may not have permission to write to this location -- check it "
                "has Editor permissions and that the Drive API is enabled on the Cloud project."
            )
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Publish the combat robotics rules PDF to Google Drive under 'RobotBattles'."
    )
    parser.add_argument(
        "--force", action="store_true", help="upload even if the PDF is unchanged"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would happen, upload nothing"
    )
    parser.add_argument("--quiet", action="store_true", help="only report problems")
    parser.add_argument(
        "--pdf", type=Path, default=None, help="path to rules PDF (default: rules/combat_robotics_game.pdf)"
    )
    parser.add_argument(
        "--folder", default=DEFAULT_FOLDER_NAME, help=f"Google Drive folder name (default: {DEFAULT_FOLDER_NAME})"
    )
    parser.add_argument(
        "--folder-id", default=None, help="Explicit Google Drive folder ID override"
    )
    args = parser.parse_args()

    pdf_path = resolve_pdf_path(args.pdf)
    if not pdf_path.is_file():
        sys.exit(
            f"No rules PDF at {pdf_path}.\n"
            "Build it first: run pdflatex combat_robotics_game.tex from rules/."
        )

    size = pdf_path.stat().st_size
    digest = sha256(pdf_path)
    state = read_state()
    unchanged = (state.get("sha256") == digest)

    if not args.quiet:
        print(f"{pdf_path.name}  {size / 1048576:.1f} MB  sha256 {digest[:12]}…")

    if unchanged and not args.force:
        if not args.quiet:
            print("unchanged since the last upload -- nothing to do (--force overrides)")
            if state.get("web_view_link"):
                print(f"File link:   {state.get('web_view_link')}")
            if state.get("folder_id"):
                print(f"Folder link: https://drive.google.com/drive/folders/{state.get('folder_id')}")
        return 0

    if args.dry_run:
        target_desc = f"folder ID {args.folder_id}" if args.folder_id else f"folder '{args.folder}'"
        print(f"[dry run] would upload {pdf_path.name} to Google Drive {target_desc}")
        if state.get("file_id"):
            print(f"[dry run] previously recorded Drive file ID: {state.get('file_id')}")
        return 0

    creds_path, token_path = find_credentials()
    if creds_path is None:
        print(SETUP, file=sys.stderr)
        return 2

    creds = build_credentials(creds_path, token_path, args.quiet)
    service = get_drive_service(creds)

    folder_id = args.folder_id
    if not folder_id:
        if not args.quiet:
            print(f"Locating '{args.folder}' folder on Google Drive…")
        folder_id = find_or_create_folder(service, args.folder)

    folder_link = f"https://drive.google.com/drive/folders/{folder_id}"

    existing_file = resolve_remote_file(
        service, folder_id, pdf_path.name, cached_file_id=state.get("file_id")
    )

    if existing_file:
        file_id = existing_file["id"]
        if not args.quiet:
            print(f"Updating existing Drive file {file_id} ('{existing_file.get('name')}') in-place…")
    else:
        file_id = None
        if not args.quiet:
            print(f"Uploading new file '{pdf_path.name}' to Drive folder '{args.folder}'…")

    response = upload(service, pdf_path, folder_id, file_id=file_id, quiet=args.quiet)
    res_id = response.get("id")
    web_view_link = response.get("webViewLink") or f"https://drive.google.com/file/d/{res_id}/view"

    write_state({
        "folder_name": args.folder,
        "folder_id": folder_id,
        "file_name": pdf_path.name,
        "file_id": res_id,
        "sha256": digest,
        "size": size,
        "web_view_link": web_view_link,
        "folder_link": folder_link,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })

    if not args.quiet:
        print(f"published {response.get('name')}  ({response.get('modifiedTime')})")
        print(f"File link:   {web_view_link}")
        print(f"Folder link: {folder_link}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
