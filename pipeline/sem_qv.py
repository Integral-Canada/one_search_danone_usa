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


def _find_col(headers: list, patterns: list, exclude: set = None):
    """Header (in pattern-priority order) matching one of `patterns`.

    Tries an EXACT (case-insensitive, whitespace-trimmed) match first, and
    only falls back to a substring match if no pattern is an exact match to
    any header. This isn't just belt-and-suspenders: a bare substring
    pattern like 'sessions' or 'query' will happily match a LONGER header
    that merely contains that word — 'Landing page + query string' contains
    'query' just as much as the real query column, 'Session Google Ads
    query', does; a GA4 export can equally have 'Sessions' alongside
    'Sessions avec engagement' or 'Sessions avec engagement par utilisateur
    actif', all three containing 'sessions'. Preferring an exact match means
    'sessions' only ever matches a column literally named "Sessions", never
    a same-family variant — regardless of which one happens to come first
    in column order. (The first case above was a real, confirmed bug against
    Silk/International Delight's live exports — the second is the same class
    of risk, not yet triggered because Oikos's real header order happens to
    put plain 'Sessions' first, exactly how the first bug went unnoticed
    until column order stopped being on its side.)

    `exclude` additionally skips column indices already claimed by another
    target, so two DIFFERENT target columns (e.g. keyword vs. landing page)
    can never resolve to the same index even if some future header makes an
    exact match ambiguous too.
    """
    exclude = exclude or set()

    def _search(match_fn):
        for p in patterns:
            for i, h in enumerate(headers):
                if i in exclude:
                    continue
                if match_fn(p, str(h)):
                    return i
        return None

    exact = _search(lambda p, h: p.strip().lower() == h.strip().lower())
    if exact is not None:
        return exact
    return _search(lambda p, h: p.lower() in h.lower())


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
    # Resolution order matters — see _find_col()'s docstring: landing-page
    # patterns are specific phrases (unambiguous), so resolve that column
    # first and exclude it before resolving the keyword column, which uses a
    # bare 'query' pattern that can otherwise collide with an LP header like
    # 'Landing page + query string'.
    col_lp  = _find_col(headers, _LP_COL_PATTERNS)
    col_kw  = _find_col(headers, _KW_COL_PATTERNS, exclude={col_lp} - {None})
    col_ses = _find_col(headers, _SES_COL_PATTERNS, exclude={col_lp, col_kw} - {None})
    col_qv  = _find_col(headers, _QV_COL_PATTERNS, exclude={col_lp, col_kw, col_ses} - {None})

    missing = [name for name, c in [('keyword', col_kw), ('landing_page', col_lp),
                                     ('sessions', col_ses), ('key_events', col_qv)] if c is None]
    if missing:
        raise RuntimeError(
            f"GA4 Ads export: could not find columns {missing}.\n"
            f"Headers found: {headers}"
        )
    print(f"  Resolved columns — keyword: {headers[col_kw]!r}, landing_page: {headers[col_lp]!r}, "
          f"sessions: {headers[col_ses]!r}, key_events: {headers[col_qv]!r}", flush=True)

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


# ── Step 1b: Read a GA4 'Compare' Explore export (both periods, one file) ────
#
# GA4's Explore UI lets you pick a primary date range plus a "Compare" range,
# and exporting that produces a different, GROUPED shape than a plain export:
# each keyword+landing-page combo becomes a 3-row block —
#   row 1: '% change'                        → delta only, not a real count
#   row 2: the primary range's absolute Sessions/Key events
#   row 3: the compare range's absolute Sessions/Key events
# — and the keyword/landing-page columns are populated only on row 1 of each
# block (blank on rows 2-3), matching how GA4 renders repeated dimension
# values as visually merged cells. read_ga4_ads() doesn't handle this: it
# would read row 1's Sessions/Key-events cells (which are '-12.80%'-style
# percentages, not counts — clean_num() strips the '%' and returns 1.74
# instead of erroring) as if they were real data, while silently discarding
# the real absolute rows for having a blank keyword/landing-page cell.
#
# This exists because it's what GA4's UI naturally produces for a two-period
# comparison — much less effort for whoever's pulling the export than doing
# two separate pulls — so the pipeline should read it correctly rather than
# require re-exporting in the flat shape.

_CMP_COL_PATTERNS = ['comparison']


def is_ga4_compare_export(headers: list) -> bool:
    """True if this GA4 Ads export has a 'Date Comparison'-style column —
    i.e. it's a two-period Compare export, not a plain single-period one."""
    return _find_col(headers, _CMP_COL_PATTERNS) is not None


