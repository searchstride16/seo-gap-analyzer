from collections import Counter, defaultdict
import pandas as pd

from utils import tokenize, normalize_ws_lower
from normalize import normalize_heading_to_bucket

def keyword_density(text: str, keywords: list[str]) -> dict:
    tokens = tokenize(text)
    total = max(len(tokens), 1)
    joined = " ".join(tokens)

    out = {}
    for kw in keywords:
        k = normalize_ws_lower(kw)
        if not k:
            continue
        # Count occurrences as a phrase in token-joined text
        # (simple method; good enough for density comparison)
        count = joined.count(k)
        out[kw] = {
            "count": count,
            "density_pct": round((count / total) * 100, 4)
        }
    return out

def summarize_structure(page: dict) -> dict:
    headings = page.get("headings", {})
    h1 = headings.get("h1", [])
    h2 = headings.get("h2", [])
    h3 = headings.get("h3", [])

    sections = page.get("sections_normalized") or []
    buckets = [s.get("bucket", "other") for s in sections]
    bucket_counts = Counter(buckets)

    schema = page.get("schema_jsonld", [])
    has_faq_schema = any(_schema_has_type(x, "FAQPage") for x in schema)
    has_org_schema = any(_schema_has_type(x, "Organization") for x in schema)
    has_localbiz_schema = any(_schema_has_any_type(x, ["LocalBusiness", "Dentist", "Plumber", "ProfessionalService"]) for x in schema)

    return {
        "url": page.get("url", ""),
        "title": page.get("meta", {}).get("title", ""),
        "meta_description": page.get("meta", {}).get("meta_description", ""),
        "canonical": page.get("meta", {}).get("canonical", ""),
        "h1_count": len(h1),
        "h2_count": len(h2),
        "h3_count": len(h3),
        "bucket_counts": dict(bucket_counts),
        "word_count": page.get("word_count", 0),
        "internal_links_count": len(page.get("internal_links", [])),
        "image_alt_count": len(page.get("image_alt_texts", [])),
        "faq_dom_count": len(page.get("faq_dom", [])),
        "has_faq_schema": has_faq_schema,
        "has_org_schema": has_org_schema,
        "has_localbiz_schema": has_localbiz_schema,
    }

def _schema_has_type(obj, type_name: str) -> bool:
    try:
        if isinstance(obj, dict):
            t = obj.get("@type")
            if isinstance(t, str):
                return t.lower() == type_name.lower()
            if isinstance(t, list):
                return any(x.lower() == type_name.lower() for x in t if isinstance(x, str))
            # graph
            g = obj.get("@graph")
            if isinstance(g, list):
                return any(_schema_has_type(x, type_name) for x in g)
        if isinstance(obj, list):
            return any(_schema_has_type(x, type_name) for x in obj)
    except Exception:
        return False
    return False

def _schema_has_any_type(obj, type_names: list[str]) -> bool:
    return any(_schema_has_type(obj, t) for t in type_names)

def competitor_average(struct_summaries: list[dict]) -> dict:
    # compute average counts across competitors
    avg = {}
    if not struct_summaries:
        return avg

    numeric_fields = [
        "h1_count", "h2_count", "h3_count", "word_count",
        "internal_links_count", "image_alt_count", "faq_dom_count"
    ]
    bool_fields = ["has_faq_schema", "has_org_schema", "has_localbiz_schema"]

    for f in numeric_fields:
        vals = [s.get(f, 0) or 0 for s in struct_summaries]
        avg[f] = round(sum(vals) / max(len(vals), 1), 2)

    for f in bool_fields:
        vals = [1 if s.get(f) else 0 for s in struct_summaries]
        avg[f] = round(sum(vals) / max(len(vals), 1), 2)  # share of competitors

    # bucket averages
    bucket_totals = defaultdict(int)
    for s in struct_summaries:
        for k, v in (s.get("bucket_counts") or {}).items():
            bucket_totals[k] += v
    avg["bucket_counts_avg"] = {k: round(v / len(struct_summaries), 2) for k, v in bucket_totals.items()}
    return avg

