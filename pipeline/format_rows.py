"""Shape merged unified rows into Masterlist column headers for the base write."""


def _f(v):
    return '' if (v is None or v == 0) else v


def format_base_rows(unified: list, p1_label: str = 'Q1 2026', p2_label: str = 'Q4 2025') -> list:
    """p1_label/p2_label default to the original Oikos period for backward
    compatibility. Pass a brand's actual period.p1_label/p2_label so the output
    keys line up with that brand's Masterlist headers — without this, a brand
    on a different period (e.g. Q2 2026 vs Q1 2026) would have its P1 (current)
    data written under a key like 'Clics SEO Q1 2026' that happens to collide
    with its OWN P2 (comparison) column, silently swapping the two periods.
    """
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
            'Keyword':                                    r.get('query') or r.get('search_term') or r.get('unified_key'),
            f'Clics OneSearch {p1_label}':                _f(gC1 + sC1),
            f'Impressions OneSearch {p1_label}':          _f(gI1 + sI1),
            f'Clics OneSearch {p2_label}':                _f(gC2 + sC2),
            f'Impressions OneSearch {p2_label}':          _f(gI2 + sI2),
            f'Clics SEO {p1_label}':                      _f(gC1),
            f'Clics SEM {p1_label}':                      _f(sC1),
            f'Clics SEO {p2_label}':                      _f(gC2),
            f'Clics SEM {p2_label}':                      _f(sC2),
            f'Impr. SEO {p1_label}':                      _f(gI1),
            f'Impr. SEM {p1_label}':                      _f(sI1),
            f'Impr. SEO {p2_label}':                      _f(gI2),
            f'Impr. SEM {p2_label}':                      _f(sI2),
            f'CTR SEO {p1_label}':                        pct(gC1, gI1),
            f'CTR SEM {p1_label}':                        pct(sC1, sI1),
            f'CTR SEO {p2_label}':                        pct(gC2, gI2),
            f'CTR SEM {p2_label}':                        pct(sC2, sI2),
            f'CPC avg. SEM {p1_label}':                   avg(sCo1, sC1),
            f'Spent SEM {p1_label}':                      _f(sCo1),
            f'Spent SEM {p2_label}':                      _f(sCo2),
        })
    return out
