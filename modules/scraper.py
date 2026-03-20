"""ColdCraft — Web scraper for company research and HR contacts."""

import re
import requests
from bs4 import BeautifulSoup
from modules.ai import summarize_company
from db import execute_db, query_db


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
}


def _fetch_page(url, timeout=15):
    """Fetch a page and return BeautifulSoup object."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except Exception as e:
        return None


def _extract_emails(soup):
    """Extract email addresses from page HTML."""
    text = soup.get_text()
    emails = set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text))

    # Also check mailto: links
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.startswith("mailto:"):
            email = href.replace("mailto:", "").split("?")[0].strip()
            if email:
                emails.add(email)

    # Filter out common non-HR emails
    ignore_patterns = [
        "noreply", "no-reply", "support@", "info@", "hello@",
        "sales@", "admin@", "webmaster@", "privacy@",
        "example.com", "sentry.io", "github.com"
    ]
    filtered = set()
    for email in emails:
        if not any(p in email.lower() for p in ignore_patterns):
            filtered.add(email)

    return filtered


def _find_team_links(soup, base_url):
    """Find links to About, Team, People, Careers pages."""
    keywords = ["about", "team", "people", "our-team", "careers", "jobs", "contact"]
    links = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        text = a.get_text().lower()
        if any(kw in href or kw in text for kw in keywords):
            full_url = href
            if href.startswith("/"):
                full_url = base_url.rstrip("/") + href
            elif not href.startswith("http"):
                full_url = base_url.rstrip("/") + "/" + href
            links.add(full_url)

    return links


def _extract_page_text(soup, max_length=5000):
    """Extract meaningful text content from a page."""
    # Remove script and style tags
    for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)

    # Clean up excessive whitespace
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return "\n".join(lines)[:max_length]


def scrape_company(company_id):
    """Scrape a company website for research info and HR contacts.

    Returns: dict with research_summary, contacts_found, emails
    """
    company = query_db("SELECT * FROM companies WHERE id = ?", (company_id,), one=True)
    if not company or not company.get("website"):
        return {"error": "Company not found or no website URL."}

    website = company["website"]
    if not website.startswith("http"):
        website = "https://" + website

    result = {
        "company_id": company_id,
        "research_summary": "",
        "contacts_found": 0,
        "emails": [],
        "pages_scraped": 0,
    }

    # Scrape main page
    all_text = ""
    all_emails = set()

    soup = _fetch_page(website)
    if not soup:
        return {"error": f"Could not fetch {website}"}

    all_text += _extract_page_text(soup) + "\n\n"
    all_emails.update(_extract_emails(soup))
    result["pages_scraped"] += 1

    # Find and scrape team/about/careers pages
    sub_links = _find_team_links(soup, website)
    for link in list(sub_links)[:5]:  # Max 5 sub-pages
        sub_soup = _fetch_page(link)
        if sub_soup:
            all_text += f"\n--- {link} ---\n"
            all_text += _extract_page_text(sub_soup) + "\n"
            all_emails.update(_extract_emails(sub_soup))
            result["pages_scraped"] += 1

    # Generate AI research summary
    try:
        summary = summarize_company(company["name"], all_text)
        execute_db(
            "UPDATE companies SET research_summary = ? WHERE id = ?",
            (summary, company_id),
        )
        result["research_summary"] = summary
    except Exception as e:
        result["research_summary"] = f"AI summary failed: {str(e)}"

    # Store discovered emails as contacts
    for email in all_emails:
        existing = query_db(
            "SELECT id FROM contacts WHERE email = ?", (email,), one=True
        )
        if not existing:
            execute_db(
                """INSERT INTO contacts (email, role, company_id, source)
                VALUES (?, 'Unknown', ?, 'scraped')""",
                (email, company_id),
            )
            result["contacts_found"] += 1

    result["emails"] = list(all_emails)
    return result


def scrape_all_unresearched():
    """Scrape all companies that don't have a research summary yet."""
    companies = query_db(
        "SELECT id, name FROM companies WHERE research_summary IS NULL OR research_summary = ''"
    )
    results = []
    for c in companies:
        r = scrape_company(c["id"])
        r["company_name"] = c["name"]
        results.append(r)
    return results
