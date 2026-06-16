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
    # Disambiguation: if comma is present but no period, treat comma as decimal separator.
    s = str(v or '0').strip()
    s = s.replace('\xa0', '').replace(' ', '').replace(' ', '')  # remove space variants
    if ',' in s and '.' not in s:
        s = s.replace(',', '.')   # French-style decimal
    else:
        s = s.replace(',', '')    # NA thousands separator
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
