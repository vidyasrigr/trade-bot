"""
Self-test for the point-in-time feature store.

Proves:
  - write_snapshot persists long-format rows under date-partitioned parquet files
  - read_panel pivots to wide format and respects (start, end, symbols) filters
  - the `as_of` guard EXCLUDES future snapshots — the property that makes the
    store honest for backtests
  - re-writing an existing date without overwrite=True raises FileExistsError
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from store.feature_store import FeatureStore, FeatureStoreConfig


def _snapshot(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["symbol", "feature_name", "value"])


class FeatureStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="featurestore_test_"))
        self.store = FeatureStore(FeatureStoreConfig(root=self.tmp))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_then_read_round_trip(self) -> None:
        d1 = date(2024, 5, 1)
        self.store.write_snapshot(d1, _snapshot([
            ("NVDA", "iv_rank", 60.0),
            ("NVDA", "vrp_z", 1.2),
            ("AAPL", "iv_rank", 35.0),
            ("AAPL", "vrp_z", 0.4),
        ]))

        panel = self.store.read_panel(["iv_rank"], d1, d1)
        self.assertEqual(len(panel), 2)
        self.assertEqual(
            sorted(panel.columns),
            ["as_of_date", "iv_rank", "symbol"],
        )
        nvda = panel[panel.symbol == "NVDA"].iloc[0]
        self.assertAlmostEqual(nvda["iv_rank"], 60.0)

    def test_as_of_blocks_future_leakage(self) -> None:
        """The property that makes this store useful for backtests."""
        d_old = date(2024, 5, 1)
        d_new = date(2024, 6, 1)
        self.store.write_snapshot(d_old, _snapshot([("NVDA", "iv_rank", 60.0)]))
        self.store.write_snapshot(d_new, _snapshot([("NVDA", "iv_rank", 92.0)]))

        # Asking the store on d_old must NOT see d_new even though d_new exists.
        panel = self.store.read_panel(
            ["iv_rank"], date(2024, 1, 1), date(2024, 12, 31), as_of=d_old,
        )
        self.assertEqual(len(panel), 1)
        self.assertEqual(panel.iloc[0]["as_of_date"], d_old)
        self.assertAlmostEqual(panel.iloc[0]["iv_rank"], 60.0)

        # Without the guard we see both (live use).
        live = self.store.read_panel(
            ["iv_rank"], date(2024, 1, 1), date(2024, 12, 31),
        )
        self.assertEqual(len(live), 2)

    def test_symbol_filter(self) -> None:
        d = date(2024, 5, 1)
        self.store.write_snapshot(d, _snapshot([
            ("NVDA", "iv_rank", 60.0),
            ("AAPL", "iv_rank", 35.0),
            ("MSFT", "iv_rank", 50.0),
        ]))
        panel = self.store.read_panel(["iv_rank"], d, d, symbols=["NVDA", "MSFT"])
        self.assertEqual(set(panel.symbol), {"NVDA", "MSFT"})

    def test_refuse_to_overwrite_existing_snapshot(self) -> None:
        d = date(2024, 5, 1)
        self.store.write_snapshot(d, _snapshot([("NVDA", "iv_rank", 60.0)]))
        with self.assertRaises(FileExistsError):
            self.store.write_snapshot(d, _snapshot([("NVDA", "iv_rank", 99.0)]))
        # Overwrite=True succeeds (used for intentional rebuilds only)
        self.store.write_snapshot(d, _snapshot([("NVDA", "iv_rank", 99.0)]), overwrite=True)
        panel = self.store.read_panel(["iv_rank"], d, d)
        self.assertAlmostEqual(panel.iloc[0]["iv_rank"], 99.0)

    def test_latest_snapshot_and_available_dates(self) -> None:
        self.assertIsNone(self.store.latest_snapshot())
        self.store.write_snapshot(date(2024, 5, 1), _snapshot([("A", "x", 1.0)]))
        self.store.write_snapshot(date(2024, 5, 2), _snapshot([("A", "x", 2.0)]))
        self.assertEqual(
            self.store.available_dates(), [date(2024, 5, 1), date(2024, 5, 2)],
        )
        latest = self.store.latest_snapshot()
        assert latest is not None
        latest_d, count = latest
        self.assertEqual(latest_d, date(2024, 5, 2))
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
