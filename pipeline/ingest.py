"""Normalize raw rows from each source into standard internal field names."""
import re
from .normalize import normalize, clean_num, parse_pct


# ── GSC ──────────────────────────────────────────────────────────────────────

def _detect_gsc_prefixes(rows: list):
    """Auto-detect P1/P2 date prefixes from GSC column headers.

    GSC exports use columns like '1/1/26 - 3/31/26 Clicks'. This function
    scans all keys in the first non-empty row and extracts the two date-range
    prefixes, returning them sorted by end-date descending (most recent = P1).
    Falls back to returning (None, None) if detection fails.
    """
    if not rows:
        return None, None
    sample = rows[0] if isinstance(rows[0], dict) else {}
    date_range_re = re.compile(r'^(\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*\d{1,2}/\d{1,2}/\d{2,4})\s+Clicks$')
    prefixes = []
    for col in sample:
        m = date_range_re.match(str(col))
        if m:
            prefixes.append(m.group(1))
    if len(prefixes) < 2:
        return None, None
    # Sort: most-recent end date first (P1). Compare last date segment.
    def _end_sort_key(prefix):
        end = prefix.split('-')[-1].strip()
        parts = end.split('/')
        try:
            return (int(parts[2]), int(parts[0]), int(parts[1]))
        except (IndexError, ValueError):
            return (0, 0, 0)
    prefixes.sort(key=_end_sort_key, reverse=True)
    return prefixes[0], prefixes[1]


def norm_gsc(rows: list, p1_prefix: str = None, p2_prefix: str = None) -> list:
    """Normalize Google Search Console query rows.

    p1_prefix / p2_prefix: the date-range string prefix used as a column-name
    prefix in the GSC export (e.g. '1/1/26 - 3/31/26'). If not supplied,
    they are auto-detected from the column headers. Raises ValueError if
    auto-detection fails and no prefixes are provided.
    """
    if not p1_prefix or not p2_prefix:
        detected_p1, detected_p2 = _detect_gsc_prefixes(rows)
        if not detected_p1:
            raise ValueError(
                "norm_gsc: could not detect GSC date-range column prefixes. "
                "Pass p1_prefix and p2_prefix explicitly from the brand config "
                "(config['period']['gsc_p1_prefix'] and gsc_p2_prefix)."
            )
        p1_prefix = p1_prefix or detected_p1
        p2_prefix = p2_prefix or detected_p2

    out = []
    for j in rows:
        query = str(j.get('Top queries') or '').strip()
        if not query:
            continue
        c1 = clean_num(j.get(f'{p1_prefix} Clicks'))
        c2 = clean_num(j.get(f'{p2_prefix} Clicks'))
        if c1 == 0 and c2 == 0:
            continue
        out.append({
            'norm_query': normalize(query),
            'query':      query,
            'gsc_clicks_p1': c1,
            'gsc_clicks_p2': c2,
            'gsc_impr_p1':   clean_num(j.get(f'{p1_prefix} Impressions')),
            'gsc_impr_p2':   clean_num(j.get(f'{p2_prefix} Impressions')),
            'gsc_ctr_p1':    parse_pct(j.get(f'{p1_prefix} CTR')),
            'gsc_ctr_p2':    parse_pct(j.get(f'{p2_prefix} CTR')),
            'gsc_pos_p1':    clean_num(j.get(f'{p1_prefix} Position')),
            'gsc_pos_p2':    clean_num(j.get(f'{p2_prefix} Position')),
        })
    return out


# ── SQR ──────────────────────────────────────────────────────────────────────

def norm_sqr(rows: list) -> list:
    out = []
    for j in rows:
        term = str(j.get('Search term') or '').strip()
        if not term:
            continue
        if term.startswith('Total:'):
            continue
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


# ── Keyword Study ─────────────────────────────────────────────────────────────

_MONTH_ABBR = {
    '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr',
    '05': 'May', '06': 'Jun', '07': 'Jul', '08': 'Aug',
    '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec',
}


def _se_month_label(iso_date: str) -> str:
    """'2026-01-01' → 'Searches: Jan 2026'"""
    parts = iso_date.split('-')
    if len(parts) < 2:
        return ''
    return f"Searches: {_MONTH_ABBR.get(parts[1], parts[1])} {parts[0]}"


def norm_ks(rows: list, se_months: list = None) -> list:
    """Normalize Keyword Study rows.

    se_months: list of ISO date strings for all reporting months in order
    (both periods combined), e.g. ['2025-10-01', ..., '2026-03-01'].
    Generated from config['period']['se_months_p2'] + config['period']['se_months_p1'].
    Falls back to Oikos Q1/Q4 2025-2026 defaults if not supplied.
    """
    if se_months is None:
        se_months = [
            '2025-10-01', '2025-11-01', '2025-12-01',
            '2026-01-01', '2026-02-01', '2026-03-01',
        ]

    month_labels = [_se_month_label(d) for d in se_months]

    out = []
    for j in rows:
        kw = str(j.get('Keyword') or '').strip()
        if not kw:
            continue
        # Issue 8: try both TOPIC (old) and TOPICS (new) column header
        topic = j.get('TOPIC') or j.get('TOPICS') or ''
        record = {
            'norm_keyword': normalize(kw),
            'keyword':      kw,
            'lang':         j.get('LANG')         or '',
            'topic':        topic,
            'category':     j.get('CATEGORY')     or '',
            'sub_category': j.get('SUB-CATEGORY') or '',
            'Yogurt types': j.get('Yogurt types') or '',
            'Taste':        j.get('Taste')        or '',
            'Packaging':    j.get('Packaging')    or '',
            'Ingredient':   j.get('Ingredient')   or '',
            'Brands':       j.get('Brand') or j.get('Brands') or '',
            'Retailer':     j.get('Retailer')     or '',
            'Demography':   j.get('Demography')   or '',
            'Benefits':     j.get('Benefits')     or '',
            'Testimonials': j.get('Testimonials') or '',
            'Bio':          j.get('Bio')          or '',
            'Moments':      j.get('Moments')      or '',
            'Recipes':      j.get('Recipes')      or '',
        }
        for label in month_labels:
            record[label] = j.get(label) or ''
        out.append(record)
    return out


# ── SE Ranking ───────────────────────────────────────────────────────────────

def norm_se(rows: list) -> list:
    """Normalize SE Ranking rows. Handles BOM on Keyword col. Filters to position <= 100."""
    out = []
    for j in rows:
        # BOM on first column header is stripped by finding the key that normalizes to 'Keyword'
        kw_key = next((k for k in j if k.replace('﻿', '').replace('﻿', '') == 'Keyword'), 'Keyword')
        kw = str(j.get(kw_key) or '').strip()
        if not kw:
            continue
        pos = clean_num(j.get('Position'))
        if pos <= 0 or pos > 100:
            continue
        cpc_str = re.sub(r'[^0-9.]', '', str(j.get('CPC') or '0'))
        cpc = float(cpc_str) if cpc_str else 0.0
        raw_url = str(j.get('URL') or '').strip()
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
