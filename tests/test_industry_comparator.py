#!/usr/bin/env python3
"""行业对比计算器单元测试"""

import json
import sys
import tempfile
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pandas as pd
import numpy as np

from industry_comparator import IndustryComparator


def test_detect_sector_from_profile():
    """测试从公司简介中检测行业"""
    comparator = IndustryComparator.__new__(IndustryComparator)

    # 直接返回行业字段（通过mapping映射为API板块名）
    assert comparator._detect_sector({"hy": "电子"}) == "1000SW1电子"
    assert comparator._detect_sector({"sshy": "计算机"}) == "1000SW1计算机"
    assert comparator._detect_sector({"行业": "医药生物"}) == "1000SW1医药生物"
    assert comparator._detect_sector({"所属行业": "汽车"}) == "1000SW1汽车"
    assert comparator._detect_sector({"industry": "Banking"}) == "Banking"

    # 空/无效输入
    assert comparator._detect_sector(None) is None
    assert comparator._detect_sector({}) is None
    assert comparator._detect_sector("invalid") is None

    # 空字符串字段
    assert comparator._detect_sector({"hy": ""}) is None

    print("[PASS] _detect_sector")


def test_detect_sector_with_mapping():
    """测试通过mapping文件查找板块名称"""
    comparator = IndustryComparator.__new__(IndustryComparator)

    # 通过keyword_to_sector映射查找
    sector = comparator._lookup_sector("电子元器件制造")
    assert sector == "1000SW1电子", f"Expected 1000SW1电子, got {sector}"

    sector = comparator._lookup_sector("新能源汽车零部件")
    assert sector == "1000SW1汽车", f"Expected 1000SW1汽车, got {sector}"

    sector = comparator._lookup_sector("MLCC被动元件")
    assert sector == "1000SW1电子", f"Expected 1000SW1电子, got {sector}"

    # 子串匹配
    sector = comparator._lookup_sector("半导体设备制造")
    assert sector == "1000SW1电子", f"Expected 1000SW1电子, got {sector}"

    # 无匹配
    sector = comparator._lookup_sector("完全未知的行业名称XYZ")
    assert sector is None

    print("[PASS] _detect_sector with mapping")


def test_extract_revenue_growth():
    comparator = IndustryComparator.__new__(IndustryComparator)

    # 8 quarters of growing revenue (list format, like API returns)
    data = [
        {"yysr": 100, "jzrq": "2023-03-31"},
        {"yysr": 110, "jzrq": "2023-06-30"},
        {"yysr": 120, "jzrq": "2023-09-30"},
        {"yysr": 130, "jzrq": "2023-12-31"},
        {"yysr": 150, "jzrq": "2024-03-31"},
    ]
    result = comparator._extract_revenue_growth(data)
    assert result["revenue_growth_pct"] == 50.0, f"Expected 50.0, got {result['revenue_growth_pct']}"

    # Dict format with "data" key
    dict_data = {"data": [
        {"yysr": 100, "jzrq": "2024-03-31"},
        {"yysr": 150, "jzrq": "2025-03-31"},
    ]}
    result = comparator._extract_revenue_growth(dict_data)
    assert result["revenue_growth_pct"] == 50.0

    # Empty data
    assert comparator._extract_revenue_growth([]) == {"revenue_growth_pct": None}
    assert comparator._extract_revenue_growth(pd.DataFrame()) == {"revenue_growth_pct": None}

    print("[PASS] _extract_revenue_growth")


def test_extract_cl_growth():
    comparator = IndustryComparator.__new__(IndustryComparator)

    # 5 quarters of CL growth (list format)
    data = [
        {"ysk": 200, "jzrq": "2023-03-31"},
        {"ysk": 220, "jzrq": "2023-06-30"},
        {"ysk": 240, "jzrq": "2023-09-30"},
        {"ysk": 260, "jzrq": "2023-12-31"},
        {"ysk": 300, "jzrq": "2024-03-31"},
    ]
    result = comparator._extract_cl_growth(data)
    assert result["cl_growth_pct"] == 50.0, f"Expected 50.0, got {result['cl_growth_pct']}"

    # No CL column
    assert comparator._extract_cl_growth([{"other": 1}, {"other": 2}]) == {"cl_growth_pct": None}

    print("[PASS] _extract_cl_growth")


