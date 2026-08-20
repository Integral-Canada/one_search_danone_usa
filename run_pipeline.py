#!/usr/bin/env python3
"""
OneSearch Pipeline — unified entry point.

Replaces run_onesearch.py. Reads all config from brands/<handle>/config.json.
After writing the Masterlist, runs SEM QV attribution as a final step.

Usage:
    python3 run_pipeline.py                          # default brand from config
    python3 run_pipeline.py --brand oikos-usa
    python3 run_pipeline.py --brand oikos-usa --max-rows 500
    python3 run_pipeline.py --brand all             # all configured brands
"""
import argparse
import datetime
import os
import re
import sys

# ── Ensure pipeline/ is importable ───────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

from pipeline.utils import (
    load_brand_config, load_env, get_token,
    sheets_get, sheets_batch_update, sheets_clear,
    col_letter, ensure_tab_exists,
)
from pipeline.normalize import normalize, clean_num
from pipeline.ingest import norm_gsc, norm_sqr, norm_se, norm_ks
from pipeline.ingest_ga4 import ga4_from_raw
from pipeline.merge import merge_gsc_sqr
from pipeline.format_rows import format_base_rows
from pipeline.trigram import build_index
from pipeline.match_se import match_se_keywords
from pipeline.match_ks import match_ks_keywords
from pipeline.sem_qv import run_sem_qv
from pipeline.enrich import enrich_volumes, enrich_monthly_volumes
from pipeline.classify import classify_competitors

DEFAULT_BRAND = 'oikos-usa'


# ── Source config reading ──────────────────────────────────────────────────────

def read_source_config(token: str, ref_id: str, ref_tab: str, client: str = None) -> dict:
    """Read the source-config sheet (Client / Export / Doc ID / Sheet Tab / URL).
    Returns {export_label: {doc_id, sheet_tab}}.

    Column A (Client) is only filled in on the first row of each brand's block —
    subsequent rows leave it blank and inherit the same client. This forward-fills
    that column, then keeps only rows belonging to `client` (case-insensitive,
    stripped). Without this filter, multiple brands sharing export labels like
    "GSC Export" or "Keyword study" would collide in one dict and silently return
    whichever brand's block appears last in the sheet — passing `client` is
    required for any registry with more than one brand's rows in it.
    """
    raw = sheets_get(token, ref_id, f"'{ref_tab}'!A:E")
    if not raw:
        return {}
    config = {}
    current_client = ''
    want = client.strip().casefold() if client else None
    for row in raw[1:]:  # skip header
        if len(row) < 3:
            continue
        cell_client = str(row[0]).strip() if len(row) > 0 else ''
        if cell_client:
            current_client = cell_client
        label   = str(row[1]).strip() if len(row) > 1 else ''
        doc_id  = str(row[2]).strip() if len(row) > 2 else ''
        tab     = str(row[3]).strip() if len(row) > 3 else ''
        if want is not None and current_client.strip().casefold() != want:
            continue
        if label and doc_id:
            config[label] = {'doc_id': doc_id, 'sheet_tab': tab}
    return config


def read_competitor_candidates(token: str, ref_id: str, ref_tab: str, client: str = None) -> list:
    """Read the 'COMPETITORS' row from the source-config sheet, if one exists.

    That row has no Doc ID (column C) — the pipe-delimited regex candidate
    list lives in column E (URL) instead, so it's invisible to
    read_source_config()'s `if label and doc_id` filter by design. This is a
    separate, deliberately raw intake point: an analyst pastes in whatever
    competitor/brand regex they already have (e.g. copied from an existing
    Keyword Study filter formula) as a first-pass candidate list.

    It is NOT auto-applied to classification. Those lists reliably mix in
    non-competitor noise (retailers, unrelated brands, generic terms) — see
    brands/silk/config.json's `_competitors_comment`. This function only
    surfaces candidates for a human to curate into a brand's config.json
    `competitors` block.
    """
    raw = sheets_get(token, ref_id, f"'{ref_tab}'!A:E")
    if not raw:
        return []
    current_client = ''
    want = client.strip().casefold() if client else None
    for row in raw[1:]:
        cell_client = str(row[0]).strip() if len(row) > 0 else ''
        if cell_client:
            current_client = cell_client
        label = str(row[1]).strip() if len(row) > 1 else ''
        if want is not None and current_client.strip().casefold() != want:
            continue
        if label.strip().upper() == 'COMPETITORS':
            blob = str(row[4]).strip() if len(row) > 4 else ''
            return [t.strip() for t in blob.split('|') if t.strip()]
    return []


