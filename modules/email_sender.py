"""ColdCraft — Email sender via SMTP."""

import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import Config
from db import execute_db, query_db


def _get_smtp_connection():
    """Create and return an SMTP connection."""
    server = smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT)
    server.starttls()
    server.login(Config.SMTP_EMAIL, Config.SMTP_PASSWORD)
    return server


def send_email(to_email, subject, body, contact_id=None, campaign_id=None, company_id=None):
    """Send a single email via SMTP.

    Returns dict with status and details.
    """
    if not Config.SMTP_EMAIL or not Config.SMTP_PASSWORD:
        return {"status": "failed", "error": "SMTP credentials not configured."}

    if not to_email:
        return {"status": "failed", "error": "No recipient email provided."}

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = Config.SMTP_EMAIL
        msg["To"] = to_email
        msg["Subject"] = subject

        # Plain text version
        msg.attach(MIMEText(body, "plain"))

        # HTML version (basic formatting)
        html_body = body.replace("\n", "<br>")
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6;">
            {html_body}
        </body>
        </html>
        """
        msg.attach(MIMEText(html, "html"))

        # Send
        server = _get_smtp_connection()
        server.sendmail(Config.SMTP_EMAIL, to_email, msg.as_string())
        server.quit()

        # Log the send
        execute_db(
            """INSERT INTO outreach_logs
                (campaign_id, contact_id, company_id, action, subject, content, status)
            VALUES (?, ?, ?, 'email_sent', ?, ?, 'sent')""",
            (campaign_id, contact_id, company_id, subject, body),
        )

        return {"status": "sent", "to": to_email, "subject": subject}

    except smtplib.SMTPAuthenticationError:
        return {"status": "failed", "error": "SMTP authentication failed. Check your email/password."}
    except smtplib.SMTPRecipientsRefused:
        return {"status": "failed", "error": f"Recipient refused: {to_email}"}
    except Exception as e:
        # Log failure
        execute_db(
            """INSERT INTO outreach_logs
                (campaign_id, contact_id, company_id, action, subject, content, status)
            VALUES (?, ?, ?, 'email_sent', ?, ?, 'failed')""",
            (campaign_id, contact_id, company_id, subject, str(e)),
        )
        return {"status": "failed", "error": str(e)}


def send_campaign_emails(campaign_id, drafts):
    """Send all email drafts for a campaign with rate limiting.

    Args:
        campaign_id: The campaign ID
        drafts: List of dicts with contact_id, contact_email, subject, body, company_name

    Returns list of send results.
    """
    results = []
    sent_count = 0

    for i, draft in enumerate(drafts):
        # Check rate limit
        recent_count = query_db(
            """SELECT COUNT(*) as cnt FROM outreach_logs
            WHERE action = 'email_sent' AND status = 'sent'
            AND created_at > datetime('now', '-1 hour')""",
            one=True,
        )
        if recent_count and recent_count["cnt"] >= Config.MAX_EMAILS_PER_HOUR:
            results.append({
                "status": "rate_limited",
                "contact": draft.get("contact_name", ""),
                "error": "Hourly email limit reached. Try again later.",
            })
            break

        # Send email
        result = send_email(
            to_email=draft["contact_email"],
            subject=draft["subject"],
            body=draft["body"],
            contact_id=draft.get("contact_id"),
            campaign_id=campaign_id,
            company_id=draft.get("company_id"),
        )
        result["contact_name"] = draft.get("contact_name", "")
        results.append(result)

        if result["status"] == "sent":
            sent_count += 1

        # Rate limit delay (except for last email)
        if i < len(drafts) - 1:
            time.sleep(Config.EMAIL_DELAY_SECONDS)

    # Update campaign
    execute_db(
        """UPDATE campaigns SET
            sent_count = sent_count + ?,
            status = CASE WHEN sent_count + ? >= total_contacts THEN 'completed' ELSE 'active' END,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?""",
        (sent_count, sent_count, campaign_id),
    )

    return results
