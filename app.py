import streamlit as st
import pandas as pd

from extractor import extract_page
from normalize import normalize_page
from analyze import (
    identify_gaps,
    keyword_density,
    summarize_structure,
    semantic_terms_from_competitors
)
from utils import rate_limit_sleep

st.set_page_config(page_title="SEO Gap Analyzer", layout="wide")

st.title("SEO Gap Analyzer (Competitors vs Yours)")
st.caption("Deterministic extraction → normalization → structured gap detection + keyword density.")

with st.sidebar:
    st.header("Inputs")
    your_url = st.text_input("Your page URL", placeholder="https://yoursite.com/service-page/")
    comp_urls_text = st.text_area(
        "Competitor URLs (one per line)",
        placeholder="https://competitor1.com/page/\nhttps://competitor2.com/page/"
    )
    niche = st.text_input("Niche (optional)", placeholder="e.g., dental, plumbing, hvac")
    keywords_text = st.text_area(
        "Target keywords (one per line)",
        placeholder="dental seo\nseo for dentists\nlocal seo for dentists"
    )
    min_delay = st.slider("Polite crawl delay (seconds)", 0.0, 5.0, 1.0, 0.5)
    run = st.button("Run analysis")

def parse_lines(txt: str):
    return [x.strip() for x in (txt or "").splitlines() if x.strip()]

if run:
    if not your_url or not comp_urls_text.strip():
        st.error("Please provide your URL and at least one competitor URL.")
        st.stop()

    comp_urls = parse_lines(comp_urls_text)
    keywords = parse_lines(keywords_text)

    st.info(f"Analyzing: 1 your page + {len(comp_urls)} competitor page(s)")

    last_ts = 0.0

    # Extract yours
    with st.spinner("Extracting your page..."):
        last_ts = rate_limit_sleep(last_ts, min_delay)
        your_raw = extract_page(your_url)
        your_page = normalize_page(your_raw)

    # Extract competitors
    competitors = []
    for i, u in enumerate(comp_urls, 1):
        with st.spinner(f"Extracting competitor {i}/{len(comp_urls)}..."):
            try:
                last_ts = rate_limit_sleep(last_ts, min_delay)
                c_raw = extract_page(u)
                c_page = normalize_page(c_raw)
                competitors.append(c_page)
            except Exception as e:
                st.warning(f"Failed to fetch {u}: {e}")

    if not competitors:
        st.error("All competitor fetches failed. Try different URLs or enable JS rendering in your own environment.")
        st.stop()

    # Summary
    st.subheader("Page summaries")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Your page")
        st.json(summarize_structure(your_page))

    with col2:
        st.markdown("### Competitors (summaries)")
        comp_summaries = [summarize_structure(c) for c in competitors]
        st.dataframe(pd.DataFrame(comp_summaries))

    # Gaps
    st.subheader("Identified gaps (baseline rules)")
    gaps_df = identify_gaps(your_page, competitors)
    st.dataframe(gaps_df, use_container_width=True)

    # Keyword density
    if keywords:
        st.subheader("Keyword density (yours vs competitor average)")
        your_kd = keyword_density(your_page.get("text", ""), keywords)
        comp_kds = [keyword_density(c.get("text", ""), keywords) for c in competitors]

        # Average competitor density
        rows = []
        for kw in keywords:
            comp_counts = [d.get(kw, {}).get("count", 0) for d in comp_kds]
            comp_density = [d.get(kw, {}).get("density_pct", 0.0) for d in comp_kds]

            rows.append({
                "keyword": kw,
                "your_count": your_kd.get(kw, {}).get("count", 0),
                "your_density_pct": your_kd.get(kw, {}).get("density_pct", 0.0),
                "competitor_avg_count": round(sum(comp_counts) / max(len(comp_counts), 1), 2),
                "competitor_avg_density_pct": round(sum(comp_density) / max(len(comp_density), 1), 4),
                "gap_hint": "Increase usage in relevant sections (not stuffing)" if your_kd.get(kw, {}).get("density_pct", 0.0) < (sum(comp_density) / max(len(comp_density), 1)) * 0.7 else ""
            })

        st.dataframe(pd.DataFrame(rows), use_container_width=True)

    # Semantic terms
    st.subheader("Competitor semantic terms (top tokens)")
    terms = semantic_terms_from_competitors(competitors, top_n=60)
    st.write("Use this list to spot niche phrases competitors emphasize. Filter out irrelevant tokens manually.")
    st.dataframe(pd.DataFrame(terms, columns=["term", "count"]), use_container_width=True)

    st.success("Done.")
