"""Masterlist validation layer.

Runs between the pipeline write and the HTML dashboard build. Catches:
  - Column name mismatches (Issue 3: French/English drift, missing expected columns)
  - Number parsing failures (Issue 6: French-format numbers silently becoming 0)
  - Rows where all numeric columns are zero (Issue: skipped data)
  - Cross-column sanity checks (coverage vs clicks/volume)
  - Blank columns that should have data

Usage:
    from pipeline.validate import validate_masterlist
    ok, report = validate_masterlist(rows, headers, cfg)
    if not ok:
        print(report)
        sys.exit(1)
"""
import re
from .normalize import clean_num


# ── Expected column groups ─────────────────────────────────────────────────────
# Each entry: (internal_name, [possible_sheet_header_variants])
# The validator checks whether AT LEAST ONE variant is present in the masterlist headers.

EXPECTED_COLUMNS = [
    ('Keyword',                  ['Keyword']),
    ('TOPICS',                   ['TOPICS']),
    ('CATEGORY',                 ['CATEGORY']),
    ('SUB-CATEGORY',             ['SUB-CATEGORY']),
    ('Average Search Volume',    ['Average Search Volume']),
    ('Position SE Ranking',      ['Position SE Ranking']),
    ('Clics OneSearch P1',       ['Clics OneSearch Q1 2026', 'Clics OneSearch Q2 2026',
                                   'Clics OneSearch Q3 2026', 'Clics OneSearch Q4 2025']),
    ('Clics SEO P1',             ['Clics SEO Q1 2026', 'Clics SEO Q2 2026',
                                   'Clics SEO Q3 2026', 'Clics SEO Q4 2025']),
    ('Clics SEM P1',             ['Clics SEM Q1 2026', 'Clics SEM Q2 2026',
                                   'Clics SEM Q3 2026', 'Clics SEM Q4 2025']),
    ('Conversions SEO P1',       ['Conversions SEO Q1 2026', 'Conversions SEO Q2 2026']),
    ('Conversions SEM P1',       ['Conversions SEM Q1 2026', 'Conversions SEM Q2 2026']),
    ('CPC SEO P1',               ['CPC SEO Q1 2026', 'CPC SEO Q2 2026']),
    ('CPC avg SEM P1',           ['CPC avg. SEM Q1 2026', 'CPC moy. SEM Q1 2026',
                                   'CPC avg. SEM Q2 2026', 'CPC moy. SEM Q2 2026']),
    ('Spent SEM P1',             ['Spent SEM Q1 2026', 'Dépense SEM Q1 2026',
                                   'Spent SEM Q2 2026', 'Dépense SEM Q2 2026']),
]

# Columns that are expected to have data for most rows (>10% non-zero).
# If a column has >90% zeros but is listed here, it's flagged as a likely mismatch.
SHOULD_HAVE_DATA = {
    'Keyword', 'TOPICS', 'CATEGORY',
    'Clics OneSearch P1', 'Average Search Volume',
}

