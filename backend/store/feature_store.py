"""
Point-in-time feature store — DuckDB/Parquet, append-only.

Why this exists: every backtest that joins to "today's" feature table silently
leaks revised data (earnings restatements, late-arriving fundamentals, survivorship-
adjusted prices). The Phase A cleanup removed false confidence; this module gives us
honest validation by partitioning snapshots by their `as_of_date` and never letting
a reader see rows from after that date.

Layout:
  data/feature_store/{YYYY}/snapshot_{YYYY-MM-DD}.parquet

Each file is a long-format snapshot: (symbol, feature_name, value, as_of_date).
DuckDB reads them as a single virtual table for cross-date queries (Phase C+D+E).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import duckdb
import pandas as pd
from loguru import logger


@dataclass(frozen=True)
class FeatureStoreConfig:
    root: Path

    @classmethod
    def from_env(cls) -> "FeatureStoreConfig":
        root = os.environ.get("FEATURE_STORE_ROOT", "data/feature_store")
        return cls(root=Path(root))


class FeatureStore:
    """
    Long-format point-in-time feature store.

    write_snapshot(date, df) — append-only; refuses to overwrite an existing day
        unless overwrite=True is explicit (this is what makes the store honest).
    read_panel(features, start, end, symbols) — returns a wide-format DataFrame
        for the requested window using ONLY the snapshots that existed by then.
    latest_snapshot() — returns (date, row_count) of the most recent snapshot or None.
    available_dates() — list of every snapshot date on disk.
    """

    def __init__(self, config: FeatureStoreConfig | None = None):
        self.config = config or FeatureStoreConfig.from_env()
        self.config.root.mkdir(parents=True, exist_ok=True)

    # ---- paths -------------------------------------------------------------

    def _snapshot_path(self, d: date) -> Path:
        return self.config.root / f"{d.year}" / f"snapshot_{d.isoformat()}.parquet"

    def _glob_pattern(self) -> str:
        return str(self.config.root / "*" / "snapshot_*.parquet")

    # ---- write -------------------------------------------------------------

    def write_snapshot(self, as_of: date, df: pd.DataFrame, *, overwrite: bool = False) -> Path:
        """
        df must have columns (symbol, feature_name, value). as_of_date is added.
        Long-format keeps the schema stable as new features are added — no ALTER TABLE.
        """
        required = {"symbol", "feature_name", "value"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"FeatureStore.write_snapshot missing columns: {missing}")
        if df.empty:
            logger.warning(f"FeatureStore: empty snapshot for {as_of} — refusing to write empty file")
            return self._snapshot_path(as_of)

        path = self._snapshot_path(as_of)
        if path.exists() and not overwrite:
            raise FileExistsError(
                f"Snapshot for {as_of} already exists at {path}. "
                "Refusing to overwrite — point-in-time means historical snapshots are immutable. "
                "Pass overwrite=True only when intentionally rebuilding."
            )
        path.parent.mkdir(parents=True, exist_ok=True)

        out = df[["symbol", "feature_name", "value"]].copy()
        out["as_of_date"] = pd.Timestamp(as_of)
        out["symbol"] = out["symbol"].astype(str)
        out["feature_name"] = out["feature_name"].astype(str)
        out["value"] = pd.to_numeric(out["value"], errors="coerce")
        out = out.dropna(subset=["value"])
        out.to_parquet(path, index=False)
        logger.info(f"FeatureStore: wrote {len(out)} rows to {path}")
        return path

    # ---- read --------------------------------------------------------------

    def read_panel(
        self,
        features: Iterable[str],
        start: date,
        end: date,
        symbols: Iterable[str] | None = None,
        *,
        as_of: date | None = None,
    ) -> pd.DataFrame:
        """
        Wide-format panel: index=(as_of_date, symbol), columns=feature_name.

        as_of: if set, ONLY snapshots with as_of_date <= as_of are read. This is
        the point-in-time guard — passing as_of=2022-06-01 makes the panel look
        exactly as it would have on 2022-06-01, even if later snapshots exist.
        Default (None) reads everything in [start, end] for live use.
        """
        feature_list = list(features)
        if not feature_list:
            return pd.DataFrame()
        if not self.available_dates():
            return pd.DataFrame()

        con = duckdb.connect(":memory:")
        try:
            placeholders = ", ".join(["?"] * len(feature_list))
            params: list = [self._glob_pattern(), *feature_list,
                            pd.Timestamp(start), pd.Timestamp(end)]
            sql = f"""
                SELECT as_of_date, symbol, feature_name, value
                FROM read_parquet(?)
                WHERE feature_name IN ({placeholders})
                  AND as_of_date >= ?
                  AND as_of_date <= ?
            """
            if as_of is not None:
                sql += " AND as_of_date <= ?"
                params.append(pd.Timestamp(as_of))
            if symbols is not None:
                symbol_list = list(symbols)
                if symbol_list:
                    sym_placeholders = ", ".join(["?"] * len(symbol_list))
                    sql += f" AND symbol IN ({sym_placeholders})"
                    params.extend(symbol_list)

            long_df = con.execute(sql, params).fetchdf()
        finally:
            con.close()

        if long_df.empty:
            return long_df
        long_df["as_of_date"] = pd.to_datetime(long_df["as_of_date"]).dt.date
        wide = long_df.pivot_table(
            index=["as_of_date", "symbol"], columns="feature_name", values="value",
            aggfunc="last",
        )
        wide.columns.name = None
        return wide.reset_index()

    # ---- metadata ----------------------------------------------------------

    def available_dates(self) -> list[date]:
        out: list[date] = []
        for path in self.config.root.glob("*/snapshot_*.parquet"):
            try:
                stem = path.stem.removeprefix("snapshot_")
                out.append(date.fromisoformat(stem))
            except ValueError:
                continue
        return sorted(out)

    def latest_snapshot(self) -> tuple[date, int] | None:
        dates = self.available_dates()
        if not dates:
            return None
        latest = dates[-1]
        df = pd.read_parquet(self._snapshot_path(latest))
        return latest, int(len(df))


_store: FeatureStore | None = None


def get_feature_store() -> FeatureStore:
    global _store
    if _store is None:
        _store = FeatureStore()
    return _store
