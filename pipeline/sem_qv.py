"""SEM Qualified Visits (QV SEM) calculation and Brand SEM recommendation tagging.

Methodology (Thomas Joachim, Jun 2026):
  1. For each landing page in the GA4 Google Ads session export:
       LP QV rate = sum(Key Events) / sum(Sessions)
  2. For each keyword+LP row:
       Attributed QV SEM = (row Sessions / LP total Sessions) × LP total Key Events
  3. Per keyword: sum attributed QV across all landing pages
  4. Write to masterlist: Conversions SEM [P1 label] (col AC) and SEM Recommendation (col BF)

Brand SEM recommendation tags (BRAND territory keywords only):
  - Exclude:     SEO+SEM Coverage > seo_cov_threshold
                 AND SEO Position <= seo_pos_threshold
                 AND QV SEM = 0
  - Keep-Active: QV SEM > 0 AND OneSearch Coverage < seo_cov_threshold
  - Keep-Test:   OneSearch Coverage > seo_cov_threshold AND QV SEM > 0
                 (organic present but paid still adding QVs)
"""
import json
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict

from .normalize import normalize, clean_num
from .utils import sheets_get, sheets_batch_update, col_letter


# ── GA4 Ads export column variants ───────────────────────────────────────────

_KW_COL_PATTERNS   = ['requ', 'query', 'terme', 'keyword', 'search']
_LP_COL_PATTERNS   = ['page de destination', 'landing page', 'landing_page']
_SES_COL_PATTERNS  = ['sessions']
_QV_COL_PATTERNS   = ['nements cl', 'key events', '\xe9v\xe9nements']  # handles partial French match


def _find_col(headers: list, patterns: list):
    for p in patterns:
        for i, h in enumerate(headers):
            if p.lower() in str(h).lower():
                return i
    return None


def _resolve_tab(token: str, file_id: str, explicit_tab) -> str:
    """Return the tab name to use. If explicit_tab is None, returns the first sheet tab title."""
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{file_id}?fields=sheets.properties"
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(req, timeout=30) as r:
        meta = json.load(r)
    tabs = [s['properties']['title'] for s in meta['sheets']]
    if explicit_tab:
        # Find by substring match (handles non-breaking space variants)
        for t in tabs:
            if explicit_tab.strip() in t or t.strip() in explicit_tab.strip():
                return t
        raise ValueError(f"GA4 Ads tab '{explicit_tab}' not found. Available: {tabs}")
    return tabs[0]


# ── Step 1: Read GA4 Ads export ───────────────────────────────────────────────

def read_ga4_ads(token: str, file_id: str, tab=None) -> list:
    """Read GA4 Google Ads session export from Sheets.

    Returns list of dicts: {keyword, lp, sessions, key_events}
    Handles metadata rows before the header and strips query strings from LPs.
    """
    resolved_tab = _resolve_tab(token, file_id, tab)
    print(f"  GA4 Ads tab resolved: {repr(resolved_tab)}", flush=True)

    raw = sheets_get(token, file_id, f"'{resolved_tab}'!A1:L10000")
    if not raw:
        raise RuntimeError(f"GA4 Ads tab '{resolved_tab}' returned no data")

    # Find header row: first row that has both a session-like column and a page-like column
    header_idx = None
    for i, row in enumerate(raw):
        joined = ' '.join(str(c) for c in row).lower()
        if 'sessions' in joined and ('page' in joined or 'requ' in joined or 'destination' in joined):
            header_idx = i
            break

    if header_idx is None:
        raise RuntimeError("GA4 Ads export: could not locate header row (needs 'sessions' + 'page' columns)")

    headers = [str(h).strip() for h in raw[header_idx]]
    col_kw  = _find_col(headers, _KW_COL_PATTERNS)
    col_lp  = _find_col(headers, _LP_COL_PATTERNS)
    col_ses = _find_col(headers, _SES_COL_PATTERNS)
    col_qv  = _find_col(headers, _QV_COL_PATTERNS)

    missing = [name for name, c in [('keyword', col_kw), ('landing_page', col_lp),
                                     ('sessions', col_ses), ('key_events', col_qv)] if c is None]
    if missing:
        raise RuntimeError(
            f"GA4 Ads export: could not find columns {missing}.\n"
            f"Headers found: {headers}"
        )

    rows = []
    for row in raw[header_idx + 1:]:
        if len(row) <= max(col_kw, col_lp, col_ses, col_qv):
            continue
        kw = str(row[col_kw]).strip()
        lp = str(row[col_lp]).strip().split('?')[0].rstrip('/')  # strip query strings
        if not lp:
            lp = '/'
        try:
            ses = clean_num(row[col_ses])
            qv  = clean_num(row[col_qv])
        except (ValueError, IndexError):
            continue
        if not kw or kw.startswith('#'):
            continue
        rows.append({'keyword': kw, 'lp': lp, 'sessions': ses, 'key_events': qv})

    print(f"  GA4 Ads: {len(rows)} rows parsed", flush=True)
    return rows


