"""ColdCraft — CSV and Google Sheets importer."""

import csv
import io
import os
import json
from db import execute_db, query_db


def import_from_csv(file_path_or_stream, source="csv"):
    """Import contacts from a CSV file or stream.

    Expected columns: Company, Website, HR Name, HR Email, Role, Notes
    (case-insensitive, flexible matching)
    """
    results = {"imported": 0, "skipped": 0, "errors": []}

    if isinstance(file_path_or_stream, str):
        with open(file_path_or_stream, "r", encoding="utf-8-sig") as f:
            content = f.read()
    else:
        content = file_path_or_stream.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig")

    # Strip BOM if still present
    content = content.lstrip("\ufeff")

    reader = csv.DictReader(io.StringIO(content))

    # Normalize headers
    if reader.fieldnames is None:
        results["errors"].append("CSV file appears to be empty or has no headers.")
        return results

    # Build a map: clean_name → original_name (as DictReader keys use originals)
    original_to_clean = {}
    for h in reader.fieldnames:
        clean = h.strip().strip("\ufeff").strip("\x00")
        original_to_clean[h] = clean

    clean_fields = list(original_to_clean.values())
    print(f"[ColdCraft] CSV headers detected: {clean_fields}")

    # Map semantic roles to the ORIGINAL header key (what DictReader uses)
    header_map = {}
    for idx, (original, clean) in enumerate(original_to_clean.items()):
        hl = clean.lower().replace(" ", "_")
        if not hl:
            # Empty header — assume first empty column is company name
            if "company" not in header_map:
                header_map["company"] = original
        elif "company" in hl:
            header_map["company"] = original
        elif "website" in hl or "url" in hl or "site" in hl:
            header_map["website"] = original
        elif "hr" in hl and "name" in hl:
            header_map["hr_name"] = original
        elif ("hr" in hl and "email" in hl) or ("email" in hl):
            header_map["hr_email"] = original
        elif "phone" in hl or "mobile" in hl or "cell" in hl or "contact" in hl:
            header_map["phone"] = original
        elif "name" in hl and "company" not in hl:
            header_map["hr_name"] = original
        elif "role" in hl or "title" in hl or "position" in hl:
            header_map["role"] = original
        elif "note" in hl:
            header_map["notes"] = original

    print(f"[ColdCraft] Header mapping: {header_map}")

    for i, row in enumerate(reader, start=2):
        try:
            company_name = (row.get(header_map.get("company", ""), "") or "").strip()
            website = (row.get(header_map.get("website", ""), "") or "").strip()
            hr_name = (row.get(header_map.get("hr_name", ""), "") or "").strip()
            hr_email = (row.get(header_map.get("hr_email", ""), "") or "").strip()
            phone = (row.get(header_map.get("phone", ""), "") or "").strip()
            role = (row.get(header_map.get("role", ""), "") or "").strip() or "HR"
            notes = (row.get(header_map.get("notes", ""), "") or "").strip()

            if not company_name:
                results["errors"].append(f"Row {i}: Missing company name, skipped.")
                results["skipped"] += 1
                continue

            # Check for duplicate email
            if hr_email:
                existing = query_db(
                    "SELECT id FROM contacts WHERE email = ?", (hr_email,), one=True
                )
                if existing:
                    results["skipped"] += 1
                    continue

            # Insert or find company
            existing_company = query_db(
                "SELECT id FROM companies WHERE LOWER(name) = LOWER(?)",
                (company_name,),
                one=True,
            )
            if existing_company:
                company_id = existing_company["id"]
            else:
                company_id = execute_db(
                    "INSERT INTO companies (name, website, source) VALUES (?, ?, ?)",
                    (company_name, website, source),
                )

            # Insert contact
            if hr_name or hr_email:
                execute_db(
                    """INSERT INTO contacts (name, email, phone, role, company_id, source, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (hr_name, hr_email, phone, role, company_id, source, notes),
                )

            results["imported"] += 1

        except Exception as e:
            results["errors"].append(f"Row {i}: {str(e)}")
            results["skipped"] += 1

    return results


def import_from_google_sheet(sheet_url, credentials_path):
    """Import contacts from a Google Sheet.

    Requires a Google Cloud service account JSON key file.
    """
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        raise ImportError(
            "Google API libraries not installed. Run: pip install google-api-python-client google-auth"
        )

    if not os.path.exists(credentials_path):
        raise FileNotFoundError(
            f"Google credentials file not found: {credentials_path}\n"
            "See the setup guide for creating a service account."
        )

    # Extract sheet ID from URL
    sheet_id = None
    if "/spreadsheets/d/" in sheet_url:
        sheet_id = sheet_url.split("/spreadsheets/d/")[1].split("/")[0]
    else:
        sheet_id = sheet_url  # Assume it's already the ID

    # Auth and fetch
    creds = Credentials.from_service_account_file(
        credentials_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    service = build("sheets", "v4", credentials=creds)
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range="A:Z")
        .execute()
    )

    values = result.get("values", [])
    if not values:
        return {"imported": 0, "skipped": 0, "errors": ["Sheet is empty."]}

    # Convert to CSV-like format for reuse
    headers = values[0]
    csv_content = ",".join(headers) + "\n"
    for row in values[1:]:
        # Pad row to match header length
        padded = row + [""] * (len(headers) - len(row))
        csv_content += ",".join(f'"{v}"' for v in padded) + "\n"

    return import_from_csv(io.StringIO(csv_content), source="google_sheets")
