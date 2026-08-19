"""Match Keyword Study keywords to unified Masterlist rows using trigram similarity.

Matching direction: index is built on the ~1,240 unified queries (small set).
We iterate the 14,273 KS keywords through that small index, then pivot to keep
the best KS match per unified row.

Performance: pre-filter drops KS keywords with zero shared trigrams (lossless).
Top-50 candidate cap bounds Jaccard calls per KS keyword.
"""
from .trigram import trigrams_arr, jaccard
from .ingest import _se_month_label, _DEFAULT_TAXONOMY_TAGS


def match_ks_keywords(ks_rows: list, index: dict, unified: list,
                      high_conf_threshold: float = 0.65,
                      p1_label: str = 'Q1 2026', p2_label: str = 'Q4 2025',
                      se_months_p1: list = None, se_months_p2: list = None,
                      taxonomy_tags: list = None) -> tuple:
    """
    p1_label/p2_label and se_months_p1/p2 default to the original Oikos period
    (Jan/Feb/Mar 2026 vs Oct/Nov/Dec 2025) for backward compatibility. Pass a
    brand's actual period config so 'Volume {label}' and the monthly
    'Searches: <Month> <Year>' columns line up with that brand's Masterlist headers.

    taxonomy_tags: same list passed to ingest.norm_ks() for this run — must match
    so the dimension names read from `ks` here are the ones actually present.
    """
    if se_months_p1 is None:
        se_months_p1 = ['2026-01-01', '2026-02-01', '2026-03-01']
    if se_months_p2 is None:
        se_months_p2 = ['2025-10-01', '2025-11-01', '2025-12-01']
    if taxonomy_tags is None:
        taxonomy_tags = _DEFAULT_TAXONOMY_TAGS
    p1_month_labels = [_se_month_label(d) for d in se_months_p1]
    p2_month_labels = [_se_month_label(d) for d in se_months_p2]
    u_keys    = index['uKeys']
    u_display = index['uDisplay']
    u_tg      = index['uTg']
    idx       = index['idx']
    unified_trigrams = set(idx.keys())

    best_ks: dict = {}
    for ks in ks_rows:
        q_arr = trigrams_arr(ks['norm_keyword'])
        if not any(t in unified_trigrams for t in q_arr):
            continue  # lossless: zero shared trigrams → Jaccard always 0

        q_set = set(q_arr)
        cand_score: dict = {}
        for t in q_arr:
            for i in idx.get(t, []):
                cand_score[i] = cand_score.get(i, 0) + 1

        if not cand_score:
            continue

        # Top-50 by shared trigram count bounds worst-case Jaccard calls
        top_cands = sorted(cand_score, key=cand_score.get, reverse=True)[:50]

        bi, bs = -1, 0.0
        for i in top_cands:
            s = jaccard(u_tg[i], q_set)
            if s > bs:
                bs = s
                bi = i

        if bi >= 0:
            k = u_keys[bi]
            # Tie-break rule: strictly-greater comparison means on an exact-score tie
            # for the same unified row, the FIRST KS keyword encountered (in ks_rows
            # iteration order) wins and later ties are discarded. Deterministic given
            # a fixed ks_rows order, but that order is whatever the Keyword Study sheet
            # returned — not guaranteed stable if the sheet is re-sorted.
            if k not in best_ks or bs > best_ks[k]['sim']:
                best_ks[k] = {'ks': ks, 'sim': bs}

    def f(v): return '' if v is None else v

    high_conf, review = [], []
    for r in unified:
        key   = r.get('unified_key') or r.get('norm_query') or ''
        kw    = r.get('query') or r.get('search_term') or key
        match = best_ks.get(key)
        sim   = round(match['sim'] * 1000) / 1000 if match else 0

        if match and match['sim'] >= high_conf_threshold:
            ks = match['ks']
            vol_p1 = sum(float(ks.get(lbl) or 0) for lbl in p1_month_labels)
            vol_p2 = sum(float(ks.get(lbl) or 0) for lbl in p2_month_labels)
            row_out = {
                'Keyword':        kw,
                '_ks_avg_vol':    ks.get('avg_monthly_searches') or 0,
                'LANG':           ks.get('lang')         or '',
                'TOPICS':         ks.get('topic')        or '',
                'CATEGORY':       ks.get('category')     or '',
                'SUB-CATEGORY':   ks.get('sub_category') or '',
                f'Volume {p1_label}': vol_p1 or '',
                f'Volume {p2_label}': vol_p2 or '',
            }
            for tag in taxonomy_tags:
                row_out[tag] = ks.get(tag) or ''
            for lbl in p2_month_labels + p1_month_labels:
                row_out[lbl] = f(ks.get(lbl))
            high_conf.append(row_out)
        else:
            source = 'borderline' if (match and match['sim'] >= 0.50) else 'unmatched'
            review.append({
                'source':             source,
                'keyword':            kw,
                'suggested_ks_match': match['ks']['keyword'] if match else '',
                'similarity':         sim,
                'match_confidence':   source,
                'approved':           '',
                'manual_ks_match':    '',
                'notes':              '',
                'gsc_clicks_p1':  r.get('gsc_clicks_p1')  or 0,
                'gsc_clicks_p2':  r.get('gsc_clicks_p2')  or 0,
                'gsc_impr_p1':    r.get('gsc_impr_p1')    or 0,
                'gsc_impr_p2':    r.get('gsc_impr_p2')    or 0,
                'sqr_clicks_p1':  r.get('sqr_clicks_p1')  or 0,
                'sqr_clicks_p2':  r.get('sqr_clicks_p2')  or 0,
                'sqr_cost_p1':    r.get('sqr_cost_p1')    or 0,
                'sqr_cost_p2':    r.get('sqr_cost_p2')    or 0,
                'sqr_impr_p1':    r.get('sqr_impr_p1')    or 0,
                'sqr_impr_p2':    r.get('sqr_impr_p2')    or 0,
            })

    return high_conf, review
