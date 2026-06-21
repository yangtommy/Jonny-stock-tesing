#!/usr/bin/env python3
"""
成长股分析系统 - 财务指标计算器
从智兔API获取原始财务数据，计算成长股核心指标。

用法:
  python financial_metrics_calculator.py --code 000001.SZ [--output result.json]
  python financial_metrics_calculator.py --input batch_codes.json --output batch_results.json
"""

import json
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from collections import defaultdict

import pandas as pd
import numpy as np

# 添加父目录到sys.path以便导入data_fetcher
sys.path.insert(0, str(Path(__file__).parent))
from data_fetcher import ZhituClient

# ── 字段名映射（智兔API拼音缩写 → 英文key） ─────────

BALANCE_SHEET_MAP = {
    "htfz": "contract_liability",      # 合同负债（新准则）
    "ysk": "advance_receipts",        # 预收款（旧准则，近似合同负债）
    "zjgc": "construction_in_progress",  # 在建工程
    "gdzc": "fixed_assets",           # 固定资产
    "zczj": "total_assets",           # 资产总计
    "fzhj": "total_liabilities",      # 负债合计
    "syzqyhj": "total_equity",        # 所有者权益合计
    "ch": "inventory",               # 存货
    "yszk": "accounts_receivable",    # 应收账款
    "yfzk": "accounts_payable",       # 应付账款
    "hbzj": "cash_equivalents",       # 货币资金
    "cqfz": "long_term_debt",         # 长期负债
    "wxzc": "intangible_assets",      # 无形资产
    "sszb": "paid_in_capital",        # 实收资本
    "zbgj": "capital_reserve",        # 资本公积
    "ylgj": "surplus_reserve",        # 盈余公积
    "wfplr": "undistributed_profit",  # 未分配利润
    "ldzchj": "total_current_assets", # 流动资产合计
    "ldfzhj": "total_current_liabilities",  # 流动负债合计
    "fldzchj": "total_noncurrent_assets",   # 非流动资产合计
    "fldfzhj": "total_noncurrent_liabilities",  # 非流动负债合计
    "j_kcg": "financial_assets",      # 交易性金融资产
}

INCOME_STATEMENT_MAP = {
    "yysr": "revenue",               # 营业收入
    "yyzcb": "total_operating_cost",  # 营业总成本
    "yycb": "cost_of_revenue",        # 营业成本
    "yylr": "operating_profit",       # 营业利润
    "lrze": "total_profit",           # 利润总额
    "jlr": "net_profit",              # 净利润
    "gsmgsyzzdjlr": "net_profit_attributable",  # 归母净利润
    "xsfy": "selling_expense",        # 销售费用
    "glfy": "admin_expense",          # 管理费用
    "cwfy": "finance_expense",        # 财务费用
    "yysjjfj": "tax_surcharge",       # 营业税金及附加
    "tzsy": "investment_income",      # 投资收益
    "ywsr": "other_operating_income", # 营业外收入
    "jbmgsy": "eps_basic",            # 基本每股收益
    "xsmgsy": "eps_diluted",          # 稀释每股收益
}

CASHFLOW_MAP = {
    "jyhdcsdxjlxj": "operating_cashflow",           # 经营活动产生的现金流量净额
    "tzhdcsdxjlxj": "investing_cashflow",           # 投资活动产生的现金流量净额
    "czhdcsdxjlxj": "financing_cashflow",           # 筹资活动产生的现金流量净额
    "gjgdzcwxzhqtqctzzfdxj": "capex",               # 购建固定资产等支付的现金
    "xssptglwsddxj": "cash_from_sales",              # 销售商品提供劳务收到的现金
    "jyhdxjlrxj": "operating_cash_inflow",           # 经营活动现金流入
    "jyhdxjlcxj": "operating_cash_outflow",          # 经营活动现金流出
}