def identify_gaps(yours: dict, competitors: list[dict]) -> pd.DataFrame:
    """
    Returns structured, actionable gaps.
    """
    your_sum = summarize_structure(yours)
    comp_sums = [summarize_structure(c) for c in competitors]
    comp_avg = competitor_average(comp_sums)

    rows = []

    # Structural bucket gaps
    your_buckets = your_sum.get("bucket_counts", {})
    comp_bucket_avg = comp_avg.get("bucket_counts_avg", {})

    for bucket, avg_count in comp_bucket_avg.items():
        your_count = your_buckets.get(bucket, 0)
        if avg_count >= 0.8 and your_count == 0 and bucket != "other":
            rows.append({
                "gap_type": "Structural",
                "gap": f"Missing section bucket: {bucket}",
                "why_it_matters": "Competitors commonly include this section; it often improves relevance, trust, or conversions.",
                "recommended_action": _action_for_bucket(bucket),
                "competitor_avg": avg_count,
                "yours": your_count,
                "confidence": "High"
            })

    # Technical gaps
    for field, label in [
        ("has_faq_schema", "FAQ schema"),
        ("has_org_schema", "Organization schema"),
        ("has_localbiz_schema", "LocalBusiness/Service schema"),
    ]:
        comp_share = comp_avg.get(field, 0)
        yours_bool = bool(your_sum.get(field))
        if comp_share >= 0.6 and not yours_bool:
            rows.append({
                "gap_type": "Technical",
                "gap": f"Missing {label}",
                "why_it_matters": "If most competitors implement it, adding it can strengthen entity signals and eligibility for rich results (where applicable).",
                "recommended_action": f"Add {label} in JSON-LD (validate with Schema.org validator).",
                "competitor_avg": comp_share,
                "yours": 1 if yours_bool else 0,
                "confidence": "High"
            })

    # Content depth gaps (counts)
    for metric, nice, action in [
        ("word_count", "Content depth (word count)", "Expand content with niche-relevant explanations, processes, and location intent."),
        ("internal_links_count", "Internal links", "Add relevant internal links to supporting service pages, location pages, and proof pages (reviews/case studies)."),
        ("faq_dom_count", "FAQ coverage", "Add 4–8 FAQs matching high-intent queries (pricing, timeline, emergency, insurance, service areas)."),
    ]:
        your_v = your_sum.get(metric, 0) or 0
        comp_v = comp_avg.get(metric, 0) or 0
        if comp_v > 0 and your_v < comp_v * 0.65:
            rows.append({
                "gap_type": "Depth",
                "gap": f"Below competitor average: {nice}",
                "why_it_matters": "Competitors provide more supporting content; this often correlates with better topical coverage and rankings.",
                "recommended_action": action,
                "competitor_avg": comp_v,
                "yours": your_v,
                "confidence": "Medium"
            })

    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame([{
            "gap_type": "None detected (basic)",
            "gap": "No major structural/technical gaps detected by baseline rules.",
            "why_it_matters": "This baseline is rule-based; consider adding keyword/intent gaps for deeper results.",
            "recommended_action": "Add keyword + intent gap module (density + semantic phrases).",
            "competitor_avg": "",
            "yours": "",
            "confidence": ""
        }])
    return df

def _action_for_bucket(bucket: str) -> str:
    actions = {
        "about_team": "Add an About/Team section. Include credentials, experience, approach, and photos. Use niche + location terms naturally.",
        "testimonials": "Add Reviews/Testimonials. Include short snippets, star ratings (without review schema abuse), and outcomes.",
        "services": "Add a Services/What We Offer section with clear sub-services and internal links to dedicated pages.",
        "faq": "Add an FAQ section and expand accordions. Target long-tail questions users search before booking.",
        "pricing": "Add Pricing/Fees guidance (even ranges) + what affects price. Users and Google love clarity.",
        "why_choose_us": "Add Why Choose Us with 5–7 differentiators tied to outcomes, trust, and process.",
        "contact": "Improve conversion block: clear CTA, phone, booking link, service area coverage, opening hours (if relevant).",
    }
    return actions.get(bucket, "Add/Improve this section based on competitor patterns and search intent.")

def semantic_terms_from_competitors(competitors: list[dict], top_n: int = 40) -> list[tuple[str, int]]:
    """
    Lightweight semantic terms: top tokens across competitors (excluding stopwords already handled).
    Use for 'relevant terms you are missing' module.
    """
    counter = Counter()
    for c in competitors:
        tokens = tokenize(c.get("text", ""))
        counter.update(tokens)
    return counter.most_common(top_n)