# ── Step 2: Calculate QV SEM per keyword ─────────────────────────────────────

def calculate_qv_sem(ga4_rows: list) -> dict:
    """Calculate QV SEM per normalized keyword using LP-rate method.

    Returns: {normalized_keyword: attributed_qv_sem (float)}
    """
    # Aggregate sessions and key_events per LP
    lp_totals: dict = defaultdict(lambda: {'sessions': 0.0, 'key_events': 0.0})
    for row in ga4_rows:
        lp_totals[row['lp']]['sessions']   += row['sessions']
        lp_totals[row['lp']]['key_events'] += row['key_events']

    # LP QV rate = key_events / sessions (per landing page)
    lp_rates = {
        lp: (v['key_events'] / v['sessions']) if v['sessions'] > 0 else 0.0
        for lp, v in lp_totals.items()
    }

    # Distribute QV to keywords: attributed_QV = (row_sessions / lp_total_sessions) × lp_key_events
    kw_qv: dict = defaultdict(float)
    for row in ga4_rows:
        lp = row['lp']
        lp_total_ses = lp_totals[lp]['sessions']
        if lp_total_ses <= 0 or row['sessions'] <= 0:
            continue
        share = row['sessions'] / lp_total_ses
        attributed = share * lp_totals[lp]['key_events']
        norm_kw = normalize(row['keyword'])
        kw_qv[norm_kw] += attributed

    total_qv = sum(kw_qv.values())
    unassigned = sum(v['key_events'] for v in lp_totals.values()) - total_qv
    print(f"  QV SEM total: {total_qv:.1f} | Unassigned (no kw match): {unassigned:.1f}", flush=True)
    return dict(kw_qv)


# ── Step 3: Tag Brand SEM recommendations ────────────────────────────────────

