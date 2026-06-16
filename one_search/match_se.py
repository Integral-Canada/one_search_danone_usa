"""Match SE Ranking keywords to unified Masterlist rows using trigram similarity."""
from .trigram import trigrams_arr, jaccard


def match_se_keywords(se_rows: list, index: dict, threshold: float = 0.60) -> list:
    u_keys   = index['uKeys']
    u_display = index['uDisplay']
    u_tg     = index['uTg']
    idx      = index['idx']

    best_se: dict = {}
    for r in se_rows:
        q_arr = trigrams_arr(r['norm_se_keyword'])
        q_set = set(q_arr)

        cand_score: dict = {}
        for t in q_arr:
            for i in idx.get(t, []):
                cand_score[i] = cand_score.get(i, 0) + 1

        if not cand_score:
            continue

        bi, bs = -1, 0.0
        for i in cand_score:
            s = jaccard(u_tg[i], q_set)
            if s > bs:
                bs = s
                bi = i

        if bi >= 0 and bs >= threshold:
            k = u_keys[bi]
            if k not in best_se or bs > best_se[k]['_sim']:
                best_se[k] = {
                    '_sim':             bs,
                    '_display':         u_display[bi],
                    'se_position':      r['se_position'],
                    'se_search_vol':    r['se_search_vol'],
                    'se_cpc':           r['se_cpc'],
                    'se_search_intent': r['se_search_intent'],
                    'se_url_path':      r.get('se_url_path') or '',
                }

    def f(v): return '' if (v is None or v == 0) else v

    return [
        {
            'Keyword':             se.get('_display') or key,
            'Position SE Ranking': f(se['se_position']),
            'CPC SEO Q1 2026':     f(se['se_cpc']),
            'Purchase intent':     se.get('se_search_intent') or '',
            '_se_url_path':        se.get('se_url_path') or '',
        }
        for key, se in best_se.items()
    ]