def test_extract_metrics():
    comparator = IndustryComparator.__new__(IndustryComparator)

    quote = {"sz": 50000000000, "pe": 35.5}
    income = [
        {"yysr": 1000, "jzrq": "2024-03-31"},
        {"yysr": 1200, "jzrq": "2025-03-31"},
    ]
    balance = [
        {"ysk": 500, "jzrq": "2024-03-31"},
        {"ysk": 600, "jzrq": "2025-03-31"},
    ]

    metrics = comparator._extract_metrics(quote, income, balance)
    assert metrics["market_cap"] == 50000000000
    assert metrics["pe"] == 35.5
    assert metrics["revenue_growth_pct"] == 20.0
    assert metrics["cl_growth_pct"] == 20.0

    # Missing fields — only revenue_growth and cl_growth are always present
    metrics_empty = comparator._extract_metrics({}, [], [])
    assert metrics_empty["revenue_growth_pct"] is None
    assert metrics_empty["cl_growth_pct"] is None

    print("[PASS] _extract_metrics")


def test_calculate_rankings():
    comparator = IndustryComparator.__new__(IndustryComparator)

    peer_data = {
        "TARGET": {"revenue_growth_pct": 35.0, "cl_growth_pct": 40.0, "pe": 50.0},
        "PEER_A": {"revenue_growth_pct": 20.0, "cl_growth_pct": 25.0, "pe": 30.0},
        "PEER_B": {"revenue_growth_pct": 15.0, "cl_growth_pct": 10.0, "pe": 25.0},
        "PEER_C": {"revenue_growth_pct": 40.0, "cl_growth_pct": 35.0, "pe": 60.0},
    }
    rankings = comparator._calculate_rankings("TARGET", peer_data)

    # TARGET has 2nd highest revenue growth (after PEER_C at 40%)
    assert "revenue_growth_pct" in rankings
    assert rankings["revenue_growth_pct"]["target_value"] == 35.0
    assert rankings["revenue_growth_pct"]["rank"] == "2/4"

    # TARGET has highest CL growth
    assert rankings["cl_growth_pct"]["rank"] == "1/4"

    # PE ranking: 3rd lowest (PEER_B:25, PEER_A:30, TARGET:50, PEER_C:60)
    assert rankings["pe"]["rank"] == "3/4"

    print("[PASS] _calculate_rankings")


def test_calculate_composite():
    comparator = IndustryComparator.__new__(IndustryComparator)

    peer_data = {
        "TARGET": {"revenue_growth_pct": 35.0, "cl_growth_pct": 40.0},
        "PEER_A": {"revenue_growth_pct": 5.0, "cl_growth_pct": 8.0},
        "PEER_B": {"revenue_growth_pct": 15.0, "cl_growth_pct": 12.0},
    }
    result = comparator._calculate_composite("TARGET", peer_data)

    # Returns summary: {target_score, max_score, rank, percentile}
    assert result["target_score"] == 10.0, f"Expected 10.0, got {result['target_score']}"
    assert result["max_score"] == 10.0
    assert result["rank"] == "1/3"

    print("[PASS] _calculate_composite")


def test_select_peers():
    comparator = IndustryComparator.__new__(IndustryComparator)

    sector_stocks = [
        {"dm": "000001.SZ"},
        {"dm": "000002.SZ"},
        {"dm": "000003.SZ"},
        {"code": "000004.SZ"},
    ]
    peers = comparator._select_peers("000001.SZ", sector_stocks, {}, limit=30)
    assert len(peers) == 3
    assert "000001.SZ" not in peers
    assert "000002.SZ" in peers

    # String format elements
    string_stocks = ["000001.SZ", "000002.SZ", "000003.SZ"]
    peers2 = comparator._select_peers("000001.SZ", string_stocks, {}, limit=30)
    assert len(peers2) == 2

    print("[PASS] _select_peers")


if __name__ == "__main__":
    test_detect_sector_from_profile()
    test_detect_sector_with_mapping()
    test_extract_revenue_growth()
    test_extract_cl_growth()
    test_extract_metrics()
    test_calculate_rankings()
    test_calculate_composite()
    test_select_peers()
    print("\nAll tests passed!")
