"""Config-driven fallback classification — competitors (and, in future, other
rule-based taxonomy dimensions) for keywords the Keyword Study fuzzy-match
didn't confidently classify.

Why this exists: the Keyword Study match (see match_ks.py) is the primary
source of TOPICS/CATEGORY for a keyword. But a Keyword Study is never
exhaustive — a competitor's product-line name that isn't in the KS export
yet, or wasn't matched confidently enough, falls through to GENERIC or
whatever the closest fuzzy match happened to be. Competitor-name presence in
a keyword's text is an unambiguous, high-confidence signal on its own — this
module applies it directly, without needing a Keyword Study match first.

Brand-specific patterns live in that brand's config.json under
`competitors` — nothing here is hardcoded per brand. A brand with no
`competitors` configured (e.g. one whose Keyword Study already covers this)
is a no-op.
"""


def classify_competitors(rows: list, competitors: list) -> int:
    """Mutates `rows` in place. Returns the number of rows changed.

    rows: masterlist row dicts (must have a 'Keyword' key).
    competitors: config['competitors'] — list of
        {"name": "Coffee Mate", "patterns": ["coffee mate", "coffeemate", "natural bliss"]}
    Competitor-name presence overrides whatever TOPICS/CATEGORY a row already
    has (including a real Keyword Study match) — a keyword that literally
    names a competitor is a competitor keyword, regardless of what else it
    superficially resembles (e.g. "flavors of natural bliss coffee creamer"
    looks like a generic product query, but naming the competitor's product
    line makes it a competitor query first).
    """
    if not competitors:
        return 0

    # Pre-lowercase patterns once
    compiled = [
        (c['name'], [p.lower() for p in c.get('patterns', [])])
        for c in competitors
    ]

    changed = 0
    for row in rows:
        kw = str(row.get('Keyword') or '').lower()
        if not kw:
            continue
        for name, patterns in compiled:
            if any(p in kw for p in patterns):
                if row.get('TOPICS') != 'COMPETITOR' or row.get('CATEGORY') != name:
                    row['TOPICS'] = 'COMPETITOR'
                    row['CATEGORY'] = name
                    row['Brands'] = name
                    changed += 1
                break  # first matching competitor wins; don't double-classify
    return changed