def raw_to_dicts(raw_values: list) -> tuple:
    """Convert Sheets API list-of-lists to (headers, list-of-dicts)."""
    if not raw_values:
        return [], []
    headers = [str(h) for h in raw_values[0]]
    rows = []
    for row in raw_values[1:]:
        d = {headers[i]: (row[i] if i < len(row) else '') for i in range(len(headers))}
        rows.append(d)
    return headers, rows


# ── Sheet management helpers ──────────────────────────────────────────────────

def get_sheet_gid(token: str, sheet_id: str, tab_name: str) -> tuple:
    """Return (gid, current_row_count) for a named tab."""
    import json, urllib.request, urllib.parse
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}?fields=sheets.properties"
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    meta = json.loads(urllib.request.urlopen(req, timeout=30).read())
    for s in meta['sheets']:
        if s['properties']['title'] == tab_name:
            gp = s['properties'].get('gridProperties', {})
            return s['properties']['sheetId'], gp.get('rowCount', 1000)
    raise ValueError(f"Tab '{tab_name}' not found in sheet {sheet_id}")


def expand_sheet_rows(token: str, sheet_id: str, gid: int, extra: int) -> None:
    import json, urllib.request
    url  = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}:batchUpdate"
    body = json.dumps({'requests': [{'appendDimension': {
        'sheetId': gid, 'dimension': 'ROWS', 'length': extra
    }}]}).encode()
    req  = urllib.request.Request(url, data=body, headers={
        'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'
    })
    urllib.request.urlopen(req, timeout=60)


# ── Main pipeline ─────────────────────────────────────────────────────────────

