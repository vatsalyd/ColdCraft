"""ColdCraft — Flask application entry point."""

import os
import json
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, send_from_directory
)
from werkzeug.utils import secure_filename
from config import Config
from db import init_db, query_db, execute_db

# Initialize
Config.ensure_dirs()
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = Config.SECRET_KEY
app.config["UPLOAD_FOLDER"] = Config.UPLOAD_DIR
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max

# Initialize database
init_db()


# ─── Dashboard ────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    stats = {
        "total_companies": query_db("SELECT COUNT(*) as c FROM companies", one=True)["c"],
        "total_contacts": query_db("SELECT COUNT(*) as c FROM contacts", one=True)["c"],
        "emails_sent": query_db(
            "SELECT COUNT(*) as c FROM outreach_logs WHERE action='email_sent' AND status='sent'",
            one=True,
        )["c"],
        "campaigns": query_db("SELECT COUNT(*) as c FROM campaigns", one=True)["c"],
        "linkedin_drafts": query_db(
            "SELECT COUNT(*) as c FROM linkedin_drafts WHERE status='pending'", one=True
        )["c"],
        "verified_companies": query_db(
            "SELECT COUNT(*) as c FROM companies WHERE verified=1", one=True
        )["c"],
    }

    recent_logs = query_db(
        """SELECT ol.*, c.name as contact_name, co.name as company_name
        FROM outreach_logs ol
        LEFT JOIN contacts c ON ol.contact_id = c.id
        LEFT JOIN companies co ON ol.company_id = co.id
        ORDER BY ol.created_at DESC LIMIT 10"""
    )

    profile = query_db("SELECT * FROM user_profile LIMIT 1", one=True)

    return render_template("dashboard.html", stats=stats, logs=recent_logs, profile=profile)


# ─── Resume / Profile ────────────────────────────────────────────────────

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if request.method == "POST":
        file = request.files.get("resume")
        if file and file.filename.endswith(".pdf"):
            filename = secure_filename(file.filename)
            filepath = os.path.join(Config.UPLOAD_DIR, filename)
            file.save(filepath)

            try:
                from modules.resume_parser import parse_and_store_resume
                parse_and_store_resume(filepath)
                flash("✅ Resume parsed successfully!", "success")
            except Exception as e:
                flash(f"❌ Error parsing resume: {str(e)}", "error")
        else:
            flash("⚠️ Please upload a PDF file.", "warning")

        return redirect(url_for("profile"))

    profile_data = query_db("SELECT * FROM user_profile LIMIT 1", one=True)
    if profile_data:
        profile_data["skills"] = json.loads(profile_data.get("skills") or "[]")
        profile_data["interests"] = json.loads(profile_data.get("interests") or "[]")
        profile_data["target_roles"] = json.loads(profile_data.get("target_roles") or "[]")

    return render_template("profile.html", profile=profile_data)


@app.route("/profile/update", methods=["POST"])
def update_profile():
    """Manually update profile fields."""
    fields = ["name", "email", "phone", "linkedin_url", "github_url", "portfolio_url"]
    existing = query_db("SELECT id FROM user_profile LIMIT 1", one=True)

    if existing:
        for field in fields:
            value = request.form.get(field, "").strip()
            if value:
                execute_db(f"UPDATE user_profile SET {field} = ? WHERE id = ?", (value, existing["id"]))
        flash("✅ Profile updated!", "success")
    else:
        flash("⚠️ Upload a resume first to create your profile.", "warning")

    return redirect(url_for("profile"))


# ─── Contacts ────────────────────────────────────────────────────────────

@app.route("/contacts")
def contacts():
    all_contacts = query_db(
        """SELECT c.*, co.name as company_name, co.verified, co.verification_score
        FROM contacts c
        LEFT JOIN companies co ON c.company_id = co.id
        ORDER BY c.created_at DESC"""
    )
    return render_template("contacts.html", contacts=all_contacts)


