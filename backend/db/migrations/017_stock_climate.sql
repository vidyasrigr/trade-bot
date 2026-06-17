-- Migration 017: Per-stock climate + market weather
-- Run after 016_phase_i_signals.sql

CREATE TABLE IF NOT EXISTS stock_climate (
    symbol         TEXT NOT NULL,
    as_of_date     DATE NOT NULL,
    climate        TEXT NOT NULL,            -- bull / bear / chop / squeeze / high_vol / unknown
    market_climate TEXT NOT NULL,            -- overall market weather (same labels)
    relative_climate TEXT NOT NULL,          -- 'outperforming' / 'inline' / 'underperforming' vs market
    momentum_score NUMERIC(6,2),             -- per-stock 60-day RS-line slope
    rs_vs_spy      NUMERIC(8,4),             -- 60-day return vs SPY
    rv_pct_1yr     NUMERIC(6,4),             -- per-stock 20d RV percentile vs own 1y history
    near_52w_high  NUMERIC(6,4),             -- (current - low52) / (high52 - low52), 0..1
    confidence     NUMERIC(5,2),             -- 0-100, how confident we are in the label
    PRIMARY KEY (symbol, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_stock_climate_date ON stock_climate(as_of_date);
CREATE INDEX IF NOT EXISTS idx_stock_climate_label ON stock_climate(climate, as_of_date);

-- Market-wide weather, one row per day
CREATE TABLE IF NOT EXISTS market_weather (
    as_of_date     DATE PRIMARY KEY,
    weather        TEXT NOT NULL,            -- bull_trend / bear_trend / chop / high_vol / crisis
    vix            NUMERIC(6,2),
    vix_term       NUMERIC(6,2),             -- vix3m - vix (contango when positive)
    breadth        NUMERIC(6,4),             -- pct of universe > 200dma
    spy_ret_5d     NUMERIC(8,4),
    spy_ret_20d    NUMERIC(8,4),
    yield_curve_10y2y NUMERIC(8,4),
    hy_oas         NUMERIC(8,4),
    notes          TEXT
);

CREATE INDEX IF NOT EXISTS idx_market_weather_weather ON market_weather(weather);
