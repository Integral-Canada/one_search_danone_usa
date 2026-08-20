import re


def normalize(s: str) -> str:
    s = str(s or '').lower()
    s = s.replace('​', ' ')  # zero-width space
    s = re.sub(r'[^a-z0-9 ]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def clean_num(v) -> float:
    # Two number formats appear in exports:
    #   GSC / NA format:    comma = thousands sep  ("1,234" → 1234)
    #   SQR French format:  space = thousands sep, comma = decimal ("135507,64" → 135507.64, "32 395" → 32395)
    #
    # Disambiguation when a period is also present: comma is always thousands sep
    # ("1,234.56"). When only a comma is present, digit-count-after-comma decides:
    #   - exactly one comma, exactly 3 digits after it → NA thousands sep ("1,234" → 1234)
    #   - exactly one comma, any other digit count      → French decimal  ("1,5" → 1.5,
    #     "135507,64" → 135507.64)
    #   - more than one comma group                     → NA thousands sep ("1,234,567")
    # Known residual ambiguity: a genuine 3-decimal value with no thousands grouping
    # (e.g. "12,345" meaning 12.345) is indistinguishable from "12,345" meaning 12345 —
    # rare for costs/volumes in this domain, so it resolves to the thousands reading.
    s = str(v or '0').strip()
    # Strip space-like separators: regular space, NBSP, narrow no-break, thin/en/ideographic space
    s = re.sub(r'[\s\xa0  - 　]', '', s)
    if ',' in s:
        if '.' in s:
            s = s.replace(',', '')  # comma = thousands sep when a period is also present
        else:
            groups = s.split(',')
            if len(groups) == 2 and len(groups[1]) == 3 and groups[1].isdigit():
                s = s.replace(',', '')     # single comma + 3 digits → NA thousands sep
            elif len(groups) == 2:
                s = s.replace(',', '.')    # single comma, other digit count → French decimal
            else:
                s = s.replace(',', '')     # multiple comma groups → NA thousands sep
    s = re.sub(r'[^0-9.\-]', '', s)
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def parse_pct(v) -> float:
    s = str(v or '0').replace('%', '').strip()
    try:
        return float(s) / 100.0
    except ValueError:
        return 0.0
