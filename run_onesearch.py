#!/usr/bin/env python3
"""
** DEPRECATED (2026-08-04) — use run_pipeline.py instead. **
This was the original single-brand, Oikos-only entry point (Apr 2026), superseded
by the config-driven multi-brand rewrite (run_pipeline.py + brands/<handle>/config.json).
Kept for reference only. Known issues not present in run_pipeline.py: hardcoded .env
path, hardcoded GSC/KS column names, hardcoded Masterlist ARRAYFORMULA column letters,
a column-AC write conflict with the SEM QV methodology. See one_search/docs/skeptic_notes.md.

OneSearch production runner.
Reads all sources from Google Sheets, runs the full pipeline, writes results to Masterlist.

Usage:
    python run_onesearch.py [--max-rows N]

    --max-rows N  Limit rows per source to N (default: 0 = all rows)
"""
import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))

from pipeline.ingest import norm_gsc, norm_sqr, norm_se, norm_ks
from pipeline.ingest_ga4 import ga4_from_raw
from pipeline.merge import merge_gsc_sqr
from pipeline.format_rows import format_base_rows
from pipeline.normalize import normalize
from pipeline.trigram import build_index
from pipeline.match_se import match_se_keywords
from pipeline.match_ks import match_ks_keywords
from pipeline.enrich import enrich_volumes, enrich_monthly_volumes

# ── Config ─────────────────────────────────────────────────────────────────────
ENV_FILE = "/Users/carlaklaasen/claude_code/.env"

# Per-client configuration. Add a new entry here for each new brand.
# Run a specific brand:  python run_onesearch.py --brand oikos-usa
# Run all brands in sequence:  python run_onesearch.py --brand all
CLIENTS = {
    'oikos-usa': {
        'ref_id':            '1o526Qv4UzP_Qfe-cjrfvcA7jRUi6zUtd9Ecp2WPMIhQ',
        'ref_tab':           'One Search ',   # trailing space matches actual sheet tab name
        'master_id':         '1W73Lzli30z4GnO_WtLjs0hWOdPcEZw1jptXKG8exKoU',
        'master_tab':        'Listing',
        'lang':              'EN',
        'kw_review_border':  '5 < Cos < 0.65',
        'kw_review_unmatch': 'Cos < .5',
    },
    # To add a new client, copy the block above and fill in the correct IDs.
    # Example:
    # 'activia-ca': {
    #     'ref_id':   '<source config sheet ID>',
    #     'ref_tab':  'One Search',
    #     'master_id': '<masterlist sheet ID>',
    #     'master_tab': 'Listing',
    #     'lang':     'EN',
    #     'kw_review_border':  '5 < Cos < 0.65',
    #     'kw_review_unmatch': 'Cos < .5',
    # },
}
DEFAULT_BRAND = 'oikos-usa'

# Keywords excluded from both GSC and SQR before the unified spine is built.
# These generate clicks with near-zero purchase intent and inflate click counts / depress ROAS.
# Add normalized (lowercase, no punctuation) terms here — exact match only.
CONN_INTENT_EXCLUSIONS = frozenset({
    'login', 'website', 'my account', 'mon compte', 'se connecter', 'espace client',
})

# ARRAYFORMULA cells to write after data rows
# Coverage = "OneSearch" / "SEO" / "SEM" / "" based on clicks presence
# Cost SEO = CPC SEO × Clicks SEO (estimated SEO media value)
FORMULAS = [
    # Coverage = Clics OneSearch / Average Search Volume (G)
    # J = Q1 2026 coverage rate
    ("'Listing'!J2",
     '=ARRAYFORMULA(IF(B2:B="","",IF(G2:G=0,"",L2:L/G2:G)))'
     ),
    # K = Q4 2025 coverage rate
    ("'Listing'!K2",
     '=ARRAYFORMULA(IF(B2:B="","",IF(G2:G=0,"",N2:N/G2:G)))'
     ),
    # Cost SEO = CPC SEO × Clics SEO
    ("'Listing'!AI2",
     '=ARRAYFORMULA(IF(ISBLANK(AF2:AF),"",AF2:AF*P2:P))'
     ),
    ("'Listing'!AK2",
     '=ARRAYFORMULA(IF(ISBLANK(AF2:AF),"",AF2:AF*R2:R))'
     ),
]

