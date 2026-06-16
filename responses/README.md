# responses/

JSON exports from completed OneSearch dashboard runs. These capture the full keyword dataset at a point in time and can be used as input when rebuilding a dashboard without re-running the pipeline.

File naming convention: `{client}_{market}_commentary_{YYYY-MM-DD}.json`

| File | Client | Date |
|---|---|---|
| `oikos_usa_commentary_2026-06-11.json` | Oikos USA | 2026-06-11 |

To use a response file in a dashboard rebuild, pass its path to `scripts/build_html_oikos.py` as the data source instead of pulling from the live Masterlist.
