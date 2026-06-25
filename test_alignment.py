"""Tests for table alignment in run_rebalance_audit and run_lump_sum.

The two tabular outputs have a long history of misalignment: the header
used '<N' widths that included the column's trailing space, but the cells
either omitted the € / % from the width math or used a different width
entirely, so every column drifted sideways as values widened. These
tests pin the invariant that every '|' separator lands at the same
column index across the header, separator, and every data row.

Also pins alignment of the Cash side-fund row against the asset rows in
gather_holdings and print_portfolio_summary: the 'Cash' label must pad
to the same width as the asset labels (Equity / Bonds / Gold) so the
trailing ':' lines up.
"""
import io
import re
import sys
from contextlib import redirect_stdout

import pytest

import main
from main import (build_strategy, gather_holdings, print_portfolio_summary,
                  run_lump_sum, run_rebalance_audit)


STRATEGY = build_strategy({"Equity": 0.60, "Bonds": 0.25, "Gold": 0.15}, 0.20)


def capture(func, *args, **kwargs) -> str:
    """Run func and return everything it printed to stdout."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        func(*args, **kwargs)
    return buf.getvalue()


def pipe_columns(line: str) -> list[int]:
    """Return the column indices of every '|' in a line."""
    return [i for i, ch in enumerate(line) if ch == "|"]


def assert_pipes_aligned(table_lines: list[str]) -> None:
    """Every non-empty line must have '|' at the same column indices.

    Skips lines that are part of the '=' separator banners (no pipes)
    and the surrounding prose ('[✓] ...', 'Note: ...'). A 'table line' is
    any line containing at least one '|'.
    """
    pipe_lines = [line for line in table_lines if "|" in line]
    assert pipe_lines, "no table lines found"
    first = pipe_columns(pipe_lines[0])
    for line in pipe_lines[1:]:
        cols = pipe_columns(line)
        assert cols == first, (
            f"misaligned table:\n  header pipes at {first}\n"
            f"  this line at {cols}:\n  {line!r}"
        )


# ── Rebalance audit table ───────────────────────────────────────────────

def test_rebalance_audit_table_aligned_on_user_portfolio():
    """The €210k portfolio that originally exposed the misalignment."""
    cv = {"Equity": 127559.25, "Bonds": 53103.54, "Gold": 30318.64}
    total = sum(cv.values())
    bp = {"Equity": 100.0, "Bonds": 50.0, "Gold": 200.0}
    sp = {"Equity": 99.0,  "Bonds": 49.0, "Gold": 199.0}
    out = capture(run_rebalance_audit, STRATEGY, cv, total, bp, sp)
    assert_pipes_aligned(out.splitlines())


def test_rebalance_audit_table_aligned_on_triggered_scenario():
    """The README Scenario B — TRIGGERED rows are wider than OK rows."""
    cv = {"Equity": 15825.0, "Bonds": 4437.0, "Gold": 7263.0}
    total = sum(cv.values())
    bp = {"Equity": 105.50, "Bonds": 52.20, "Gold": 121.05}
    sp = {"Equity": 105.40, "Bonds": 52.10, "Gold": 120.95}
    out = capture(run_rebalance_audit, STRATEGY, cv, total, bp, sp)
    assert_pipes_aligned(out.splitlines())


def test_rebalance_audit_table_aligned_with_wide_values():
    """A €10M portfolio produces 9-digit values that stress the column width."""
    cv = {"Equity": 6_000_000.0, "Bonds": 2_500_000.0, "Gold": 1_500_000.0}
    total = sum(cv.values())
    bp = {"Equity": 100.0, "Bonds": 50.0, "Gold": 200.0}
    sp = {"Equity": 99.0,  "Bonds": 49.0, "Gold": 199.0}
    out = capture(run_rebalance_audit, STRATEGY, cv, total, bp, sp)
    lines = out.splitlines()
    pipe_lines = [line for line in lines if "|" in line]
    # When values overflow the column width, the cell grows wider than the
    # header. Alignment then requires every cell in that column to also
    # grow — the header's '<12' is a minimum, so the pipe shifts right
    # consistently. Just assert every pipe line agrees.
    first = pipe_columns(pipe_lines[0])
    for line in pipe_lines[1:]:
        assert pipe_columns(line) == first, f"misaligned with wide values:\n  {line!r}"


# ── Lump-sum table ─────────────────────────────────────────────────────

def test_lump_sum_table_aligned():
    cv = {"Equity": 15825.0, "Bonds": 4437.0, "Gold": 7263.0}
    total = sum(cv.values())
    bp = {"Equity": 105.50, "Bonds": 52.20, "Gold": 121.05}
    out = capture(run_lump_sum, STRATEGY, cv, total, 3000.0, bp)
    assert_pipes_aligned(out.splitlines())


def test_lump_sum_table_aligned_with_wide_cash_values():
    """A €1M lump sum produces 7-digit cash values that stress the column."""
    cv = {"Equity": 100_000.0, "Bonds": 50_000.0, "Gold": 30_000.0}
    total = sum(cv.values())
    bp = {"Equity": 100.0, "Bonds": 50.0, "Gold": 200.0}
    out = capture(run_lump_sum, STRATEGY, cv, total, 1_000_000.0, bp)
    lines = out.splitlines()
    pipe_lines = [line for line in lines if "|" in line]
    first = pipe_columns(pipe_lines[0])
    for line in pipe_lines[1:]:
        assert pipe_columns(line) == first, f"misaligned with wide cash:\n  {line!r}"


# ── Cash side-fund row aligns with asset rows ───────────────────────────
#
# gather_holdings and print_portfolio_summary both print a "Cash" row
# alongside the asset rows. The Cash label must pad to the same width as
# the asset labels (Equity / Bonds / Gold) so the trailing ':' lines up
# — previously the Cash rows hardcoded one extra space, shifting the
# whole line one column right of the asset rows.

STRATEGY_FULL = build_strategy({"Equity": 0.60, "Bonds": 0.25, "Gold": 0.15}, 0.20)
VEHICLES = {"Equity": "SPYY", "Bonds": "XGLE", "Gold": "EWG2"}


def _colon_columns(lines: list[str]) -> dict[str, int]:
    """Map asset label → column index of the ':' that follows it."""
    result = {}
    for line in lines:
        m = re.match(r"^\s+(\w+)\s*:", line)
        if m:
            label = m.group(1)
            result[label] = line.index(":")
    return result


def test_gather_holdings_cash_row_aligns_with_asset_rows():
    """The ':' after 'Cash' must be at the same column as after each asset."""
    preloaded: dict[str, object] = {"Equity": 455.0, "Bonds": 236.0, "Gold": 263.0}
    buf = io.StringIO()
    with redirect_stdout(buf):
        gather_holdings(STRATEGY_FULL, VEHICLES, preloaded, cash=205.19)
    cols = _colon_columns(buf.getvalue().splitlines())
    # All four rows must be present and agree on the ':' column.
    assert set(cols) == {"Equity", "Bonds", "Gold", "Cash"}
    columns = list(cols.values())
    assert all(c == columns[0] for c in columns), (
        f"misaligned ':' columns: {cols}"
    )


def test_print_portfolio_summary_cash_row_aligns_with_asset_rows():
    """The Cash row in the portfolio summary must align with the asset rows."""
    shares = {"Equity": 455.0, "Bonds": 236.0, "Gold": 263.0}
    prices = {"Equity": 280.90, "Bonds": 225.07, "Gold": 114.17}
    buf = io.StringIO()
    with redirect_stdout(buf):
        print_portfolio_summary(STRATEGY_FULL, shares, prices, cash=205.19)
    cols = _colon_columns(buf.getvalue().splitlines())
    assert set(cols) == {"Equity", "Bonds", "Gold", "Cash"}
    columns = list(cols.values())
    assert all(c == columns[0] for c in columns), (
        f"misaligned ':' columns: {cols}"
    )


def test_gather_holdings_cash_row_aligned_when_prompted(monkeypatch):
    """Alignment must also hold when cash is prompted (not from config)."""
    monkeypatch.setattr(main, "get_float_input", lambda prompt: 500.0)
    preloaded: dict[str, object] = {"Equity": 455.0, "Bonds": 236.0, "Gold": 263.0}
    buf = io.StringIO()
    with redirect_stdout(buf):
        gather_holdings(STRATEGY_FULL, VEHICLES, preloaded, cash=None)
    cols = _colon_columns(buf.getvalue().splitlines())
    # When prompted, the Cash row isn't printed by gather_holdings (the
    # prompt handles it). Only the three asset rows appear.
    assert set(cols) == {"Equity", "Bonds", "Gold"}
    columns = list(cols.values())
    assert all(c == columns[0] for c in columns), (
        f"misaligned ':' columns: {cols}"
    )