def _ga4_header_row(token: str, file_id: str, tab=None) -> tuple:
    """Resolve the tab, locate the header row, return (raw_rows, header_idx, headers).
    Shared by read_ga4_ads_compare() and the format-detection probe in
    run_sem_qv() — read_ga4_ads() (the flat-export reader) keeps its own
    copy of this logic untouched, so the already-working single-period path
    can't be affected by anything added here.
    """
    resolved_tab = _resolve_tab(token, file_id, tab)
    raw = sheets_get(token, file_id, f"'{resolved_tab}'!A1:L60000")
    if not raw:
        raise RuntimeError(f"GA4 Ads tab '{resolved_tab}' returned no data")
    header_idx = None
    for i, row in enumerate(raw):
        joined = ' '.join(str(c) for c in row).lower()
        if 'sessions' in joined and ('page' in joined or 'requ' in joined or 'destination' in joined):
            header_idx = i
            break
    if header_idx is None:
        raise RuntimeError("GA4 Ads export: could not locate header row (needs 'sessions' + 'page' columns)")
    headers = [str(h).strip() for h in raw[header_idx]]
    return raw, header_idx, headers


def detect_ga4_compare_mode(token: str, file_id: str, tab=None) -> bool:
    """Lightweight probe: does this GA4 Ads export use the 'Compare' shape?"""
    _, _, headers = _ga4_header_row(token, file_id, tab)
    return is_ga4_compare_export(headers)


def read_ga4_ads_compare(token: str, file_id: str, tab=None) -> tuple:
    """Read a GA4 'Compare' Explore export covering two date ranges at once.

    Returns (rows_a, rows_b, label_a, label_b): rows_a/rows_b are the same
    {keyword, lp, sessions, key_events} dict shape read_ga4_ads() returns,
    one list per period; label_a/label_b are the literal date-range strings
    GA4 wrote for each (e.g. 'Apr 1 - Jun 30, 2026'), in the order GA4 lists
    them — primary range first, compare range second, per GA4's own
    Explore-UI convention (never alphabetical or chronological order).
    """
    raw, header_idx, headers = _ga4_header_row(token, file_id, tab)
    print(f"  GA4 Ads tab resolved: {repr(_resolve_tab(token, file_id, tab))} (Compare export)", flush=True)

    # See _find_col()'s docstring — landing-page column resolved first
    # (specific phrase, unambiguous), keyword column excludes it (its 'query'
    # pattern can otherwise match an LP header like 'Landing page + query
    # string' — the exact collision hit against Silk/ID's real exports).
    col_lp  = _find_col(headers, _LP_COL_PATTERNS)
    col_kw  = _find_col(headers, _KW_COL_PATTERNS, exclude={col_lp} - {None})
    col_cmp = _find_col(headers, _CMP_COL_PATTERNS, exclude={col_lp, col_kw} - {None})
    col_ses = _find_col(headers, _SES_COL_PATTERNS, exclude={col_lp, col_kw, col_cmp} - {None})
    col_qv  = _find_col(headers, _QV_COL_PATTERNS, exclude={col_lp, col_kw, col_cmp, col_ses} - {None})

    missing = [name for name, c in [('keyword', col_kw), ('landing_page', col_lp),
                                     ('date_comparison', col_cmp),
                                     ('sessions', col_ses), ('key_events', col_qv)] if c is None]
    if missing:
        raise RuntimeError(
            f"GA4 Ads Compare export: could not find columns {missing}.\n"
            f"Headers found: {headers}"
        )
    print(f"  Resolved columns — keyword: {headers[col_kw]!r}, landing_page: {headers[col_lp]!r}, "
          f"date_comparison: {headers[col_cmp]!r}, sessions: {headers[col_ses]!r}, "
          f"key_events: {headers[col_qv]!r}", flush=True)

    rows_a, rows_b = [], []
    labels: list = []
    last_kw, last_lp = '', ''
    for row in raw[header_idx + 1:]:
        if len(row) <= max(col_kw, col_lp, col_cmp, col_ses, col_qv):
            continue
        kw_cell = str(row[col_kw]).strip()
        lp_cell = str(row[col_lp]).strip()
        if kw_cell:
            last_kw = kw_cell
        if lp_cell:
            last_lp = lp_cell

        cmp_label = str(row[col_cmp]).strip()
        if not cmp_label or cmp_label.lower() == '% change':
            continue  # delta-only summary row — not a real count
        if not last_kw or last_kw.startswith('#'):
            continue  # 'Grand total' block (no keyword forward-filled yet) or a comment row

        try:
            ses = clean_num(row[col_ses])
            qv  = clean_num(row[col_qv])
        except (ValueError, IndexError):
            continue

        lp = last_lp.split('?')[0].rstrip('/')
        if not lp:
            lp = '/'

        if cmp_label not in labels:
            labels.append(cmp_label)
            if len(labels) > 2:
                raise RuntimeError(
                    f"GA4 Ads Compare export: found a 3rd distinct date-range label "
                    f"{cmp_label!r} (expected exactly 2: {labels[:2]!r}) — a row's date "
                    f"range didn't match either known period, which would otherwise "
                    f"silently fold into period 2. Check for inconsistent date formatting "
                    f"in the export."
                )
        bucket = rows_a if labels.index(cmp_label) == 0 else rows_b
        bucket.append({'keyword': last_kw, 'lp': lp, 'sessions': ses, 'key_events': qv})

    label_a = labels[0] if len(labels) > 0 else None
    label_b = labels[1] if len(labels) > 1 else None
    print(f"  GA4 Ads (Compare export): {len(rows_a)} rows for {label_a!r}, "
          f"{len(rows_b)} rows for {label_b!r}", flush=True)
    return rows_a, rows_b, label_a, label_b


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


