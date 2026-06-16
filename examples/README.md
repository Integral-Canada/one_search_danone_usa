# examples/

Sample data files showing the expected format for pipeline inputs and outputs. Use these to understand data structure before connecting live sources.

| File | What it shows |
|---|---|
| `MASTERLIST - Oikos OneSearch - Example.csv` | Completed 57-column Masterlist output for Oikos USA |
| `activia_ca_onesearch_dashboard.html` | Completed OneSearch dashboard for Activia Canada |
| `activia_ca_onesearch_dashboard_ref.html` | Reference version of the Activia Canada dashboard |

The pipeline reads live data from Google Sheets — these files are not used at runtime. See `export_requirements_oikos.md` in `docs/` for the full spec of what each source export should look like.
