import json
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from utils import clean_text, safe_urljoin, tokenize

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SEOGapAnalyzer/1.0; +https://example.com/bot)"
}

def fetch_html(url: str, timeout: int = 20) -> str:
    r = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text

def _remove_noise(soup: BeautifulSoup):
    # Remove obvious noise
    for tag in soup(["script", "style", "noscript", "svg", "canvas"]):
        tag.decompose()
    for tag in soup.find_all(True):
        # remove hidden elements
        style = (tag.get("style") or "").lower()
        if "display:none" in style or "visibility:hidden" in style:
            tag.decompose()

def extract_schema_jsonld(soup: BeautifulSoup):
    schemas = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        txt = script.get_text(" ", strip=True)
        if not txt:
            continue
        try:
            data = json.loads(txt)
            schemas.append(data)
        except Exception:
            # some sites put multiple JSON objects or trailing commas
            # keep raw as fallback
            schemas.append({"_raw": txt})
    return schemas

def extract_meta(soup: BeautifulSoup):
    title = clean_text(soup.title.get_text(" ", strip=True)) if soup.title else ""
    desc = ""
    canonical = ""
    meta_desc = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    if meta_desc and meta_desc.get("content"):
        desc = clean_text(meta_desc["content"])
    link_can = soup.find("link", rel=re.compile("canonical", re.I))
    if link_can and link_can.get("href"):
        canonical = clean_text(link_can["href"])
    return {"title": title, "meta_description": desc, "canonical": canonical}

def extract_headings(soup: BeautifulSoup):
    headings = {f"h{i}": [] for i in range(1, 7)}
    for i in range(1, 7):
        for h in soup.find_all(f"h{i}"):
            t = clean_text(h.get_text(" ", strip=True))
            if t:
                headings[f"h{i}"].append(t)
    return headings

def extract_internal_links(soup: BeautifulSoup, base_url: str):
    base_netloc = urlparse(base_url).netloc.lower()
    links = []
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue
        full = safe_urljoin(base_url, href)
        netloc = urlparse(full).netloc.lower()
        if netloc == base_netloc:
            anchor = clean_text(a.get_text(" ", strip=True))
            links.append({"url": full, "anchor": anchor})
    return links

def extract_alt_texts(soup: BeautifulSoup):
    alts = []
    for img in soup.find_all("img"):
        alt = clean_text(img.get("alt") or "")
        if alt:
            alts.append(alt)
    return alts

def detect_faq_pairs(soup: BeautifulSoup):
    """
    Best-effort FAQ detection:
    - Looks for sections with 'faq' in id/class
    - Also tries common accordion patterns
    """
    faqs = []

    # 1) Schema FAQPage (if present) is handled elsewhere. This is DOM fallback.
    candidates = []
    for tag in soup.find_all(True):
        cls = " ".join(tag.get("class") or []).lower()
        tid = (tag.get("id") or "").lower()
        if "faq" in cls or "faq" in tid:
            candidates.append(tag)

    # 2) Accordion-ish: buttons + panels
    if not candidates:
        for tag in soup.find_all(["section", "div"]):
            cls = " ".join(tag.get("class") or []).lower()
            if any(k in cls for k in ["accordion", "toggle", "collapse"]):
                candidates.append(tag)

    seen = set()
    for c in candidates[:5]:  # cap
        # Try to interpret Q/A patterns
        qs = c.find_all(["h3", "h4", "button"])
        for q in qs:
            qtxt = clean_text(q.get_text(" ", strip=True))
            if not qtxt or len(qtxt) < 6:
                continue
            # find nearest sibling text
            atxt = ""
            nxt = q.find_next_sibling()
            if nxt:
                atxt = clean_text(nxt.get_text(" ", strip=True))
            if not atxt:
                # sometimes answer is next element after parent
                parent = q.parent
                if parent:
                    nxt2 = parent.find_next_sibling()
                    if nxt2:
                        atxt = clean_text(nxt2.get_text(" ", strip=True))
            if qtxt and atxt:
                key = (qtxt.lower(), atxt.lower()[:60])
                if key in seen:
                    continue
                seen.add(key)
                faqs.append({"q": qtxt, "a": atxt})

    # keep it clean
    faqs = [x for x in faqs if len(x["a"]) > 20]
    return faqs[:30]

def extract_sections_by_headings(soup: BeautifulSoup):
    """
    Build sections by walking H1/H2/H3 and capturing following text until next heading of same/higher level.
    This is a deterministic, comparable “content blocks” output.
    """
    sections = []
    heading_tags = soup.find_all(re.compile("^h[1-3]$", re.I))
    if not heading_tags:
        return sections

    for idx, h in enumerate(heading_tags):
        level = int(h.name[1])
        title = clean_text(h.get_text(" ", strip=True))
        if not title:
            continue

        content_parts = []
        cur = h.next_siblings
        for sib in cur:
            if getattr(sib, "name", None) and re.match(r"^h[1-3]$", sib.name, re.I):
                # stop at next major heading
                break
            # include paragraphs/lists
            if getattr(sib, "get_text", None):
                txt = clean_text(sib.get_text(" ", strip=True))
                if txt and len(txt) > 20:
                    content_parts.append(txt)

        body = clean_text(" ".join(content_parts))
        sections.append({"level": level, "heading": title, "text": body})

    # remove very thin sections
    sections = [s for s in sections if len(s["text"]) > 60 or len(s["heading"]) > 10]
    return sections[:80]

def extract_page(url: str, use_js: bool = False) -> dict:
    """
    Deterministic extractor.
    If use_js=True, you can swap fetch_html() with a playwright renderer (see README).
    """
    html = fetch_html(url)
    soup = BeautifulSoup(html, "lxml")
    _remove_noise(soup)

    meta = extract_meta(soup)
    headings = extract_headings(soup)
    sections = extract_sections_by_headings(soup)
    schema = extract_schema_jsonld(soup)
    links_internal = extract_internal_links(soup, url)
    alts = extract_alt_texts(soup)
    faqs_dom = detect_faq_pairs(soup)

    # page text for keyword density
    text = clean_text(soup.get_text(" ", strip=True))

    tokens = tokenize(text)
    word_count = len(tokens)

    return {
        "url": url,
        "meta": meta,
        "headings": headings,
        "sections": sections,
        "faq_dom": faqs_dom,
        "schema_jsonld": schema,
        "internal_links": links_internal,
        "image_alt_texts": alts,
        "text": text,
        "word_count": word_count,
    }
