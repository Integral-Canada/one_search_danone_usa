"""Match Keyword Study keywords to unified Masterlist rows using trigram similarity.

Matching direction: index is built on the ~1,240 unified queries (small set).
We iterate the 14,273 KS keywords through that small index, then pivot to keep
the best KS match per unified row.

Performance: pre-filter drops KS keywords with zero shared trigrams (lossless).
Top-50 candidate cap bounds Jaccard calls per KS keyword.
"""
from .trigram import trigrams_arr, jaccard


def match_ks_keywords(ks_rows: list, index: dict, unified: list,
                      high_conf_threshold: float = 0.65) -> tuple:
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
            vol_p1 = (float(ks.get('Searches: Jan 2026') or 0)
                    + float(ks.get('Searches: Feb 2026') or 0)
                    + float(ks.get('Searches: Mar 2026') or 0))
            vol_p2 = (float(ks.get('Searches: Oct 2025') or 0)
                    + float(ks.get('Searches: Nov 2025') or 0)
                    + float(ks.get('Searches: Dec 2025') or 0))
            high_conf.append({
                'Keyword':        kw,
                '_ks_avg_vol':    ks.get('avg_monthly_searches') or 0,
                'LANG':           ks.get('lang')         or '',
                'TOPICS':         ks.get('topic')        or '',
                'CATEGORY':       ks.get('category')     or '',
                'SUB-CATEGORY':   ks.get('sub_category') or '',
                'Volume Q1 2026': vol_p1 or '',
                'Volume Q4 2025': vol_p2 or '',
                'Yogurt types':   ks.get('Yogurt types')       or '',
                'Taste':          ks.get('Taste')              or '',
                'Packaging':      ks.get('Packaging')          or '',
                'Ingredient':     ks.get('Ingredient')         or '',
                'Brands':         ks.get('Brands')             or '',
                'Retailer':       ks.get('Retailer')           or '',
                'Demography':     ks.get('Demography')         or '',
                'Benefits':       ks.get('Benefits')           or '',
                'Testimonials':   ks.get('Testimonials')       or '',
                'Bio':            ks.get('Bio')                or '',
                'Moments':        ks.get('Moments')            or '',
                'Recipes':        ks.get('Recipes')            or '',
                'Searches: Oct 2025': f(ks.get('Searches: Oct 2025')),
                'Searches: Nov 2025': f(ks.get('Searches: Nov 2025')),
                'Searches: Dec 2025': f(ks.get('Searches: Dec 2025')),
                'Searches: Jan 2026': f(ks.get('Searches: Jan 2026')),
                'Searches: Feb 2026': f(ks.get('Searches: Feb 2026')),
                'Searches: Mar 2026': f(ks.get('Searches: Mar 2026')),
            })
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
