#!/usr/bin/env python3
"""
成长股分析系统 - 行业对比计算器
针对目标公司所在行业，计算各项指标的同业排名和百分位。

用法:
  python industry_comparator.py --code 000001.SZ [--output result.json]
  python industry_comparator.py --code 000001.SZ --sector "1000SW1银行" [--output result.json]
"""

import json
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from data_fetcher import ZhituClient


class IndustryComparator:
    """行业对比分析器"""

    def __init__(self, client: ZhituClient = None,
                 max_workers: int = 5):
        self.client = client or ZhituClient()
        self.max_workers = max_workers

    def analyze(self, code: str, sector_name: str = None,
                peer_limit: int = 30) -> dict:
        """
        行业对比分析

        Args:
            code: 目标股票代码
            sector_name: 行业板块名称（如 "1000SW1电力设备"），不指定则自动识别
            peer_limit: 最多对比的同业公司数量
        """
        result = {
            "code": code,
            "analysis_date": datetime.now().strftime("%Y-%m-%d"),
            "sector": sector_name or "auto",
            "peer_count": 0,
            "rankings": {},
            "composite_score": {},
            "peer_details": [],
            "assessment": "",
        }

        # 获取目标公司数据
        target_profile = self.client.get_company_profile(code)
        target_quote = self.client.get_realtime_quote(code)
        target_income = self.client.get_income_statement(code)
        target_balance = self.client.get_balance_sheet(code)

        # 自动识别行业
        if not sector_name:
            sector_name = self._detect_sector(target_profile)
            result["sector"] = sector_name or "未知行业"

        if not sector_name:
            result["assessment"] = "无法识别行业，无法进行同业对比"
            return result

        # 获取行业成分股
        try:
            sector_stocks = self.client.get_sector_stocks(sector_name)
        except Exception:
            result["assessment"] = f"无法获取'{sector_name}'行业的成分股"
            return result

        if not sector_stocks or len(sector_stocks) < 2:
            result["assessment"] = f"行业'{sector_name}'成分股数量不足"
            return result

        # 限制对比数量，优先市值相近的
        peers = self._select_peers(code, sector_stocks, target_quote, peer_limit)
        result["peer_count"] = len(peers)

        # 获取同业数据
        peer_data = self._fetch_peer_data(peers)
        peer_data[code] = self._extract_metrics(
            target_quote, target_income, target_balance
        )

        # 计算排名
        result["rankings"] = self._calculate_rankings(code, peer_data)
        result["composite_score"] = self._calculate_composite(code, peer_data)
        result["peer_details"] = self._build_peer_table(peer_data)

        # 生成判断
        result["assessment"] = self._generate_assessment(result)

        return result

    def _detect_sector(self, profile: dict) -> Optional[str]:
        """从公司简介中自动检测行业"""
        if not isinstance(profile, dict):
            return None
        # 智兔API可能的行业字段（按优先级）
        for key in ["hy", "sshy", "行业", "所属行业", "industry", "sw_hy", "申万行业"]:
            if key in profile and profile[key]:
                sector = str(profile[key]).strip()
                if sector:
                    # 尝试通过mapping文件查找匹配
                    mapped = self._lookup_sector(sector)
                    return mapped if mapped else sector

        # 遍历所有字段值，尝试模糊匹配
        for key, value in profile.items():
            if isinstance(value, str) and value.strip():
                mapped = self._lookup_sector(value.strip())
                if mapped:
                    return mapped

        return None

    def _lookup_sector(self, keyword: str) -> Optional[str]:
        """通过行业映射表查找智兔API板块名称"""
        mapping_path = Path(__file__).parent.parent / "config" / "industry_mapping.json"
        if not mapping_path.exists():
            return None

        try:
            with open(mapping_path) as f:
                mapping = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        keyword_to_sector = mapping.get("keyword_to_sector", {})
        # 按关键字长度降序匹配，避免短关键字误匹配（如"新能源"误匹配"新能源汽车"）
        for kw, sector in sorted(keyword_to_sector.items(), key=lambda x: -len(x[0])):
            if kw in keyword or keyword in kw:
                return sector
        return None

    def _select_peers(self, target_code: str, sector_stocks: list,
                      target_quote: dict, limit: int) -> list[str]:
        """选择可比同业公司"""
        codes = []
        for item in sector_stocks:
            if isinstance(item, dict):
                c = item.get("dm", item.get("code", ""))
            else:
                c = str(item)
            if c and c != target_code:
                codes.append(c)

        if len(codes) <= limit:
            return codes

        # 按市值相近度排序选择
        target_mcap = self._safe_float(target_quote.get("总市值") or target_quote)
        if target_mcap:
            return codes[:limit]  # 简化：取前N只
        return codes[:limit]

    def _fetch_peer_data(self, codes: list[str]) -> dict:
        """并行获取同业公司的核心数据"""
        results = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for c in codes:
                futures[executor.submit(self._fetch_single_peer, c)] = c

            for future in as_completed(futures):
                code = futures[future]
                try:
                    results[code] = future.result()
                except Exception as e:
                    results[code] = {"error": str(e)}

        return results

    def _fetch_single_peer(self, code: str) -> dict:
        """获取单只同业公司的精简数据"""
        try:
            quote = self.client.get_realtime_quote(code)
            income = self.client.get_income_statement(code)
            balance = self.client.get_balance_sheet(code)
            return self._extract_metrics(quote, income, balance)
        except Exception:
            return {}

    def _extract_metrics(self, quote: dict, income: any,
                         balance: any) -> dict:
        """从原始数据中提取关键对比指标"""
        metrics = {}

        # Market cap (API returns 'sz' for 总市值)
        for key in ["sz", "总市值", "zsz", "market_cap", "total_mv"]:
            if isinstance(quote, dict) and key in quote:
                try:
                    metrics["market_cap"] = float(quote[key])
                    break
                except (ValueError, TypeError):
                    pass

        # PE
        for key in ["pe", "市盈率", "PE", "pe_ttm"]:
            if isinstance(quote, dict) and key in quote:
                try:
                    metrics["pe"] = float(quote[key])
                    break
                except (ValueError, TypeError):
                    pass

        # 收入增长率
        metrics.update(self._extract_revenue_growth(income))

        # 合同负债增速
        metrics.update(self._extract_cl_growth(balance))

        return metrics

    def _extract_revenue_growth(self, income: any) -> dict:
        """Extract revenue YoY growth rate."""
        result = {"revenue_growth_pct": None}
        if isinstance(income, list):
            df = pd.DataFrame(income)
        elif isinstance(income, dict):
            df = pd.DataFrame(income.get("data", [income]))
        else:
            return result

        if df.empty:
            return result

        rev_col = None
        for col in ["yysr", "营业收入", "营业总收入", "revenue"]:
            if col in df.columns:
                rev_col = col
                break

        if rev_col is None:
            return result

        date_col = None
        for col in ["jzrq", "报告日期", "截止日期", "日期", "report_date"]:
            if col in df.columns:
                date_col = col
                break

        df[rev_col] = pd.to_numeric(df[rev_col], errors="coerce")
        df = df.dropna(subset=[rev_col])

        if date_col and date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
            df = df.dropna(subset=[date_col])
            df = df.sort_values(date_col).drop_duplicates(subset=[date_col], keep="last")
            rev = df[rev_col]
        else:
            rev = df[rev_col]

        if len(rev) < 2:
            return result

        # YoY: 4-period gap for quarterly data, 1-period for annual
        if len(rev) >= 5:
            result["revenue_growth_pct"] = round(
                float(rev.iloc[-1] / rev.iloc[-5] - 1) * 100, 1
            )
        else:
            result["revenue_growth_pct"] = round(
                float(rev.iloc[-1] / rev.iloc[-2] - 1) * 100, 1
            )

        return result

    def _extract_cl_growth(self, balance: any) -> dict:
        """Extract contract liability YoY growth rate."""
        result = {"cl_growth_pct": None}
        if isinstance(balance, list):
            df = pd.DataFrame(balance)
        elif isinstance(balance, dict):
            df = pd.DataFrame(balance.get("data", [balance]))
        else:
            return result

        if df.empty:
            return result

        cl_col = None
        for col in ["htfz", "ysk", "合同负债", "预收款项", "contract_liability", "advance_receipts"]:
            if col in df.columns:
                cl_col = col
                break

        if cl_col is None:
            return result

        date_col = None
        for col in ["jzrq", "报告日期", "截止日期", "日期", "report_date"]:
            if col in df.columns:
                date_col = col
                break

        df[cl_col] = pd.to_numeric(df[cl_col], errors="coerce")
        df = df.dropna(subset=[cl_col])

        if date_col and date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
            df = df.dropna(subset=[date_col])
            df = df.sort_values(date_col).drop_duplicates(subset=[date_col], keep="last")
            cl = df[cl_col]
        else:
            cl = df[cl_col]

        if len(cl) < 2:
            return result

        if len(cl) >= 5:
            result["cl_growth_pct"] = round(
                float(cl.iloc[-1] / cl.iloc[-5] - 1) * 100, 1
            )
        else:
            result["cl_growth_pct"] = round(
                float(cl.iloc[-1] / cl.iloc[-2] - 1) * 100, 1
            )

        return result

    def _calculate_rankings(self, target_code: str,
                            peer_data: dict) -> dict:
        """计算目标公司在行业中的各项排名"""
        rankings = {}

        for metric in ["revenue_growth_pct", "cl_growth_pct"]:
            values = {}
            for code, data in peer_data.items():
                val = data.get(metric)
                if val is not None:
                    values[code] = val

            if target_code in values and len(values) > 1:
                sorted_vals = sorted(values.items(), key=lambda x: x[1], reverse=True)
                rank = next(i + 1 for i, (c, _) in enumerate(sorted_vals) if c == target_code)
                percentile = (len(values) - rank) / len(values) * 100
                rankings[metric] = {
                    "rank": f"{rank}/{len(values)}",
                    "percentile": round(percentile, 1),
                    "industry_median": round(float(np.median(list(values.values()))), 2),
                    "target_value": round(values[target_code], 2),
                }

        # PE排名（越低越好）
        values = {}
        for code, data in peer_data.items():
            val = data.get("pe")
            if val is not None and val > 0 and val < 1000:
                values[code] = val

        if target_code in values and len(values) > 1:
            sorted_vals = sorted(values.items(), key=lambda x: x[1])
            rank = next(i + 1 for i, (c, _) in enumerate(sorted_vals) if c == target_code)
            percentile = rank / len(values) * 100  # PE低=好
            rankings["pe"] = {
                "rank": f"{rank}/{len(values)}",
                "percentile": round(percentile, 1),
                "industry_median": round(float(np.median(list(values.values()))), 2),
                "target_value": round(values[target_code], 2),
            }

        return rankings

    def _calculate_composite(self, target_code: str,
                             peer_data: dict) -> dict:
        """计算综合成长性得分"""
        scores = {}

        for code, data in peer_data.items():
            score = 0
            count = 0

            # 收入增长分
            rg = data.get("revenue_growth_pct")
            if rg is not None:
                count += 1
                if rg > 30:
                    score += 10
                elif rg > 20:
                    score += 7
                elif rg > 10:
                    score += 5
                elif rg > 0:
                    score += 3
                else:
                    score += 1

            # 合同负债增长分
            cl = data.get("cl_growth_pct")
            if cl is not None:
                count += 1
                if cl > 30:
                    score += 10
                elif cl > 20:
                    score += 7
                elif cl > 10:
                    score += 5
                elif cl > 0:
                    score += 3
                else:
                    score += 1

            if count > 0:
                scores[code] = score / count
            else:
                scores[code] = 0

        # 排名
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        target_score = scores.get(target_code, 0)
        if target_score > 0 and len(sorted_scores) > 1:
            rank = next(i + 1 for i, (c, _) in enumerate(sorted_scores) if c == target_code)
        else:
            rank = len(sorted_scores)

        return {
            "target_score": round(target_score, 1),
            "max_score": round(sorted_scores[0][1], 1) if sorted_scores else 0,
            "rank": f"{rank}/{len(sorted_scores)}",
            "percentile": round((len(sorted_scores) - rank) / len(sorted_scores) * 100, 1) if len(sorted_scores) > 1 else 0,
        }

    def _build_peer_table(self, peer_data: dict) -> list[dict]:
        """构建同业对比表（Top 10）"""
        table = []
        for code, data in peer_data.items():
            table.append({
                "code": code,
                "market_cap_billion": round(data.get("market_cap", 0) / 1e8, 1) if data.get("market_cap") else None,
                "pe": data.get("pe"),
                "revenue_growth_pct": data.get("revenue_growth_pct"),
                "cl_growth_pct": data.get("cl_growth_pct"),
            })

        # 按市值降序
        table.sort(key=lambda x: x.get("market_cap_billion") or 0, reverse=True)
        return table[:10]

    def _generate_assessment(self, result: dict) -> str:
        """生成行业对比判断"""
        composite = result.get("composite_score", {})
        rankings = result.get("rankings", {})
        peer_count = result.get("peer_count", 0)

        if peer_count < 2:
            return "可比公司数量不足，行业对比参考有限"

        percentile = composite.get("percentile", 0)

        parts = []
        if percentile >= 80:
            parts.append(f"综合成长性位于行业前{100 - percentile:.0f}%，处于领先地位")
        elif percentile >= 50:
            parts.append(f"综合成长性位于行业中上水平（前{100 - percentile:.0f}%）")
        elif percentile >= 20:
            parts.append(f"综合成长性处于行业中下水平")
        else:
            parts.append("综合成长性落后于行业大多数公司")

        # 收入增长排名
        rg_rank = rankings.get("revenue_growth_pct", {})
        if rg_rank:
            parts.append(f"收入增速排名{rg_rank['rank']}，行业中位数{rg_rank['industry_median']}%")

        return "；".join(parts)

    def _safe_float(self, val) -> Optional[float]:
        try:
            return float(val)
        except (ValueError, TypeError):
            return None


def main():
    parser = argparse.ArgumentParser(description="行业对比计算器")
    parser.add_argument("--code", type=str, required=True, help="股票代码，如 000001.SZ")
    parser.add_argument("--sector", type=str, help="行业板块名称（可选，自动识别）")
    parser.add_argument("--output", type=str, help="输出文件路径")
    args = parser.parse_args()

    comparator = IndustryComparator()
    result = comparator.analyze(args.code, args.sector)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"结果已保存到 {args.output}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
