"""Normalize raw rows from each source into standard internal field names."""
import re
from .normalize import normalize, clean_num, parse_pct


def norm_gsc(rows: list) -> list:
    out = []
    for j in rows:
        query = str(j.get('Top queries') or '').strip()
        if not query:
            continue
        c1 = clean_num(j.get('1/1/26 - 3/31/26 Clicks'))
        c2 = clean_num(j.get('10/1/25 - 12/31/25 Clicks'))
        if c1 == 0 and c2 == 0:
            continue
        out.append({
            'norm_query': normalize(query),
            'query': query,
            'gsc_clicks_p1': c1,
            'gsc_clicks_p2': c2,
            'gsc_impr_p1':   clean_num(j.get('1/1/26 - 3/31/26 Impressions')),
            'gsc_impr_p2':   clean_num(j.get('10/1/25 - 12/31/25 Impressions')),
            'gsc_ctr_p1':    parse_pct(j.get('1/1/26 - 3/31/26 CTR')),
            'gsc_ctr_p2':    parse_pct(j.get('10/1/25 - 12/31/25 CTR')),
            'gsc_pos_p1':    clean_num(j.get('1/1/26 - 3/31/26 Position')),
            'gsc_pos_p2':    clean_num(j.get('10/1/25 - 12/31/25 Position')),
        })
    return out


def norm_sqr(rows: list) -> list:
    out = []
    for j in rows:
        term = str(j.get('Search term') or '').strip()
        if not term:
            continue
        # Drop Google Ads aggregate summary rows
        if term.startswith('Total:'):
            continue
        # Drop Performance Max rows — they dilute Search ROAS and are not search-intent data
        campaign_type = str(j.get('Campaign Type') or '').strip().lower()
        if 'performance max' in campaign_type:
            continue
        c1 = clean_num(j.get('Clicks'))
        c2 = clean_num(j.get('Clicks (Compare to)'))
        if c1 == 0 and c2 == 0:
            continue
        out.append({
            'norm_term':      normalize(term),
            'search_term':    term,
            'search_keyword': str(j.get('Search keyword') or ''),
            'sqr_clicks_p1':  c1,
            'sqr_clicks_p2':  c2,
            'sqr_cost_p1':    clean_num(j.get('Cost')),
            'sqr_cost_p2':    clean_num(j.get('Cost (Compare to)')),
            'sqr_impr_p1':    clean_num(j.get('Impr.')),
            'sqr_impr_p2':    clean_num(j.get('Impr. (Compare to)')),
        })
    return out


def norm_ks(rows: list) -> list:
    out = []
    for j in rows:
        kw = str(j.get('Keyword') or '').strip()
        if not kw:
            continue
        out.append({
            'norm_keyword':         normalize(kw),
            'keyword':              kw,
            'avg_monthly_searches': clean_num(j.get('Avg. monthly searches') or 0),
            'lang':                 j.get('LANG')  or '',
            'topic':                j.get('TOPIC') or '',
            'category':     j.get('CATEGORY')     or '',
            'sub_category': j.get('SUB-CATEGORY') or '',
            'Yogurt types':       j.get('Yogurt types')       or '',
            'Taste':              j.get('Taste')              or '',
            'Packaging':          j.get('Packaging')          or '',
            'Ingredient':         j.get('Ingredient')         or '',
            'Brands':             j.get('Brand') or j.get('Brands') or '',
            'Retailer':           j.get('Retailer')           or '',
            'Demography':         j.get('Demography')         or '',
            'Benefits':           j.get('Benefits')           or '',
            'Testimonials':       j.get('Testimonials')       or '',
            'Bio':                j.get('Bio')                or '',
            'Moments':            j.get('Moments')            or '',
            'Recipes':            j.get('Recipes')            or '',
            'Searches: Oct 2025': j.get('Searches: Oct 2025') or '',
            'Searches: Nov 2025': j.get('Searches: Nov 2025') or '',
            'Searches: Dec 2025': j.get('Searches: Dec 2025') or '',
            'Searches: Jan 2026': j.get('Searches: Jan 2026') or '',
            'Searches: Feb 2026': j.get('Searches: Feb 2026') or '',
            'Searches: Mar 2026': j.get('Searches: Mar 2026') or '',
        })
    return out


def norm_se(rows: list) -> list:
    """Normalize SE Ranking rows. Handles BOM on Keyword col. Filters to position ≤ 100."""
    out = []
    for j in rows:
        kw_key = next((k for k in j if k.replace('﻿', '') == 'Keyword'), 'Keyword')
        kw = str(j.get(kw_key) or '').strip()
        if not kw:
            continue
        pos = clean_num(j.get('Position'))
        if pos <= 0 or pos > 100:
            continue
        cpc_str = re.sub(r'[^0-9.]', '', str(j.get('CPC') or '0'))
        cpc = float(cpc_str) if cpc_str else 0.0
        raw_url = str(j.get('URL') or '').strip()
        # Extract just the path, strip domain (https://www.oikos.com/path/ → /path/)
        se_path = re.sub(r'^https?://[^/]+', '', raw_url).rstrip('/') or ''
        out.append({
            'norm_se_keyword':  normalize(kw),
            'se_keyword':       kw,
            'se_position':      pos,
            'se_search_vol':    clean_num(j.get('Search vol.')),
            'se_cpc':           cpc,
            'se_search_intent': j.get('Search intent') or '',
            'se_url_path':      se_path,
        })
    return out
