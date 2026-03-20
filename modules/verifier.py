"""ColdCraft — Company verification module."""

import re
import requests
from db import execute_db, query_db


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
}


def _check_website_alive(url):
    """Check if the website is reachable and has SSL."""
    if not url:
        return {"alive": False, "ssl": False, "score": 0}
    if not url.startswith("http"):
        url = "https://" + url
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        is_ssl = resp.url.startswith("https://")
        return {"alive": True, "ssl": is_ssl, "score": 20 if is_ssl else 10}
    except Exception:
        return {"alive": False, "ssl": False, "score": 0}


def _check_domain_age(domain):
    """Check domain registration info via WHOIS."""
    try:
        import whois
        w = whois.whois(domain)
        if w.creation_date:
            from datetime import datetime
            created = w.creation_date
            if isinstance(created, list):
                created = created[0]
            age_days = (datetime.now() - created).days
            if age_days > 365:
                return {"age_days": age_days, "score": 25, "note": f"Domain is {age_days // 365} years old"}
            elif age_days > 90:
                return {"age_days": age_days, "score": 15, "note": f"Domain is {age_days} days old"}
            else:
                return {"age_days": age_days, "score": 5, "note": f"Domain is only {age_days} days old — very new"}
        return {"age_days": None, "score": 10, "note": "WHOIS data available but no creation date"}
    except Exception:
        return {"age_days": None, "score": 5, "note": "Could not fetch WHOIS data"}


def _check_linkedin_presence(company_name):
    """Check if company has a LinkedIn page (via Google search)."""
    try:
        query = f"site:linkedin.com/company {company_name}"
        resp = requests.get(
            "https://www.google.com/search",
            params={"q": query, "num": 3},
            headers=HEADERS,
            timeout=10,
        )
        has_linkedin = "linkedin.com/company" in resp.text.lower()
        return {"found": has_linkedin, "score": 25 if has_linkedin else 0}
    except Exception:
        return {"found": False, "score": 0}


def _check_social_presence(company_name):
    """Check for other social media presence."""
    score = 0
    notes = []
    for platform, query in [
        ("Glassdoor", f"site:glassdoor.com {company_name}"),
        ("Google Reviews", f'"{company_name}" reviews'),
    ]:
        try:
            resp = requests.get(
                "https://www.google.com/search",
                params={"q": query, "num": 3},
                headers=HEADERS,
                timeout=10,
            )
            if company_name.lower() in resp.text.lower():
                score += 15
                notes.append(f"{platform}: Found")
            else:
                notes.append(f"{platform}: Not found")
        except Exception:
            notes.append(f"{platform}: Check failed")

    return {"score": min(score, 30), "notes": notes}


def verify_company(company_id):
    """Run all verification checks on a company.

    Returns a score 0-100 and detailed notes.
    """
    company = query_db("SELECT * FROM companies WHERE id = ?", (company_id,), one=True)
    if not company:
        return {"error": "Company not found"}

    website = company.get("website", "")
    name = company["name"]
    domain = ""
    if website:
        domain = re.sub(r"https?://", "", website).split("/")[0]

    checks = {}
    total_score = 0

    # 1. Website check
    checks["website"] = _check_website_alive(website)
    total_score += checks["website"]["score"]

    # 2. Domain age
    if domain:
        checks["domain"] = _check_domain_age(domain)
        total_score += checks["domain"]["score"]

    # 3. LinkedIn presence
    checks["linkedin"] = _check_linkedin_presence(name)
    total_score += checks["linkedin"]["score"]

    # 4. Social/review presence
    checks["social"] = _check_social_presence(name)
    total_score += checks["social"]["score"]

    # Cap at 100
    total_score = min(total_score, 100)

    # Generate notes
    notes = []
    if checks["website"]["alive"]:
        notes.append(f"✅ Website is live" + (" with SSL" if checks["website"]["ssl"] else " (no SSL ⚠️)"))
    else:
        notes.append("❌ Website is not reachable")

    if "domain" in checks and checks["domain"].get("note"):
        notes.append(checks["domain"]["note"])

    if checks["linkedin"]["found"]:
        notes.append("✅ LinkedIn company page found")
    else:
        notes.append("⚠️ No LinkedIn company page found")

    for n in checks["social"].get("notes", []):
        notes.append(n)

    # Store results
    verification_text = "\n".join(notes)
    execute_db(
        """UPDATE companies SET
            verified = ?, verification_score = ?, verification_notes = ?
        WHERE id = ?""",
        (1 if total_score >= 50 else 0, total_score, verification_text, company_id),
    )

    return {
        "company_id": company_id,
        "company_name": name,
        "score": total_score,
        "verified": total_score >= 50,
        "notes": notes,
        "checks": checks,
    }


def verify_all_unverified():
    """Verify all companies that haven't been checked yet."""
    companies = query_db(
        "SELECT id, name FROM companies WHERE verification_score = 0 OR verification_score IS NULL"
    )
    results = []
    for c in companies:
        r = verify_company(c["id"])
        results.append(r)
    return results