def write_qv_sem_period(
    token: str,
    master_id: str,
    master_tab: str,
    qv_sem_map: dict,
    period_label: str,
) -> None:
    """Write QV SEM values for a single period's 'Conversions SEM {period_label}'
    column only — no Brand SEM Recommendation tagging (that's a P1-only, current-
    period decision; see tag_sem_recommendations docstring). Used for a
    comparison-period (P2) GA4 Ads export, kept separate from write_qv_sem()
    so a brand with only a P1 export configured never touches a P2 column.
    """
    col_name = f'Conversions SEM {period_label}'
    print(f"\nWriting QV SEM ({period_label}) → Masterlist '{master_tab}'...", flush=True)

    header_raw = sheets_get(token, master_id, f"'{master_tab}'!1:1")
    if not header_raw:
        raise RuntimeError(f"Masterlist '{master_tab}' returned empty header row")
    headers = [str(h) for h in header_raw[0]]
    try:
        col_pos = headers.index(col_name) + 1  # 1-based
    except ValueError:
        raise RuntimeError(
            f"Column '{col_name}' not found in Masterlist headers.\n"
            f"Verify the masterlist was built with the correct period label.\n"
            f"Headers (first 10): {headers[:10]}"
        )
    col_letter_ = col_letter(col_pos)

    kw_raw = sheets_get(token, master_id, f"'{master_tab}'!B2:B")
    all_keywords = [str(r[0]) if r else '' for r in kw_raw]
    n_rows = len(all_keywords)

    values = []
    for kw in all_keywords:
        qv = qv_sem_map.get(normalize(kw), '')
        values.append([round(qv, 4) if qv else ''])

    sheets_batch_update(token, master_id, [
        (f"'{master_tab}'!{col_letter_}2:{col_letter_}{n_rows + 1}", values),
    ])
    qv_written = sum(1 for v in values if v[0])
    print(f"  Wrote {qv_written} QV SEM values → col {col_letter_}", flush=True)


# ── Main entry point ──────────────────────────────────────────────────────────