def _parse_api_table(data: dict, field_map: dict) -> pd.DataFrame:
    """
    解析智兔API返回的财务报表数据为DataFrame。

    智兔API返回格式通常为:
    [{"报告日期": "2024-12-31", "合同负债": 123456, ...}, ...]
    或 {"data": [...]}
    """
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        records = data.get("data", data.get("items", [data]))
    else:
        return pd.DataFrame()

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # 重命名列
    rename_cols = {}
    for cn_name, en_name in field_map.items():
        if cn_name in df.columns:
            rename_cols[cn_name] = en_name
    df.rename(columns=rename_cols, inplace=True)

    # 解析日期列（智兔API使用拼音缩写jzrq = 截止日期）
    date_col = None
    for col in ["jzrq", "报告日期", "截止日期", "日期", "date", "report_date"]:
        if col in df.columns:
            date_col = col
            break
    if date_col:
        df["report_date"] = pd.to_datetime(df[date_col], errors="coerce")
        df.drop(columns=[date_col], inplace=True)

    # 数值列转换
    for col in df.columns:
        if col == "report_date":
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.sort_values("report_date")


def safe_growth_rate(series: pd.Series, periods: int = 4) -> Optional[float]:
    """计算同比增长率，处理缺失值"""
    clean = series.dropna()
    if len(clean) < periods + 1:
        return None
    current = clean.iloc[-1]
    base = clean.iloc[-(periods + 1)]
    if base == 0 or pd.isna(base) or pd.isna(current):
        return None
    return float((current / base - 1) * 100)


def safe_qoq_rate(series: pd.Series) -> Optional[float]:
    """计算环比增长率"""
    clean = series.dropna()
    if len(clean) < 2:
        return None
    current = clean.iloc[-1]
    prev = clean.iloc[-2]
    if prev == 0 or pd.isna(prev) or pd.isna(current):
        return None
    return float((current / prev - 1) * 100)


def trend_direction(series: pd.Series, min_periods: int = 3) -> str:
    """判断趋势方向: accelerating / steady / decelerating / declining"""
    clean = series.dropna()
    if len(clean) < min_periods:
        return "insufficient_data"

    recent = clean.iloc[-min_periods:]
    if len(recent) < 2:
        return "insufficient_data"

    diffs = recent.diff().dropna()
    if len(diffs) < 2:
        # 只有一期变化
        if diffs.iloc[-1] > 0:
            return "rising"
        else:
            return "declining"

    # 检查二阶差分（加速/减速）
    second_diff = diffs.diff().dropna()
    if len(second_diff) > 0:
        if (second_diff > 0).all() and (diffs > 0).all():
            return "accelerating"
        elif (second_diff < 0).all() and (diffs > 0).all():
            return "decelerating"

    if (diffs > 0).all():
        return "rising"
    elif (diffs < 0).all():
        return "declining"
    else:
        return "fluctuating"


