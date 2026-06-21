#!/usr/bin/env python3
"""估值分析器单元测试"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pandas as pd
import numpy as np

from valuation_analyzer import ValuationAnalyzer


def test_find_column():
    analyzer = ValuationAnalyzer.__new__(ValuationAnalyzer)
    df = pd.DataFrame({"pe": [10, 20], "date": ["2024-01-01", "2024-06-01"]})

    assert analyzer._find_column(df, ["pe", "市盈率"]) == "pe"
    assert analyzer._find_column(df, ["pb", "市净率"]) is None
    assert analyzer._find_column(df, ["date", "日期"]) == "date"

    print("[PASS] _find_column")


def test_safe_float():
    analyzer = ValuationAnalyzer.__new__(ValuationAnalyzer)

    assert analyzer._safe_float({"pe": 35.5}, ["pe"]) == 35.5
    assert analyzer._safe_float({"sjl": "6.8"}, ["sjl"]) == 6.8
    assert analyzer._safe_float({"sz": None}, ["sz"]) is None
    assert analyzer._safe_float({}, ["pe"]) is None
    assert analyzer._safe_float(None, ["pe"]) is None
    assert analyzer._safe_float({"pe": 35.5}, ["pb", "sjl"]) is None

    print("[PASS] _safe_float")


def test_extract_current():
    analyzer = ValuationAnalyzer.__new__(ValuationAnalyzer)

    df = pd.DataFrame({
        "pe": [10, 15, 20, 18, 25],
        "date": pd.date_range("2024-01-01", periods=5, freq="QE"),
    })
    val = analyzer._extract_current(df, "pe")
    assert val == 25.0, f"Expected 25.0, got {val}"

    # Missing column
    assert analyzer._extract_current(df, "pb") is None

    print("[PASS] _extract_current")


def test_calc_percentile():
    analyzer = ValuationAnalyzer.__new__(ValuationAnalyzer)

    df = pd.DataFrame({
        "pe": list(range(10, 60)),
        "date": pd.date_range("2020-01-01", periods=50, freq="QE"),
    })
    result = analyzer._calc_percentile(df, "pe", years=5)
    assert result["current_percentile"] is not None
    assert result["current_percentile"] >= 90  # 当前值最大
    assert "min" in result and "max" in result and "median" in result

    # Short data
    short = analyzer._calc_percentile(df.head(5), "pe")
    assert short["current_percentile"] is None

    print("[PASS] _calc_percentile")


def test_calc_revenue_growth():
    analyzer = ValuationAnalyzer.__new__(ValuationAnalyzer)

    # 8 quarters of growing revenue
    rev = [100, 105, 110, 115, 120, 130, 140, 150]
    df = pd.DataFrame({
        "yysr": rev,
        "jzrq": pd.date_range("2023-01-01", periods=8, freq="QE"),
    })
    result = analyzer._calc_revenue_growth(df)
    assert result["latest_yoy_pct"] is not None
    # YoY: 150/115 - 1 = 30.4% (iloc[-1] vs iloc[-5])
    assert result["latest_yoy_pct"] == 30.4, f"Expected 30.4, got {result['latest_yoy_pct']}"

    # Few data points
    short_df = pd.DataFrame({"yysr": [100, 110], "jzrq": pd.to_datetime(["2024-01-01", "2024-04-01"])})
    short_result = analyzer._calc_revenue_growth(short_df)
    assert short_result["latest_yoy_pct"] == 10.0

    # No revenue column
    empty_df = pd.DataFrame({"other": [1, 2, 3]})
    empty_result = analyzer._calc_revenue_growth(empty_df)
    assert empty_result["latest_yoy_pct"] is None

    print("[PASS] _calc_revenue_growth")


def test_classify_valuation_type():
    analyzer = ValuationAnalyzer.__new__(ValuationAnalyzer)

    # Explosive growth (>30%)
    assert "爆发成长" in analyzer._classify_valuation_type(
        50, {"latest_yoy_pct": 35.0, "trend": "accelerating"}, pd.DataFrame(), None
    )

    # Steady growth (<15%)
    assert "平稳增长" in analyzer._classify_valuation_type(
        20, {"latest_yoy_pct": 10.0, "trend": "stable"}, pd.DataFrame(), None
    )

    # Declining
    assert "衰退" in analyzer._classify_valuation_type(
        5, {"latest_yoy_pct": -15.0, "trend": "declining"}, pd.DataFrame(), None
    )

    # Moderate growth with accelerating trend → explosive
    assert "爆发成长" in analyzer._classify_valuation_type(
        30, {"latest_yoy_pct": 25.0, "trend": "accelerating"}, pd.DataFrame(), None
    )

    # No data
    assert "无法判定" in analyzer._classify_valuation_type(
        None, {"latest_yoy_pct": None}, pd.DataFrame(), None
    )

    print("[PASS] _classify_valuation_type")


def test_safe_float_edge_cases():
    analyzer = ValuationAnalyzer.__new__(ValuationAnalyzer)

    # Non-numeric string
    assert analyzer._safe_float({"pe": "N/A"}, ["pe"]) is None
    # Zero
    assert analyzer._safe_float({"pe": 0}, ["pe"]) == 0.0
    # Negative value
    assert analyzer._safe_float({"pe": -5.2}, ["pe"]) == -5.2
    # Multi-key fallback
    assert analyzer._safe_float({"pb": 3.5}, ["pe", "pb"]) == 3.5

    print("[PASS] _safe_float edge cases")


if __name__ == "__main__":
    test_find_column()
    test_safe_float()
    test_extract_current()
    test_calc_percentile()
    test_calc_revenue_growth()
    test_classify_valuation_type()
    test_safe_float_edge_cases()
    print("\nAll tests passed!")
