"""ColdCraft — Gemini Pro AI wrapper."""

import json
import google.generativeai as genai
from config import Config


# Configure Gemini
_model = None


def _get_model():
    """Lazy-init the Gemini model."""
    global _model
    if _model is None:
        genai.configure(api_key=Config.GEMINI_API_KEY)
        _model = genai.GenerativeModel("gemini-2.5-pro-preview-05-06")
    return _model


def generate_text(prompt, temperature=0.7, max_tokens=2048):
    """Generate text from a prompt using Gemini Pro."""
    model = _get_model()
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        ),
    )
    return response.text.strip()


def generate_json(prompt, temperature=0.3, max_tokens=2048):
    """Generate and parse JSON from a prompt."""
    full_prompt = prompt + "\n\nRespond ONLY with valid JSON. No markdown, no explanation."
    text = generate_text(full_prompt, temperature=temperature, max_tokens=max_tokens)

    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    text = text.strip()

    return json.loads(text)


def summarize_company(company_name, page_text):
    """Summarize a company's work, culture, and recent projects."""
    prompt = f"""Analyze this company and provide a concise research summary.

Company: {company_name}
Website Content:
{page_text[:4000]}

Provide a summary covering:
1. What the company does (1-2 sentences)
2. Their tech stack or domain expertise
3. Recent projects or products
4. Company culture indicators
5. Potential areas where an intern could contribute

Keep it concise — max 200 words."""
    return generate_text(prompt, temperature=0.3)


def compose_cold_email(user_profile, contact, company, research_summary):
    """Generate a personalized cold email for an internship pitch."""
    prompt = f"""Write a personalized cold email from an aspiring intern to a company HR/recruiter.

=== SENDER (the intern) ===
Name: {user_profile.get('name', 'N/A')}
Email: {user_profile.get('email', 'N/A')}
Phone: {user_profile.get('phone', 'N/A')}
LinkedIn: {user_profile.get('linkedin_url', 'N/A')}
GitHub: {user_profile.get('github_url', 'N/A')}
Portfolio: {user_profile.get('portfolio_url', 'N/A')}
Skills: {user_profile.get('skills', 'N/A')}
Experience: {user_profile.get('experience', 'N/A')}

=== RECIPIENT ===
HR Name: {contact.get('name', 'Hiring Manager')}
Role: {contact.get('role', 'HR')}
Company: {company.get('name', 'the company')}

=== COMPANY RESEARCH ===
{research_summary}

=== INSTRUCTIONS ===
Write a cold email that:
1. Has a compelling subject line (prefix with "Subject: ")
2. Opens with something specific about the company's work — show you did your research
3. Briefly introduce yourself and your relevant skills
4. Explain specifically how you can contribute to their current projects as an intern
5. Include a clear, humble ask for an internship opportunity or a brief call
6. End with a professional signature including all contact details

Tone: Confident but humble, enthusiastic, professional. NOT generic.
Length: 150-250 words (excluding signature).

Format the email with "Subject: " on the first line, then a blank line, then the email body."""
    return generate_text(prompt, temperature=0.7, max_tokens=1024)


def draft_linkedin_comment(post_content, post_author, user_interests):
    """Generate a brief, passionate LinkedIn comment draft."""
    prompt = f"""Write a brief LinkedIn comment on this post.

Post by: {post_author}
Post content: {post_content[:2000]}

Your areas of interest/expertise: {user_interests}

Rules:
- Maximum 2-3 sentences
- Reference something SPECIFIC from the post
- Show genuine passion and curiosity
- Add a brief insight or thoughtful question
- Do NOT say "Great post!" or anything generic
- Sound like a real person, not a bot
- Show you actually read and thought about the post

Write ONLY the comment text, nothing else."""
    return generate_text(prompt, temperature=0.8, max_tokens=200)


def parse_resume_text(resume_text):
    """Extract structured data from resume text using Gemini."""
    prompt = f"""Extract structured information from this resume.

Resume Text:
{resume_text[:5000]}

Return a JSON object with these fields:
{{
    "name": "Full name",
    "email": "Email address",
    "phone": "Phone number",
    "linkedin_url": "LinkedIn profile URL",
    "github_url": "GitHub profile URL",
    "portfolio_url": "Portfolio/website URL",
    "skills": ["skill1", "skill2", ...],
    "interests": ["area of interest 1", "area of interest 2", ...],
    "experience": "Brief summary of experience in 2-3 sentences",
    "target_roles": ["role1", "role2", ...]
}}

For any field not found in the resume, use null.
For skills and interests, extract at least 5-10 items each if possible.
Interests should include both technical areas AND industry domains."""
    return generate_json(prompt, temperature=0.2)