def tag_sem_recommendations(
    masterlist_rows: list,
    qv_sem_map: dict,
    seo_cov_threshold: float = 0.10,
    seo_pos_threshold: int = 5,
    competitor_blocklist: set = None,
    p1_label: str = 'Q1 2026',
) -> list:
    """Tag BRAND keywords with Exclude / Keep-Active / Keep-Test.

    masterlist_rows: list of dicts (full masterlist, all territories).
    qv_sem_map: {normalized_keyword: qv_sem} from calculate_qv_sem().

    Returns list of (row_index, keyword, tag) for BRAND rows only.
    row_index is 0-based (excluding header).

    Issue 2 fix: uses OneSearch coverage (SEO + SEM clicks / volume), not SEO-only.
    """
    if competitor_blocklist is None:
        competitor_blocklist = set()

    results = []
    for idx, row in enumerate(masterlist_rows):
        if str(row.get('TOPICS', '')).strip().upper() != 'BRAND':
            continue
        kw = str(row.get('Keyword', '')).strip()
        if not kw:
            continue

        norm_kw = normalize(kw)
        if norm_kw in competitor_blocklist:
            continue

        # OneSearch coverage = (SEO clicks + SEM clicks) / volume  [Issue 2 fix]
        seo_clicks = clean_num(row.get(f'Clics SEO {p1_label}', 0))
        sem_clicks = clean_num(row.get(f'Clics SEM {p1_label}', 0))
        volume     = clean_num(row.get('Average Search Volume', 0))
        os_cov     = (seo_clicks + sem_clicks) / volume if volume > 0 else 0.0

        pos   = clean_num(row.get('Position SE Ranking', 0))
        qv_sem = qv_sem_map.get(norm_kw, 0.0)

        if os_cov > seo_cov_threshold and (pos <= seo_pos_threshold or pos == 0) and qv_sem == 0:
            tag = 'Exclude'
        elif qv_sem > 0 and os_cov < seo_cov_threshold:
            tag = 'Keep-Active'
        elif os_cov > seo_cov_threshold and qv_sem > 0:
            tag = 'Keep-Test'
        else:
            tag = ''  # unclassified — leave blank

        results.append({'row_index': idx, 'keyword': kw, 'tag': tag, 'qv_sem': qv_sem})

    counts = {'Exclude': 0, 'Keep-Active': 0, 'Keep-Test': 0, '': 0}
    for r in results:
        counts[r['tag']] = counts.get(r['tag'], 0) + 1
    print(f"  Brand SEM tags — Exclude: {counts['Exclude']} | "
          f"Keep-Active: {counts['Keep-Active']} | "
          f"Keep-Test: {counts['Keep-Test']} | "
          f"Unclassified: {counts.get('', 0)}", flush=True)
    return results


# ── Step 4: Write results to Masterlist ──────────────────────────────────────

def write_qv_sem(
    token: str,
    master_id: str,
    master_tab: str,
    qv_sem_map: dict,
    sem_reco: list,
    p1_label: str = 'Q1 2026',
) -> None:
    """Write QV SEM values (col AC) and SEM Recommendation tags (col BF) to Masterlist.

    Reads the Masterlist header to resolve exact column positions dynamically.
    Extends the sheet if BF column does not yet exist.
    """
    print(f"\nWriting QV SEM → Masterlist '{master_tab}'...", flush=True)
    col_qv_name   = f'Conversions SEM {p1_label}'
    col_reco_name = 'SEM Recommendation'

    # Read full masterlist to resolve column positions
    header_raw = sheets_get(token, master_id, f"'{master_tab}'!1:1")
    if not header_raw:
        raise RuntimeError(f"Masterlist '{master_tab}' returned empty header row")

    headers = [str(h) for h in header_raw[0]]

    def _col_pos(name):
        try:
            return headers.index(name) + 1  # 1-based
        except ValueError:
            return None

    ac_pos   = _col_pos(col_qv_name)
    bf_pos   = _col_pos(col_reco_name)

    if ac_pos is None:
        raise RuntimeError(
            f"Column '{col_qv_name}' not found in Masterlist headers.\n"
            f"Verify the masterlist was built with the correct period label.\n"
            f"Headers (first 10): {headers[:10]}"
        )

    # If BF column missing, append it
    if bf_pos is None:
        bf_pos = len(headers) + 1
        sheets_batch_update(token, master_id, [
            (f"'{master_tab}'!{col_letter(bf_pos)}1", [[col_reco_name]])
        ])
        headers.append(col_reco_name)
        print(f"  Added '{col_reco_name}' as column {col_letter(bf_pos)}", flush=True)

    ac_letter = col_letter(ac_pos)
    bf_letter = col_letter(bf_pos)

    # Read all masterlist keywords (col B = Keyword, row 2+)
    kw_raw = sheets_get(token, master_id, f"'{master_tab}'!B2:B")
    all_keywords = [str(r[0]) if r else '' for r in kw_raw]
    n_rows = len(all_keywords)

    # Build keyword → row-index map (0-based, row 2 = index 0)
    kw_to_idx: dict = {}
    for i, kw in enumerate(all_keywords):
        kw_to_idx[normalize(kw)] = i

    # Build AC column values (QV SEM for every row)
    ac_values = []
    for kw in all_keywords:
        qv = qv_sem_map.get(normalize(kw), '')
        ac_values.append([round(qv, 4) if qv else ''])

    # Build BF column values (tag for BRAND rows only; '' for all others)
    bf_values = [[''] for _ in range(n_rows)]
    for rec in sem_reco:
        row_idx = rec['row_index']
        if 0 <= row_idx < n_rows:
            bf_values[row_idx] = [rec['tag']]

    # Write in one batch
    updates = [
        (f"'{master_tab}'!{ac_letter}2:{ac_letter}{n_rows + 1}", ac_values),
        (f"'{master_tab}'!{bf_letter}2:{bf_letter}{n_rows + 1}", bf_values),
    ]
    sheets_batch_update(token, master_id, updates)
    qv_written = sum(1 for v in ac_values if v[0])
    tag_written = sum(1 for v in bf_values if v[0])
    print(f"  Wrote {qv_written} QV SEM values → col {ac_letter}", flush=True)
    print(f"  Wrote {tag_written} SEM Recommendation tags → col {bf_letter}", flush=True)


