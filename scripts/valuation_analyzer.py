#!/usr/bin/env python3
"""
成长股分析系统 - 估值分析器
计算PE/PB/PS/PEG的历史分位和估值类型判定。

用法:
  python valuation_analyzer.py --code 000001.SZ [--output result.json]
"""

import json
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from data_fetcher import ZhituClient


class ValuationAnalyzer:
    """估值分析器"""

    def __init__(self, client: ZhituClient = None):
        self.client = client or ZhituClient()

    def analyze(self, code: str) -> dict:
        """
        对单只股票进行估值分析

        Returns:
            包含估值类型、历史分位、同业对比的结构化结果
        """
        # 获取数据
        indicators = self.client.get_indicators(code)
        quote = self.client.get_realtime_quote(code)
        income = self.client.get_income_statement(code)
        profile = self.client.get_company_profile(code)

        # 解析
        df_indicators = pd.DataFrame(indicators) if isinstance(indicators, list) else pd.DataFrame()
        if isinstance(income, list):
            df_income = pd.DataFrame(income)
        elif isinstance(income, dict):
            df_income = pd.DataFrame(income.get("data", income.get("items", [income])))
        else:
            df_income = pd.DataFrame()

        # 字段名映射
        for col in list(df_indicators.columns):
            if col in ["日期", "date", "trade_date"]:
                df_indicators.rename(columns={col: "date"}, inplace=True)

        if "date" in df_indicators.columns:
            df_indicators["date"] = pd.to_datetime(df_indicators["date"], errors="coerce")
            df_indicators = df_indicators.sort_values("date")

        # PE/PB字段名识别（优先智兔API的拼音缩写，其次中文全称）
        pe_col = self._find_column(df_indicators, ["pe", "市盈率", "PE", "pe_ttm", "pe_ratio", "syl"])
        pb_col = self._find_column(df_indicators, ["pb", "市净率", "PB", "pb_ratio", "sjl"])
        ps_col = self._find_column(df_indicators, ["ps", "市销率", "PS", "ps_ratio", "sxl"])

        result = {
            "code": code,
            "analysis_date": datetime.now().strftime("%Y-%m-%d"),
            "current_valuation": {},
            "historical_percentile": {},
            "valuation_type": "",
            "peg_analysis": {},
            "assessment": "",
        }

        # 实时行情中提取当前估值和市值
        # 智兔API字段: pe=市盈率, sjl=市净率(市净率), sz=总市值
        current_pe = self._safe_float(quote, ["pe"])
        current_pb = self._safe_float(quote, ["sjl"])
        current_ps = None  # PS需要自行计算
        market_cap = self._safe_float(quote, ["sz"])  # 总市值

        result["current_valuation"] = {
            "pe": current_pe,
            "pb": current_pb,
            "ps": current_ps,
            "market_cap_billion": round(market_cap / 1e8, 2) if market_cap else None,
        }

        # ── 历史PE分位（通过历史价格 + 财务数据推算） ────
        # 注意：智兔API的 /hs/indicators 返回的是技术指标(量比/涨跌幅)，
        # 不是估值指标。历史PE分位需要从历史价格和盈利数据推算。
        # 这里使用简化的方法：从历史行情和最近PE推算大概的历史PE范围
        try:
            history = self.client.get_history(code, "d", "f", limit=5)
        except Exception:
            history = []

        result["historical_percentile"] = {
            "pe": self._calc_pe_percentile_from_price(
                code, current_pe, market_cap
            ),
            "pb": {"current_percentile": None, "note": "历史PB分位不可直接获取"},
            "ps": {"current_percentile": None, "note": "历史PS分位不可直接获取"},
        }

        # ── 收入增长 → PEG ───────────────────────────
        revenue_growth = self._calc_revenue_growth(df_income)
        result["revenue_growth_analysis"] = revenue_growth

        # PEG = PE / 增长率
        if current_pe and revenue_growth.get("latest_yoy_pct"):
            growth_rate = revenue_growth["latest_yoy_pct"]
            if growth_rate > 0:
                peg = current_pe / growth_rate
                result["peg_analysis"] = {
                    "peg": round(peg, 2),
                    "assessment": (
                        "PEG<1，估值相对增长偏低" if peg < 1
                        else "PEG合理" if peg < 1.5
                        else "PEG偏高，增长需加速才能消化估值"
                    )
                }

        # ── 估值类型判定 ──────────────────────────────
        result["valuation_type"] = self._classify_valuation_type(
            current_pe, revenue_growth, df_indicators, pe_col
        )
        result["assessment"] = self._generate_assessment(result)

        return result

    def _find_column(self, df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
        for c in candidates:
            if c in df.columns:
                return c
        return None

    def _extract_current(self, df: pd.DataFrame, col: Optional[str],
                         date_col: str = "date") -> Optional[float]:
        if col is None or col not in df.columns:
            return None
        valid = df.dropna(subset=[col])
        if valid.empty:
            return None
        if date_col in valid.columns:
            valid = valid.sort_values(date_col)
        return float(valid[col].iloc[-1])

    def _calc_pe_percentile_from_price(self, code: str, current_pe: Optional[float],
                                         market_cap: Optional[float]) -> dict:
        """通过历史价格走势估算PE大概分位范围（简化方法）"""
        if current_pe is None:
            return {"current_percentile": None, "note": "缺少当前PE数据"}

        try:
            # 获取近3年历史价格，估算价格波动范围
            three_years_ago = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y%m%d")
            history = self.client.get_history(code, "d", "f", start=three_years_ago)
        except Exception:
            history = []

        if not isinstance(history, list) or len(history) < 100:
            return {
                "current_percentile": None,
                "note": "历史数据不足",
                "current_pe": current_pe,
            }

        df = pd.DataFrame(history)
        if "c" not in df.columns:
            return {"current_percentile": None, "note": "缺少收盘价数据"}

        # 通过价格范围估算PE范围
        prices = pd.to_numeric(df["c"], errors="coerce").dropna()
        current_price = prices.iloc[-1] if len(prices) > 0 else None
        if current_price is None:
            return {"current_percentile": None, "note": "无法获取当前价格"}

        # 假设EPS稳定，PE变化主要来自价格波动
        # 估算历史PE = current_pe * (historical_price / current_price)
        estimated_pe_series = current_pe * prices / current_price
        pe_percentile = (estimated_pe_series <= current_pe).mean() * 100

        return {
            "current_percentile": round(float(pe_percentile), 1),
            "estimated_pe_3yr_min": round(float(estimated_pe_series.min()), 1),
            "estimated_pe_3yr_max": round(float(estimated_pe_series.max()), 1),
            "estimated_pe_3yr_median": round(float(estimated_pe_series.median()), 1),
            "data_points": len(prices),
            "note": "基于近3年价格变动和当前EPS估算的PE分位",
            "interpretation": (
                "极度低估" if pe_percentile < 10
                else "相对低估" if pe_percentile < 25
                else "估值适中" if pe_percentile < 75
                else "相对高估" if pe_percentile < 90
                else "极度高估"
            )
        }

    def _calc_percentile(self, df: pd.DataFrame, col: Optional[str],
                         years: int = 5) -> dict:
        """计算当前值在历史中的分位数"""
        if col is None or col not in df.columns:
            return {"current_percentile": None, "data_years": 0}

        valid = df.dropna(subset=[col]).copy()
        if "date" in valid.columns:
            cutoff = datetime.now() - timedelta(days=years * 365)
            valid = valid[valid["date"] >= cutoff]

        if valid.empty or len(valid) < 10:
            return {"current_percentile": None, "data_points": len(valid)}

        current = valid[col].iloc[-1]
        percentile = (valid[col] <= current).mean() * 100

        return {
            "current_percentile": round(float(percentile), 1),
            "min": round(float(valid[col].min()), 2),
            "max": round(float(valid[col].max()), 2),
            "median": round(float(valid[col].median()), 2),
            "data_points": len(valid),
            "interpretation": (
                "极度低估" if percentile < 10
                else "相对低估" if percentile < 25
                else "估值适中" if percentile < 75
                else "相对高估" if percentile < 90
                else "极度高估"
            )
        }

    def _calc_revenue_growth(self, df_income: pd.DataFrame) -> dict:
        """Calculate revenue YoY growth rate from income statement data."""
        result = {"latest_yoy_pct": None, "trend": "insufficient_data"}

        rev_col = self._find_column(
            df_income,
            ["yysr", "营业收入", "营业总收入", "revenue"]
        )
        if rev_col is None:
            return result

        df = df_income.copy()
        date_col = self._find_column(df, ["jzrq", "报告日期", "截止日期", "日期", "report_date"])
        if date_col:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

        df[rev_col] = pd.to_numeric(df[rev_col], errors="coerce")
        df = df.dropna(subset=[rev_col])

        if date_col:
            df = df.dropna(subset=[date_col])
            # Deduplicate: keep last record per date
            df = df.sort_values(date_col).drop_duplicates(subset=[date_col], keep="last")
            df = df.set_index(date_col)
            rev = df[rev_col].sort_index()
        else:
            rev = df[rev_col]

        if len(rev) < 2:
            return result

        # YoY growth: compare with 4 quarters ago for quarterly data
        if len(rev) >= 5:
            yoy = float((rev.iloc[-1] / rev.iloc[-5] - 1) * 100)
        else:
            yoy = float((rev.iloc[-1] / rev.iloc[-2] - 1) * 100)

        result["latest_yoy_pct"] = round(yoy, 1)

        # Trend: compare recent YoY vs older YoY using 4-period gaps
        if len(rev) >= 9:
            recent_growth = (rev.iloc[-1] / rev.iloc[-5] - 1) * 100
            older_growth = (rev.iloc[-5] / rev.iloc[-9] - 1) * 100
            if recent_growth > older_growth + 5:
                result["trend"] = "accelerating"
            elif recent_growth < older_growth - 5:
                result["trend"] = "decelerating"
            else:
                result["trend"] = "stable"
        elif len(rev) >= 5:
            recent_growth = (rev.iloc[-1] / rev.iloc[-5] - 1) * 100
            older_growth = (rev.iloc[-3] / rev.iloc[-5] - 1) * 100 if len(rev) >= 6 else None
            if older_growth is not None:
                if recent_growth > older_growth + 5:
                    result["trend"] = "accelerating"
                elif recent_growth < older_growth - 5:
                    result["trend"] = "decelerating"
                else:
                    result["trend"] = "stable"

        return result

    def _classify_valuation_type(self, pe: Optional[float],
                                 revenue_growth: dict,
                                 df_indicators: pd.DataFrame,
                                 pe_col: Optional[str]) -> str:
        """判定估值类型：平稳增长型 / 爆发成长型 / 衰退型 / 周期型"""
        growth = revenue_growth.get("latest_yoy_pct")
        trend = revenue_growth.get("trend", "")

        if growth is None:
            return "数据不足，无法判定"

        if growth < -10:
            return "衰退型（收入大幅下滑，低估值可能为价值陷阱）"
        elif growth < 0:
            return "衰退型（收入下滑）"
        elif growth < 15:
            return "平稳增长型（估值匹配度至关重要）"
        elif growth < 30:
            if trend == "accelerating":
                return "爆发成长型（增速加快，估值非首要矛盾）"
            return "平稳增长型偏成长（关注增速能否加速）"
        else:
            return "爆发成长型（高增长可消化高估值，核心看逻辑是否持续）"

    def _generate_assessment(self, result: dict) -> str:
        """生成估值综合判断"""
        val_type = result.get("valuation_type", "")
        pe_pct = result.get("historical_percentile", {}).get("pe", {}).get("current_percentile")
        peg_data = result.get("peg_analysis", {})

        if "衰退" in val_type:
            return "公司处于衰退期，当前估值参考意义有限，重点判断业绩拐点"

        if "爆发成长" in val_type:
            if peg_data.get("peg", 999) < 1:
                return "爆发成长+低PEG：估值相对增长偏低，若成长逻辑成立则估值有扩张空间"
            else:
                return "爆发成长+偏高PEG：市场已给予成长溢价，核心跟踪成长逻辑是否持续兑现"

        if "平稳增长" in val_type:
            if pe_pct is not None and pe_pct < 25:
                return "平稳增长+估值偏低：安全边际较好，但成长弹性有限"
            elif pe_pct is not None and pe_pct > 75:
                return "平稳增长+估值偏高：风险收益比不佳，等待更好买点"
            else:
                return "平稳增长+估值适中：符合基本面，但缺乏超额收益弹性"

        return "估值与成长匹配度一般，需更多数据判断"

    def _safe_float(self, data: dict, keys: list[str]) -> Optional[float]:
        """安全提取float值"""
        if not isinstance(data, dict):
            return None
        for k in keys:
            if k in data:
                try:
                    return float(data[k])
                except (ValueError, TypeError):
                    continue
        return None


def main():
    parser = argparse.ArgumentParser(description="估值分析器")
    parser.add_argument("--code", type=str, required=True, help="股票代码，如 000001.SZ")
    parser.add_argument("--output", type=str, help="输出文件路径")
    args = parser.parse_args()

    analyzer = ValuationAnalyzer()
    result = analyzer.analyze(args.code)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"结果已保存到 {args.output}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
