import re
from rapidfuzz import fuzz
from utils import normalize_ws_lower, clean_text

# Add your own niche-specific synonyms here over time:
SECTION_SYNONYMS = [
    ("about_team", [r"meet (the|our) (doctor|dentist|dentists|team)", r"about (the )?team", r"our team", r"who we are"]),
    ("testimonials", [r"testimonials", r"reviews", r"patient stories", r"client stories", r"what (clients|patients) say"]),
    ("services", [r"services", r"what we offer", r"treatments", r"solutions", r"service areas?"]),
    ("faq", [r"faq", r"frequently asked", r"questions"]),
    ("pricing", [r"pricing", r"fees", r"cost", r"plans"]),
    ("why_choose_us", [r"why choose us", r"why us", r"our difference", r"what makes us"]),
    ("contact", [r"contact", r"book (now|online)", r"get in touch", r"request (a )?quote"]),
]

def normalize_heading_to_bucket(heading: str) -> str:
    h = normalize_ws_lower(heading)
    for bucket, patterns in SECTION_SYNONYMS:
        for p in patterns:
            if re.search(p, h):
                return bucket
    return "other"

def fuzzy_equivalent(a: str, b: str, threshold: int = 88) -> bool:
    """
    For headings: detects close matches like “Meet our Dentists” vs “Meet the Doctor”
    after normalization. Bucketing handles most, this is extra.
    """
    a2 = normalize_ws_lower(a)
    b2 = normalize_ws_lower(b)
    if not a2 or not b2:
        return False
    return fuzz.token_set_ratio(a2, b2) >= threshold

def normalize_page(extracted: dict) -> dict:
    sections = extracted.get("sections", [])
    norm_sections = []
    for s in sections:
        bucket = normalize_heading_to_bucket(s.get("heading", ""))
        norm_sections.append({**s, "bucket": bucket})

    return {**extracted, "sections_normalized": norm_sections}