def run_sem_qv(token: str, cfg: dict) -> None:
    """Full SEM QV pipeline step. Called as the last step of run_pipeline.py.

    cfg: merged brand config dict (from utils.load_brand_config).
    Skips gracefully if ga4_ads_file_id is null/missing in config.

    P1 (current period) drives both the QV SEM numbers AND the Brand SEM
    Recommendation tag (col BF) — that tag is a forward-looking campaign
    decision, not a trend, so it stays P1-only even when P2 is configured.

    P2 (comparison period) can come from either of two places:
      - ga4_ads_file_id_p2: a second, separate flat export for P2 — read and
        written into 'Conversions SEM {p2_label}' the same way as P1.
      - OR, if ga4_ads_file_id (P1) turns out to be a GA4 'Compare' Explore
        export (both periods in one file — see read_ga4_ads_compare()'s
        docstring for why that shape exists and needs its own reader), its
        second period is used for P2 automatically — no separate P2 export
        needed. An explicit ga4_ads_file_id_p2, if configured, always takes
        priority over this fallback.
    Either way, if neither produces a P2 source, 'Conversions SEM {p2_label}'
    is skipped gracefully, same as P1 — left to its proxy/existing value.
    """
    sheets_cfg  = cfg.get('sheets', {})
    master_id   = sheets_cfg.get('master_id')
    master_tab  = sheets_cfg.get('master_tab', 'Listing')
    ga4_file_id = sheets_cfg.get('ga4_ads_file_id')
    ga4_tab     = sheets_cfg.get('ga4_ads_tab')
    p1_label    = cfg.get('period', {}).get('p1_label', 'Q1 2026')

    ga4_file_id_p2 = sheets_cfg.get('ga4_ads_file_id_p2')
    ga4_tab_p2     = sheets_cfg.get('ga4_ads_tab_p2')
    p2_label       = cfg.get('period', {}).get('p2_label', 'Q4 2025')

    sem_qv_cfg       = cfg.get('sem_qv', {})
    seo_cov_threshold = float(cfg.get('sem_qv', {}).get(
        'seo_cov_threshold',
        cfg.get('defaults', {}).get('sem_qv', {}).get('seo_cov_threshold', 0.10)
    ))
    seo_pos_threshold = int(sem_qv_cfg.get('seo_pos_threshold', 5))
    competitor_blocklist = set(sem_qv_cfg.get('competitor_blocklist', []))

    has_p1 = bool(ga4_file_id) and str(ga4_file_id).strip().upper() != 'TBD'
    has_p2 = bool(ga4_file_id_p2) and str(ga4_file_id_p2).strip().upper() != 'TBD'

    if not has_p1 and not has_p2:
        print("  SEM QV: GA4 Ads file ID not configured — skipping QV SEM calculation.\n"
              "  Add 'ga4_ads_file_id' to brands/[handle]/config.json to enable.",
              flush=True)
        return

    print("\n── SEM QV Attribution ──────────────────────────────────────────", flush=True)

    p2_written = False
    compare_rows_p2 = None
    compare_label_p2 = None

    if has_p1:
        # Step 1: Read GA4 Ads export — detect a 'Compare' export first, since
        # it needs a structurally different reader (see read_ga4_ads_compare).
        is_compare = detect_ga4_compare_mode(token, ga4_file_id, ga4_tab)
        if is_compare:
            print("  GA4 Ads export detected as a 'Compare' export (two periods, "
                  "one file).", flush=True)
            rows_p1, compare_rows_p2, label_p1, compare_label_p2 = read_ga4_ads_compare(
                token, ga4_file_id, ga4_tab
            )
            ga4_rows = rows_p1
        else:
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

        # Step 4: Tag Brand SEM recommendations (P1 only — see docstring)
        sem_reco = tag_sem_recommendations(
            masterlist_rows, qv_sem_map,
            seo_cov_threshold=seo_cov_threshold,
            seo_pos_threshold=seo_pos_threshold,
            competitor_blocklist=competitor_blocklist,
            p1_label=p1_label,
        )

        # Step 5: Write results
        write_qv_sem(token, master_id, master_tab, qv_sem_map, sem_reco, p1_label=p1_label)

        # An explicit ga4_ads_file_id_p2 always wins if configured (handled
        # below); otherwise, a Compare export's second period fills P2.
        if compare_rows_p2 is not None and not has_p2:
            print(f"  Using this Compare export's second period ({compare_label_p2!r}) "
                  f"for 'Conversions SEM {p2_label}' — no separate P2 export configured.",
                  flush=True)
            qv_sem_map_p2 = calculate_qv_sem(compare_rows_p2)
            write_qv_sem_period(token, master_id, master_tab, qv_sem_map_p2, period_label=p2_label)
            p2_written = True
    else:
        print("  SEM QV (P1): GA4 Ads file ID not configured — skipping.", flush=True)

    if has_p2 and not p2_written:
        ga4_rows_p2 = read_ga4_ads(token, ga4_file_id_p2, ga4_tab_p2)
        qv_sem_map_p2 = calculate_qv_sem(ga4_rows_p2)
        write_qv_sem_period(token, master_id, master_tab, qv_sem_map_p2, period_label=p2_label)
        p2_written = True
    elif not p2_written:
        print("  SEM QV (P2): GA4 Ads file ID not configured — leaving "
              f"'Conversions SEM {p2_label}' to its proxy/existing value.", flush=True)

    print("── SEM QV complete ─────────────────────────────────────────────\n", flush=True)
