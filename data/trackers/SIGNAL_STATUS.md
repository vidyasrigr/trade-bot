SIGNAL STATUS  -  generated 2026-06-19 20:30
===============================================================================================
Tested: 5/49   PASS: 0   SANDBOX: 4   NO_EDGE: 1   BLOCKED: 0   PENDING: 44
By stream:  O 2/19   S 3/23   M 3/18   L 1/12
===============================================================================================

-- ENGINE ------------------------------------------------------------------------------------
SIGNAL                    O S M L  DATA     TRAIN  WF_DSR  MTM_DD  VERDICT   BLOCKED_BY
calendar                  . x . x  ready        -       -       -  PENDING   -
candles                   . x . .  ready        -       -       -  PENDING   -
chart_patterns            . x . .  ready        -       -       -  PENDING   -
fundamental               . . x x  ready        -       -       -  PENDING   -
greeks                    x . . .  ready        -       -       -  PENDING   -
iv_analysis               x . . .  ready        -       -       -  PENDING   -
liquidity                 x x . .  ready        -       -       -  PENDING   -
macro                     . . . x  ready        -       -       -  PENDING   -
momentum                  . x x .  ready        -       -       -  PENDING   -
options_chain             x . . .  ready        -       -       -  PENDING   -
risk                      . x x .  ready        -       -       -  PENDING   -
sentiment                 . x . .  ready        -       -       -  PENDING   -
support_resistance        . x . .  ready        -       -       -  PENDING   -
trade_structure           x . . .  ready        -       -       -  PENDING   -
trend                     . x x .  ready        -       -       -  PENDING   -

-- OVERLAY -----------------------------------------------------------------------------------
SIGNAL                    O S M L  DATA     TRAIN  WF_DSR  MTM_DD  VERDICT   BLOCKED_BY
earnings_adj_iv           x . . .  ready        -       -       -  PENDING   -
gex_dex                   x . . .  ready        -       -       -  PENDING   -
options_flow              x . . .  ready        -       -       -  PENDING   -
pre_fomc_drift            x x . .  ready        -       -       -  PENDING   -
regime_markov_market      . . x x  ready        -       -       -  PENDING   -
regime_markov_per_symbol  . x x .  ready        -       -       -  PENDING   -
volatility_regime         x x . .  ready        -       -       -  PENDING   -

-- CROSS_SECTION -----------------------------------------------------------------------------
SIGNAL                    O S M L  DATA     TRAIN  WF_DSR  MTM_DD  VERDICT   BLOCKED_BY
insider_analyst_combo     . . x x  ready        -       -       -  PENDING   -
insider_cluster           . . x x  ready        -       -       -  PENDING   -
iv_call_put_spread        x . . .  ready        -       -       -  PENDING   -
iv_term_slope             x . . .  ready        -       -       -  PENDING   -
momentum_12_1             . x x x  ready     0.28    0.75      8%  SANDBOX   partial gate
reddit_mentions           . x . .  ready        -       -       -  PENDING   -
reddit_polarity           . x . .  ready        -       -       -  PENDING   -
short_squeeze             . x x .  ready        -       -       -  PENDING   -
skew_25d                  x . . .  ready     0.00    0.75      5%  SANDBOX   partial gate
supply_chain_lead_lag     . x x .  ready     0.03    0.04     26%  NO_EDGE   -
vrp_level                 x . . .  ready        -       -       -  PENDING   -
vrp_z                     x . . .  ready        -       -       -  PENDING   -
whale_flow                x . . .  ready        -       -       -  PENDING   -

-- COMPOUND ----------------------------------------------------------------------------------
SIGNAL                    O S M L  DATA     TRAIN  WF_DSR  MTM_DD  VERDICT   BLOCKED_BY
analyst_revision_cascade  . x x .  ready        -       -       -  PENDING   -
beat_and_raise_pead       . x x .  ready     0.55    0.25     56%  SANDBOX   partial gate
sector_dispersion         . . x .  ready        -       -       -  PENDING   -

-- DNA ---------------------------------------------------------------------------------------
SIGNAL                    O S M L  DATA     TRAIN  WF_DSR  MTM_DD  VERDICT   BLOCKED_BY
stock_dna                 . x x x  ready        -       -       -  PENDING   -

-- STRATEGY ----------------------------------------------------------------------------------
SIGNAL                    O S M L  DATA     TRAIN  WF_DSR  MTM_DD  VERDICT   BLOCKED_BY
pre_fomc_straddle         x . . .  ready        -       -       -  PENDING   -
vrp_harvest               x . . .  ready     0.82    0.32     87%  SANDBOX   DD>25% hard gate

-- FEATURE_ONLY ------------------------------------------------------------------------------
SIGNAL                    O S M L  DATA     TRAIN  WF_DSR  MTM_DD  VERDICT   BLOCKED_BY
cot_extreme               . x x .  ready        -       -       -  PENDING   -
finra_short_volume        . x . .  ready        -       -       -  PENDING   -
halo_boost                . x x .  ready        -       -       -  PENDING   -
hy_credit_spread          . . . x  ready        -       -       -  PENDING   -
political_boost           . . x x  ready        -       -       -  PENDING   -
smart_money_crowded       . . . x  ready        -       -       -  PENDING   -
vix_term_contango         x . . .  ready        -       -       -  PENDING   -
yield_curve_slope         . . . x  ready        -       -       -  PENDING   -

