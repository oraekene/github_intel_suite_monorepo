"""
pia/scan/colab_scanner.py

Fetches Google Colab notebooks (.ipynb) from a specified Google Drive
folder using the Google Drive API.

Setup:
1. Go to https://console.cloud.google.com/
2. Create a project → Enable "Google Drive API"
3. Create credentials → Service Account → Download JSON key
4. Share your Colab folder with the service account email
5. Set credentials_file and colab_folder_id in config.yaml
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field

from utils import cfg, log
from scan.local_scanner import ProjectFile


def scan_colab_notebooks() -> list[ProjectFile]:
    """
    Download and parse all Colab notebooks from the configured Drive folder.
    Returns a list of ProjectFile objects (source="colab").
    """
    if not cfg("projects.colab.enabled", False):
        log.info("Colab scanning disabled in config.")
        return []

    creds_file = cfg("projects.colab.credentials_file", "")
    folder_id  = cfg("projects.colab.colab_folder_id", "")

    if not creds_file or creds_file.startswith("<REPLACE"):
        log.warning("Colab credentials not configured — skipping Colab scan.")
        return []
    if not folder_id or folder_id.startswith("<REPLACE"):
        log.warning("Colab folder ID not configured — skipping Colab scan.")
        return []

    try:
        from googleapiclient.discovery import build
        from google.oauth2.service_account import Credentials
        from googleapiclient.http import MediaIoBaseDownload
    except ImportError:
        log.error(
            "Google API packages not installed.\n"
            "Run: pip install google-api-python-client google-auth"
        )
        return []

    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    creds  = Credentials.from_service_account_file(creds_file, scopes=scopes)
    drive  = build("drive", "v3", credentials=creds)

    log.info(f"Scanning Colab folder: {folder_id}")

    # List all .ipynb files recursively under the folder
    notebooks = _list_notebooks(drive, folder_id)
    log.info(f"Found {len(notebooks)} Colab notebooks")

    all_files: list[ProjectFile] = []

    for nb_meta in notebooks:
        content = _download_notebook(drive, nb_meta["id"])
        if not content:
            continue

        name = nb_meta.get("name", "unknown.ipynb")
        proj = _infer_project_name(nb_meta)

        # Parse cells
        parsed = _parse_notebook_cells(content)

        all_files.append(ProjectFile(
            project_name  = proj,
            project_root  = f"colab:{folder_id}",
            relative_path = name,
            abs_path      = f"https://colab.research.google.com/drive/{nb_meta['id']}",
            file_type     = "ipynb",
            content       = parsed,
            source        = "colab",
            metadata      = {
                "project":       proj,
                "relative_path": name,
                "file_type":     "ipynb",
                "source":        "colab",
                "drive_id":      nb_meta["id"],
            },
        ))

    log.info(f"Colab scan complete — {len(all_files)} notebooks")
    return all_files


# ── Drive helpers ─────────────────────────────────────────────────────────────

def _list_notebooks(drive, folder_id: str) -> list[dict]:
    """Recursively list all .ipynb files under a Drive folder."""
    results = []
    query = (
        f"'{folder_id}' in parents "
        f"and mimeType='application/vnd.google.colaboratory' "
        f"and trashed=false"
    )
    page_token = None
    while True:
        resp = drive.files().list(
            q=query,
            spaces="drive",
            fields="nextPageToken, files(id, name, parents)",
            pageToken=page_token,
        ).execute()
        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    # Also check for plain .ipynb files (sometimes stored as generic type)
    query2 = (
        f"'{folder_id}' in parents "
        f"and name contains '.ipynb' "
        f"and trashed=false"
    )
    page_token = None
    while True:
        resp = drive.files().list(
            q=query2,
            spaces="drive",
            fields="nextPageToken, files(id, name, parents)",
            pageToken=page_token,
        ).execute()
        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    # Deduplicate by id
    seen = set()
    unique = []
    for f in results:
        if f["id"] not in seen:
            seen.add(f["id"])
            unique.append(f)
    return unique


def _download_notebook(drive, file_id: str) -> str | None:
    try:
        from googleapiclient.http import MediaIoBaseDownload
        import io
        buf = io.BytesIO()
        req = drive.files().export_media(
            fileId=file_id,
            mimeType="application/json",
        )
        dl = MediaIoBaseDownload(buf, req)
        done = False
        while not done:
            _, done = dl.next_chunk()
        return buf.getvalue().decode("utf-8", errors="replace")
    except Exception:
        # Fallback: direct download
        try:
            content = drive.files().get_media(fileId=file_id).execute()
            return content.decode("utf-8", errors="replace")
        except Exception as e:
            log.debug(f"  Could not download notebook {file_id}: {e}")
            return None


def _parse_notebook_cells(raw: str) -> str:
    try:
        import nbformat
        nb = nbformat.reads(raw, as_version=4)
        parts = []
        for cell in nb.cells:
            if cell.cell_type in ("code", "markdown") and cell.source.strip():
                tag = "# CODE\n" if cell.cell_type == "code" else "# MARKDOWN\n"
                parts.append(tag + cell.source.strip())
        return "\n\n".join(parts)
    except Exception:
        return raw


def _infer_project_name(meta: dict) -> str:
    name = meta.get("name", "colab_notebook")
    # Strip extension
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return name