# Numeric columns for parsing audit (a sample of values is parsed and checked)
NUMERIC_COLS = [
    'Average Search Volume', 'Position SE Ranking',
    'Clics OneSearch P1', 'Clics SEO P1', 'Clics SEM P1',
    'CPC avg SEM P1', 'Spent SEM P1', 'Conversions SEO P1', 'Conversions SEM P1',
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pct(n: int, total: int) -> str:
    if total == 0:
        return '0%'
    return f'{100 * n // total}%'


def _resolve_col(internal_name: str, variants: list, headers: list):
    """Return the first header variant that exists, or None."""
    for v in variants:
        if v in headers:
            return v
    # Fuzzy: try case-insensitive match
    lower_headers = {h.lower(): h for h in headers}
    for v in variants:
        if v.lower() in lower_headers:
            return lower_headers[v.lower()]
    return None


def _detect_french_format(v: str) -> bool:
    """Return True if value looks like French-format number (space thousands, comma decimal)."""
    s = str(v or '').strip()
    # e.g. "32 395" or "1 234,56"
    return bool(re.match(r'^\d{1,3}( \d{3})+$', s) or
                re.match(r'^\d{1,3}( \d{3})*,\d+$', s))


# ── Main validation function ───────────────────────────────────────────────────

def validate_masterlist(
    rows: list,
    headers: list,
    cfg: dict = None,
    sample_size: int = 20,
) -> tuple:
    """Validate a masterlist (list of row-dicts or list-of-lists).

    rows: list of dicts (preferred) or list-of-lists (headers must be provided separately).
    headers: list of column header strings.
    cfg: brand config dict (optional — used for period-specific column name checks).
    sample_size: number of rows to inspect for number parsing audit.

    Returns (ok: bool, report: str).
    ok is True if no blocking issues are found (warnings are non-blocking).
    """
    lines = ['', '══ MASTERLIST VALIDATION REPORT ══════════════════════════']

    if not rows:
        return False, '\n'.join(lines + ['ERROR: No rows in masterlist.'])

    n_rows = len(rows)
    lines.append(f'  Rows: {n_rows:,}  |  Columns: {len(headers)}')

    errors   = []
    warnings = []
    infos    = []

    # ── 1. Column presence audit ─────────────────────────────────────────────
    lines.append('')
    lines.append('  ── Column presence ──────────────────────────────────────')
    col_map: dict = {}  # internal_name → resolved_header
    for internal, variants in EXPECTED_COLUMNS:
        found = _resolve_col(internal, variants, headers)
        col_map[internal] = found
        if found:
            marker = '✓' if found == variants[0] else f'✓ (as "{found}")'
            lines.append(f'  {marker:40s} {internal}')
            if found != variants[0]:
                warnings.append(f'Column "{internal}" found as "{found}" — expected "{variants[0]}". '
                                 f'Check that both pipeline and HTML builder use the same name.')
        else:
            lines.append(f'  ✗ MISSING                                {internal}')
            if internal in SHOULD_HAVE_DATA:
                errors.append(f'Critical column missing: "{internal}" (tried: {variants})')
            else:
                warnings.append(f'Column "{internal}" not found (tried: {variants})')

    # ── 2. Data completeness per column ──────────────────────────────────────
    lines.append('')
    lines.append('  ── Data completeness ────────────────────────────────────')
    for internal in SHOULD_HAVE_DATA:
        col = col_map.get(internal)
        if not col:
            continue
        non_blank = sum(1 for r in rows if str(r.get(col, '')).strip() not in ('', '0'))
        pct = _pct(non_blank, n_rows)
        marker = '✓' if non_blank > n_rows * 0.1 else '⚠'
        lines.append(f'  {marker} {internal}: {non_blank:,}/{n_rows:,} rows with data ({pct})')
        if non_blank == 0 and internal in SHOULD_HAVE_DATA:
            errors.append(f'"{internal}" has NO data — column likely mismatched or data not written.')
        elif non_blank < n_rows * 0.05:
            warnings.append(f'"{internal}" has very few values ({pct}) — possible column name mismatch.')

    # ── 3. Number parsing audit ───────────────────────────────────────────────
    lines.append('')
    lines.append('  ── Number parsing (sample) ──────────────────────────────')
    sample_rows = rows[:sample_size]
    for internal in NUMERIC_COLS:
        col = col_map.get(internal)
        if not col:
            continue
        raw_vals   = [str(r.get(col, '')) for r in sample_rows if str(r.get(col, '')).strip()]
        if not raw_vals:
            lines.append(f'  — {internal}: no sample values')
            continue
        parsed     = [clean_num(v) for v in raw_vals]
        n_zero     = sum(1 for p in parsed if p == 0)
        n_french   = sum(1 for v in raw_vals if _detect_french_format(v))
        max_val    = max(parsed) if parsed else 0
        # Flag: if raw looks non-zero but parsed as 0, parsing may be failing
        raw_nonzero = sum(1 for v in raw_vals if v not in ('', '0'))
        if raw_nonzero > 0 and n_zero == len(parsed):
            errors.append(
                f'Number parsing failure in "{internal}": {len(raw_vals)} samples, '
                f'all parsed as 0. Raw sample: {raw_vals[:3]}'
            )
            lines.append(f'  ✗ {internal}: ALL zeros after parsing — raw: {raw_vals[:3]}')
        elif n_french > 0:
            lines.append(f'  ⚠ {internal}: {n_french} French-format values detected — max={max_val:,.2f}')
            warnings.append(f'French-format numbers detected in "{internal}" — verify clean_num() is used.')
        else:
            lines.append(f'  ✓ {internal}: max={max_val:,.2f}')

    # ── 4. Zero-row integrity ────────────────────────────────────────────────
    lines.append('')
    lines.append('  ── Row integrity (all-zero check) ───────────────────────')
    numeric_header_cols = [col_map[n] for n in ['Clics OneSearch P1', 'Clics SEO P1', 'Clics SEM P1']
                           if col_map.get(n)]
    if numeric_header_cols:
        all_zero_rows = []
        for i, row in enumerate(rows):
            if all(clean_num(row.get(c, 0)) == 0 for c in numeric_header_cols):
                all_zero_rows.append(i)
        pct = _pct(len(all_zero_rows), n_rows)
        if len(all_zero_rows) > n_rows * 0.5:
            errors.append(
                f'{len(all_zero_rows):,} rows ({pct}) have zero clicks across all click columns — '
                f'data likely did not flow from GSC/SQR into masterlist.'
            )
            lines.append(f'  ✗ {len(all_zero_rows):,} rows ({pct}) all-zero clicks — data pipeline issue')
        elif all_zero_rows:
            lines.append(f'  ⚠ {len(all_zero_rows):,} rows ({pct}) all-zero clicks '
                         f'(first 3 keywords: {[str(rows[i].get("Keyword","?")) for i in all_zero_rows[:3]]})')
        else:
            lines.append(f'  ✓ No all-zero click rows found')

    # ── 5. Cross-column sanity: coverage ────────────────────────────────────
    lines.append('')
    lines.append('  ── Cross-column sanity ──────────────────────────────────')
    clicks_col = col_map.get('Clics OneSearch P1')
    vol_col    = col_map.get('Average Search Volume')
    if clicks_col and vol_col:
        with_vol     = [(clean_num(r.get(vol_col, 0)), clean_num(r.get(clicks_col, 0)))
                        for r in rows if clean_num(r.get(vol_col, 0)) > 0]
        coverage_vals = [c / v for v, c in with_vol if v > 0]
        if coverage_vals:
            avg_cov = sum(coverage_vals) / len(coverage_vals) * 100
            over_100 = sum(1 for x in coverage_vals if x > 1.0)
            lines.append(f'  ✓ Coverage sanity: avg={avg_cov:.1f}% | {over_100} rows >100% (capped for display)')
            if avg_cov > 50:
                warnings.append(
                    f'Average coverage {avg_cov:.1f}% is very high — '
                    f'check that volume column is not blank or that clicks column is correct.'
                )
        else:
            lines.append(f'  — Coverage sanity: no rows with volume > 0')

    # ── Summary ──────────────────────────────────────────────────────────────
    lines.append('')
    lines.append('  ── Summary ──────────────────────────────────────────────')
    if errors:
        lines.append(f'  ✗ {len(errors)} ERROR(s) — dashboard build BLOCKED:')
        for e in errors:
            lines.append(f'    • {e}')
    if warnings:
        lines.append(f'  ⚠ {len(warnings)} WARNING(s) — review before proceeding:')
        for w in warnings:
            lines.append(f'    • {w}')
    if not errors and not warnings:
        lines.append('  ✓ All checks passed — proceed to HTML build')
    elif not errors:
        lines.append('  Warnings are non-blocking. Run build_dashboard.py to continue.')

    lines.append('══════════════════════════════════════════════════════════')
    lines.append('')

    ok = len(errors) == 0
    return ok, '\n'.join(lines)
