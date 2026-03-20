"""ColdCraft — GitHub outreach helper.

Finds relevant repos, orgs, and contributors in user's area of interest.
Suggests engagement opportunities (stars, issues, PRs).
"""

import requests
from modules.ai import generate_text
from modules.resume_parser import get_user_profile
from db import execute_db, query_db


API_BASE = "https://api.github.com"
HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "ColdCraft-Outreach-Engine",
}


def search_repos(interests, per_page=10):
    """Search GitHub for trending repos matching user interests."""
    repos = []

    for interest in interests[:5]:
        try:
            resp = requests.get(
                f"{API_BASE}/search/repositories",
                params={
                    "q": f"{interest} language:python OR language:javascript",
                    "sort": "updated",
                    "order": "desc",
                    "per_page": per_page,
                },
                headers=HEADERS,
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("items", [])[:5]:
                    repos.append({
                        "name": item["full_name"],
                        "url": item["html_url"],
                        "description": item.get("description", ""),
                        "stars": item["stargazers_count"],
                        "language": item.get("language", ""),
                        "updated": item["updated_at"],
                        "interest": interest,
                        "open_issues": item["open_issues_count"],
                        "owner_type": item["owner"]["type"],
                    })
        except Exception:
            continue

    return repos


def find_engagement_opportunities(num_results=10):
    """Find GitHub repos and engagement opportunities based on user profile."""
    profile = get_user_profile()
    if not profile:
        return {"error": "No user profile found. Upload your resume first."}

    interests = profile.get("interests", [])
    skills = profile.get("skills", [])
    search_terms = interests + skills[:3]

    repos = search_repos(search_terms, per_page=5)

    if not repos:
        return {"error": "No relevant repos found."}

    # Use AI to generate engagement suggestions
    opportunities = []
    for repo in repos[:num_results]:
        try:
            prompt = f"""Given this GitHub repository:
Name: {repo['name']}
Description: {repo['description']}
Language: {repo['language']}
Stars: {repo['stars']}
Open Issues: {repo['open_issues']}

And a user with these skills: {', '.join(skills[:5])}

Suggest ONE specific, actionable way this user could engage with this repo to get noticed.
Options: star it, open a meaningful issue, contribute a fix, write a helpful discussion post, etc.

Be specific — if suggesting a contribution, mention what kind.
Keep response to 2-3 sentences max."""

            suggestion = generate_text(prompt, temperature=0.7, max_tokens=150)
            repo["suggestion"] = suggestion
            opportunities.append(repo)
        except Exception:
            repo["suggestion"] = "⭐ Star this repo and explore its issues for contribution opportunities."
            opportunities.append(repo)

    return opportunities


def get_repo_issues(repo_full_name, per_page=10):
    """Get open issues from a repo (good-first-issue tagged preferred)."""
    issues = []
    try:
        # Try good-first-issue first
        resp = requests.get(
            f"{API_BASE}/search/issues",
            params={
                "q": f"repo:{repo_full_name} is:issue is:open label:\"good first issue\"",
                "per_page": per_page,
            },
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("items", []):
                issues.append({
                    "title": item["title"],
                    "url": item["html_url"],
                    "labels": [l["name"] for l in item.get("labels", [])],
                    "created": item["created_at"],
                    "comments": item["comments"],
                })

        # If not enough, get regular issues
        if len(issues) < per_page:
            resp = requests.get(
                f"{API_BASE}/repos/{repo_full_name}/issues",
                params={"state": "open", "per_page": per_page - len(issues)},
                headers=HEADERS,
                timeout=10,
            )
            if resp.status_code == 200:
                for item in resp.json():
                    if "pull_request" not in item:
                        issues.append({
                            "title": item["title"],
                            "url": item["html_url"],
                            "labels": [l["name"] for l in item.get("labels", [])],
                            "created": item["created_at"],
                            "comments": item["comments"],
                        })
    except Exception:
        pass

    return issues
