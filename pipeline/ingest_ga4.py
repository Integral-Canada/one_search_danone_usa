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
