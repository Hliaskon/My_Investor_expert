"""
Κοινά fixtures. Τα tests ΔΕΝ κάνουν κανένα network call: το yfinance
αντικαθίσταται από fake module ΠΡΙΝ φορτωθεί το screener (όλες οι
συναρτήσεις κάνουν `import yfinance` lazily, άρα παίρνουν το fake).
"""
import os
import sys
import types

import pandas as pd
import pytest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_DIR)


class FakeYF:
    """Δεδομένα ανά ticker — κάθε test τα γεμίζει μέσω του fixture `yf`."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.infos, self.qf, self.qb = {}, {}, {}
        self.cf, self.fin, self.ge = {}, {}, {}
        self.prices = pd.DataFrame()


FAKE = FakeYF()


class _Ticker:
    def __init__(self, t, session=None):
        self.t = t

    @property
    def info(self):
        return FAKE.infos[self.t]

    @property
    def quarterly_financials(self):
        return FAKE.qf.get(self.t)

    @property
    def quarterly_balance_sheet(self):
        return FAKE.qb.get(self.t)

    @property
    def cashflow(self):
        return FAKE.cf.get(self.t)

    @property
    def financials(self):
        return FAKE.fin.get(self.t)

    @property
    def growth_estimates(self):
        return FAKE.ge.get(self.t)

    insider_purchases = None

    def history(self, period="1y"):
        return pd.DataFrame()


def _download(tickers, **kw):
    cols = [t for t in tickers if t in FAKE.prices.columns]
    d = FAKE.prices[cols].copy()
    d.columns = pd.MultiIndex.from_product([["Close"], cols])
    return d


_mod = types.ModuleType("yfinance")
_mod.Ticker = _Ticker
_mod.download = _download
_mod.__version__ = "fake"
sys.modules["yfinance"] = _mod

os.environ["EXTENDED_METRICS"] = "1"
os.environ.pop("FRED_API_KEY", None)


@pytest.fixture
def yf():
    FAKE.reset()
    yield FAKE
    FAKE.reset()


@pytest.fixture
def S():
    import screener
    return screener


# Βασικό .info μιας "κανονικής" US μετοχής: P/E 10, EPS 10, τιμή 100.
BASE_INFO = dict(
    symbol="X", trailingPE=10.0, priceToBook=1.5, beta=1.0, debtToEquity=50,
    returnOnEquity=0.18, dividendYield=0.02, targetMeanPrice=None,
    fiftyTwoWeekHigh=None, fiftyTwoWeekLow=None, earningsQuarterlyGrowth=0.05,
    enterpriseToEbitda=7.0, sector="Industrials", currency="USD",
    financialCurrency="USD", trailingEps=10.0, currentPrice=100.0,
    fiftyDayAverage=100.0, sharesOutstanding=1_000,
)

ANNUAL_COLS    = pd.date_range("2022-12-31", periods=4, freq="YE")[::-1]
QUARTERLY_COLS = pd.date_range("2025-01-01", periods=4, freq="QE")[::-1]
