# scripts/

Utility and diagnostic scripts. These are standalone — run them individually for specific tasks, not as part of the main pipeline.

| File | What it does |
|---|---|
| `diagnose_se.py` | Debugs SE Ranking fuzzy match quality — shows which keywords matched, which didn't, and why |
| `fetch_se_ranking_volumes.py` | Fetches search volumes from the SE Ranking API for a given keyword list |
| `build_html_oikos.py` | Builds the Oikos USA OneSearch HTML dashboard from Masterlist data |
| `build_n8n_workflow.py` | Generates an n8n workflow JSON for pipeline automation |
| `patch_commentary.py` | Patches commentary JSON exports with updated annotations |
| `run_taxonomy_enrichment.py` | Standalone taxonomy enrichment run (separate from the main pipeline) |
| `pipeline_sample_test.py` | Integration test — runs the full pipeline against a small sample dataset |
| `sample_test.py` | Unit-level tests for individual pipeline modules |