class FinancialMetricsCalculator:
    """成长股财务指标计算器"""

    def __init__(self, client: ZhituClient = None):
        self.client = client or ZhituClient()

    def analyze(self, code: str) -> dict:
        """
        对单只股票进行完整财务指标分析。

        Args:
            code: 股票代码，如 "000001.SZ"

        Returns:
            结构化JSON分析结果
        """
        # 并行获取所有需要的财务数据
        balance = self.client.get_balance_sheet(code)
        income = self.client.get_income_statement(code)
        cashflow = self.client.get_cashflow_statement(code)
        ratios_raw = self.client.get_financial_ratios(code)
        indicators = self.client.get_financial_indicators(code)
        profile = self.client.get_company_profile(code)
        quote = self.client.get_realtime_quote(code)

        # 解析为DataFrame
        df_balance = _parse_api_table(balance, BALANCE_SHEET_MAP)
        df_income = _parse_api_table(income, INCOME_STATEMENT_MAP)
        df_cashflow = _parse_api_table(cashflow, CASHFLOW_MAP)
        df_ratios = _parse_api_table(ratios_raw, {})  # ratios字段名不确定，保留原始
        df_indicators = pd.DataFrame(indicators) if isinstance(indicators, list) else pd.DataFrame()

        result = {
            "code": code,
            "name": self._extract_name(profile, quote),
            "industry": self._extract_industry(profile),
            "analysis_date": datetime.now().strftime("%Y-%m-%d"),
            "data_quality": {},
            "contract_liability": {},
            "capacity_expansion": {},
            "revenue_profit": {},
            "cashflow_quality": {},
            "summary": {},
        }

        # ── 1. 合同负债/预收款分析 ────────────────────
        cl_data = self._analyze_contract_liability(df_balance, df_income)
        result["contract_liability"] = cl_data

        # ── 2. 产能扩张分析 ──────────────────────────
        cap_data = self._analyze_capacity(df_balance, df_cashflow, df_income)
        result["capacity_expansion"] = cap_data

        # ── 3. 收入利润增长分析 ──────────────────────
        rp_data = self._analyze_revenue_profit(df_income, df_indicators)
        result["revenue_profit"] = rp_data

        # ── 4. 现金流质量分析 ──────────────────────────
        cf_data = self._analyze_cashflow(df_cashflow, df_income, df_balance)
        result["cashflow_quality"] = cf_data

        # ── 5. 综合摘要 ──────────────────────────────
        result["summary"] = self._generate_summary(result)
        result["data_quality"] = self._assess_data_quality(
            df_balance, df_income, df_cashflow
        )

        return result

    def _extract_name(self, profile: dict, quote: dict) -> str:
        """从API数据中提取公司名称"""
        for src in [profile, quote]:
            if isinstance(src, dict):
                for key in ["mc", "公司名称", "name", "gsmc"]:
                    if key in src:
                        return str(src[key])
        return "未知"

    def _extract_industry(self, profile: dict) -> str:
        """从公司简介中提取行业/概念"""
        if isinstance(profile, dict):
            for key in ["hy", "行业", "所属行业", "industry", "idea"]:
                if key in profile and profile[key]:
                    val = str(profile[key])
                    # idea字段可能包含多个概念，取前2个
                    if key == "idea" and len(val) > 30:
                        concepts = val.split(",")[:3]
                        return "/".join(concepts)
                    return val
        return "未知"

    def _analyze_contract_liability(self, df_balance: pd.DataFrame,
                                    df_income: pd.DataFrame) -> dict:
        """分析合同负债/预收款：增速、占比、趋势"""
        result = {
            "current_value": None,
            "yoy_growth_pct": None,
            "qoq_growth_pct": None,
            "trend": "insufficient_data",
            "ratio_to_revenue_pct": None,
            "ratio_trend": "insufficient_data",
            "assessment": "数据不足，无法判断",
        }

        # 确定合同负债列（优先合同负债，其次预收款项）
        cl_col = None
        for col in ["contract_liability", "advance_receipts"]:
            if col in df_balance.columns and not df_balance[col].dropna().empty:
                cl_col = col
                break

        if cl_col is None:
            result["assessment"] = "未找到合同负债或预收款数据"
            return result

        cl_series = df_balance[cl_col].dropna().sort_index()
        # 保证按日期排序
        df_balance = df_balance.dropna(subset=[cl_col]).sort_values("report_date")
        cl_series = df_balance.set_index("report_date")[cl_col]

        result["current_value"] = float(cl_series.iloc[-1]) if len(cl_series) > 0 else None
        result["yoy_growth_pct"] = safe_growth_rate(cl_series, 4)
        result["qoq_growth_pct"] = safe_qoq_rate(cl_series)
        result["trend"] = trend_direction(cl_series)

        # 合同负债/营业收入比率
        if "revenue" in df_income.columns and not df_income["revenue"].dropna().empty:
            df_income_sorted = df_income.dropna(subset=["revenue"]).sort_values("report_date")
            rev_series = df_income_sorted.set_index("report_date")["revenue"]

            # 找到最近一个报告期的比率
            if len(cl_series) > 0 and len(rev_series) > 0:
                latest_date = cl_series.index[-1]
                # 找日期最接近的收入数据
                time_diffs = [(i, abs((d - latest_date).days)) for i, d in enumerate(rev_series.index)]
                closest_idx = min(time_diffs, key=lambda x: x[1])[0]
                latest_rev = rev_series.iloc[closest_idx]
                if latest_rev > 0:
                    result["ratio_to_revenue_pct"] = float(
                        cl_series.iloc[-1] / latest_rev * 100
                    )

                # 比率趋势
                common_dates = cl_series.index.intersection(rev_series.index)
                if len(common_dates) >= 3:
                    ratio_series = cl_series[common_dates] / rev_series[common_dates]
                    result["ratio_trend"] = trend_direction(ratio_series * 100)

        # 生成判断
        result["assessment"] = self._assess_cl(result)

        return result

    def _assess_cl(self, cl_data: dict) -> str:
        """生成合同负债判断"""
        if cl_data.get("yoy_growth_pct") is None:
            return "合同负债数据不足"
        yoy = cl_data["yoy_growth_pct"]
        trend = cl_data.get("trend", "")
        ratio = cl_data.get("ratio_to_revenue_pct")

        parts = []
        if yoy > 30:
            parts.append(f"合同负债同比大幅增长{yoy:.1f}%，未来收入释放潜力强")
        elif yoy > 10:
            parts.append(f"合同负债同比增长{yoy:.1f}%，有增长迹象")
        elif yoy > 0:
            parts.append(f"合同负债微增{yoy:.1f}%，增长力度一般")
        elif yoy > -10:
            parts.append(f"合同负债同比下降{abs(yoy):.1f}%，需关注是否正常交付转收入")
        else:
            parts.append(f"合同负债大幅下降{abs(yoy):.1f}%，需警惕新订单断档风险")

        if trend == "accelerating":
            parts.append("增速呈加速趋势")
        elif trend == "decelerating":
            parts.append("增速放缓，关注拐点")

        if ratio is not None:
            if ratio > 50:
                parts.append(f"占收入比{ratio:.1f}%，收入前置确定性高")
            elif ratio < 10:
                parts.append(f"占收入比仅{ratio:.1f}%，对收入前瞻指导有限")

        return "；".join(parts) if parts else "数据有限，无法判断"

    def _analyze_capacity(self, df_balance: pd.DataFrame,
                          df_cashflow: pd.DataFrame,
                          df_income: pd.DataFrame) -> dict:
        """分析产能扩张指标"""
        result = {
            "construction_in_progress": {},
            "capacity_intensity": {},
            "asset_turnover": {},
            "expansion_evidence": [],
            "assessment": "数据不足",
        }

        # 在建工程分析
        if "construction_in_progress" in df_balance.columns:
            df = df_balance.sort_values("report_date")
            cip = df.set_index("report_date")["construction_in_progress"].dropna()
            if len(cip) > 0:
                result["construction_in_progress"] = {
                    "current_value": float(cip.iloc[-1]),
                    "yoy_growth_pct": safe_growth_rate(cip, 4),
                    "trend": trend_direction(cip),
                }

                # 在建工程/固定资产比率
                if "fixed_assets" in df.columns:
                    fa = df.set_index("report_date")["fixed_assets"].dropna()
                    common = cip.index.intersection(fa.index)
                    if len(common) > 0:
                        ratio = cip[common].iloc[-1] / fa[common].iloc[-1] * 100 if fa[common].iloc[-1] > 0 else None
                        result["construction_in_progress"]["ratio_to_fixed_assets_pct"] = (
                            float(ratio) if ratio is not None else None
                        )

        # 资本开支强度（capex / 折旧摊销近似） → 用 capex/revenue
        if "capex" in df_cashflow.columns and "revenue" in df_income.columns:
            df_cf = df_cashflow.sort_values("report_date")
            df_inc = df_income.sort_values("report_date")
            capex_s = df_cf.set_index("report_date")["capex"].dropna()
            rev_s = df_inc.set_index("report_date")["revenue"].dropna()
            common = capex_s.index.intersection(rev_s.index)
            if len(common) > 0:
                capex_latest = capex_s[common].iloc[-1]
                rev_latest = rev_s[common].iloc[-1]
                if rev_latest > 0:
                    result["capacity_intensity"] = {
                        "capex_to_revenue_pct": float(capex_latest / rev_latest * 100),
                        "assessment": (
                            "资本开支强度较高，处于扩张期" if abs(capex_latest / rev_latest) > 0.1
                            else "资本开支强度正常" if abs(capex_latest / rev_latest) > 0.03
                            else "资本开支强度偏低，扩张动力不足"
                        )
                    }

        # 固定资产周转率趋势
        if "fixed_assets" in df_balance.columns and "revenue" in df_income.columns:
            fa = df_balance.sort_values("report_date").set_index("report_date")["fixed_assets"]
            rev = df_income.sort_values("report_date").set_index("report_date")["revenue"]
            common = fa.dropna().index.intersection(rev.dropna().index)
            if len(common) >= 3:
                turnover = rev[common] / fa[common]
                result["asset_turnover"] = {
                    "current": float(turnover.iloc[-1]) if len(turnover) > 0 else None,
                    "trend": trend_direction(turnover),
                }

        # 扩张证据汇总
        evidence = result["expansion_evidence"]
        cip_yoy = result.get("construction_in_progress", {}).get("yoy_growth_pct")
        if cip_yoy is not None and cip_yoy > 20:
            evidence.append(f"在建工程同比增长{cip_yoy:.1f}%，扩产积极")
        if cip_yoy is not None and cip_yoy < -20:
            evidence.append(f"在建工程同比下降{abs(cip_yoy):.1f}%，扩产减速")

        capex_ratio = result.get("capacity_intensity", {}).get("capex_to_revenue_pct")
        if capex_ratio is not None and capex_ratio > 10:
            evidence.append(f"资本开支占收入{capex_ratio:.1f}%，重投入扩张期")

        turnover_trend = result.get("asset_turnover", {}).get("trend", "")
        if turnover_trend == "rising":
            evidence.append("固定资产周转率上升，产能利用率提高")
        elif turnover_trend == "declining":
            evidence.append("固定资产周转率下降，新产能消化存疑")

        # 综合判断
        if cip_yoy is not None and cip_yoy > 20 and capex_ratio is not None and capex_ratio > 10:
            result["assessment"] = "积极扩产中，在建工程和资本开支双高，关注投产节奏"
        elif cip_yoy is not None and cip_yoy > 10:
            result["assessment"] = "稳步扩产中，在建工程增长"
        elif cip_yoy is not None and cip_yoy < -10:
            result["assessment"] = "扩产减速，在建工程下降，可能进入成熟期"
        else:
            result["assessment"] = "产能变化不显著"

        return result

    def _analyze_revenue_profit(self, df_income: pd.DataFrame,
                                df_indicators: pd.DataFrame) -> dict:
        """分析收入利润增长（使用同比增速而非原始值，避免季度季节性干扰）"""
        result = {
            "revenue_growth": {},
            "net_profit_growth": {},
            "gross_margin": {},
            "net_margin": {},
            "roe": {},
            "revenue_quality": "insufficient_data",
        }

        df = df_income.sort_values("report_date")
        ts = df.set_index("report_date")

        # 收入增长 - 使用YoY而非QoQ
        if "revenue" in ts.columns:
            rev = ts["revenue"].dropna()
            if len(rev) >= 8:
                # 计算每期同比增速(4个季度前)
                yoy_growth_series = rev.pct_change(periods=4).dropna() * 100
                result["revenue_growth"] = {
                    "latest_quarter_value": float(rev.iloc[-1]),
                    "yoy_growth_pct": safe_growth_rate(rev, 4),
                    "qoq_growth_pct": safe_qoq_rate(rev),
                    "trend": trend_direction(yoy_growth_series) if len(yoy_growth_series) >= 2 else "insufficient_data",
                }

        # 净利润增长 - 同样使用YoY
        net_col = None
        for col in ["net_profit_attributable", "net_profit"]:
            if col in ts.columns:
                net_col = col
                break
        if net_col:
            net = ts[net_col].dropna()
            if len(net) >= 8:
                yoy_growth = net.pct_change(periods=4).dropna() * 100
                result["net_profit_growth"] = {
                    "latest_quarter_value": float(net.iloc[-1]),
                    "yoy_growth_pct": safe_growth_rate(net, 4),
                    "trend": trend_direction(yoy_growth) if len(yoy_growth) >= 2 else "insufficient_data",
                }

        # 毛利率
        if "revenue" in ts.columns and "cost_of_revenue" in ts.columns:
            rev = ts["revenue"]
            cost = ts["cost_of_revenue"]
            common = rev.dropna().index.intersection(cost.dropna().index)
            if len(common) >= 2:
                gm = (rev[common] - cost[common]) / rev[common] * 100
                result["gross_margin"] = {
                    "current_pct": float(gm.iloc[-1]),
                    "trend": trend_direction(gm),
                }

        # 净利率
        if net_col and "revenue" in ts.columns:
            net = ts[net_col]
            rev = ts["revenue"]
            common = net.dropna().index.intersection(rev.dropna().index)
            if len(common) >= 2:
                nm = net[common] / rev[common] * 100
                result["net_margin"] = {
                    "current_pct": float(nm.iloc[-1]),
                    "trend": trend_direction(nm),
                }

        # ROE（从财务报表推断：净利润/所有者权益）
        if net_col:
            # 这里使用净利率 * 资产周转率 * 权益乘数的杜邦分解
            # 简化：从ratios数据或自行计算
            pass

        # 收入质量判断
        rev_trend = result.get("revenue_growth", {}).get("trend", "")
        gm_trend = result.get("gross_margin", {}).get("trend", "")
        if rev_trend in ("accelerating", "rising") and gm_trend in ("rising", "accelerating"):
            result["revenue_quality"] = "量价齐升，增长质量高"
        elif rev_trend in ("accelerating", "rising"):
            result["revenue_quality"] = "收入增长，毛利率平稳"
        elif rev_trend == "declining":
            result["revenue_quality"] = "收入下滑，需警惕"
        else:
            result["revenue_quality"] = "增长态势不明确"

        return result

    def _analyze_cashflow(self, df_cashflow: pd.DataFrame,
                          df_income: pd.DataFrame,
                          df_balance: pd.DataFrame) -> dict:
        """分析现金流质量"""
        result = {
            "ocf_to_profit_ratio": None,
            "ocf_trend": "insufficient_data",
            "capex_coverage": None,
            "cash_from_sales_to_revenue_pct": None,
            "assessment": "数据不足",
        }

        df_cf = df_cashflow.sort_values("report_date").set_index("report_date")
        df_inc = df_income.sort_values("report_date").set_index("report_date")

        # 经营活动现金流 / 净利润
        if "operating_cashflow" in df_cf.columns:
            ocf = df_cf["operating_cashflow"].dropna()
            if len(ocf) >= 4:
                result["ocf_trend"] = trend_direction(ocf)

            # OCF / Net Profit
            net_col = None
            for col in ["net_profit_attributable", "net_profit"]:
                if col in df_inc.columns:
                    net_col = col
                    break
            if net_col and len(ocf) > 0:
                net = df_inc[net_col].dropna()
                common = ocf.index.intersection(net.index)
                if len(common) > 0:
                    latest_ocf = ocf[common].iloc[-1]
                    latest_net = net[common].iloc[-1]
                    if latest_net != 0:
                        ratio = float(latest_ocf / latest_net)
                        result["ocf_to_profit_ratio"] = ratio

        # 销售收到现金 / 营业收入
        if "cash_from_sales" in df_cf.columns and "revenue" in df_inc.columns:
            cfs = df_cf["cash_from_sales"].dropna()
            rev = df_inc["revenue"].dropna()
            common = cfs.index.intersection(rev.index)
            if len(common) > 0:
                result["cash_from_sales_to_revenue_pct"] = float(
                    cfs[common].iloc[-1] / rev[common].iloc[-1] * 100
                )

        # 现金流质量判断
        ocf_ratio = result.get("ocf_to_profit_ratio")
        ocf_trend = result.get("ocf_trend", "")
        if ocf_ratio is not None:
            if ocf_ratio > 1.0 and ocf_trend in ("rising", "accelerating"):
                result["assessment"] = "现金流优异，利润含金量高"
            elif ocf_ratio > 0.8:
                result["assessment"] = "现金流良好，利润有现金流支撑"
            elif ocf_ratio > 0:
                result["assessment"] = "现金流弱于利润，关注应收和存货"
            else:
                result["assessment"] = "经营现金流为负，利润质量存疑"

        return result

    def _assess_data_quality(self, df_balance: pd.DataFrame,
                             df_income: pd.DataFrame,
                             df_cashflow: pd.DataFrame) -> dict:
        """评估数据完整性和质量"""
        return {
            "balance_sheet_records": len(df_balance),
            "income_statement_records": len(df_income),
            "cashflow_records": len(df_cashflow),
            "has_contract_liability": (
                "contract_liability" in df_balance.columns
                or "advance_receipts" in df_balance.columns
            ),
            "has_construction_in_progress": "construction_in_progress" in df_balance.columns,
            "has_capex": "capex" in df_cashflow.columns,
            "sufficient_history": (
                len(df_income) >= 8
                and len(df_balance) >= 8
                and len(df_cashflow) >= 4
            ),
        }

    def _generate_summary(self, result: dict) -> dict:
        """生成综合摘要"""
        cl = result.get("contract_liability", {})
        cap = result.get("capacity_expansion", {})
        rp = result.get("revenue_profit", {})
        cf = result.get("cashflow_quality", {})

        # 成长信号计数
        signals = {
            "contract_liability_positive": (
                (cl.get("yoy_growth_pct") or 0) > 10
                and cl.get("trend", "") in ("accelerating", "rising")
            ),
            "capacity_expansion_active": (
                cap.get("assessment", "") and "积极扩产" in cap.get("assessment", "")
            ),
            "revenue_accelerating": (
                rp.get("revenue_growth", {}).get("trend", "") == "accelerating"
            ),
            "high_quality_cashflow": (
                cf.get("assessment", "") and "优异" in cf.get("assessment", "")
            ),
            "gross_margin_improving": (
                rp.get("gross_margin", {}).get("trend", "") in ("accelerating", "rising")
            ),
        }

        positive_count = sum(1 for v in signals.values() if v)

        growth_types = []
        if signals["contract_liability_positive"]:
            growth_types.append("订单/预收款驱动")
        if signals["capacity_expansion_active"]:
            growth_types.append("产能扩张驱动")
        if signals["revenue_accelerating"]:
            growth_types.append("收入加速增长")
        if signals["high_quality_cashflow"]:
            growth_types.append("现金流优异")

        return {
            "positive_signals_count": positive_count,
            "total_signals": len(signals),
            "growth_types": growth_types if growth_types else ["待判定"],
            "overall_quality": (
                "强成长信号" if positive_count >= 4
                else "中等偏强" if positive_count >= 3
                else "中性" if positive_count >= 2
                else "弱信号"
            ),
            "signals_detail": signals,
        }


def main():
    parser = argparse.ArgumentParser(description="成长股财务指标计算器")
    parser.add_argument("--code", type=str, help="单只股票代码，如 000001.SZ")
    parser.add_argument("--input", type=str, help="批量代码JSON文件")
    parser.add_argument("--output", type=str, help="输出文件路径")
    args = parser.parse_args()

    if not args.code and not args.input:
        parser.error("必须指定 --code 或 --input")

    calculator = FinancialMetricsCalculator()

    if args.code:
        result = calculator.analyze(args.code)
        if args.output:
            with open(args.output, "w") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"结果已保存到 {args.output}")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.input:
        with open(args.input) as f:
            codes = json.load(f)
        results = {}
        for code in codes:
            try:
                results[code] = calculator.analyze(code)
                print(f"[OK] {code}")
            except Exception as e:
                results[code] = {"error": str(e)}
                print(f"[ERR] {code}: {e}")

        output_path = args.output or "batch_results.json"
        with open(output_path, "w") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"批量结果已保存到 {output_path}")


if __name__ == "__main__":
    main()
