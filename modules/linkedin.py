"""ColdCraft — LinkedIn comment drafter.

Finds relevant LinkedIn posts and generates comment drafts.
All drafts are manual — user copies and pastes them.
"""

import re
import requests
from bs4 import BeautifulSoup
from modules.ai import draft_linkedin_comment, generate_text
from modules.resume_parser import get_user_profile
from db import execute_db, query_db


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
}


def _search_linkedin_posts(interests, num_results=10):
    """Search Google for recent LinkedIn posts matching user interests.

    Returns list of dicts with url, title, snippet.
    """
    posts = []

    for interest in interests[:5]:  # Limit to top 5 interests
        query = f'site:linkedin.com/posts "{interest}" OR "{interest.lower()}"'
        try:
            resp = requests.get(
                "https://www.google.com/search",
                params={"q": query, "num": 5},
                headers=HEADERS,
                timeout=10,
            )
            soup = BeautifulSoup(resp.text, "lxml")

            for result in soup.select("div.g, div[data-sokoban-container]"):
                link_tag = result.find("a", href=True)
                if not link_tag:
                    continue
                url = link_tag["href"]
                if "linkedin.com/posts/" not in url and "linkedin.com/feed/" not in url:
                    continue

                title = result.find("h3")
                snippet = result.find("div", class_="VwiC3b") or result.find("span", class_="st")

                posts.append({
                    "url": url,
                    "title": title.get_text() if title else "",
                    "snippet": snippet.get_text() if snippet else "",
                    "interest": interest,
                })

        except Exception:
            continue

        if len(posts) >= num_results:
            break

    return posts[:num_results]


def _extract_post_content(post):
    """Build a content summary from available post data."""
    parts = []
    if post.get("title"):
        parts.append(f"Title: {post['title']}")
    if post.get("snippet"):
        parts.append(f"Content: {post['snippet']}")
    if post.get("interest"):
        parts.append(f"Topic: {post['interest']}")
    return "\n".join(parts) if parts else "No content available"


def generate_comment_drafts(num_posts=5):
    """Find relevant LinkedIn posts and generate comment drafts.

    Returns list of drafts with post info and suggested comment.
    """
    profile = get_user_profile()
    if not profile:
        return {"error": "No user profile found. Upload your resume first."}

    interests = profile.get("interests", [])
    skills = profile.get("skills", [])

    if not interests and not skills:
        return {"error": "No interests or skills found in profile."}

    # Combine interests and skills for searching
    search_terms = interests + skills[:3]

    # Find relevant posts
    posts = _search_linkedin_posts(search_terms, num_results=num_posts)

    if not posts:
        # Fallback: use AI to generate topic-based comments
        return _generate_topic_drafts(interests)

    drafts = []
    for post in posts:
        content = _extract_post_content(post)
        author = post.get("title", "").split("-")[0].strip() if post.get("title") else "the author"

        try:
            comment = draft_linkedin_comment(
                content, author, ", ".join(interests[:5])
            )
        except Exception as e:
            comment = f"[Draft generation failed: {str(e)}]"

        # Store in DB
        draft_id = execute_db(
            """INSERT INTO linkedin_drafts
                (post_url, post_author, post_summary, comment_draft)
            VALUES (?, ?, ?, ?)""",
            (post.get("url", ""), author, content, comment),
        )

        drafts.append({
            "id": draft_id,
            "post_url": post.get("url", ""),
            "post_author": author,
            "post_topic": post.get("interest", ""),
            "post_snippet": post.get("snippet", "")[:200],
            "comment_draft": comment,
        })

    return drafts


def _generate_topic_drafts(interests):
    """Fallback: generate generic but passionate comment drafts based on interests."""
    drafts = []
    for interest in interests[:5]:
        prompt = f"""Imagine you found a LinkedIn post about {interest}.
The post discusses recent trends, challenges, or innovations in this field.

Write a brief, passionate comment (2-3 sentences) that:
- Shows deep interest in {interest}
- Adds a unique perspective or asks a thoughtful question
- Sounds authentic and enthusiastic

Also provide a suggested search query to find such posts on LinkedIn.

Format:
SEARCH: [your search query]
COMMENT: [your comment]"""

        try:
            result = generate_text(prompt, temperature=0.8, max_tokens=200)
            search_query = ""
            comment = result

            if "SEARCH:" in result and "COMMENT:" in result:
                parts = result.split("COMMENT:")
                search_query = parts[0].replace("SEARCH:", "").strip()
                comment = parts[1].strip()

            draft_id = execute_db(
                """INSERT INTO linkedin_drafts
                    (post_url, post_author, post_summary, comment_draft)
                VALUES (?, ?, ?, ?)""",
                ("", "Search: " + search_query, interest, comment),
            )

            drafts.append({
                "id": draft_id,
                "post_url": "",
                "post_author": "",
                "post_topic": interest,
                "post_snippet": f"Search LinkedIn for: {search_query}",
                "comment_draft": comment,
            })
        except Exception:
            continue

    return drafts


def get_pending_drafts():
    """Get all pending (unused) LinkedIn comment drafts."""
    return query_db(
        "SELECT * FROM linkedin_drafts WHERE status = 'pending' ORDER BY created_at DESC"
    )


def mark_draft_used(draft_id):
    """Mark a draft as used."""
    execute_db("UPDATE linkedin_drafts SET status = 'used' WHERE id = ?", (draft_id,))


def mark_draft_skipped(draft_id):
    """Mark a draft as skipped."""
    execute_db("UPDATE linkedin_drafts SET status = 'skipped' WHERE id = ?", (draft_id,))
