import csv
import logging
import os
from google.oauth2 import service_account
import gspread

CANONICAL_FIELDS = ["source", "title", "company", "location", "link", "posted_at", "description"]

logger = logging.getLogger(__name__)

def write_csv(jobs: list[dict], path: str) -> None:
    """
    Writes a list of canonical job dictionaries to a local CSV file.
    Creates parent directories if they do not exist.
    """
    if not jobs:
        logger.warning("No jobs to write to CSV.")
        return

    # Ensure parent directories exist
    parent_dir = os.path.dirname(path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    logger.info("Writing %d jobs to CSV: %s", len(jobs), path)
    try:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CANONICAL_FIELDS, extrasaction="ignore")
            writer.writeheader()
            for job in jobs:
                writer.writerow(job)
    except Exception as exc:
        logger.error("Failed to write CSV to %s: %s", path, exc)
        raise

def write_to_sheet(jobs: list[dict], sheet_url: str) -> None:
    """
    Writes a list of canonical job dictionaries to a Google Sheet target.
    Requires GOOGLE_SERVICE_ACCOUNT_JSON env var to be configured.
    """
    if not jobs:
        logger.warning("No jobs to write to Google Sheet.")
        return

    creds_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not creds_path:
        logger.warning("GOOGLE_SERVICE_ACCOUNT_JSON is not configured in the environment. Skipping Google Sheets write.")
        return

    if not os.path.exists(creds_path):
        logger.warning("Service account JSON file not found at: %s. Skipping Google Sheets write.", creds_path)
        return

    logger.info("Writing %d jobs to Google Sheet at %s", len(jobs), sheet_url)
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = service_account.Credentials.from_service_account_file(creds_path, scopes=scopes)
        client = gspread.authorize(creds)
        
        # Open sheet by URL
        sheet = client.open_by_url(sheet_url)
        worksheet = sheet.get_worksheet(0) # Default to first sheet
        
        # Clear existing content
        worksheet.clear()
        
        # Build payload (header + data rows)
        payload = [CANONICAL_FIELDS]
        for job in jobs:
            row = [job.get(field, "") for field in CANONICAL_FIELDS]
            payload.append(row)
            
        worksheet.update("A1", payload)
        logger.info("Successfully populated Google Sheet.")
    except Exception as exc:
        logger.error("Failed to write to Google Sheet: %s", exc)
        raise