# Masterlist header cells that were written with outdated year labels.
# The pipeline corrects these at the start of each run so data lands in the right column.
HEADER_CORRECTIONS = {
    'Conversions SEO Q4 2024': 'Conversions SEO Q4 2025',
    'Conversions SEM Q4 2024': 'Conversions SEM Q4 2025',
    'Searches: Oct 2024': 'Searches: Oct 2025',
    'Searches: Nov 2024': 'Searches: Nov 2025',
    'Searches: Dec 2024': 'Searches: Dec 2025',
    'Searches: Jan 2025': 'Searches: Jan 2026',
    'Searches: Feb 2025': 'Searches: Feb 2026',
    'Searches: Mar 2025': 'Searches: Mar 2026',
}

# Columns whose content is set by ARRAYFORMULA — build_row writes '' here but
# we must fully clear them before writing the formula so ARRAYFORMULA can expand.
FORMULA_COLS = {"'Listing'!J2:J", "'Listing'!K2:K",
                "'Listing'!AI2:AI", "'Listing'!AK2:AK"}

# Pipeline field name → Masterlist column header (only entries that differ)
COLUMN_ALIASES = {
    "CPC avg. SEM Q1 2026": "CPC moy. SEM Q1 2026",
    "Spent SEM Q1 2026":    "Dépense SEM Q1 2026",
    "Spent SEM Q4 2025":    "Dépense SEM Q4 2025",
}


# ── Helpers ────────────────────────────────────────────────────────────────────
def _col_letter(idx):
    """Convert 0-based column index to A, B, … Z, AA, AB … letter."""
    if idx < 26:
        return chr(65 + idx)
    return chr(64 + idx // 26) + chr(65 + idx % 26)


# ── Auth ───────────────────────────────────────────────────────────────────────
def load_env():
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def get_token(env):
    data = urllib.parse.urlencode({
        "client_id":     env["GOOGLE_CLIENT_ID"],
        "client_secret": env["GOOGLE_CLIENT_SECRET"],
        "refresh_token": env["GOOGLE_REFRESH_TOKEN"],
        "grant_type":    "refresh_token",
    }).encode()
    resp = json.loads(urllib.request.urlopen(
        urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    ).read())
    return resp["access_token"]


# ── Sheets helpers ─────────────────────────────────────────────────────────────
def sheets_get(token, sheet_id, range_):
    url = (f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
           f"/values/{urllib.parse.quote(range_, safe='!:')}"
           f"?valueRenderOption=UNFORMATTED_VALUE")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read()).get("values", [])
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  HTTP {e.code} reading {range_}: {body[:200]}", flush=True)
        raise


def get_sheet_gid(token, spreadsheet_id, tab_name):
    """Return (gid, current_row_count) for the named tab."""
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    meta = json.loads(urllib.request.urlopen(req, timeout=30).read())
    for sheet in meta.get('sheets', []):
        props = sheet.get('properties', {})
        if props.get('title') == tab_name:
            rows = props.get('gridProperties', {}).get('rowCount', 1000)
            return props.get('sheetId'), rows
    return None, 1000


def expand_sheet_rows(token, spreadsheet_id, gid, extra_rows):
    """Append extra_rows to the sheet so we don't hit grid limits."""
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}:batchUpdate"
    payload = {"requests": [{"appendDimension": {
        "sheetId": gid, "dimension": "ROWS", "length": extra_rows
    }}]}
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()


