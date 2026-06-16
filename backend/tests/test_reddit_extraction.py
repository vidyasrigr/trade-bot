"""Reddit ticker extraction — must filter common false positives."""

from data.reddit import _extract_tickers, _polarity


def test_extracts_dollar_prefixed_tickers():
    assert "NVDA" in _extract_tickers("Big move in $NVDA today")


def test_extracts_bare_uppercase_tickers():
    out = _extract_tickers("Buying NVDA calls into earnings")
    assert "NVDA" in out


def test_stop_words_filtered():
    out = _extract_tickers("THE BIG NEW WAY TO BUY")
    assert "BIG" not in out
    assert "THE" not in out
    assert "BUY" not in out
    assert "NEW" not in out


def test_common_finance_acronyms_excluded():
    text = "YOLO into FOMC, WSB consensus is MOON"
    out = _extract_tickers(text)
    for excluded in ("YOLO", "FOMC", "WSB", "MOON"):
        assert excluded not in out


def test_empty_input_returns_empty():
    assert _extract_tickers(None) == []
    assert _extract_tickers("") == []


def test_polarity_bullish():
    assert _polarity("calls calls calls into earnings", "") == "bullish"


def test_polarity_bearish():
    assert _polarity("buying puts, this will crash", "downside everywhere") == "bearish"


def test_polarity_neutral():
    assert _polarity("watching the market", "") == "neutral"