# ── Main entry point ──────────────────────────────────────────────────────────

def run_sem_qv(token: str, cfg: dict) -> None:
    """Full SEM QV pipeline step. Called as the last step of run_pipeline.py.

    cfg: merged brand config dict (from utils.load_brand_config).
    Skips gracefully if ga4_ads_file_id is null/missing in config.
    """
    sheets_cfg  = cfg.get('sheets', {})
    master_id   = sheets_cfg.get('master_id')
    master_tab  = sheets_cfg.get('master_tab', 'Listing')
    ga4_file_id = sheets_cfg.get('ga4_ads_file_id')
    ga4_tab     = sheets_cfg.get('ga4_ads_tab')
    p1_label    = cfg.get('period', {}).get('p1_label', 'Q1 2026')

    sem_qv_cfg       = cfg.get('sem_qv', {})
    seo_cov_threshold = float(cfg.get('sem_qv', {}).get(
        'seo_cov_threshold',
        cfg.get('defaults', {}).get('sem_qv', {}).get('seo_cov_threshold', 0.10)
    ))
    seo_pos_threshold = int(sem_qv_cfg.get('seo_pos_threshold', 5))
    competitor_blocklist = set(sem_qv_cfg.get('competitor_blocklist', []))

    if not ga4_file_id or str(ga4_file_id).strip().upper() == 'TBD':
        print("  SEM QV: GA4 Ads file ID not configured — skipping QV SEM calculation.\n"
              "  Add 'ga4_ads_file_id' to brands/[handle]/config.json to enable.",
              flush=True)
        return

    print("\n── SEM QV Attribution ──────────────────────────────────────────", flush=True)

    # Step 1: Read GA4 Ads export
    ga4_rows = read_ga4_ads(token, ga4_file_id, ga4_tab)

    # Step 2: Calculate QV SEM
    qv_sem_map = calculate_qv_sem(ga4_rows)

    # Step 3: Read Masterlist for tagging
    print("  Reading Masterlist for Brand SEM tagging...", flush=True)
    raw = sheets_get(token, master_id, f"'{master_tab}'!A1:BF")
    if not raw:
        raise RuntimeError(f"Masterlist '{master_tab}' is empty — run the main pipeline first")

    headers = [str(h) for h in raw[0]]
    masterlist_rows = []
    for row in raw[1:]:
        d = {headers[i]: (row[i] if i < len(row) else '') for i in range(len(headers))}
        masterlist_rows.append(d)

    # Step 4: Tag Brand SEM recommendations
    sem_reco = tag_sem_recommendations(
        masterlist_rows, qv_sem_map,
        seo_cov_threshold=seo_cov_threshold,
        seo_pos_threshold=seo_pos_threshold,
        competitor_blocklist=competitor_blocklist,
        p1_label=p1_label,
    )

    # Step 5: Write results
    write_qv_sem(token, master_id, master_tab, qv_sem_map, sem_reco, p1_label=p1_label)
    print("── SEM QV complete ─────────────────────────────────────────────\n", flush=True)