@app.route("/contacts/import", methods=["POST"])
def import_contacts():
    file = request.files.get("csv_file")
    sheet_url = request.form.get("sheet_url", "").strip()

    if file and file.filename.endswith(".csv"):
        try:
            from modules.sheets import import_from_csv
            result = import_from_csv(file.stream, source="csv")
            flash(
                f"✅ Imported {result['imported']} contacts, {result['skipped']} skipped.",
                "success",
            )
            if result["errors"]:
                flash(f"⚠️ Warnings: {'; '.join(result['errors'][:3])}", "warning")
        except Exception as e:
            flash(f"❌ Import error: {str(e)}", "error")

    elif sheet_url:
        try:
            from modules.sheets import import_from_google_sheet
            result = import_from_google_sheet(sheet_url, Config.GOOGLE_SHEETS_CREDENTIALS)
            flash(
                f"✅ Imported {result['imported']} contacts from Google Sheets.",
                "success",
            )
        except Exception as e:
            flash(f"❌ Sheets import error: {str(e)}", "error")
    else:
        flash("⚠️ Please provide a CSV file or Google Sheet URL.", "warning")

    return redirect(url_for("contacts"))


@app.route("/contacts/<int:contact_id>/delete", methods=["POST"])
def delete_contact(contact_id):
    execute_db("DELETE FROM contacts WHERE id = ?", (contact_id,))
    flash("Contact deleted.", "success")
    return redirect(url_for("contacts"))


# ─── Companies ────────────────────────────────────────────────────────────

@app.route("/companies")
def companies():
    all_companies = query_db(
        """SELECT c.*,
            (SELECT COUNT(*) FROM contacts WHERE company_id = c.id) as contact_count
        FROM companies c ORDER BY c.created_at DESC"""
    )
    return render_template("companies.html", companies=all_companies)


@app.route("/companies/<int:company_id>/research", methods=["POST"])
def research_company(company_id):
    try:
        from modules.scraper import scrape_company
        result = scrape_company(company_id)
        if "error" in result:
            flash(f"❌ {result['error']}", "error")
        else:
            flash(
                f"✅ Researched! Found {result['contacts_found']} contacts, "
                f"scraped {result['pages_scraped']} pages.",
                "success",
            )
    except Exception as e:
        flash(f"❌ Research error: {str(e)}", "error")

    return redirect(url_for("companies"))


@app.route("/companies/<int:company_id>/verify", methods=["POST"])
def verify_company(company_id):
    try:
        from modules.verifier import verify_company as _verify
        result = _verify(company_id)
        if "error" in result:
            flash(f"❌ {result['error']}", "error")
        else:
            status = "✅ Verified" if result["verified"] else "⚠️ Caution"
            flash(f"{status} — Score: {result['score']}/100", "success")
    except Exception as e:
        flash(f"❌ Verification error: {str(e)}", "error")

    return redirect(url_for("companies"))


@app.route("/companies/research-all", methods=["POST"])
def research_all():
    try:
        from modules.scraper import scrape_all_unresearched
        results = scrape_all_unresearched()
        flash(f"✅ Researched {len(results)} companies.", "success")
    except Exception as e:
        flash(f"❌ Error: {str(e)}", "error")
    return redirect(url_for("companies"))


@app.route("/companies/verify-all", methods=["POST"])
def verify_all():
    try:
        from modules.verifier import verify_all_unverified
        results = verify_all_unverified()
        flash(f"✅ Verified {len(results)} companies.", "success")
    except Exception as e:
        flash(f"❌ Error: {str(e)}", "error")
    return redirect(url_for("companies"))


# ─── Campaigns & Email ───────────────────────────────────────────────────

@app.route("/campaigns")
def campaigns():
    all_campaigns = query_db("SELECT * FROM campaigns ORDER BY created_at DESC")
    return render_template("campaigns.html", campaigns=all_campaigns)


@app.route("/campaigns/create", methods=["POST"])
def create_campaign():
    name = request.form.get("name", "").strip()
    campaign_type = request.form.get("type", "email")

    if not name:
        flash("⚠️ Campaign name is required.", "warning")
        return redirect(url_for("campaigns"))

    contact_ids = request.form.getlist("contact_ids")
    total = len(contact_ids)

    campaign_id = execute_db(
        "INSERT INTO campaigns (name, type, total_contacts) VALUES (?, ?, ?)",
        (name, campaign_type, total),
    )

    flash(f"✅ Campaign '{name}' created with {total} contacts.", "success")
    return redirect(url_for("compose", campaign_id=campaign_id))


@app.route("/compose")
def compose():
    campaign_id = request.args.get("campaign_id")
    contact_id = request.args.get("contact_id")

    draft = None
    if contact_id:
        try:
            from modules.email_composer import compose_email
            draft = compose_email(int(contact_id))
        except Exception as e:
            flash(f"❌ Error composing email: {str(e)}", "error")

    contacts_list = query_db(
        """SELECT c.*, co.name as company_name
        FROM contacts c
        LEFT JOIN companies co ON c.company_id = co.id
        WHERE c.email IS NOT NULL AND c.email != ''
        ORDER BY co.name"""
    )

    return render_template(
        "compose.html",
        draft=draft,
        contacts=contacts_list,
        campaign_id=campaign_id,
    )


