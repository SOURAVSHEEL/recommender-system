# """
# url_fetcher.py — Fetch & extract JD text from a URL
# """

# import logging
# import re

# import requests
# from bs4 import BeautifulSoup

# log = logging.getLogger(__name__)


# def is_url(text: str) -> bool:
#     return bool(re.match(r"https?://", text.strip()))


# def fetch_jd_from_url(url: str) -> str:
#     """Fetch a URL and return cleaned page text for use as query."""
#     log.info("Fetching JD from URL: %s", url)

#     resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
#     resp.raise_for_status()
#     log.debug("HTTP %s — content length: %d bytes", resp.status_code, len(resp.content))

#     soup = BeautifulSoup(resp.text, "html.parser")
#     for tag in soup(["script", "style", "nav", "footer", "header"]):
#         tag.decompose()

#     text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))[:3000]
#     log.info("JD text extracted — %d chars", len(text))

#     return text

import logging
import re
import requests
from bs4 import BeautifulSoup
from typing import List

log = logging.getLogger(__name__)

def is_url(text: str) -> bool:
    return bool(re.match(r"https?://", text.strip()))

def extract_skills(text: str) -> List[str]:
    """Extract skills from JD text"""
    patterns = [
        r'(skills?|abilities?|requirements?|responsibilities?)[^:]*:\s*([^\.]+?)(?=\.|$|\n)',
        r'(must have|required|experience with)\s+([^\.]+?)(?=\.|$|\n)',
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})(?:\s+(?:programming|development|experience|skills?))'
    ]
    skills = []
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.I)
        for match in matches:
            skill = match.group(2).strip().lower()
            if 2 < len(skill) < 50:
                skills.extend([s.strip() for s in re.split(r'[,\n;]', skill) if len(s) > 2])
    return list(set(skills[:10]))  # Top 10 unique skills

def fetch_jd_from_url(url: str) -> str:
    """Fetch URL and return enhanced JD text with extracted skills"""
    log.info("Fetching JD from URL: %s", url)
    
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    resp.raise_for_status()
    
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    
    text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))
    
    # Extract JD-specific section if available
    jd_section = soup.find(['div', 'section'], class_=re.compile(r'(job|description|responsibilities|requirements)', re.I))
    if jd_section:
        text = jd_section.get_text(separator=' ', strip=True)
    
    # Extract skills and enhance
    skills = extract_skills(text)
    skills_text = f"Key skills: {', '.join(skills)}." if skills else ""
    
    enhanced_text = f"{skills_text} {text}"[:2000]
    log.info("JD enhanced - %d chars, %d skills", len(enhanced_text), len(skills))
    
    return enhanced_text
