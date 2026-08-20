#!/usr/bin/env python3
"""
OneSearch HTML Dashboard Builder — generic, config-driven.

Patches build_html_oikos with brand config from brands/<handle>/config.json,
then runs the same HTML build pipeline. All brand-specific values come from
the config; hardcoded Oikos values in build_html_oikos are overridden at runtime.

Usage:
    python3 build_html.py
    python3 build_html.py --brand oikos-usa
"""
import argparse
import json
import os
import sys
from collections import defaultdict

# ── Path setup ────────────────────────────────────────────────────────────────
_SCRIPTS_DIR  = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR     = os.path.dirname(_SCRIPTS_DIR)
sys.path.insert(0, _ROOT_DIR)
sys.path.insert(0, _SCRIPTS_DIR)

import build_html_oikos as _bh
from pipeline.utils import load_brand_config, load_env, get_token, sheets_get as _sheets_get
from pipeline.normalize import clean_num


def _load_defaults() -> dict:
    path = os.path.join(_ROOT_DIR, 'brands', 'defaults.json')
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _build_data_map(p1: str, p2: str) -> list:
    return [
        (0, 'Keyword'), (1, 'TOPICS'), (2, 'CATEGORY'), (3, 'SUB-CATEGORY'),
        (4, 'Average Search Volume'),
        (5, f'Volume {p1}'),       (6,  f'Volume {p2}'),
        (9, f'Clics OneSearch {p1}'), (10, f'Impressions OneSearch {p1}'),
        (11, f'Clics OneSearch {p2}'), (12, f'Impressions OneSearch {p2}'),
        (13, f'Clics SEO {p1}'),   (14, f'Clics SEM {p1}'),
        (15, f'Clics SEO {p2}'),   (16, f'Clics SEM {p2}'),
        (17, f'Impr. SEO {p1}'),   (18, f'Impr. SEM {p1}'),
        (19, f'Impr. SEO {p2}'),   (20, f'Impr. SEM {p2}'),
        (21, f'CTR SEO {p1}'),     (22, f'CTR SEM {p1}'),
        (23, f'CTR SEO {p2}'),     (24, f'CTR SEM {p2}'),
        (25, f'Conversions SEO {p1}'), (26, f'Conversions SEM {p1}'),
        (27, f'Conversions SEO {p2}'), (28, f'Conversions SEM {p2}'),
        (29, f'CPC SEO {p1}'),     (30, f'CPC avg. SEM {p1}'),
        (32, f'Cost SEO {p1}'),    (34, f'Cost SEO {p2}'),
        (35, 'Position SE Ranking'), (36, 'LANG'),
    ]


