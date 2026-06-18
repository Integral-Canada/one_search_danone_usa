"""Post-pipeline enrichment via external APIs.

Two steps, both run after the main pipeline writes to the Masterlist:

1. enrich_volumes — SE Ranking API fills Average Search Volume (G) for keywords
   that still have no volume after the pipeline (H and I both blank).

2. enrich_taxonomy — Claude API classifies keywords missing TOPICS/CATEGORY/
   SUB-CATEGORY and fills all taxonomy tag columns.

All public functions accept an optional `cfg` dict (brand config).
When provided, period labels, SE months, API source, taxonomy columns, and the
system prompt are read from cfg. Module-level defaults are kept for standalone use.
"""
import json
import time
import urllib.parse
import urllib.request

# Module-level defaults (overridden when cfg is passed at call time)
_DEFAULT_SE_MONTHS = [
    "2025-10-01", "2025-11-01", "2025-12-01",
    "2026-01-01", "2026-02-01", "2026-03-01",
]
_DEFAULT_SE_SOURCE = "us"

SE_BATCH     = 500   # max keywords per SE Ranking API call
CLAUDE_BATCH = 50    # keywords per Claude call
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

_DEFAULT_TAXONOMY_COLS = [
    'Questions', 'Yogurt types', 'Taste', 'Packaging', 'Ingredient',
    'Brands', 'Retailer', 'Demography', 'Benefits', 'Testimonials',
    'Bio', 'Moments', 'Recipes',
]
TOPIC_COLS = ['TOPICS', 'CATEGORY', 'SUB-CATEGORY']

_MONTH_ABBR = {
    '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr',
    '05': 'May', '06': 'Jun', '07': 'Jul', '08': 'Aug',
    '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec',
}


# ── Config helpers ─────────────────────────────────────────────────────────────

def _se_months(cfg: dict) -> list:
    """Return list of ISO month strings from brand config or fall back to default."""
    if cfg:
        period = cfg.get('period', {})
        p2 = period.get('se_months_p2', [])
        p1 = period.get('se_months_p1', [])
        combined = p2 + p1
        if combined:
            return combined
    return _DEFAULT_SE_MONTHS


def _se_source(cfg: dict) -> str:
    if cfg:
        return cfg.get('period', {}).get('se_api_source', _DEFAULT_SE_SOURCE)
    return _DEFAULT_SE_SOURCE


def _taxonomy_cols(cfg: dict) -> list:
    if cfg and cfg.get('taxonomy_tags'):
        return list(cfg['taxonomy_tags'])
    return _DEFAULT_TAXONOMY_COLS


def _month_label(iso_date: str) -> str:
    """'2026-01-01' → 'Searches: Jan 2026'"""
    parts = iso_date.split('-')
    if len(parts) < 2:
        return ''
    return f"Searches: {_MONTH_ABBR.get(parts[1], parts[1])} {parts[0]}"


def _p1_label(cfg: dict) -> str:
    return cfg.get('period', {}).get('p1_label', 'Q1 2026') if cfg else 'Q1 2026'


def _p2_label(cfg: dict) -> str:
    return cfg.get('period', {}).get('p2_label', 'Q4 2025') if cfg else 'Q4 2025'


def _build_system_message(cfg: dict) -> str:
    """Build Claude classification system message from brand config.

    Uses taxonomy_prompt.system_message if present.
    Otherwise builds a generic prompt from brand_context, topics, and taxonomy_tags.
    """
    tp = (cfg or {}).get('taxonomy_prompt', {})

    # Prefer an explicit full system message stored in config
    if tp.get('system_message'):
        return tp['system_message']

    brand_ctx   = tp.get('brand_context', 'this brand')
    topics      = tp.get('topics', ['PRODUCT', 'GENERIC', 'BRAND', 'COMPETITOR', 'HEALTH', 'RECIPE', 'OTHER'])
    tag_cols    = _taxonomy_cols(cfg)

    topic_str = ' | '.join(topics)
    tag_fields = '\n'.join(
        f'- "{col}": relevant value if detected, else ""'
        for col in tag_cols
    )

    return (
        f"You are classifying search keywords for {brand_ctx}.\n\n"
        "For each keyword return a JSON array. Every item must have these exact fields:\n"
        '- "keyword": copy the keyword exactly\n'
        f'- "TOPICS": one of {topic_str}\n'
        '- "CATEGORY": a short category label (e.g. "Yogurt", "Brand", "Nutrition")\n'
        '- "SUB-CATEGORY": more specific label\n'
        f'{tag_fields}\n\n'
        "Rules:\n"
        "- If TOPICS/CATEGORY/SUB-CATEGORY are noted as already set, keep them exactly as-is.\n"
        '- Blank fields must be "" not null.\n'
        "- Return ONLY a valid JSON array. No explanation, no markdown fences."
    )


