"""ColdCraft — Resume parser module."""

import os
import json
import fitz  # PyMuPDF
from modules.ai import parse_resume_text
from db import execute_db, query_db


def extract_text_from_pdf(pdf_path):
    """Extract all text from a PDF file."""
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text.strip()


def parse_and_store_resume(pdf_path):
    """Parse a resume PDF and store the extracted profile in the database."""
    # Extract text
    raw_text = extract_text_from_pdf(pdf_path)
    if not raw_text:
        raise ValueError("Could not extract text from the resume PDF.")

    # Use AI to parse structured data
    profile = parse_resume_text(raw_text)

    # Check if profile already exists
    existing = query_db("SELECT id FROM user_profile LIMIT 1", one=True)

    if existing:
        execute_db(
            """UPDATE user_profile SET
                name=?, email=?, phone=?, linkedin_url=?, github_url=?,
                portfolio_url=?, skills=?, interests=?, experience=?,
                target_roles=?, resume_path=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?""",
            (
                profile.get("name"),
                profile.get("email"),
                profile.get("phone"),
                profile.get("linkedin_url"),
                profile.get("github_url"),
                profile.get("portfolio_url"),
                json.dumps(profile.get("skills", [])),
                json.dumps(profile.get("interests", [])),
                profile.get("experience"),
                json.dumps(profile.get("target_roles", [])),
                pdf_path,
                existing["id"],
            ),
        )
        return existing["id"]
    else:
        return execute_db(
            """INSERT INTO user_profile
                (name, email, phone, linkedin_url, github_url, portfolio_url,
                 skills, interests, experience, target_roles, resume_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                profile.get("name"),
                profile.get("email"),
                profile.get("phone"),
                profile.get("linkedin_url"),
                profile.get("github_url"),
                profile.get("portfolio_url"),
                json.dumps(profile.get("skills", [])),
                json.dumps(profile.get("interests", [])),
                profile.get("experience"),
                json.dumps(profile.get("target_roles", [])),
                pdf_path,
            ),
        )


def get_user_profile():
    """Get the current user profile."""
    profile = query_db("SELECT * FROM user_profile ORDER BY id DESC LIMIT 1", one=True)
    if profile:
        profile["skills"] = json.loads(profile.get("skills") or "[]")
        profile["interests"] = json.loads(profile.get("interests") or "[]")
        profile["target_roles"] = json.loads(profile.get("target_roles") or "[]")
    return profile
