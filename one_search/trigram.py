from typing import Dict, List, Set


def trigrams_arr(s: str) -> List[str]:
    s = ' ' + s + ' '
    seen: Set[str] = set()
    out: List[str] = []
    for i in range(len(s) - 2):
        t = s[i:i + 3]
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def jaccard(u_arr: List[str], q_set: Set[str]) -> float:
    n = sum(1 for t in u_arr if t in q_set)
    denom = len(u_arr) + len(q_set) - n
    return n / denom if denom > 0 else 0.0


def build_index(unified_rows: List[dict]) -> dict:
    """Build n=3 trigram index on unified rows. Returns {uKeys, uDisplay, uTg, idx}."""
    from .normalize import normalize
    u_keys = [r.get('unified_key') or r.get('norm_query') or '' for r in unified_rows]
    u_display = [r.get('query') or r.get('search_term') or r.get('unified_key') or '' for r in unified_rows]
    u_tg = [trigrams_arr(normalize(k)) for k in u_keys]

    idx: Dict[str, List[int]] = {}
    for i, tg in enumerate(u_tg):
        for t in tg:
            if t not in idx:
                idx[t] = []
            idx[t].append(i)

    return {'uKeys': u_keys, 'uDisplay': u_display, 'uTg': u_tg, 'idx': idx}
