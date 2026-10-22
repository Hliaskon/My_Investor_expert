"""
Πλήρες run του screener.py (__main__) σε προσωρινό αντίγραφο του repo,
με fake yfinance και fake SMTP — ελέγχει ότι όλα τα κομμάτια δένουν:
screening → tier → snapshot → performance → history → email.
"""
import email
import glob
import os
import runpy
import shutil
import smtplib

import numpy as np
import pandas as pd

from conftest import REPO_DIR, BASE_INFO, ANNUAL_COLS


class _FakeSMTP:
    sent = []

    def __init__(self, *a):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def login(self, *a):
        pass

    def sendmail(self, sender, receiver, msg):
        _FakeSMTP.sent.append(msg)


def test_full_run(tmp_path, yf, monkeypatch):
    for f in glob.glob(os.path.join(REPO_DIR, "*.py")) + [os.path.join(REPO_DIR, "history.csv")]:
        shutil.copy(f, tmp_path)
    pd.DataFrame({"ticker": ["CHEAP", "FAIR"], "name": ["c", "f"],
                  "sector": ["Industrials"] * 2}).to_csv(tmp_path / "wl.csv", index=False)

    yf.infos["CHEAP"] = dict(BASE_INFO)
    yf.cf["CHEAP"] = pd.DataFrame([[15000] * 4], index=["Free Cash Flow"], columns=ANNUAL_COLS)
    yf.infos["FAIR"] = dict(BASE_INFO)
    yf.cf["FAIR"] = pd.DataFrame([[6000] * 4], index=["Free Cash Flow"], columns=ANNUAL_COLS)
    days = pd.bdate_range("2026-08-01", pd.Timestamp.today())
    hist_tickers = pd.read_csv(tmp_path / "history.csv")["ticker"].unique().tolist()
    yf.prices = pd.DataFrame({t: np.linspace(100, 110, len(days)) for t in hist_tickers}, index=days)
    yf.prices["SPY"] = 100.0

    _FakeSMTP.sent.clear()
    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)
    for k, v in dict(EMAIL_SENDER="a@x", EMAIL_PASSWORD="p", EMAIL_RECEIVER="b@x",
                     WATCHLIST_FILE="wl.csv", REQUEST_DELAY="0").items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    runpy.run_path(str(tmp_path / "screener.py"), run_name="__main__")

    snaps = os.listdir(tmp_path / "snapshots")
    assert len(snaps) == 1
    snap = pd.read_csv(tmp_path / "snapshots" / snaps[0]).set_index("ticker")
    assert set(snap.index) == {"CHEAP", "FAIR"}            # ΟΛΟ το universe, όχι μόνο shortlist
    assert bool(snap.loc["CHEAP", "passed_filters"]) and not bool(snap.loc["FAIR", "passed_filters"])
    assert snap.loc["CHEAP", "fcf_source"] == "reported"

    assert len(_FakeSMTP.sent) == 1
    msg = email.message_from_string(_FakeSMTP.sent[0])
    html = msg.get_payload()[0].get_payload(decode=True).decode()
    assert "Excess Return vs Benchmark" in html
    assert "FCF: reported" in html
