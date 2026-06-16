"""Shape merged unified rows into Masterlist column headers for the base write."""


def _f(v):
    return '' if (v is None or v == 0) else v


def format_base_rows(unified: list) -> list:
    out = []
    for r in unified:
        gC1  = r.get('gsc_clicks_p1') or 0
        gC2  = r.get('gsc_clicks_p2') or 0
        sC1  = r.get('sqr_clicks_p1') or 0
        sC2  = r.get('sqr_clicks_p2') or 0
        gI1  = r.get('gsc_impr_p1')   or 0
        gI2  = r.get('gsc_impr_p2')   or 0
        sI1  = r.get('sqr_impr_p1')   or 0
        sI2  = r.get('sqr_impr_p2')   or 0
        sCo1 = r.get('sqr_cost_p1')   or 0
        sCo2 = r.get('sqr_cost_p2')   or 0

        def pct(clicks, impr):
            return f"{round(clicks / impr * 10000) / 100}%" if impr > 0 else ''

        def avg(cost, clicks):
            return round(cost / clicks * 100) / 100 if clicks > 0 else ''

        out.append({
            'Keyword':                          r.get('query') or r.get('search_term') or r.get('unified_key'),
            'Clics OneSearch Q1 2026':          _f(gC1 + sC1),
            'Impressions OneSearch Q1 2026':    _f(gI1 + sI1),
            'Clics OneSearch Q4 2025':          _f(gC2 + sC2),
            'Impressions OneSearch Q4 2025':    _f(gI2 + sI2),
            'Clics SEO Q1 2026':                _f(gC1),
            'Clics SEM Q1 2026':                _f(sC1),
            'Clics SEO Q4 2025':                _f(gC2),
            'Clics SEM Q4 2025':                _f(sC2),
            'Impr. SEO Q1 2026':                _f(gI1),
            'Impr. SEM Q1 2026':                _f(sI1),
            'Impr. SEO Q4 2025':                _f(gI2),
            'Impr. SEM Q4 2025':                _f(sI2),
            'CTR SEO Q1 2026':                  pct(gC1, gI1),
            'CTR SEM Q1 2026':                  pct(sC1, sI1),
            'CTR SEO Q4 2025':                  pct(gC2, gI2),
            'CTR SEM Q4 2025':                  pct(sC2, sI2),
            'CPC avg. SEM Q1 2026':             avg(sCo1, sC1),
            'Spent SEM Q1 2026':                _f(sCo1),
            'Spent SEM Q4 2025':                _f(sCo2),
        })
    return out
