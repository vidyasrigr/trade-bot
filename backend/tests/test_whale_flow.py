"""whale_flow._classify_chain — the pure scoring function."""

from analysis.whale_flow import _classify_chain


def _contract(*, strike, otype, vol, oi, ask, delta):
    return {
        "strike": strike,
        "option_type": otype,
        "volume": vol,
        "open_interest": oi,
        "ask": ask,
        "greeks": {"delta": delta},
    }


def test_empty_chain_returns_none():
    assert _classify_chain([]) is None


def test_thin_volume_dropped():
    chain = [_contract(strike=100, otype="C", vol=5, oi=100, ask=1.0, delta=0.5)]
    assert _classify_chain(chain) is None


def test_small_oi_dropped():
    chain = [_contract(strike=100, otype="C", vol=1000, oi=5, ask=1.0, delta=0.5)]
    # Tiny OI = noisy ratio, dropped.
    assert _classify_chain(chain) is None


def test_below_premium_floor_dropped():
    # Vol=300 × 0.05 × 100 = $1500 < PREMIUM_FLOOR $25k
    chain = [_contract(strike=100, otype="C", vol=300, oi=100, ask=0.05, delta=0.5)]
    assert _classify_chain(chain) is None


def test_deep_otm_lottery_filtered():
    """delta=0.05 is Boyer-Vorkink lottery zone — must drop."""
    chain = [_contract(strike=100, otype="C", vol=10_000, oi=1_000,
                       ask=0.20, delta=0.05)]
    out = _classify_chain(chain)
    # The single contract is filtered; no other to support a signal.
    assert out is None


def test_bullish_imbalance_when_calls_dominate():
    chain = [
        _contract(strike=100, otype="C", vol=5000, oi=1000, ask=2.0, delta=0.4),
        _contract(strike=95,  otype="P", vol=200,  oi=1000, ask=2.0, delta=-0.3),
    ]
    out = _classify_chain(chain)
    assert out is not None
    assert out.call_sweep_usd > 0
    # Put leg too small to clear vol/OI gate, so imbalance ≈ +1
    assert out.directional_imbalance > 0.9


def test_balanced_flow_zero_imbalance():
    chain = [
        _contract(strike=100, otype="C", vol=5000, oi=1000, ask=2.0, delta=0.4),
        _contract(strike=95,  otype="P", vol=5000, oi=1000, ask=2.0, delta=-0.4),
    ]
    out = _classify_chain(chain)
    assert out is not None
    assert abs(out.directional_imbalance) < 0.1


def test_whale_signal_is_premium_times_imbalance_magnitude():
    chain = [_contract(strike=100, otype="C", vol=5000, oi=1000,
                       ask=2.0, delta=0.4)]
    out = _classify_chain(chain)
    expected = out.sweep_score * abs(out.directional_imbalance)
    assert abs(out.whale_signal - expected) < 1e-2
