#!/usr/bin/env python3
"""财务指标计算器的单元测试"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

# 测试数据验证逻辑（不实际调用API）
import pandas as pd
import numpy as np

from financial_metrics_calculator import (
    safe_growth_rate,
    safe_qoq_rate,
    trend_direction,
    _parse_api_table,
    BALANCE_SHEET_MAP,
    INCOME_STATEMENT_MAP,
)


def test_safe_growth_rate():
    series = pd.Series([100, 110, 120, 130, 150])
    rate = safe_growth_rate(series, periods=4)
    assert rate == 50.0, f"Expected 50%, got {rate}"

    # 不足periods
    short = pd.Series([100, 110])
    assert safe_growth_rate(short, 4) is None

    print("[PASS] safe_growth_rate")


def test_trend_direction():
    # 加速增长
    accel = pd.Series([100, 105, 112, 122, 140])
    assert trend_direction(accel) == "accelerating"

    # 减速增长
    decel = pd.Series([100, 120, 135, 143, 145])
    assert trend_direction(decel) == "decelerating"

    # 下降
    down = pd.Series([100, 95, 90, 85, 80])
    assert trend_direction(down) == "declining"

    print("[PASS] trend_direction")


def test_parse_api_table():
    # 使用智兔API实际返回的拼音缩写字段名
    data = [
        {"jzrq": "2024-12-31", "ysk": 1000, "gdzc": 5000},
        {"jzrq": "2024-09-30", "ysk": 800, "gdzc": 4000},
    ]
    df = _parse_api_table(data, BALANCE_SHEET_MAP)
    assert "advance_receipts" in df.columns
    assert "fixed_assets" in df.columns
    assert len(df) == 2
    # sorted by report_date ascending
    assert df.iloc[0]["advance_receipts"] == 800

    print("[PASS] _parse_api_table")


if __name__ == "__main__":
    test_safe_growth_rate()
    test_trend_direction()
    test_parse_api_table()
    print("\nAll tests passed!")
