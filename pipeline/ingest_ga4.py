"""Parse GA4 page-level export → {url_path: key_events}.

GA4 exports have 9 metadata rows before the header (row 10 = header in Sheets).
Key column is 'Key events ' (note trailing space in some exports).

Also handles the GA4 Google Ads session export format, which uses:
  'Page de destination + chaîne de requête' as the page path column.
"""
from .normalize import clean_num

_PATH_COL_CANDIDATES = (
    'Page path and screen class',
    'Page path and screen class ',
    "Chemin de la page et classe de l'écran",
    'Page de destination + chaîne de requête',   # GA4 Ads sessions export
    'Landing page + query string',               # GA4 Ads sessions export (EN)
)
_EVENTS_COL_CANDIDATES = ('Key events ', 'Key events', 'Événements clés')

# Dimension/metric columns that are never themselves the custom-event-name
# column, used by _resolve_events_col()'s last-resort fallback below.
_KNOWN_NON_EVENT_COLS = {
    'Session default channel group', 'Session Google Ads query', 'Date Comparison',
    'Sessions', 'Views', 'Active users', 'Online active user views',
    'Average online active user engagement time', 'Total revenue',
} | set(_PATH_COL_CANDIDATES)


def _resolve_events_col(headers: list) -> str:
    """Find the events/key-events column in a GA4 export header row.

    Tries, in order: (1) a generic 'Key events' label, (2) the column
    immediately before 'Total revenue' — real exports sometimes name this
    column after the specific event itself (e.g. 'mikmak_checkout') instead
    of a generic label, and that column is consistently placed right before
    Total revenue when Total revenue is present, (3) the last column that
    isn't a known dimension/metric name — covers real exports seen with no
    Total revenue column at all, where the custom event-name column is
    simply the final column with nothing after it (e.g. a Landing-page-
    dimensioned Compare export ending in '...,Sessions,mikmak_checkout').
    Returns '' if nothing resolves (caller should warn and treat as zero).
    """
    for c in _EVENTS_COL_CANDIDATES:
        if c in headers:
            return c
    if 'Total revenue' in headers:
        idx = headers.index('Total revenue')
        if idx > 0:
            col = headers[idx - 1]
            print(f"  GA4 export: events column resolved by position as "
                  f"'{col}' (no generic 'Key events' label found)", flush=True)
            return col
    remaining = [h for h in headers if h not in _KNOWN_NON_EVENT_COLS]
    if len(remaining) == 1:
        col = remaining[0]
        print(f"  GA4 export: events column resolved as the one remaining "
              f"unrecognized column '{col}' (no 'Key events' label or "
              f"'Total revenue' anchor found)", flush=True)
        return col
    return ''


def _normalize_path(raw_path: str) -> str:
    """Strip the query string and trailing slash(es) from a page path, while
    preserving the homepage root ('/') instead of collapsing it to ''.

    Real bug found via Activia's real GA4 export: '/?msclkid=...'.split('?')[0]
    is '/', and a bare '/'.rstrip('/') is '' — not '/'. Every homepage row with
    a tracking-parameter query string (very common for paid-search landing
    pages) then fails every caller's `if not path: continue` check and gets
    silently dropped, undercounting homepage conversions. Confirmed this cost
    ~18-19% of real events in one real export before this fix.
    """
    path = raw_path.split('?')[0].rstrip('/')
    return path if path else ('/' if raw_path.split('?')[0] else '')


def norm_ga4_rows(rows: list) -> dict:
    """Convert list-of-dicts rows to {normalized_path: key_events}.

    Tolerates header rows that precede the data (non-dict or dict with
    unrecognised keys are skipped automatically).
    """
    path_col = events_col = None
    result: dict = {}

    for row in rows:
        if not isinstance(row, dict):
            continue

        # First row that looks like a data header — establish column names
        if path_col is None:
            for c in _PATH_COL_CANDIDATES:
                if c in row:
                    path_col = c
                    break
            if path_col is None:
                continue  # still in metadata rows
            events_col = _resolve_events_col(list(row.keys())) or None
            if events_col is None:
                print(f"  WARNING: GA4 export has a recognized path column ('{path_col}') "
                      f"but no recognized events column (tried {_EVENTS_COL_CANDIDATES}, "
                      f"a Total-revenue-anchored fallback, and a last-remaining-column "
                      f"fallback). All conversions from this source will be 0. "
                      f"Header row keys: {list(row.keys())[:12]}", flush=True)

        raw_path = str(row.get(path_col) or '').strip()
        # Strip query strings (?...) before normalizing — GA4 Ads export includes them
        path = _normalize_path(raw_path)
        if not path or path.startswith('#'):
            continue

        if events_col is None:
            continue  # already warned above; nothing to accumulate
        events = clean_num(row.get(events_col, 0))
        if events > 0:
            result[path] = result.get(path, 0.0) + events

    return result


