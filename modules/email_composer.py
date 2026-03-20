"""ColdCraft — Email composer using Gemini Pro."""

from modules.ai import compose_cold_email
from modules.resume_parser import get_user_profile
from db import query_db, execute_db


def compose_email(contact_id):
    """Compose a personalized cold email for a specific contact.

    Returns dict with subject, body, and metadata.
    """
    # Get user profile
    profile = get_user_profile()
    if not profile:
        return {"error": "No user profile found. Please upload your resume first."}

    # Get contact and company
    contact = query_db("SELECT * FROM contacts WHERE id = ?", (contact_id,), one=True)
    if not contact:
        return {"error": "Contact not found."}

    company = None
    if contact.get("company_id"):
        company = query_db(
            "SELECT * FROM companies WHERE id = ?", (contact["company_id"],), one=True
        )

    if not company:
        return {"error": "No company associated with this contact."}

    research = company.get("research_summary", "")
    if not research:
        research = f"Company: {company.get('name', 'Unknown')}. Website: {company.get('website', 'N/A')}."

    # Generate email via AI
    try:
        raw_email = compose_cold_email(profile, contact, company, research)
    except Exception as e:
        return {"error": f"AI generation failed: {str(e)}"}

    # Parse subject and body
    subject = ""
    body = raw_email
    if raw_email.lower().startswith("subject:"):
        lines = raw_email.split("\n", 1)
        subject = lines[0].replace("Subject:", "").replace("subject:", "").strip()
        body = lines[1].strip() if len(lines) > 1 else ""

    return {
        "contact_id": contact_id,
        "contact_name": contact.get("name", "Unknown"),
        "contact_email": contact.get("email", ""),
        "company_name": company.get("name", ""),
        "subject": subject,
        "body": body,
        "raw": raw_email,
    }


def compose_for_campaign(campaign_id):
    """Compose emails for all contacts in a campaign (not yet sent)."""
    campaign = query_db("SELECT * FROM campaigns WHERE id = ?", (campaign_id,), one=True)
    if not campaign:
        return {"error": "Campaign not found."}

    # Get contacts that haven't been emailed in this campaign
    contacts = query_db(
        """SELECT c.* FROM contacts c
        WHERE c.company_id IN (
            SELECT company_id FROM contacts
            WHERE id NOT IN (
                SELECT contact_id FROM outreach_logs
                WHERE campaign_id = ? AND action = 'email_sent'
            )
        )
        AND c.email IS NOT NULL AND c.email != ''""",
        (campaign_id,),
    )

    drafts = []
    for contact in contacts:
        draft = compose_email(contact["id"])
        if "error" not in draft:
            drafts.append(draft)

    return drafts
