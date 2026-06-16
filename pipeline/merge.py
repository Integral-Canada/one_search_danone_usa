"""Full outer join GSC ∪ SQR on normalized keyword, with dedup and click filtering."""


def merge_gsc_sqr(gsc_rows: list, sqr_rows: list) -> list:
    gsc_filtered = [r for r in gsc_rows if r['gsc_clicks_p1'] > 1 or r['gsc_clicks_p2'] > 1]
    sqr_filtered = [r for r in sqr_rows if r['sqr_clicks_p1'] > 1 or r['sqr_clicks_p2'] > 1]

    # Dedup GSC: SUM clicks+impr, weighted-avg position, recompute CTR
    gsc_map: dict = {}
    for r in gsc_filtered:
        k = r['norm_query']
        if k not in gsc_map:
            gsc_map[k] = dict(r)
        else:
            m = gsc_map[k]
            pi1, pi2 = m['gsc_impr_p1'], m['gsc_impr_p2']
            m['gsc_clicks_p1'] += r['gsc_clicks_p1']
            m['gsc_clicks_p2'] += r['gsc_clicks_p2']
            m['gsc_impr_p1']   += r['gsc_impr_p1']
            m['gsc_impr_p2']   += r['gsc_impr_p2']
            if m['gsc_impr_p1'] > 0:
                m['gsc_pos_p1'] = (m['gsc_pos_p1'] * pi1 + r['gsc_pos_p1'] * r['gsc_impr_p1']) / m['gsc_impr_p1']
            if m['gsc_impr_p2'] > 0:
                m['gsc_pos_p2'] = (m['gsc_pos_p2'] * pi2 + r['gsc_pos_p2'] * r['gsc_impr_p2']) / m['gsc_impr_p2']
    for m in gsc_map.values():
        m['gsc_ctr_p1'] = m['gsc_clicks_p1'] / m['gsc_impr_p1'] if m['gsc_impr_p1'] > 0 else 0.0
        m['gsc_ctr_p2'] = m['gsc_clicks_p2'] / m['gsc_impr_p2'] if m['gsc_impr_p2'] > 0 else 0.0

    # Dedup SQR: SUM clicks+cost+impr, concat unique search_keyword values
    sqr_map: dict = {}
    for r in sqr_filtered:
        k = r['norm_term']
        if k not in sqr_map:
            sqr_map[k] = dict(r)
            sqr_map[k]['_kws'] = {r['search_keyword']}
        else:
            m = sqr_map[k]
            m['sqr_clicks_p1'] += r['sqr_clicks_p1']
            m['sqr_clicks_p2'] += r['sqr_clicks_p2']
            m['sqr_cost_p1']   += r['sqr_cost_p1']
            m['sqr_cost_p2']   += r['sqr_cost_p2']
            m['sqr_impr_p1']   += r['sqr_impr_p1']
            m['sqr_impr_p2']   += r['sqr_impr_p2']
            m['_kws'].add(r['search_keyword'])
    for m in sqr_map.values():
        m['search_keyword'] = ' | '.join(sorted(m.pop('_kws')))

    # Full outer join: GSC-only rows get SQR cols = 0; SQR-only rows get GSC cols = 0
    ZSQR = dict(sqr_clicks_p1=0.0, sqr_clicks_p2=0.0, sqr_cost_p1=0.0, sqr_cost_p2=0.0,
                sqr_impr_p1=0.0, sqr_impr_p2=0.0, search_keyword='', search_term='')
    ZGSC  = dict(gsc_clicks_p1=0.0, gsc_clicks_p2=0.0, gsc_impr_p1=0.0, gsc_impr_p2=0.0,
                 gsc_ctr_p1=0.0, gsc_ctr_p2=0.0, gsc_pos_p1=0.0, gsc_pos_p2=0.0, query='')

    sqr_rem = dict(sqr_map)
    unified: dict = {}
    for k, g in gsc_map.items():
        unified[k] = {'unified_key': k, **ZSQR, **g}
        if k in sqr_rem:
            unified[k].update(sqr_rem.pop(k))
    for k, s in sqr_rem.items():
        unified[k] = {'unified_key': k, 'norm_query': k, **ZGSC, **s}

    return list(unified.values())
