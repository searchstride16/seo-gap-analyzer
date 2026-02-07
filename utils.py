import re
import time
from urllib.parse import urlparse, urljoin

STOPWORDS = set("""
a an the and or but if then else when while for to of in on at by with from as is are was were be been being
this that these those it its you your we our they their i me my he she them his her
can could should would may might will just
""".split())

def clean_text(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def normalize_ws_lower(s: str) -> str:
    return clean_text(s).lower()

def safe_urljoin(base: str, href: str) -> str:
    try:
        return urljoin(base, href)
    except Exception:
        return href

def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

def tokenize(text: str):
    # simple tokenizer for keyword density
    text = normalize_ws_lower(text)
    text = re.sub(r"[^a-z0-9\s\-]", " ", text)
    tokens = [t for t in text.split() if t and t not in STOPWORDS and len(t) > 2]
    return tokens

def rate_limit_sleep(last_ts: float, min_interval_sec: float = 1.0):
    now = time.time()
    dt = now - last_ts
    if dt < min_interval_sec:
        time.sleep(min_interval_sec - dt)
    return time.time()