# ── Sheets helpers ─────────────────────────────────────────────────────────────

def _sheets_get(token, sheet_id, range_):
    url = (f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
           f"/values/{urllib.parse.quote(range_, safe='!:')}"
           f"?valueRenderOption=UNFORMATTED_VALUE")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read()).get("values", [])
    except urllib.error.HTTPError as e:
        if e.code == 400:
            return None
        print(f"  HTTP {e.code} on {range_}: {e.read().decode()[:200]}", flush=True)
        raise


def _sheets_write(token, sheet_id, data_ranges):
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values:batchUpdate"
    payload = {
        "valueInputOption": "USER_ENTERED",
        "data": [{"range": r, "majorDimension": "ROWS", "values": v}
                 for r, v in data_ranges],
    }
    body = json.dumps(payload).encode()
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, data=body,
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=90).read()).get(
                "totalUpdatedCells", 0)
        except Exception as e:
            wait = 15 * (attempt + 1)
            print(f"    Write attempt {attempt + 1} failed: {e} — retry in {wait}s", flush=True)
            time.sleep(wait)
    return 0


def _col_letter(idx):
    """Convert 0-based column index to A, B, … Z, AA, AB …"""
    if idx < 26:
        return chr(65 + idx)
    return chr(64 + idx // 26) + chr(65 + idx % 26)


def _read_all_rows(token, sheet_id, tab):
    """Read all data rows from tab in 1000-row chunks. Returns [(sheet_row, row_list), …]."""
    result = []
    for start in range(2, 10000, 1000):
        chunk = _sheets_get(token, sheet_id, f"'{tab}'!A{start}:BF{start + 999}")
        if chunk is None or chunk == []:
            break
        for i, row in enumerate(chunk):
            result.append((start + i, row))
    return result


# ── SE Ranking API ─────────────────────────────────────────────────────────────

def _ser_fetch(keywords, api_key, se_months, se_api_source='us'):
    """Bulk-fetch monthly volumes from SE Ranking. Returns {keyword_lower: avg_monthly_vol}."""
    url  = f"https://api.seranking.com/v1/keywords/export?source={se_api_source}"
    body = json.dumps({"keywords": keywords}).encode()
    req  = urllib.request.Request(url, data=body,
        headers={"Authorization": f"Token {api_key}",
                 "Content-Type": "application/json"})
    for attempt in range(4):
        try:
            rows = json.loads(urllib.request.urlopen(req, timeout=90).read())
            if not isinstance(rows, list):
                time.sleep(15 * (attempt + 1))
                continue
            result = {}
            for r in rows:
                if not r.get("is_data_found"):
                    continue
                trend = r.get("history_trend") or {}
                vols  = [trend.get(m, 0) or 0 for m in se_months]
                avg   = round(sum(vols) / len(vols)) if any(vols) else 0
                if avg > 0:
                    result[r["keyword"].lower()] = avg
            return result
        except Exception as e:
            wait = 15 * (attempt + 1)
            print(f"    SE API attempt {attempt + 1}: {e} — retry in {wait}s", flush=True)
            time.sleep(wait)
    return {}


def enrich_volumes(token, master_id, master_tab, ser_api_key, cfg=None):
    """Fill Average Search Volume, Volume P1, and Volume P2 for rows where average is blank.

    Average Search Volume = avg monthly volume from SE Ranking.
    Volume P1 and Volume P2 are back-filled as avg * 3 (3-month proxy).
    """
    print("\nEnriching missing search volumes via SE Ranking API…", flush=True)

    months = _se_months(cfg)
    source = _se_source(cfg)
    p1     = _p1_label(cfg)
    p2     = _p2_label(cfg)

    hdrs_raw = _sheets_get(token, master_id, f"'{master_tab}'!1:1")
    if not hdrs_raw:
        print("  Could not read Masterlist headers", flush=True)
        return
    hdrs    = hdrs_raw[0]
    hdr_idx = {h: i for i, h in enumerate(hdrs)}

    g_idx  = hdr_idx.get('Average Search Volume')
    h_idx  = hdr_idx.get(f'Volume {p1}')
    i_idx  = hdr_idx.get(f'Volume {p2}')
    l_idx  = hdr_idx.get(f'Clics OneSearch {p1}')
    kw_idx = hdr_idx.get('Keyword', 1)

    if g_idx is None:
        print("  'Average Search Volume' column not found", flush=True)
        return

    all_rows = _read_all_rows(token, master_id, master_tab)

    def cell(row, idx):
        return str(row[idx]).strip() if idx is not None and idx < len(row) else ''

    to_enrich = []
    for sheet_row, row in all_rows:
        kw = cell(row, kw_idx)
        g  = cell(row, g_idx)
        l  = float(row[l_idx]) if l_idx is not None and l_idx < len(row) and row[l_idx] else 0
        if kw and g == '' and l > 0:
            to_enrich.append({'sheet_row': sheet_row, 'keyword': kw})

    print(f"  {len(to_enrich)} rows need search volume", flush=True)
    if not to_enrich:
        return

    vol_map = {}
    batches = [to_enrich[i:i + SE_BATCH] for i in range(0, len(to_enrich), SE_BATCH)]
    for bi, batch in enumerate(batches):
        kws = [r['keyword'] for r in batch]
        print(f"  Batch {bi + 1}/{len(batches)}: {len(kws)} keywords… ", end="", flush=True)
        result = _ser_fetch(kws, ser_api_key, months, source)
        vol_map.update(result)
        print(f"{len(result)} found", flush=True)
        if bi < len(batches) - 1:
            time.sleep(8)

    g_col = _col_letter(g_idx)
    h_col = _col_letter(h_idx) if h_idx is not None else None
    i_col = _col_letter(i_idx) if i_idx is not None else None

    updates = []
    for item in to_enrich:
        avg = vol_map.get(item['keyword'].lower())
        if avg is None:
            continue
        sr = item['sheet_row']
        updates.append((f"'{master_tab}'!{g_col}{sr}", [[avg]]))
        if h_col:
            updates.append((f"'{master_tab}'!{h_col}{sr}", [[avg * 3]]))
        if i_col:
            updates.append((f"'{master_tab}'!{i_col}{sr}", [[avg * 3]]))

    print(f"  Writing {len(updates)} cells…", flush=True)
    cells = 0
    for i in range(0, len(updates), 50):
        cells += _sheets_write(token, master_id, updates[i:i + 50])
        if i + 50 < len(updates):
            time.sleep(1)
    print(f"  Done — {cells} cells updated", flush=True)


# ── Claude API ─────────────────────────────────────────────────────────────────

def _claude_classify(items, api_key, system_message):
    """Send a batch of keyword dicts to Claude Haiku. Returns list of classified dicts."""
    lines = []
    for it in items:
        suffix = (f' [already set: TOPICS={it["TOPICS"]}, CATEGORY={it["CATEGORY"]}]'
                  if it.get('TOPICS') else '')
        lines.append(f'- "{it["keyword"]}"{suffix}')

    user_msg = "Keywords:\n" + "\n".join(lines)
    body = json.dumps({
        "model":      CLAUDE_MODEL,
        "max_tokens": 16000,
        "system":     system_message,
        "messages":   [{"role": "user", "content": user_msg}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
    )

    for attempt in range(3):
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
            text = resp["content"][0]["text"].strip()
            if text.startswith("```"):
                parts = text.split("```")
                text  = parts[1][4:] if parts[1].startswith("json") else parts[1]
            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"    Claude JSON error (attempt {attempt + 1}): {e}", flush=True)
            time.sleep(5)
        except urllib.error.HTTPError as e:
            body_err = e.read().decode()[:200]
            print(f"    Claude HTTP {e.code} (attempt {attempt + 1}): {body_err}", flush=True)
            time.sleep(15 if e.code == 529 else 10)
        except Exception as e:
            print(f"    Claude API attempt {attempt + 1}: {e}", flush=True)
            time.sleep(10)
    return []


def _ser_fetch_monthly(keywords, api_key, se_months, se_api_source='us'):
    """Bulk-fetch per-month volumes from SE Ranking. Returns {keyword_lower: {month: volume}}."""
    url  = f"https://api.seranking.com/v1/keywords/export?source={se_api_source}"
    body = json.dumps({"keywords": keywords}).encode()
    req  = urllib.request.Request(url, data=body,
        headers={"Authorization": f"Token {api_key}",
                 "Content-Type": "application/json"})
    for attempt in range(4):
        try:
            rows = json.loads(urllib.request.urlopen(req, timeout=90).read())
            if not isinstance(rows, list):
                time.sleep(15 * (attempt + 1))
                continue
            result = {}
            for r in rows:
                if not r.get("is_data_found"):
                    continue
                trend   = r.get("history_trend") or {}
                monthly = {m: int(trend.get(m) or 0) for m in se_months}
                if any(v > 0 for v in monthly.values()):
                    result[r["keyword"].lower()] = monthly
            return result
        except Exception as e:
            wait = 15 * (attempt + 1)
            print(f"    SE API attempt {attempt + 1}: {e} — retry in {wait}s", flush=True)
            time.sleep(wait)
    return {}


def enrich_monthly_volumes(token, master_id, master_tab, ser_api_key, cfg=None):
    """Fill monthly search volume columns (Searches: Mon YYYY) where blank."""
    months = _se_months(cfg)
    source = _se_source(cfg)
    p1     = _p1_label(cfg)

    month_hdrs = [_month_label(m) for m in months]
    label_range = f"{_month_label(months[0])} – {_month_label(months[-1])}" if months else ''
    print(f"\nEnriching monthly search volumes ({label_range}) via SE Ranking API…", flush=True)

    hdrs_raw = _sheets_get(token, master_id, f"'{master_tab}'!1:1")
    if not hdrs_raw:
        print("  Could not read Masterlist headers", flush=True)
        return
    hdrs    = hdrs_raw[0]
    hdr_idx = {h: i for i, h in enumerate(hdrs)}

    month_col_letters = [
        _col_letter(hdr_idx[h]) if h in hdr_idx else None for h in month_hdrs
    ]
    missing_hdrs = [h for h, ltr in zip(month_hdrs, month_col_letters) if ltr is None]
    if missing_hdrs:
        print(f"  Warning: columns not found — {missing_hdrs}", flush=True)
    if not any(month_col_letters):
        print("  No monthly volume columns found — skipping", flush=True)
        return

    kw_idx   = hdr_idx.get('Keyword', 1)
    g_idx    = hdr_idx.get('Average Search Volume')
    l_idx    = hdr_idx.get(f'Clics OneSearch {p1}')
    first_mi = hdr_idx.get(month_hdrs[0]) if month_hdrs else None

    if first_mi is None:
        return

    all_rows = _read_all_rows(token, master_id, master_tab)

    def cell(row, idx):
        return str(row[idx]).strip() if idx is not None and idx < len(row) else ''

    to_enrich = []
    for sheet_row, row in all_rows:
        kw = cell(row, kw_idx)
        if not kw or cell(row, first_mi) != '':
            continue
        has_vol    = g_idx is not None and cell(row, g_idx) not in ('', '0')
        has_clicks = False
        if l_idx is not None and l_idx < len(row) and row[l_idx]:
            try:
                has_clicks = float(row[l_idx]) > 0
            except (ValueError, TypeError):
                pass
        if has_vol or has_clicks:
            to_enrich.append({'sheet_row': sheet_row, 'keyword': kw})

    print(f"  {len(to_enrich)} rows need monthly volumes", flush=True)
    if not to_enrich:
        return

    vol_map = {}
    batches = [to_enrich[i:i + SE_BATCH] for i in range(0, len(to_enrich), SE_BATCH)]
    for bi, batch in enumerate(batches):
        kws = [r['keyword'] for r in batch]
        print(f"  Batch {bi + 1}/{len(batches)}: {len(kws)} keywords… ", end="", flush=True)
        result = _ser_fetch_monthly(kws, ser_api_key, months, source)
        vol_map.update(result)
        print(f"{len(result)} found", flush=True)
        if bi < len(batches) - 1:
            time.sleep(8)

    updates = []
    for item in to_enrich:
        monthly = vol_map.get(item['keyword'].lower())
        if not monthly:
            continue
        for col_ltr, month_key in zip(month_col_letters, months):
            if col_ltr is None:
                continue
            val = monthly.get(month_key, 0)
            if val:
                updates.append((f"'{master_tab}'!{col_ltr}{item['sheet_row']}", [[val]]))

    print(f"  Writing {len(updates)} monthly volume cells…", flush=True)
    total_cells = 0
    for i in range(0, len(updates), 50):
        total_cells += _sheets_write(token, master_id, updates[i:i + 50])
        if i + 50 < len(updates):
            time.sleep(1)
    print(f"  Monthly volumes done — {total_cells} cells updated", flush=True)


def enrich_taxonomy(token, master_id, master_tab, anthropic_key, cfg=None):
    """Fill taxonomy columns and missing TOPICS/CATEGORY/SUB-CATEGORY using Claude API."""
    print("\nEnriching taxonomy via Claude API…", flush=True)

    tax_cols       = _taxonomy_cols(cfg)
    system_message = _build_system_message(cfg)

    hdrs_raw = _sheets_get(token, master_id, f"'{master_tab}'!1:1")
    if not hdrs_raw:
        return
    hdrs    = hdrs_raw[0]
    hdr_idx = {h: i for i, h in enumerate(hdrs)}

    fill_cols = TOPIC_COLS + tax_cols
    missing   = [c for c in fill_cols if c not in hdr_idx]
    if missing:
        print(f"  Warning: headers not found — {missing}", flush=True)

    all_rows = _read_all_rows(token, master_id, master_tab)

    kw_idx = hdr_idx.get('Keyword', 1)

    def cell(row, col):
        i = hdr_idx.get(col)
        return str(row[i]).strip() if i is not None and i < len(row) else ''

    to_enrich = []
    for sheet_row, row in all_rows:
        kw = row[kw_idx] if kw_idx < len(row) else ''
        if not kw:
            continue
        any_blank = any(cell(row, c) == '' for c in fill_cols if c in hdr_idx)
        if any_blank:
            to_enrich.append({
                'sheet_row':    sheet_row,
                'keyword':      str(kw),
                'TOPICS':       cell(row, 'TOPICS'),
                'CATEGORY':     cell(row, 'CATEGORY'),
                'SUB-CATEGORY': cell(row, 'SUB-CATEGORY'),
                '_existing':    {c: cell(row, c) for c in fill_cols if c in hdr_idx},
            })

    print(f"  {len(to_enrich)} rows need taxonomy enrichment", flush=True)
    if not to_enrich:
        return

    classified_map = {}
    batches = [to_enrich[i:i + CLAUDE_BATCH] for i in range(0, len(to_enrich), CLAUDE_BATCH)]
    print(f"  Sending {len(batches)} batches to Claude ({CLAUDE_BATCH} keywords/batch)…",
          flush=True)

    for bi, batch in enumerate(batches):
        print(f"    Batch {bi + 1}/{len(batches)}: {len(batch)} keywords… ", end="", flush=True)
        results = _claude_classify(batch, anthropic_key, system_message)
        for r in results:
            kw = str(r.get('keyword', '')).strip()
            if kw:
                classified_map[kw.lower()] = r
        print(f"{len(results)} classified", flush=True)
        if bi < len(batches) - 1:
            time.sleep(1)

    print(f"  Total classified: {len(classified_map)}", flush=True)

    updates = []
    for item in to_enrich:
        cls = classified_map.get(item['keyword'].lower())
        if not cls:
            continue
        existing  = item['_existing']
        sheet_row = item['sheet_row']

        for col in fill_cols:
            if col not in hdr_idx:
                continue
            current = existing.get(col, '')
            new_val = str(cls.get(col, '') or '')
            if current == '' and new_val:
                col_ltr = _col_letter(hdr_idx[col])
                updates.append((f"'{master_tab}'!{col_ltr}{sheet_row}", [[new_val]]))

    print(f"  Writing {len(updates)} taxonomy cells…", flush=True)
    total_cells = 0
    for i in range(0, len(updates), 50):
        total_cells += _sheets_write(token, master_id, updates[i:i + 50])
        if i + 50 < len(updates):
            time.sleep(1)
    print(f"  Taxonomy enrichment done — {total_cells} cells updated", flush=True)