@app.route("/send-email", methods=["POST"])
def send_email():
    to_email = request.form.get("to_email", "").strip()
    subject = request.form.get("subject", "").strip()
    body = request.form.get("body", "").strip()
    contact_id = request.form.get("contact_id")
    campaign_id = request.form.get("campaign_id")

    if not to_email or not subject or not body:
        flash("⚠️ Email, subject, and body are all required.", "warning")
        return redirect(url_for("compose"))

    try:
        from modules.email_sender import send_email as _send
        result = _send(
            to_email=to_email,
            subject=subject,
            body=body,
            contact_id=int(contact_id) if contact_id else None,
            campaign_id=int(campaign_id) if campaign_id else None,
        )
        if result["status"] == "sent":
            flash(f"✅ Email sent to {to_email}!", "success")
        else:
            flash(f"❌ Send failed: {result.get('error', 'Unknown error')}", "error")
    except Exception as e:
        flash(f"❌ Error: {str(e)}", "error")

    return redirect(url_for("compose"))


# ─── LinkedIn ─────────────────────────────────────────────────────────────

@app.route("/linkedin")
def linkedin():
    drafts = query_db(
        "SELECT * FROM linkedin_drafts WHERE status = 'pending' ORDER BY created_at DESC"
    )
    return render_template("linkedin.html", drafts=drafts)


@app.route("/linkedin/generate", methods=["POST"])
def generate_linkedin_drafts():
    try:
        from modules.linkedin import generate_comment_drafts
        num = int(request.form.get("num_posts", 5))
        result = generate_comment_drafts(num_posts=num)
        if isinstance(result, dict) and "error" in result:
            flash(f"❌ {result['error']}", "error")
        else:
            flash(f"✅ Generated {len(result)} comment drafts!", "success")
    except Exception as e:
        flash(f"❌ Error: {str(e)}", "error")

    return redirect(url_for("linkedin"))


@app.route("/linkedin/<int:draft_id>/used", methods=["POST"])
def mark_used(draft_id):
    execute_db("UPDATE linkedin_drafts SET status = 'used' WHERE id = ?", (draft_id,))
    return redirect(url_for("linkedin"))


@app.route("/linkedin/<int:draft_id>/skip", methods=["POST"])
def mark_skipped(draft_id):
    execute_db("UPDATE linkedin_drafts SET status = 'skipped' WHERE id = ?", (draft_id,))
    return redirect(url_for("linkedin"))


# ─── GitHub ───────────────────────────────────────────────────────────────

@app.route("/github")
def github():
    return render_template("github.html", opportunities=None)


@app.route("/github/discover", methods=["POST"])
def discover_github():
    try:
        from modules.github import find_engagement_opportunities
        opportunities = find_engagement_opportunities(num_results=10)
        if isinstance(opportunities, dict) and "error" in opportunities:
            flash(f"❌ {opportunities['error']}", "error")
            return redirect(url_for("github"))
        return render_template("github.html", opportunities=opportunities)
    except Exception as e:
        flash(f"❌ Error: {str(e)}", "error")
        return redirect(url_for("github"))


# ─── Activity Log ─────────────────────────────────────────────────────────

@app.route("/activity")
def activity():
    logs = query_db(
        """SELECT ol.*, c.name as contact_name, c.email as contact_email,
            co.name as company_name
        FROM outreach_logs ol
        LEFT JOIN contacts c ON ol.contact_id = c.id
        LEFT JOIN companies co ON ol.company_id = co.id
        ORDER BY ol.created_at DESC
        LIMIT 100"""
    )
    return render_template("activity.html", logs=logs)


# ─── API Endpoints ────────────────────────────────────────────────────────

@app.route("/api/stats")
def api_stats():
    return jsonify({
        "companies": query_db("SELECT COUNT(*) as c FROM companies", one=True)["c"],
        "contacts": query_db("SELECT COUNT(*) as c FROM contacts", one=True)["c"],
        "emails_sent": query_db(
            "SELECT COUNT(*) as c FROM outreach_logs WHERE action='email_sent' AND status='sent'",
            one=True,
        )["c"],
    })


# ─── Run ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=Config.DEBUG, port=5000)