def _patch_module(brand_key: str, cfg: dict) -> None:
    """Override build_html_oikos module-level globals and buggy functions from brand config."""
    brand_cfg  = cfg.get('brand', {})
    period_cfg = cfg.get('period', {})
    sheets_cfg = cfg.get('sheets', {})
    defaults   = _load_defaults()

    # ── Module-level globals ──────────────────────────────────────────────────
    _bh.MASTER_ID   = sheets_cfg['master_id']
    _bh.MASTER_TAB  = sheets_cfg.get('master_tab', 'Listing')
    _bh.QS_SHEET_ID = sheets_cfg.get('qs_sheet_id', '')
    _bh.BRAND_NAME  = cfg.get('client_name', brand_key)
    def _color_or_default(value, default):
        # A brand's color fields are frequently left as the literal placeholder
        # "TBD" until someone picks real brand colors. apply_brand() does a blind
        # string substitution of these into the template's CSS, so an unfixed
        # "TBD" becomes an invalid CSS value like "background: TBD" — silently
        # dropped by the browser, breaking backgrounds and making white-on-color
        # text invisible. Fall back to a neutral default instead.
        v = str(value or '').strip()
        return default if (not v or v.upper() == 'TBD') else v

    _bh.BRAND_COLOR = _color_or_default(brand_cfg.get('color'), '#004f79')
    _bh.ACCENT_CLR  = _color_or_default(brand_cfg.get('accent_color'), '#1a7aad')
    _bh.LIGHT_BG    = _color_or_default(brand_cfg.get('light_bg'), '#f0f6fb')
    _bh.PERIOD_P1   = period_cfg.get('p1_label', 'Q1 2026')
    _bh.PERIOD_P4   = period_cfg.get('p2_label', 'Q4 2025')
    _bh.PERIOD      = period_cfg.get('display', f"{_bh.PERIOD_P1} vs {_bh.PERIOD_P4}")
    _bh.TERRITORY_DEFINITIONS = cfg.get('territories', {})
    _bh.TERRITORY_TOPICS      = list(cfg.get('territories', {}).keys())
    _bh.TOPIC_ORDER           = cfg.get('topic_order', [])
    _bh.OS_RECO_FILTER        = cfg.get('reco_filter', {})
    _bh.OS_RECO_MERGE_GROUPS  = cfg.get('reco_merge_groups', {})
    _bh.TAXONOMY_TAGS         = cfg.get('taxonomy_tags', _bh.TAXONOMY_TAGS)
    _bh.BRAND_REGEX_SHEET_ID  = brand_cfg.get('regex_sheet_id', '')
    _bh.BRAND_REGEX_TAB       = brand_cfg.get('regex_sheet_tab', '')
    _bh.BRAND_REGEX_NAME      = brand_cfg.get('regex_sheet_name_col', brand_key)
    _bh.BRAND_REGEX_DEFAULT   = brand_cfg.get('regex_default', brand_key.split('-')[0])
    cov_cfg = cfg.get('coverage_targets', {})
    def_cov = defaults.get('coverage_targets', {})
    _bh.COV_TARGET_BRAND   = cov_cfg.get('brand',   def_cov.get('brand', 10))
    _bh.COV_TARGET_GENERIC = cov_cfg.get('generic', def_cov.get('generic', 3))
    _bh.DATA_MAP = _build_data_map(_bh.PERIOD_P1, _bh.PERIOD_P4)
    _bh.SPEND_P1 = [f'Spent SEM {_bh.PERIOD_P1}', f'Dépense SEM {_bh.PERIOD_P1}',
                    f'Spend SEM {_bh.PERIOD_P1}',  f'Cost SEM {_bh.PERIOD_P1}']
    _bh.SPEND_P4 = [f'Spent SEM {_bh.PERIOD_P4}', f'Dépense SEM {_bh.PERIOD_P4}',
                    f'Spend SEM {_bh.PERIOD_P4}',  f'Cost SEM {_bh.PERIOD_P4}']

    # SEM conversions (QV SEM) are only real once a GA4 Ads Sessions export is
    # configured for this brand — otherwise the column is genuinely unmeasured,
    # not zero. Narrative text must say so instead of reading it as a real zero.
    ga4_ads_id = sheets_cfg.get('ga4_ads_file_id')
    _bh.SEM_CONV_MEASURED = bool(ga4_ads_id) and str(ga4_ads_id).strip().upper() != 'TBD'

    # ── Shared API helpers → use pipeline.utils ───────────────────────────────
    _bh.load_env   = load_env
    _bh.get_token  = get_token
    _bh.sheets_get = _sheets_get

    # ── Fix _n(): old version breaks French numbers (space = thousands sep) ───
    _bh._n = lambda v, default=0: (
        clean_num(v) if v is not None and str(v).strip() != '' else default
    )

    # ── Fix read_masterlist(): extend column range from BE → BF ──────────────
    def _patched_read_masterlist(token):
        hdrs_raw = _bh.sheets_get(token, _bh.MASTER_ID, f"'{_bh.MASTER_TAB}'!1:1")
        if not hdrs_raw:
            raise ValueError('Cannot read masterlist headers')
        headers = [str(h) for h in hdrs_raw[0]]
        print(f'  {len(headers)} columns', flush=True)
        rows = []
        for start in range(2, 20000, 1000):
            chunk = _bh.sheets_get(token, _bh.MASTER_ID,
                                   f"'{_bh.MASTER_TAB}'!A{start}:BF{start+999}")
            if chunk is None or chunk == []:
                break
            for row in chunk:
                while len(row) < len(headers):
                    row.append('')
                rows.append({h: row[i] for i, h in enumerate(headers)})
        print(f'  {len(rows)} rows', flush=True)
        return headers, rows
    _bh.read_masterlist = _patched_read_masterlist

    # ── Fix build_data(): headers-based spend detection + dynamic col names ───
    def _patched_build_data(rows, headers=None):
        if headers is None:
            headers = list(rows[0].keys()) if rows else []
        spend_p1 = next((c for c in _bh.SPEND_P1 if c in headers), None)
        spend_p4 = next((c for c in _bh.SPEND_P4 if c in headers), None)
        p1, p4   = _bh.PERIOD_P1, _bh.PERIOD_P4
        data_rows = []
        for row in rows:
            kw = _bh._s(row.get('Keyword', ''))
            if not kw:
                continue
            avg_vol     = _bh._n(row.get('Average Search Volume', 0))
            clics_os_p1 = _bh._n(row.get(f'Clics OneSearch {p1}', 0))
            clics_os_p4 = _bh._n(row.get(f'Clics OneSearch {p4}', 0))
            cov_p1 = round(clics_os_p1 / avg_vol, 4) if avg_vol > 0 else 0
            cov_p4 = round(clics_os_p4 / avg_vol, 4) if avg_vol > 0 else 0
            dr = [0] * 37
            for idx, col in _bh.DATA_MAP:
                val = row.get(col, '')
                dr[idx] = _bh._s(val) if idx in _bh.STRING_INDICES else _bh._n(val)
            dr[7]  = cov_p1
            dr[8]  = cov_p4
            dr[31] = _bh._n(row.get(spend_p1, 0)) if spend_p1 else 0
            dr[33] = _bh._n(row.get(spend_p4, 0)) if spend_p4 else 0
            data_rows.append(dr)
        return data_rows
    _bh.build_data = _patched_build_data

    # ── Fix compute_territory_stats(): headers-based spend + dynamic cols ─────
    def _patched_compute_territory_stats(rows, headers=None):
        if headers is None:
            headers = list(rows[0].keys()) if rows else []
        spend_p1 = next((c for c in _bh.SPEND_P1 if c in headers), None)
        spend_p4 = next((c for c in _bh.SPEND_P4 if c in headers), None)
        p1, p4   = _bh.PERIOD_P1, _bh.PERIOD_P4
        stats = defaultdict(lambda: {
            'count': 0,
            'volume_q1': 0.0, 'volume_q4': 0.0, 'avg_volume': 0.0,
            'os_clicks_q1': 0.0, 'os_clicks_q4': 0.0,
            'seo_clicks_q1': 0.0, 'seo_clicks_q4': 0.0,
            'sem_clicks_q1': 0.0, 'sem_clicks_q4': 0.0,
            'conv_seo_q1': 0.0, 'conv_seo_q4': 0.0,
            'conv_sem_q1': 0.0, 'conv_sem_q4': 0.0,
            'spend_q1': 0.0, 'spend_q4': 0.0,
            'top_kws': [],
        })
        for row in rows:
            topic = _bh._s(row.get('TOPICS', ''))
            kw    = _bh._s(row.get('Keyword', ''))
            if not topic or not kw:
                continue
            s = stats[topic]
            s['count'] += 1
            s['volume_q1']  += _bh._n(row.get(f'Volume {p1}', 0))
            s['volume_q4']  += _bh._n(row.get(f'Volume {p4}', 0))
            s['avg_volume'] += _bh._n(row.get('Average Search Volume', 0))
            os_q1  = _bh._n(row.get(f'Clics OneSearch {p1}', 0))
            os_q4  = _bh._n(row.get(f'Clics OneSearch {p4}', 0))
            seo_q1 = _bh._n(row.get(f'Clics SEO {p1}', 0))
            seo_q4 = _bh._n(row.get(f'Clics SEO {p4}', 0))
            sem_q1 = _bh._n(row.get(f'Clics SEM {p1}', 0))
            sem_q4 = _bh._n(row.get(f'Clics SEM {p4}', 0))
            s['os_clicks_q1']  += os_q1;  s['os_clicks_q4']  += os_q4
            s['seo_clicks_q1'] += seo_q1; s['seo_clicks_q4'] += seo_q4
            s['sem_clicks_q1'] += sem_q1; s['sem_clicks_q4'] += sem_q4
            s['conv_seo_q1'] += _bh._n(row.get(f'Conversions SEO {p1}', 0))
            s['conv_seo_q4'] += _bh._n(row.get(f'Conversions SEO {p4}', 0))
            s['conv_sem_q1'] += _bh._n(row.get(f'Conversions SEM {p1}', 0))
            s['conv_sem_q4'] += _bh._n(row.get(f'Conversions SEM {p4}', 0))
            if spend_p1:
                s['spend_q1'] += _bh._n(row.get(spend_p1, 0))
            if spend_p4:
                s['spend_q4'] += _bh._n(row.get(spend_p4, 0))
            s['top_kws'].append({
                'kw': kw, 'os_q1': os_q1, 'os_q4': os_q4,
                'avg_vol': _bh._n(row.get('Average Search Volume', 0)),
                'seo_q1': seo_q1, 'sem_q1': sem_q1,
            })
        for s in stats.values():
            s['top_kws'].sort(key=lambda x: x['os_q1'], reverse=True)
            s['top_kws'] = s['top_kws'][:8]
        return dict(stats)
    _bh.compute_territory_stats = _patched_compute_territory_stats

    # ── Fix build_sqr_data(): dynamic column names ────────────────────────────
    def _patched_build_sqr_data(rows):
        p1, p4 = _bh.PERIOD_P1, _bh.PERIOD_P4
        sqr_rows = []
        for r in rows:
            sem_q1 = _bh._n(r.get(f'Clics SEM {p1}', 0))
            sem_q4 = _bh._n(r.get(f'Clics SEM {p4}', 0))
            if sem_q1 <= 0 and sem_q4 <= 0:
                continue
            kw     = _bh._s(r.get('Keyword', ''))
            impr_q1= _bh._n(r.get(f'Impr. SEM {p1}', 0))
            cout_q1= _bh._n(r.get(f'Spent SEM {p1}') or r.get(f'Cost SEM {p1}')
                             or r.get(f'Coût SEM {p1}', 0))
            conv_q1= _bh._n(r.get(f'Conversions SEM {p1}', 0))
            ctr_q1 = _bh._n(r.get(f'CTR SEM {p1}', 0))
            cpc_q1 = _bh._n(r.get(f'CPC avg. SEM {p1}') or r.get(f'CPC moy. SEM {p1}', 0))
            cpa_q1 = cout_q1 / conv_q1 if conv_q1 > 0 else 0
            impr_q4= _bh._n(r.get(f'Impr. SEM {p4}', 0))
            cout_q4= _bh._n(r.get(f'Spent SEM {p4}') or r.get(f'Cost SEM {p4}')
                             or r.get(f'Coût SEM {p4}', 0))
            conv_q4= _bh._n(r.get(f'Conversions SEM {p4}', 0))
            ctr_q4 = _bh._n(r.get(f'CTR SEM {p4}', 0))
            cpa_q4 = cout_q4 / conv_q4 if conv_q4 > 0 else 0
            sqr_rows.append([
                kw, _bh._s(r.get('TOPICS', '')), '', '', '',
                impr_q1, sem_q1, cout_q1, 0, conv_q1, 0, ctr_q1, cpc_q1, cpa_q1,
                impr_q4, sem_q4, cout_q4, 0, conv_q4, 0, ctr_q4, 0, cpa_q4,
                _bh._s(r.get('TOPICS', '')), _bh._s(r.get('CATEGORY', '')),
            ])
        sqr_rows.sort(key=lambda x: x[6], reverse=True)
        lines = ['var SQR_ACTIVIA = [']
        for i, row in enumerate(sqr_rows):
            comma = ',' if i < len(sqr_rows) - 1 else ''
            lines.append('  [' + ','.join(_bh._js_val(v) for v in row) + ']' + comma)
        lines.append('];')
        return '\n'.join(lines)
    _bh.build_sqr_data = _patched_build_sqr_data


