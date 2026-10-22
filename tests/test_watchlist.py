import os

import pandas as pd
import pytest

from conftest import REPO_DIR
from build_watchlist import normalize_intl_ticker, KNOWN_EXCHANGE_SUFFIXES


@pytest.mark.parametrize("raw, suffix, expected", [
    ("SAP.DE.DE", ".DE", "SAP.DE"),    # διπλό suffix
    ("AIR.PA.DE", ".DE", "AIR.PA"),    # εσωτερικό suffix = πραγματικό χρηματιστήριο
    ("BT.A",      ".L",  "BT-A.L"),    # share class → Yahoo format
    ("BT.A.L",    ".L",  "BT-A.L"),
    ("ADS",       ".DE", "ADS.DE"),
    ("ULVR.L",    ".L",  "ULVR.L"),
    (" sap ",     ".DE", "SAP.DE"),
])
def test_normalize_intl_ticker(raw, suffix, expected):
    assert normalize_intl_ticker(raw, suffix) == expected


def test_europe_watchlist_is_clean():
    wl = pd.read_csv(os.path.join(REPO_DIR, "watchlist_europe.csv"))
    assert not wl["ticker"].duplicated().any()
    for t in wl["ticker"]:
        assert t.endswith(KNOWN_EXCHANGE_SUFFIXES), t
        base = t[: t.rindex(".")]
        assert "." not in base, f"διπλό suffix: {t}"


def test_screener_accepts_all_builder_suffixes():
    # Το screener.py κρατάει δική του λίστα (δεν κάνει import το
    # build_watchlist) — τα δύο πρέπει να μένουν συγχρονισμένα.
    src = open(os.path.join(REPO_DIR, "screener.py"), encoding="utf-8").read()
    for sfx in KNOWN_EXCHANGE_SUFFIXES:
        assert f'"{sfx}"' in src, f"{sfx} λείπει από INTL_SUFFIXES του screener.py"
