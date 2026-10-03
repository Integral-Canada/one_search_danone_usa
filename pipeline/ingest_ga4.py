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
            for c in _EVENTS_COL_CANDIDATES:
                if c in row:
                    events_col = c
                    break
            if path_col is None:
                continue  # still in metadata rows
            if events_col is None:
                # Some GA4 exports name the events column after the specific event
                # itself (e.g. 'mikmak_checkout') instead of a generic 'Key events'
                # label. In every such export seen so far, that column is always
                # the one immediately before 'Total revenue' — fall back to that
                # position rather than silently returning zero conversions.
                keys = list(row.keys())
                if 'Total revenue' in keys:
                    idx = keys.index('Total revenue')
                    if idx > 0:
                        events_col = keys[idx - 1]
                        print(f"  GA4 export: events column resolved by position as "
                              f"'{events_col}' (no generic 'Key events' label found)", flush=True)
                if events_col is None:
                    print(f"  WARNING: GA4 export has a recognized path column ('{path_col}') "
                          f"but no recognized events column (tried {_EVENTS_COL_CANDIDATES}). "
                          f"All conversions from this source will be 0. "
                          f"Header row keys: {list(row.keys())[:12]}", flush=True)

        raw_path = str(row.get(path_col) or '').strip()
        # Strip query strings (?...) before normalizing — GA4 Ads export includes them
        path = raw_path.split('?')[0].rstrip('/')
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
                for c in _EVENTS_COL_CANDIDATES:
                    if c in headers:
                        events_col = c
                        break
                if events_col is None and 'Total revenue' in headers:
                    idx = headers.index('Total revenue')
                    if idx > 0:
                        events_col = headers[idx - 1]
                        print(f"  GA4 Compare export: events column resolved by position as "
                              f"'{events_col}' (no generic 'Key events' label found)", flush=True)
            continue

        d = {headers[i]: (row[i] if i < len(row) else '') for i in range(len(headers))}
        raw_path = str(d.get(path_col) or '').strip()
        if raw_path:
            last_path = raw_path.split('?')[0].rstrip('/')
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