def main() -> None:
    parser = argparse.ArgumentParser(description='OneSearch HTML Dashboard Builder')
    parser.add_argument('--brand', default='oikos-usa')
    args = parser.parse_args()
    brand_key = args.brand

    cfg = load_brand_config(brand_key)
    _patch_module(brand_key, cfg)

    dashboards_dir = os.path.join(_ROOT_DIR, 'dashboards', brand_key)
    os.makedirs(dashboards_dir, exist_ok=True)
    _bh.OUTPUT_DIR  = dashboards_dir
    _bh.OUTPUT_FILE = os.path.join(dashboards_dir,
                                   f'{brand_key.replace("/", "-")}_onesearch_dashboard.html')

    print(f'Building {_bh.BRAND_NAME} OneSearch Dashboard…', flush=True)

    print('\n  Loading credentials…', flush=True)
    env   = load_env()
    token = get_token(env)
    print('  Token OK', flush=True)

    print(f'\n  Reading Masterlist "{_bh.MASTER_TAB}"…', flush=True)
    headers, rows = _bh.read_masterlist(token)

    print('\n  Building DATA…', flush=True)
    data_rows = _bh.build_data(rows, headers)
    print(f'  {len(data_rows)} keyword rows', flush=True)

    print('\n  Building TAGS…', flush=True)
    tags = _bh.build_tags(rows)
    print(f'  {len(tags)} keywords with taxonomy tags', flush=True)

    print('\n  Computing territory stats…', flush=True)
    territory_stats = _bh.compute_territory_stats(rows, headers)
    classified = sum(s['count'] for s in territory_stats.values())
    print(f'  {len(territory_stats)} territories · {classified} classified rows', flush=True)

    print('\n  Loading brand-detection regex from reference sheet…', flush=True)
    brand_regex = _bh.load_brand_regex(token)

    print('\n  Loading HTML template…', flush=True)
    with open(_bh.TEMPLATE, encoding='utf-8') as f:
        html = f.read()
    print(f'  Template: {len(html):,} chars', flush=True)

    print('\n  Injecting DATA, TAGS, QS, SQR…', flush=True)
    html, _ = _bh.replace_block(html, 'DATA', _bh.js_data(data_rows))
    html, _ = _bh.replace_block(html, 'TAGS', _bh.js_tags(tags))
    qs_js   = _bh.load_qs_data(token, rows)
    sqr_js  = _bh.build_sqr_data(rows)
    html, _ = _bh.replace_block(html, 'QS_CLASSIFIED', qs_js)
    html, _ = _bh.replace_block(html, 'SQR_ACTIVIA',   sqr_js, decl='var')
    html, _ = _bh.replace_block(html, 'SQR_DATA',      'var SQR_DATA = [];', decl='var')

    print('  Applying brand colours and labels…', flush=True)
    html = _bh.apply_brand(html)

    print('  Applying English labels…', flush=True)
    html = _bh.apply_english(html)

    print('\n  Building Territory Deep Dive panel…', flush=True)
    html = _bh.replace_territory_panel(html, _bh.build_territory_panel(territory_stats))

    print('  Building Recommendations panel…', flush=True)
    html = _bh.replace_recos_panel(html, territory_stats)

    print('  Patching OneSearch JS…', flush=True)
    html = _bh.patch_onesearch_js(html)
    # Fix any residual hardcoded brand example string after oikos-specific patch
    brand_lower = _bh.BRAND_NAME.lower()
    html = html.replace('"oikos usa"',          f'"{brand_lower}"')
    html = html.replace('<em>oikos usa</em>',    f'<em>{brand_lower}</em>')

    print('  Stripping embedded docs…', flush=True)
    html = _bh.clean_embedded_docs(html)
    html = _bh.truncate_after_last_script(html)

    print('  Injecting brand config, export UI, reco filter…', flush=True)
    html = _bh.inject_brand_config(html, brand_regex)
    html = _bh.inject_export_ui(html)
    html = _bh.inject_reco_filter(html)

    taxonomy_html = _bh.build_taxonomy_glossary_html(rows)
    if '<!-- TAXONOMY_GLOSSARY -->' in html:
        html = html.replace('<!-- TAXONOMY_GLOSSARY -->', taxonomy_html, 1)

    print(f'\n  Writing → {_bh.OUTPUT_FILE}', flush=True)
    with open(_bh.OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    size_kb = os.path.getsize(_bh.OUTPUT_FILE) / 1024
    print(f'\nDone.', flush=True)
    print(f'  Output : {_bh.OUTPUT_FILE}', flush=True)
    print(f'  Size   : {size_kb:.0f} KB', flush=True)
    print(f'  Open   : open "{_bh.OUTPUT_FILE}"', flush=True)


if __name__ == '__main__':
    main()
