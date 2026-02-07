# SEO Gap Analyzer (Streamlit)

This tool compares your page vs competitor pages and outputs:
- Structural gaps (normalized sections)
- Technical gaps (schema presence heuristics)
- Depth gaps (word count, internal links, FAQ volume)
- Keyword density (yours vs competitor average)
- Competitor semantic terms (lightweight)

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