def _run(brand_key: str, max_rows=None) -> None:
    cfg = load_brand_config(brand_key)

    sheets_cfg       = cfg.get('sheets', {})
    ref_id           = sheets_cfg['ref_id']
    ref_tab          = sheets_cfg['ref_tab']
    ref_client       = sheets_cfg.get('ref_client')
    master_id        = sheets_cfg['master_id']
    master_tab       = sheets_cfg['master_tab']
    kw_review_border = cfg.get('kw_review_border_tab', '5 < Cos < 0.65')
    kw_review_unmatch= cfg.get('kw_review_unmatch_tab', 'Cos < .5')

    period_cfg  = cfg.get('period', {})
    p1_label    = period_cfg.get('p1_label', 'Q1 2026')
    p2_label    = period_cfg.get('p2_label', 'Q4 2025')
    gsc_p1_prefix = period_cfg.get('gsc_p1_prefix')   # e.g. "1/1/26 - 3/31/26"
    gsc_p2_prefix = period_cfg.get('gsc_p2_prefix')   # e.g. "10/1/25 - 12/31/25"
    se_months   = (period_cfg.get('se_months_p2', []) +
                   period_cfg.get('se_months_p1', []))  # P2 months first (chronological)

    client_lang       = cfg.get('lang', 'EN')
    column_aliases    = cfg.get('column_aliases', {})
    header_corrections= cfg.get('header_corrections', {})
    conn_excl_list    = cfg.get('conn_intent_exclusions', [])
    conn_intent_excl  = frozenset(conn_excl_list)

    T = master_tab  # ARRAYFORMULA cells resolved dynamically once master_hdr is read (below)

    # ── Log file setup ────────────────────────────────────────────────────────
    log_dir  = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    ts       = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_path = os.path.join(log_dir, f'pipeline_{brand_key}_{ts}.log')

    class _Tee:
        def __init__(self, *streams):
            self._streams = streams
        def write(self, data):
            for s in self._streams:
                try:
                    s.write(data)
                except Exception:
                    pass
        def flush(self):
            for s in self._streams:
                try:
                    s.flush()
                except Exception:
                    pass

    _log_fh  = open(log_path, 'w', encoding='utf-8')
    sys.stdout = _Tee(sys.__stdout__, _log_fh)
    sys.stderr = _Tee(sys.__stderr__, _log_fh)

    print('=' * 64, flush=True)
    print(f'OneSearch Pipeline  brand={brand_key}  max-rows={max_rows or "all"}', flush=True)
    print(f'Period: {p1_label} vs {p2_label}', flush=True)
    print(f'Log: {log_path}', flush=True)
    print('=' * 64, flush=True)

    # ── Auth ──────────────────────────────────────────────────────────────────
    print('\nLoading credentials…', flush=True)
    env   = load_env()
    token = get_token(env)
    print('  Token OK', flush=True)

    # ── Source config ─────────────────────────────────────────────────────────
    print('\nReading source config…', flush=True)
    if not ref_client:
        sys.exit(
            "ERROR: 'ref_client' is missing from brands/[handle]/config.json 'sheets' block.\n"
            "This registry sheet has more than one brand's rows in it — without an exact "
            "match to column A (Client) in the 'One Search' tab, exports would resolve to "
            "whichever brand's block happens to appear last in the sheet."
        )
    source_config = read_source_config(token, ref_id, ref_tab, client=ref_client)
    for label, src in source_config.items():
        print(f'  [{label}]  doc={src["doc_id"][:22]}…  tab={src["sheet_tab"]!r}', flush=True)

    # A 'COMPETITORS' row in the registry is a raw, uncurated candidate list —
    # never auto-applied (see read_competitor_candidates docstring). Just flag
    # it so the analyst knows to reconcile it with config['competitors'].
    candidates = read_competitor_candidates(token, ref_id, ref_tab, client=ref_client)
    configured_names = {c['name'].casefold() for c in cfg.get('competitors', [])}
    unreviewed = [t for t in candidates if t.casefold() not in configured_names
                  and not any(t.casefold() in p for c in cfg.get('competitors', [])
                              for p in c.get('patterns', []))]
    if unreviewed:
        print(f"\nNOTE: registry has a COMPETITORS candidate row with {len(unreviewed)} term(s) "
              f"not yet reflected in this brand's config['competitors']:", flush=True)
        print(f"  {' | '.join(unreviewed)}", flush=True)
        print("  This raw list mixes real competitors with retailers/generic noise — "
              "review and curate into config.json manually, do not copy wholesale.", flush=True)

    def require(label: str) -> dict:
        if label not in source_config:
            sys.exit(f"ERROR: '{label}' not found in source config sheet")
        c = source_config[label]
        if not c['doc_id']:
            sys.exit(f"ERROR: '{label}' has no Doc ID in source config")
        return c

    def lim(rows: list) -> list:
        return rows[:max_rows] if max_rows else rows

    # ── Read sources from Google Sheets ──────────────────────────────────────
    print('\nReading source data from Google Sheets…', flush=True)

    ks_cfg        = require('Keyword study')
    ks_raw_vals   = sheets_get(token, ks_cfg['doc_id'], f"'{ks_cfg['sheet_tab']}'!A:BF")
    _, ks_raw     = raw_to_dicts(ks_raw_vals)
    ks_raw        = lim(ks_raw)
    print(f'  KS: {len(ks_raw)} rows', flush=True)

    gsc_cfg       = require('GSC Export')
    gsc_raw_vals  = sheets_get(token, gsc_cfg['doc_id'], f"'{gsc_cfg['sheet_tab']}'!A:Z")
    _, gsc_raw    = raw_to_dicts(gsc_raw_vals)
    gsc_raw       = lim(gsc_raw)
    print(f'  GSC: {len(gsc_raw)} rows', flush=True)

    sqr_cfg       = require('Account Level SQR Report')
    sqr_raw_vals  = sheets_get(token, sqr_cfg['doc_id'], f"'{sqr_cfg['sheet_tab']}'!A:V")
    _, sqr_raw    = raw_to_dicts(sqr_raw_vals)
    sqr_raw       = lim(sqr_raw)
    print(f'  SQR: {len(sqr_raw)} rows', flush=True)

    se_cfg        = require('SE Ranking')
    se_raw_vals   = sheets_get(token, se_cfg['doc_id'], f"'{se_cfg['sheet_tab']}'!A:Z")
    _, se_raw     = raw_to_dicts(se_raw_vals)
    se_raw        = lim(se_raw)
    print(f'  SE: {len(se_raw)} rows', flush=True)

    def read_ga4(label: str) -> dict:
        c = source_config.get(label)
        if not c or not c.get('doc_id'):
            print(f"  GA4 '{label}': not configured, skipping", flush=True)
            return {}
        vals   = sheets_get(token, c['doc_id'], f"'{c['sheet_tab']}'!A1:H")
        result = ga4_from_raw(vals)
        print(f"  GA4 '{label}': {len(result)} pages with key events", flush=True)
        return result

    checkout_map    = read_ga4('Conversions: Checkout')
    offline_map     = read_ga4('Conversions: Click Offline Store')
    checkout_q4_map = read_ga4(f'Conversions: Checkout {p2_label}')
    offline_q4_map  = read_ga4(f'Conversions: Click Offline Store {p2_label}')

    # ── Normalize sources ─────────────────────────────────────────────────────
    print('\nNormalizing…', flush=True)
    try:
        gsc_norm = norm_gsc(gsc_raw, p1_prefix=gsc_p1_prefix, p2_prefix=gsc_p2_prefix)
    except ValueError as e:
        sys.exit(f'ERROR in norm_gsc: {e}')
    print(f'  GSC: {len(gsc_norm)}/{len(gsc_raw)} kept', flush=True)

    sqr_norm = norm_sqr(sqr_raw)
    print(f'  SQR: {len(sqr_norm)}/{len(sqr_raw)} kept', flush=True)

    se_norm = norm_se(se_raw)
    print(f'  SE:  {len(se_norm)}/{len(se_raw)} kept (pos ≤ 100)', flush=True)

    ks_norm = norm_ks(ks_raw, se_months=se_months if se_months else None,
                       taxonomy_tags=cfg.get('taxonomy_tags'))
    print(f'  KS:  {len(ks_norm)}/{len(ks_raw)} kept', flush=True)

    # ── Connection-intent filter ──────────────────────────────────────────────
    if conn_intent_excl:
        gsc_pre, sqr_pre = len(gsc_norm), len(sqr_norm)
        gsc_norm = [r for r in gsc_norm if r['norm_query'] not in conn_intent_excl]
        sqr_norm = [r for r in sqr_norm if r['norm_term']  not in conn_intent_excl]
        gsc_excl = gsc_pre - len(gsc_norm)
        sqr_excl = sqr_pre - len(sqr_norm)
        if gsc_excl or sqr_excl:
            print(f'  Connection-intent filter: {gsc_excl} GSC + {sqr_excl} SQR rows excluded',
                  flush=True)

    # ── Merge GSC + SQR ──────────────────────────────────────────────────────
    print('\nMerging GSC + SQR…', flush=True)
    unified = merge_gsc_sqr(gsc_norm, sqr_norm)
    gsc_only = sum(1 for r in unified if r.get('sqr_clicks_p1', 0) == 0)
    sqr_only = sum(1 for r in unified if r.get('gsc_clicks_p1', 0) == 0)
    both_    = len(unified) - gsc_only - sqr_only
    print(f'  Unified: {len(unified)} rows  (GSC-only: {gsc_only}, '
          f'SQR-only: {sqr_only}, Both: {both_})', flush=True)

    base = format_base_rows(unified, p1_label=p1_label, p2_label=p2_label)

    # ── Trigram index ─────────────────────────────────────────────────────────
    print('\nBuilding trigram index…', flush=True)
    index = build_index(unified)
    print(f'  {len(index["uKeys"])} keys  {len(index["idx"])} trigrams', flush=True)

    # ── Match SE Ranking ──────────────────────────────────────────────────────
    print('\nMatching SE Ranking (threshold=0.60)…', flush=True)
    se_matches = match_se_keywords(se_norm, index, p1_label=p1_label)
    print(f'  SE matches: {len(se_matches)}', flush=True)
    se_by_kw = {m['Keyword']: m for m in se_matches}

    # ── Match Keyword Study ───────────────────────────────────────────────────
    print('Matching Keyword Study (threshold=0.65)…', flush=True)
    high_conf, review = match_ks_keywords(
        ks_norm, index, unified,
        p1_label=p1_label, p2_label=p2_label,
        se_months_p1=period_cfg.get('se_months_p1'),
        se_months_p2=period_cfg.get('se_months_p2'),
        taxonomy_tags=cfg.get('taxonomy_tags'),
    )
    print(f'  KS auto-matched: {len(high_conf)}  for review: {len(review)}', flush=True)
    ks_by_kw = {m['Keyword']: m for m in high_conf}

    # ── Merge pipeline outputs ────────────────────────────────────────────────
    print('\nMerging pipeline outputs…', flush=True)
    gsc_pos_by_kw = {
        (r.get('query') or r.get('search_term') or ''): r.get('gsc_pos_p1', 0)
        for r in unified if r.get('gsc_pos_p1', 0)
    }

    url_path_by_idx = {}
    merged_rows = []

    for idx, b in enumerate(base):
        kw  = b.get('Keyword') or ''
        row = dict(b)

        se = se_by_kw.get(kw, {})
        row.update({k: v for k, v in se.items() if not k.startswith('_') and k != 'Keyword'})
        if se.get('_se_url_path'):
            url_path_by_idx[idx] = se['_se_url_path']

        ks = ks_by_kw.get(kw, {})
        row.update({k: v for k, v in ks.items() if k != 'Keyword'})

        if not row.get('LANG'):
            row['LANG'] = client_lang

        h = float(row.get('Volume Q1 2026') or row.get(f'Volume {p1_label}') or 0)
        i_val = float(row.get('Volume Q4 2025') or row.get(f'Volume {p2_label}') or 0)
        if h or i_val:
            row['Average Search Volume'] = round((h + i_val) / 6)

        if not row.get('Position SE Ranking'):
            gsc_pos = gsc_pos_by_kw.get(kw, 0)
            if gsc_pos:
                row['Position SE Ranking'] = round(gsc_pos)

        merged_rows.append(row)

    # ── Competitor classification (config-driven fallback) ───────────────────
    n_competitor = classify_competitors(merged_rows, cfg.get('competitors', []))
    if n_competitor:
        print(f"\nCompetitor classification: {n_competitor} rows reclassified from "
              f"config['competitors']", flush=True)

    # ── GA4 pro-rata conversion distribution ──────────────────────────────────
    print('\nDistributing GA4 conversions…', flush=True)

    # Build URL → keyword indices map (for SE URL paths)
    url_to_idxs: dict = {}
    for idx, path in url_path_by_idx.items():
        url_to_idxs.setdefault(path, []).append(idx)

    # For keywords with no SE URL, infer from word overlap with page path
    for idx, row in enumerate(merged_rows):
        if idx in url_path_by_idx:
            continue
        kw_words = set(normalize(row.get('Keyword', '')).split())
        for path, idxs in url_to_idxs.items():
            path_words = set(re.sub(r'[^a-z0-9]', ' ', path.lower()).split())
            if len(kw_words & path_words) >= 2:
                url_path_by_idx[idx] = path
                break

    # Distribute checkout (SEO) and offline-store (SEO proxy) conversions
    def _distribute_conversions(url_map: dict, conv_col: str) -> None:
        url_to_row_idxs: dict = {}
        for idx, path in url_path_by_idx.items():
            url_to_row_idxs.setdefault(path, []).append(idx)
        for path, row_idxs in url_to_row_idxs.items():
            page_events = url_map.get(path, 0)
            if not page_events:
                continue
            total_seo = sum(
                clean_num(merged_rows[i].get('Clics SEO Q1 2026', 0) or
                          merged_rows[i].get(f'Clics SEO {p1_label}', 0))
                for i in row_idxs
            )
            if not total_seo:
                continue
            for i in row_idxs:
                seo = clean_num(merged_rows[i].get('Clics SEO Q1 2026', 0) or
                                merged_rows[i].get(f'Clics SEO {p1_label}', 0))
                if seo:
                    merged_rows[i][conv_col] = round(seo / total_seo * page_events, 4)

    # Column ownership: Conversions SEM P1 (col AC) is exclusively owned by
    # sem_qv.run_sem_qv() (Thomas's QV-SEM LP-attribution methodology) whenever
    # GA4 Ads data is configured for this brand — it overwrites this column
    # unconditionally later in this run. Writing the offline-store proxy here
    # too would just be silently discarded, and misreports the pre-overwrite
    # "hit count" below. Only fall back to the proxy when GA4 Ads QV SEM isn't
    # configured, so the column isn't left completely blank.
    _ga4_ads_id = sheets_cfg.get('ga4_ads_file_id')
    has_qv_sem = bool(_ga4_ads_id) and str(_ga4_ads_id).strip().upper() != 'TBD'
    _distribute_conversions(checkout_map, f'Conversions SEO {p1_label}')
    if not has_qv_sem:
        _distribute_conversions(offline_map, f'Conversions SEM {p1_label}')
    _distribute_conversions(checkout_q4_map, f'Conversions SEO {p2_label}')
    _distribute_conversions(offline_q4_map, f'Conversions SEM {p2_label}')

    conv_seo = sum(1 for r in merged_rows if r.get(f'Conversions SEO {p1_label}'))
    sem_p1_note = 'owned by sem_qv.py (written below)' if has_qv_sem else 'SEM proxy (no GA4 Ads configured)'
    print(f'  Conversion hits — SEO: {conv_seo}  |  Conversions SEM P1: {sem_p1_note}', flush=True)

    # ── Build row values aligned to Masterlist headers ────────────────────────
    print('\nReading Masterlist headers…', flush=True)
    master_hdr_raw = sheets_get(token, master_id, f"'{master_tab}'!1:1")
    if not master_hdr_raw:
        sys.exit(f"ERROR: Could not read Masterlist '{master_tab}' headers")

    master_hdr = [str(h) for h in master_hdr_raw[0]]

    # Apply header corrections (fix outdated year labels)
    hdr_updates = []
    for i, h in enumerate(master_hdr):
        if h in header_corrections:
            new_h = header_corrections[h]
            master_hdr[i] = new_h
            hdr_updates.append((f"'{master_tab}'!{col_letter(i + 1)}1", [[new_h]]))
            print(f'  Header corrected: "{h}" → "{new_h}"', flush=True)
    if hdr_updates:
        sheets_batch_update(token, master_id, hdr_updates)

    # Build alias lookup: if pipeline writes "CPC avg. SEM Q1 2026" but sheet has
    # "CPC moy. SEM Q1 2026", the alias maps the pipeline key to the sheet column.
    alias_lookup = {}
    for pipeline_key, sheet_col in column_aliases.items():
        if sheet_col in master_hdr:
            alias_lookup[pipeline_key] = sheet_col

    # ── Resolve ARRAYFORMULA target + input columns by header name, not literal
    # letters. A column inserted anywhere in the Masterlist would silently break
    # formulas that hardcode "J", "AF", etc. — resolving by name survives that.
    def _hdr_letter(name: str, required: bool = True):
        aliased = alias_lookup.get(name, name)
        if aliased in master_hdr:
            return col_letter(master_hdr.index(aliased) + 1)
        if required:
            sys.exit(f"ERROR: required column '{name}' not found in Masterlist headers "
                      f"— cannot build ARRAYFORMULA cells")
        return None

    kw_col     = _hdr_letter('Keyword')
    vol_col    = _hdr_letter('Average Search Volume')
    os_p1_col  = _hdr_letter(f'Clics OneSearch {p1_label}')
    os_p2_col  = _hdr_letter(f'Clics OneSearch {p2_label}')
    cpc_col    = _hdr_letter(f'CPC SEO {p1_label}')
    seo_p1_col = _hdr_letter(f'Clics SEO {p1_label}')
    seo_p2_col = _hdr_letter(f'Clics SEO {p2_label}')
    cov_p1_col = _hdr_letter(f'Coverage One Search {p1_label}', required=False)
    cov_p2_col = _hdr_letter(f'Coverage One Search {p2_label}', required=False)
    cost_p1_col = _hdr_letter(f'Cost SEO {p1_label}', required=False)
    cost_p2_col = _hdr_letter(f'Cost SEO {p2_label}', required=False)

    arrayformulas = []
    formula_col_ranges = set()
    if cov_p1_col:
        arrayformulas.append((f"'{T}'!{cov_p1_col}2",
            f'=ARRAYFORMULA(IF({kw_col}2:{kw_col}="","",IF({vol_col}2:{vol_col}=0,"",'
            f'{os_p1_col}2:{os_p1_col}/{vol_col}2:{vol_col})))'))
        formula_col_ranges.add(f"'{T}'!{cov_p1_col}2:{cov_p1_col}")
    if cov_p2_col:
        arrayformulas.append((f"'{T}'!{cov_p2_col}2",
            f'=ARRAYFORMULA(IF({kw_col}2:{kw_col}="","",IF({vol_col}2:{vol_col}=0,"",'
            f'{os_p2_col}2:{os_p2_col}/{vol_col}2:{vol_col})))'))
        formula_col_ranges.add(f"'{T}'!{cov_p2_col}2:{cov_p2_col}")
    if cost_p1_col:
        arrayformulas.append((f"'{T}'!{cost_p1_col}2",
            f'=ARRAYFORMULA(IF(ISBLANK({cpc_col}2:{cpc_col}),"",{cpc_col}2:{cpc_col}*{seo_p1_col}2:{seo_p1_col}))'))
        formula_col_ranges.add(f"'{T}'!{cost_p1_col}2:{cost_p1_col}")
    if cost_p2_col:
        arrayformulas.append((f"'{T}'!{cost_p2_col}2",
            f'=ARRAYFORMULA(IF(ISBLANK({cpc_col}2:{cpc_col}),"",{cpc_col}2:{cpc_col}*{seo_p2_col}2:{seo_p2_col}))'))
        formula_col_ranges.add(f"'{T}'!{cost_p2_col}2:{cost_p2_col}")
    if not arrayformulas:
        print('  WARNING: no Coverage/Cost columns found — skipping ARRAYFORMULA cells', flush=True)

    def build_row(row_dict: dict) -> list:
        out = []
        for h in master_hdr:
            pipeline_key = next((k for k, v in alias_lookup.items() if v == h), h)
            val = row_dict.get(pipeline_key, row_dict.get(h, ''))
            out.append(val if val is not None else '')
        return out

    values_to_write = [build_row(r) for r in merged_rows]

    # ── Ensure sheet has enough rows ──────────────────────────────────────────
    needed_rows   = len(values_to_write) + 50
    gid, cur_rows = get_sheet_gid(token, master_id, master_tab)
    if cur_rows < needed_rows:
        extra = needed_rows - cur_rows
        print(f"  Expanding '{master_tab}': {cur_rows} → {needed_rows} rows", flush=True)
        expand_sheet_rows(token, master_id, gid, extra)

    # ── Clear and write Masterlist ────────────────────────────────────────────
    print(f"\nClearing Masterlist '{master_tab}' rows 2+…", flush=True)
    sheets_clear(token, master_id, f"'{master_tab}'!A2:ZZ")

    print(f"Writing {len(values_to_write)} rows to Masterlist…", flush=True)
    import time as _time
    CHUNK = 500
    for i in range(0, len(values_to_write), CHUNK):
        chunk     = values_to_write[i:i + CHUNK]
        row_start = i + 2
        row_end   = row_start + len(chunk) - 1
        range_str = f"'{master_tab}'!A{row_start}:ZZ{row_end}"
        sheets_batch_update(token, master_id, [(range_str, chunk)])
        print(f"  Wrote rows {row_start}–{row_end}", flush=True)
        if i + CHUNK < len(values_to_write):
            _time.sleep(1)

    # ── Write KW Review tabs ──────────────────────────────────────────────────
    print('\nWriting KW Review tabs…', flush=True)

    def write_review_tab(tab_name: str, rows: list) -> None:
        if not rows:
            return
        gid = ensure_tab_exists(token, master_id, tab_name)
        _, cur_rows = get_sheet_gid(token, master_id, tab_name)
        needed = len(rows) + 50
        if needed > cur_rows:
            expand_sheet_rows(token, master_id, gid, needed - cur_rows)
        sheets_clear(token, master_id, f"'{tab_name}'!A2:ZZ")
        hdr_raw = sheets_get(token, master_id, f"'{tab_name}'!1:1")
        if not hdr_raw or not hdr_raw[0]:
            hdrs    = list(rows[0].keys()) if rows else []
            sheets_batch_update(token, master_id, [(f"'{tab_name}'!A1", [hdrs])])
        else:
            hdrs = [str(h) for h in hdr_raw[0]]
        row_vals = [[str(r.get(h, '')) for h in hdrs] for r in rows]
        for i in range(0, len(row_vals), CHUNK):
            chunk = row_vals[i:i + CHUNK]
            r_start = i + 2
            sheets_batch_update(token, master_id,
                                [(f"'{tab_name}'!A{r_start}:ZZ{r_start + len(chunk) - 1}", chunk)])
        print(f"  {tab_name}: {len(row_vals)} rows written", flush=True)

    write_review_tab(kw_review_border,  [r for r in review if r.get('_review_type') == 'border'])
    write_review_tab(kw_review_unmatch, [r for r in review if r.get('_review_type') != 'border'])

    # ── Write ARRAYFORMULA cells ──────────────────────────────────────────────
    print('\nWriting ARRAYFORMULA cells…', flush=True)
    for range_str in formula_col_ranges:
        sheets_clear(token, master_id, range_str)
    sheets_batch_update(token, master_id, [(cell, [[formula]]) for cell, formula in arrayformulas])
    print(f'  {len(arrayformulas)} formulas written', flush=True)

    # ── Post-write: SE Ranking API volume enrichment ──────────────────────────
    ser_key = env.get('SE_RANKING_API_KEY', '')
    if ser_key:
        print('\nRunning SE Ranking volume enrichment…', flush=True)
        try:
            enrich_volumes(token, master_id, master_tab, ser_key, cfg=cfg)
            enrich_monthly_volumes(token, master_id, master_tab, ser_key, cfg=cfg)
        except Exception as exc:
            print(f'  WARNING: SE enrichment failed ({exc}) — volumes may be incomplete', flush=True)
    else:
        print('\nSE_RANKING_API_KEY not set — skipping volume enrichment', flush=True)

    # ── SEM QV attribution (final pipeline step) ──────────────────────────────
    run_sem_qv(token, cfg)

    # ── Validation summary ────────────────────────────────────────────────────
    from pipeline.validate import validate_masterlist
    print('\nRunning post-write validation…', flush=True)
    raw_master = sheets_get(token, master_id, f"'{master_tab}'!A1:BF")
    if raw_master:
        val_hdrs, val_rows = raw_to_dicts(raw_master)
        ok, report = validate_masterlist(val_rows, val_hdrs, cfg)
        print(report, flush=True)
        if not ok:
            print('⚠  Validation found blocking issues — review before running build_dashboard.py',
                  flush=True)
    else:
        print('WARNING: Could not re-read Masterlist for validation', flush=True)

    print('\n' + '=' * 64, flush=True)
    print(f'Pipeline complete. Masterlist rows: {len(values_to_write)}', flush=True)
    print(f'Review the Masterlist, then run:', flush=True)
    print(f'  python3 build_dashboard.py --brand {brand_key}', flush=True)
    print('=' * 64, flush=True)

    _log_fh.close()
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__


def main() -> None:
    parser = argparse.ArgumentParser(description='OneSearch Pipeline')
    parser.add_argument('--brand', default=DEFAULT_BRAND,
                        help=f'Brand handle (default: {DEFAULT_BRAND}), or "all"')
    parser.add_argument('--max-rows', type=int, default=None,
                        help='Limit rows per source (for testing)')
    args = parser.parse_args()

    brands = [args.brand] if args.brand != 'all' else _list_brands()
    for brand in brands:
        _run(brand, max_rows=args.max_rows)


def _list_brands() -> list:
    brands_dir = os.path.join(os.path.dirname(__file__), 'brands')
    return [
        d for d in os.listdir(brands_dir)
        if os.path.isfile(os.path.join(brands_dir, d, 'config.json'))
    ]


if __name__ == '__main__':
    main()