def ga4_from_raw(raw_values: list) -> dict:
    """Convert raw Sheets API list-of-lists (row 10 = header) to {path: events}.

    Skips all rows before the first one that contains the page path column header.
    """
    headers = None
    rows = []
    for row in raw_values:
        if headers is None:
            # Look for the header row (contains page path col name)
            row_str = [str(c) for c in row]
            if any(c in row_str for c in _PATH_COL_CANDIDATES):
                headers = row_str
        else:
            d = {headers[i]: (row[i] if i < len(row) else '') for i in range(len(headers))}
            rows.append(d)

    return norm_ga4_rows(rows)


def is_ga4_compare_export(raw_values: list) -> bool:
    """True if this GA4 export has GA4's built-in Compare feature applied
    (a 'Date Comparison' column), rather than being a single-period export."""
    for row in raw_values[:15]:
        row_str = [str(c) for c in row]
        if any(c in row_str for c in _PATH_COL_CANDIDATES) and 'Date Comparison' in row_str:
            return True
    return False


def ga4_from_raw_compare(raw_values: list) -> tuple:
    """Like ga4_from_raw(), but for a GA4 export with the built-in Compare
    feature applied — one file covering two periods via repeating 3-row
    blocks per page path (a '% change' delta row, then one row per period),
    with the path cell populated only on the first row of each block (GA4's
    blank-fill-below convention for repeated dimension values). Same shape
    as pipeline/sem_qv.py's read_ga4_ads_compare(), independently needed
    here since this is a page-path+events export, not a keyword+landing-
    page+sessions one.

    Returns (map_a, map_b, label_a, label_b) — map_a/map_b are {path: events}
    dicts for the two periods, label_a/label_b their real GA4 date-range text
    (first-seen-labeled bucket = a, second-seen = b).
    """
    headers = None
    path_col = events_col = cmp_col = None
    last_path = ''
    label_a = label_b = None
    map_a: dict = {}
    map_b: dict = {}

    for row in raw_values:
        if headers is None:
            row_str = [str(c) for c in row]
            if any(c in row_str for c in _PATH_COL_CANDIDATES) and 'Date Comparison' in row_str:
                headers = row_str
                for c in _PATH_COL_CANDIDATES:
                    if c in headers:
                        path_col = c
                        break
                cmp_col = 'Date Comparison'
                events_col = _resolve_events_col(headers) or None
            continue

        d = {headers[i]: (row[i] if i < len(row) else '') for i in range(len(headers))}
        raw_path = str(d.get(path_col) or '').strip()
        if raw_path:
            last_path = _normalize_path(raw_path)
        cmp_label = str(d.get(cmp_col) or '').strip()
        if not cmp_label or cmp_label == '% change' or not last_path or last_path.startswith('#'):
            continue

        if label_a is None:
            label_a = cmp_label
        elif cmp_label != label_a and label_b is None:
            label_b = cmp_label
        elif cmp_label not in (label_a, label_b):
            raise RuntimeError(
                f"GA4 Compare export has a 3rd distinct Date Comparison label "
                f"({cmp_label!r}, besides {label_a!r} and {label_b!r}) — "
                f"cannot split into exactly two periods")

        events = clean_num(d.get(events_col, 0)) if events_col else 0.0
        if events <= 0:
            continue
        target = map_a if cmp_label == label_a else map_b
        target[last_path] = target.get(last_path, 0.0) + events

    return map_a, map_b, label_a, label_b
