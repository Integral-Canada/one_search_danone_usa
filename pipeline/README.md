# pipeline/

Core Python module for the OneSearch pipeline. These files are imported by `run_onesearch.py` at the repo root — you don't run them directly.

| File | Role |
|---|---|
| `normalize.py` | Text and number cleaning shared across all sources |
| `ingest.py` | Normalizes raw rows from GSC, SQR, SE Ranking, and Keyword Study into standard field names |
| `ingest_ga4.py` | Parses GA4 page-level exports into a `{url_path: key_events}` lookup |
| `merge.py` | Full outer join of GSC and SQR onto a unified keyword spine |
| `trigram.py` | Character trigram index and Jaccard similarity — the core of fuzzy matching |
| `match_se.py` | Matches SE Ranking keywords to the unified spine (threshold ≥ 0.60) |
| `match_ks.py` | Matches Keyword Study keywords to the unified spine (≥ 0.65 auto, 0.50–0.65 review) |
| `format_rows.py` | Shapes merged data into the 57-column Masterlist structure |
| `enrich.py` | Post-write SE Ranking API enrichment to fill in missing search volumes |