def sheets_clear(token, sheet_id, range_):
    url = (f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
           f"/values/{urllib.parse.quote(range_, safe='!:')}:clear")
    req = urllib.request.Request(url, data=b'{}',
                                  headers={"Authorization": f"Bearer {token}",
                                           "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def sheets_batch_update(token, sheet_id, data_ranges, input_option="USER_ENTERED"):
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values:batchUpdate"
    payload = {
        "valueInputOption": input_option,
        "data": [
            {"range": r, "majorDimension": "ROWS", "values": v}
            for r, v in data_ranges
        ]
    }
    body = json.dumps(payload).encode()
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, data=body,
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"})
            resp = json.loads(urllib.request.urlopen(req, timeout=90).read())
            return resp.get("totalUpdatedCells", 0)
        except urllib.error.HTTPError as e:
            body_err = e.read().decode()
            wait = 15 * (attempt + 1)
            print(f"  Write attempt {attempt+1} HTTP {e.code}: {body_err[:200]} — retry in {wait}s",
                  flush=True)
            time.sleep(wait)
        except Exception as e:
            wait = 15 * (attempt + 1)
            print(f"  Write attempt {attempt+1} failed: {e} — retry in {wait}s", flush=True)
            time.sleep(wait)
    return 0


def raw_to_dicts(raw_rows):
    """Convert list-of-lists from Sheets API to list-of-dicts using first row as headers."""
    if not raw_rows:
        return [], []
    headers = [str(h) for h in raw_rows[0]]
    out = []
    for row in raw_rows[1:]:
        d = {h: (row[i] if i < len(row) else '') for i, h in enumerate(headers)}
        out.append(d)
    return headers, out


# ── Source config ──────────────────────────────────────────────────────────────
def read_source_config(token, ref_id, ref_tab):
    """Read source config sheet → {export_label: {doc_id, sheet_tab}}.
    Sheet columns: Client (A), Export (B), Doc ID (C), Sheet Tab (D).
    """
    raw = sheets_get(token, ref_id, f"'{ref_tab}'!A:D")
    _, rows = raw_to_dicts(raw)
    config = {}
    for r in rows:
        label = str(r.get('Export') or '').strip()
        if label:
            config[label] = {
                'doc_id':    str(r.get('Doc ID') or '').strip(),
                'sheet_tab': str(r.get('Sheet Tab') or '').strip(),
            }
    return config


# ── Row serialization ──────────────────────────────────────────────────────────
def build_row(data_dict, headers):
    """Build a list of values aligned to headers. Applies COLUMN_ALIASES for lookup."""
    row = []
    for h in headers:
        val = data_dict.get(h, '')
        if val == '':
            # try alias lookup (pipeline key → sheet column name)
            for pipeline_key, sheet_col in COLUMN_ALIASES.items():
                if sheet_col == h:
                    val = data_dict.get(pipeline_key, '')
                    break
        row.append('' if val is None else val)
    return row


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-rows', type=int, default=0,
                        help='Limit rows per source (0 = all)')
    parser.add_argument('--brand', default=DEFAULT_BRAND,
                        help=f'Brand key from CLIENTS (default: {DEFAULT_BRAND}), or "all" to run every brand in sequence')
    args = parser.parse_args()

    # ── Run all brands sequentially
    if args.brand == 'all':
        brands = list(CLIENTS.keys())
        print(f"Running all brands in sequence: {brands}", flush=True)
        for brand_key in brands:
            print(f"\n{'#' * 60}", flush=True)
            print(f"# Brand: {brand_key}", flush=True)
            print(f"{'#' * 60}", flush=True)
            args.brand = brand_key
            _run(args)
        return

    _run(args)


def _run(args):
    """Execute the full pipeline for a single brand."""
    brand_key = args.brand
    if brand_key not in CLIENTS:
        print(f"ERROR: unknown brand '{brand_key}'. Available: {list(CLIENTS)}", flush=True)
        sys.exit(1)

    cfg = CLIENTS[brand_key]
    ref_id            = cfg['ref_id']
    ref_tab           = cfg['ref_tab']
    master_id         = cfg['master_id']
    master_tab        = cfg['master_tab']
    client_lang       = cfg.get('lang', 'EN')
    kw_review_border  = cfg.get('kw_review_border', '5 < Cos < 0.65')
    kw_review_unmatch = cfg.get('kw_review_unmatch', 'Cos < .5')

    # Build ARRAYFORMULA cells and formula-col ranges dynamically from master_tab
    T = master_tab
    formulas = [
        (f"'{T}'!J2",  f'=ARRAYFORMULA(IF(B2:B="","",IF(G2:G=0,"",L2:L/G2:G)))'),
        (f"'{T}'!K2",  f'=ARRAYFORMULA(IF(B2:B="","",IF(G2:G=0,"",N2:N/G2:G)))'),
        (f"'{T}'!AI2", f'=ARRAYFORMULA(IF(ISBLANK(AF2:AF),"",AF2:AF*P2:P))'),
        (f"'{T}'!AK2", f'=ARRAYFORMULA(IF(ISBLANK(AF2:AF),"",AF2:AF*R2:R))'),
    ]
    formula_cols = {f"'{T}'!J2:J", f"'{T}'!K2:K", f"'{T}'!AI2:AI", f"'{T}'!AK2:AK"}

    MAX = args.max_rows

    # ── Log file setup (tee stdout to a timestamped log file)
    log_dir  = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    ts       = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = os.path.join(log_dir, f"onesearch_{ts}.log")

    class _Tee:
        def __init__(self, *streams):
            self._streams = streams
        def write(self, data):
            for s in self._streams:
                s.write(data)
        def flush(self):
            for s in self._streams:
                s.flush()

    _log_fh  = open(log_path, "w", encoding="utf-8")
    sys.stdout = _Tee(sys.__stdout__, _log_fh)

    print("=" * 60, flush=True)
    print(f"OneSearch Pipeline  (max-rows={MAX or 'all'})", flush=True)
    print(f"Log file: {log_path}", flush=True)
    print("=" * 60, flush=True)

    # ── Auth
    print("\nLoading credentials…", flush=True)
    env   = load_env()
    token = get_token(env)
    print("  Token OK", flush=True)

    # ── Source config
    print("\nReading source config…", flush=True)
    config = read_source_config(token, ref_id, ref_tab)
    for label, src in config.items():
        print(f"  [{label}]  doc={src['doc_id'][:20]}…  tab={src['sheet_tab']!r}", flush=True)

    def require(label):
        if label not in config:
            print(f"ERROR: '{label}' not found in source config sheet", flush=True)
            sys.exit(1)
        c = config[label]
        if not c['doc_id']:
            print(f"ERROR: '{label}' has no Doc ID in source config", flush=True)
            sys.exit(1)
        return c

    def lim(rows):
        return rows[:MAX] if MAX else rows

    # ── Read sources from Google Sheets
    print("\nReading source data from Google Sheets…", flush=True)

    ks_cfg = require('Keyword study')
    ks_raw_values = sheets_get(token, ks_cfg['doc_id'],
                               f"'{ks_cfg['sheet_tab']}'!A:BF")
    _, ks_raw = raw_to_dicts(ks_raw_values)
    ks_raw = lim(ks_raw)
    print(f"  KS: {len(ks_raw)} rows", flush=True)

    gsc_cfg = require('GSC Export')
    gsc_raw_values = sheets_get(token, gsc_cfg['doc_id'],
                                f"'{gsc_cfg['sheet_tab']}'!A:Z")
    _, gsc_raw = raw_to_dicts(gsc_raw_values)
    gsc_raw = lim(gsc_raw)
    print(f"  GSC: {len(gsc_raw)} rows", flush=True)

    # SQR: Google Sheet has headers in row 1 (unlike the CSV export which had a title row first)
    sqr_cfg = require('Account Level SQR Report')
    sqr_raw_values = sheets_get(token, sqr_cfg['doc_id'],
                                f"'{sqr_cfg['sheet_tab']}'!A:V")
    _, sqr_raw = raw_to_dicts(sqr_raw_values)
    sqr_raw = lim(sqr_raw)
    print(f"  SQR: {len(sqr_raw)} rows", flush=True)

    se_cfg = require('SE Ranking')
    se_raw_values = sheets_get(token, se_cfg['doc_id'],
                               f"'{se_cfg['sheet_tab']}'!A:Z")
    _, se_raw = raw_to_dicts(se_raw_values)
    se_raw = lim(se_raw)
    print(f"  SE: {len(se_raw)} rows", flush=True)

    # GA4 conversions — header is at row 10, read from row 10 onward
    def read_ga4(label) -> dict:
        cfg = config.get(label)
        if not cfg or not cfg.get('doc_id'):
            print(f"  GA4 '{label}': not configured, skipping", flush=True)
            return {}
        vals = sheets_get(token, cfg['doc_id'], f"'{cfg['sheet_tab']}'!A10:H")
        result = ga4_from_raw(vals)
        print(f"  GA4 '{label}': {len(result)} pages with key events", flush=True)
        return result

    checkout_map    = read_ga4('Conversions: Checkout')
    offline_map     = read_ga4('Conversions: Click Offline Store')
    checkout_q4_map = read_ga4('Conversions: Checkout Q4 2025')
    offline_q4_map  = read_ga4('Conversions: Click Offline Store Q4 2025')

    # ── Normalize
    print("\nNormalizing…", flush=True)
    gsc_norm = norm_gsc(gsc_raw)
    print(f"  GSC: {len(gsc_norm)}/{len(gsc_raw)} kept", flush=True)

    sqr_norm = norm_sqr(sqr_raw)
    print(f"  SQR: {len(sqr_norm)}/{len(sqr_raw)} kept", flush=True)

    se_norm = norm_se(se_raw)
    print(f"  SE:  {len(se_norm)}/{len(se_raw)} kept (pos ≤ 100)", flush=True)

    ks_norm = norm_ks(ks_raw)
    print(f"  KS:  {len(ks_norm)}/{len(ks_raw)} kept", flush=True)

    # ── Connection-intent keyword filter
    # Exact match on normalized keyword. These inflate click counts and depress ROAS
    # without contributing purchase intent. Excluded from both GSC and SQR before merge.
    if CONN_INTENT_EXCLUSIONS:
        gsc_pre = len(gsc_norm)
        sqr_pre = len(sqr_norm)
        gsc_norm = [r for r in gsc_norm if r['norm_query'] not in CONN_INTENT_EXCLUSIONS]
        sqr_norm = [r for r in sqr_norm if r['norm_term']  not in CONN_INTENT_EXCLUSIONS]
        gsc_excl = gsc_pre - len(gsc_norm)
        sqr_excl = sqr_pre - len(sqr_norm)
        if gsc_excl or sqr_excl:
            print(f"  Connection-intent filter: {gsc_excl} GSC + {sqr_excl} SQR rows excluded",
                  flush=True)
        else:
            print(f"  Connection-intent filter: 0 rows matched exclusion list", flush=True)

    # ── Merge GSC + SQR
    print("\nMerging GSC + SQR…", flush=True)
    unified = merge_gsc_sqr(gsc_norm, sqr_norm)
    print(f"  Unified: {len(unified)} rows", flush=True)

    gsc_only = sum(1 for r in unified if r.get('sqr_clicks_p1', 0) == 0)
    sqr_only = sum(1 for r in unified if r.get('gsc_clicks_p1', 0) == 0)
    both     = len(unified) - gsc_only - sqr_only
    print(f"  GSC-only: {gsc_only}  SQR-only: {sqr_only}  Both: {both}", flush=True)

    # ── Format base rows
    base = format_base_rows(unified)
    print(f"  Base rows: {len(base)}", flush=True)

    # ── Build trigram index (built once, reused for SE + KS)
    print("\nBuilding trigram index…", flush=True)
    index = build_index(unified)
    print(f"  {len(index['uKeys'])} keys  {len(index['idx'])} trigrams", flush=True)

    # ── Match SE Ranking
    print("\nMatching SE Ranking (threshold=0.60)…", flush=True)
    se_matches = match_se_keywords(se_norm, index)
    print(f"  SE matches: {len(se_matches)}", flush=True)
    se_by_kw = {m['Keyword']: m for m in se_matches}

    # ── Match Keyword Study
    print("Matching Keyword Study (threshold=0.65)…", flush=True)
    high_conf, review = match_ks_keywords(ks_norm, index, unified)
    print(f"  KS auto-matched: {len(high_conf)}  for review: {len(review)}", flush=True)
    ks_by_kw = {m['Keyword']: m for m in high_conf}

    # ── Merge all pipeline outputs into one row per keyword
    print("\nMerging pipeline outputs…", flush=True)

    # GSC position lookup — used as fallback when SE Ranking has no position for a keyword
    gsc_pos_by_kw = {}
    for r in unified:
        kw_display = r.get('query') or r.get('search_term') or r.get('unified_key', '')
        pos = r.get('gsc_pos_p1', 0)
        if kw_display and pos:
            gsc_pos_by_kw[kw_display] = pos

    merged_rows = []
    url_path_by_idx  = {}  # row index → SE URL path (consumed in GA4 pro-rata step below)
    gsc_pos_fallback = 0   # rows where col F came from GSC instead of SE Ranking

    for idx, b in enumerate(base):
        kw  = b.get('Keyword') or ''
        row = dict(b)
        se  = se_by_kw.get(kw, {})
        row.update({k: v for k, v in se.items() if not k.startswith('_') and k != 'Keyword'})
        ks  = ks_by_kw.get(kw, {})
        row.update({k: v for k, v in ks.items() if k != 'Keyword'})

        # LANG fallback: use client_lang when KS has no LANG value or row has no KS match
        if not row.get('LANG'):
            row['LANG'] = client_lang

        # G = (Volume Q1 2026 + Volume Q4 2025) / 6 — avg monthly across the 6-month window
        h = float(row.get('Volume Q1 2026') or 0)
        i = float(row.get('Volume Q4 2025') or 0)
        if h or i:
            row['Average Search Volume'] = round((h + i) / 6)

        # SE position fallback: no SE match → use GSC average position (rounded, no decimals)
        if not row.get('Position SE Ranking'):
            gsc_pos = gsc_pos_by_kw.get(kw, 0)
            if gsc_pos:
                row['Position SE Ranking'] = round(gsc_pos)
                gsc_pos_fallback += 1

        # Track SE URL path for GA4 pro-rata step
        url_path = se.get('_se_url_path') or ''
        if url_path:
            url_path_by_idx[idx] = url_path

        merged_rows.append(row)

    # ── GA4 pro-rata conversion distribution
    # When multiple keywords share the same SE landing page URL, conversions are split
    # by each keyword's Q1 SEO click share rather than assigning the full total to each.
    _conv_maps = [
        ('Conversions SEO Q1 2026', checkout_map),
        ('Conversions SEM Q1 2026', offline_map),
        ('Conversions SEO Q4 2025', checkout_q4_map),
        ('Conversions SEM Q4 2025', offline_q4_map),
    ]

    # ── GA4 URL inference for keywords without SE Ranking matches
    # SE-matched keywords already have their landing page URL in url_path_by_idx.
    # For GSC-only keywords, infer the URL by word-overlap between the keyword
    # and each GA4 URL's slug (path segments after stripping language/dir prefixes).
    _all_ga4_urls = set()
    for _, cm in _conv_maps:
        _all_ga4_urls.update(cm.keys())

    if _all_ga4_urls:
        def _slug_words(url_path):
            p = re.sub(r'^/(en-us|fr-ca|en-ca|fr-fr)/', '/', url_path)
            p = re.sub(r'^/(products?|yogurt|category|blog|recipes?)/', '/', p)
            return set(normalize(p.strip('/').replace('-', ' ').replace('/', ' ')).split())

        ga4_slug_words = {u: _slug_words(u) for u in _all_ga4_urls}
        url_inferred = 0
        for idx, row in enumerate(merged_rows):
            if idx in url_path_by_idx:
                continue  # already linked via SE Ranking
            if float(row.get('Clics SEO Q1 2026') or 0) == 0:
                continue  # keyword has no organic clicks — conversions don't apply
            kw_words = set(normalize(row.get('Keyword', '')).split())
            if len(kw_words) < 2:
                continue  # single-word keywords match too broadly
            best_url, best_score = None, 0.0
            for url_path, slug_words in ga4_slug_words.items():
                if not slug_words:
                    continue
                overlap = len(kw_words & slug_words)
                if overlap >= 2:
                    score = overlap / max(len(kw_words), len(slug_words))
                    if score > best_score:
                        best_score = score
                        best_url = url_path
            if best_url and best_score >= 0.5:
                url_path_by_idx[idx] = best_url
                url_inferred += 1
        if url_inferred:
            print(f"  GA4 URL inference: {url_inferred} additional keywords matched to GA4 URLs",
                  flush=True)

    url_to_entries = {}  # url_path → [(row_idx, gsc_clicks_p1)]
    for row_idx, url_path in url_path_by_idx.items():
        if any(url_path in cm for _, cm in _conv_maps):
            clicks = float(merged_rows[row_idx].get('Clics SEO Q1 2026') or 0)
            url_to_entries.setdefault(url_path, []).append((row_idx, clicks))

    conv_hits = 0
    for url_path, entries in url_to_entries.items():
        total_clicks = sum(c for _, c in entries)
        for row_idx, clicks in entries:
            share = (clicks / total_clicks) if total_clicks > 0 else (1.0 / len(entries))
            row  = merged_rows[row_idx]
            hit  = False
            for col_name, conv_map in _conv_maps:
                total_conv = conv_map.get(url_path, 0)
                if total_conv:
                    val = round(total_conv * share)
                    if val > 0:
                        row[col_name] = val
                        hit = True
            if hit:
                conv_hits += 1

    se_hits = sum(1 for r in merged_rows if r.get('Position SE Ranking') not in ('', None))
    ks_hits = sum(1 for r in merged_rows
                  if r.get('Volume Q1 2026') not in ('', None, 0)
                  or r.get('Volume Q4 2025') not in ('', None, 0))
    g_hits  = sum(1 for r in merged_rows if r.get('Average Search Volume', '') != '')
    print(f"  SE data rows:    {se_hits}/{len(merged_rows)}", flush=True)
    print(f"  KS volume rows:  {ks_hits}/{len(merged_rows)}", flush=True)
    print(f"  G populated:     {g_hits}/{len(merged_rows)}", flush=True)
    print(f"  Conversion hits: {conv_hits}/{len(merged_rows)} rows", flush=True)

    # ── Read Masterlist header row (to write in the correct column order)
    print("\nReading Masterlist header row…", flush=True)
    master_hdr_raw = sheets_get(token, master_id, f"'{master_tab}'!1:1")
    if not master_hdr_raw or not master_hdr_raw[0]:
        print("ERROR: Masterlist header row is empty", flush=True)
        sys.exit(1)
    master_headers = [str(h) for h in master_hdr_raw[0]]
    print(f"  {len(master_headers)} columns", flush=True)

    # ── Correct outdated column headers (year labels drift between projects)
    hdr_updates = []
    for i, h in enumerate(master_headers):
        if h in HEADER_CORRECTIONS:
            new_h = HEADER_CORRECTIONS[h]
            col_letter = _col_letter(i)
            hdr_updates.append((f"'{master_tab}'!{col_letter}1", [[new_h]]))
            master_headers[i] = new_h
            print(f"  Header fix: col {col_letter} '{h}' → '{new_h}'", flush=True)
    if hdr_updates:
        sheets_batch_update(token, master_id, hdr_updates)
        print(f"  {len(hdr_updates)} header(s) corrected", flush=True)
    else:
        print("  Headers OK — no corrections needed", flush=True)

    # Audit: which pipeline fields map to which header positions?
    all_pipeline_keys = set()
    for r in merged_rows:
        all_pipeline_keys.update(r.keys())

    matched_cols   = [h for h in master_headers if h in all_pipeline_keys or
                      any(sh == h for sh in COLUMN_ALIASES.values())]
    unmatched_cols = [h for h in master_headers if h not in matched_cols]
    print(f"  Matched: {len(matched_cols)} cols  Unmatched (will be blank): {len(unmatched_cols)} cols",
          flush=True)
    if unmatched_cols:
        print(f"  Blank cols: {unmatched_cols}", flush=True)

    # ── Build row values
    values_to_write = [build_row(r, master_headers) for r in merged_rows]

    # ── Refresh token before writing
    print("\nRefreshing token before write…", flush=True)
    token = get_token(env)

    # ── Ensure Listing tab has enough rows for all data + buffer
    needed_rows = len(values_to_write) + 50  # +1 header +49 buffer
    gid, current_rows = get_sheet_gid(token, master_id, master_tab)
    if gid is not None and current_rows < needed_rows:
        extra = needed_rows - current_rows
        print(f"  Expanding '{master_tab}' by {extra} rows ({current_rows} → {needed_rows})", flush=True)
        expand_sheet_rows(token, master_id, gid, extra)

    # ── Clear and rewrite Masterlist data rows
    print(f"Clearing Masterlist '{master_tab}' rows 2+…", flush=True)
    sheets_clear(token, master_id, f"'{master_tab}'!A2:ZZ")

    print(f"Writing {len(values_to_write)} rows…", flush=True)

    CHUNK = 500
    for i in range(0, len(values_to_write), CHUNK):
        chunk     = values_to_write[i:i + CHUNK]
        row_start = i + 2
        row_end   = row_start + len(chunk) - 1
        range_str = f"'{master_tab}'!A{row_start}:ZZ{row_end}"
        cells = sheets_batch_update(token, master_id, [(range_str, chunk)])
        print(f"  Rows {row_start}–{row_end}: {cells} cells written", flush=True)
        if i + CHUNK < len(values_to_write):
            time.sleep(1)

    # ── KW Review tabs (borderline → 5 < Cos < 0.65, unmatched → Cos < .5)
    def write_review_tab(tab_name, rows_to_write):
        print(f"\nClearing '{tab_name}' rows 2+…", flush=True)
        sheets_clear(token, master_id, f"'{tab_name}'!A2:ZZ")
        if not rows_to_write:
            print("  No rows to write.", flush=True)
            return
        hdr_raw = sheets_get(token, master_id, f"'{tab_name}'!1:1")
        if hdr_raw and hdr_raw[0]:
            hdrs = [str(h) for h in hdr_raw[0]]
        else:
            hdrs = list(rows_to_write[0].keys())
            sheets_batch_update(token, master_id, [(f"'{tab_name}'!A1", [hdrs])])
        vals = [build_row(r, hdrs) for r in rows_to_write]
        for i in range(0, len(vals), CHUNK):
            chunk     = vals[i:i + CHUNK]
            row_start = i + 2
            row_end   = row_start + len(chunk) - 1
            cells = sheets_batch_update(token, master_id,
                                        [(f"'{tab_name}'!A{row_start}:ZZ{row_end}", chunk)])
            print(f"  '{tab_name}' rows {row_start}–{row_end}: {cells} cells", flush=True)
            if i + CHUNK < len(vals):
                time.sleep(1)

    borderline = [r for r in review if r.get('source') == 'borderline']
    unmatched  = [r for r in review if r.get('source') != 'borderline']

    write_review_tab(kw_review_border, borderline)
    write_review_tab(kw_review_unmatch, unmatched)

    # ── Write ARRAYFORMULA cells (Coverage J/K, Cost SEO AI/AK)
    # The bulk data write puts '' in formula columns which blocks ARRAYFORMULA expansion.
    # Explicitly clear those columns first so the formula can expand into truly blank cells.
    print(f"\nClearing formula columns before ARRAYFORMULA write…", flush=True)
    token = get_token(env)  # refresh before formula write
    for col_range in sorted(formula_cols):
        sheets_clear(token, master_id, col_range)
        print(f"  Cleared {col_range}", flush=True)

    print(f"Writing ARRAYFORMULA cells…", flush=True)
    formula_ranges = [(cell, [[formula]]) for cell, formula in formulas]
    cells_written = sheets_batch_update(token, master_id, formula_ranges,
                                        input_option="USER_ENTERED")
    for cell, formula in formulas:
        print(f"  {cell}: {formula[:60]}…", flush=True)
    print(f"  Total cells: {cells_written}", flush=True)

    # ── Summary
    # volC  = total planned keyword volume (all rows with Average Search Volume)
    # osVolC = volume of keywords that have at least one SEO click (active capture)
    vol_c   = sum(int(r.get('Average Search Volume') or 0) for r in merged_rows)
    os_vol_c = sum(
        int(r.get('Average Search Volume') or 0) for r in merged_rows
        if (r.get('Clics SEO Q1 2026') or 0) > 0 or (r.get('Clics SEO Q4 2025') or 0) > 0
    )

    print(f"\n{'=' * 60}", flush=True)
    print("OneSearch Pipeline Complete", flush=True)
    print(f"  Unified rows:       {len(unified)}", flush=True)
    print(f"  SE matches:         {len(se_matches)} (threshold 0.60)", flush=True)
    print(f"  Pos. col F source:  {len(se_matches)} SE Ranking  +  {gsc_pos_fallback} GSC fallback", flush=True)
    print(f"  KS auto-matched:    {len(high_conf)}", flush=True)
    print(f"  KS borderline:      {len(borderline)}", flush=True)
    print(f"  KS unmatched:       {len(unmatched)}", flush=True)
    print(f"  Conv. hits (GA4):   {conv_hits} rows (pro-rata by SEO click share)", flush=True)
    print(f"  Masterlist rows:    {len(values_to_write)}", flush=True)
    print(f"  ARRAYFORMULA cells: {len(formulas)} written", flush=True)
    print(f"  volC (all KS vol.): {vol_c:,}/month  ({sum(1 for r in merged_rows if r.get('Average Search Volume'))} kws)", flush=True)
    print(f"  osVolC (w/ clicks): {os_vol_c:,}/month  ({sum(1 for r in merged_rows if (r.get('Clics SEO Q1 2026') or 0) > 0 or (r.get('Clics SEO Q4 2025') or 0) > 0)} kws with SEO clicks)", flush=True)
    print(f"{'=' * 60}", flush=True)

    # ── Post-pipeline enrichment
    token   = get_token(env)
    ser_key = env.get('SE_RANKING_API_KEY', '')
    if ser_key:
        enrich_volumes(token, master_id, master_tab, ser_key)
        token = get_token(env)
        enrich_monthly_volumes(token, master_id, master_tab, ser_key)
    else:
        print("\nSE_RANKING_API_KEY not set in .env — skipping volume enrichment", flush=True)

    print(f"\n{'=' * 60}", flush=True)
    print("Pipeline complete. To fill taxonomy columns run:", flush=True)
    print("  python3 run_taxonomy_enrichment.py", flush=True)
    print(f"{'=' * 60}", flush=True)

    # ── Close log
    sys.stdout = sys.__stdout__
    _log_fh.close()
    print(f"\nLog saved → {log_path}", flush=True)


if __name__ == "__main__":
    main()
