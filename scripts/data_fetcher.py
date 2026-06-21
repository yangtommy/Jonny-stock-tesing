#!/usr/bin/env python3
"""
成长股分析系统 - 数据获取模块
封装智兔沪深API (api.zhituapi.com) 的所有数据请求，提供缓存和限速功能。
"""

import json
import os
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any

import requests


class ZhituClient:
    """智兔API客户端，处理认证、缓存、限速"""

    BASE_URL = "https://api.zhituapi.com"

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "settings.json"

        with open(config_path) as f:
            self.config = json.load(f)

        self.token = self.config["api"]["token"]
        # 可从环境变量覆盖token
        if os.environ.get("ZHITU_TOKEN"):
            self.token = os.environ["ZHITU_TOKEN"]

        self.rate_limit = self.config["api"]["rate_limit_per_minute"]
        self.timeout = self.config["api"]["request_timeout"]
        self._last_request_time = 0
        self._min_interval = 60.0 / self.rate_limit

        # 缓存目录
        cache_dir = self.config["cache"]["dir"]
        self.cache_dir = Path(__file__).parent.parent / cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_enabled = self.config["cache"]["enabled"]

        # 请求会话
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "GrowthStockAnalyzer/1.0",
            "Accept": "application/json"
        })

    def _rate_limit(self):
        """限速控制"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def _cache_key(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def _cache_path(self, cache_key: str) -> Path:
        return self.cache_dir / f"{cache_key}.json"

    def _read_cache(self, cache_key: str, ttl_hours: float) -> Optional[dict]:
        if not self.cache_enabled:
            return None
        path = self._cache_path(cache_key)
        if not path.exists():
            return None
        age = time.time() - path.stat().st_mtime
        if age > ttl_hours * 3600:
            return None
        with open(path) as f:
            return json.load(f)

    def _write_cache(self, cache_key: str, data: dict):
        if not self.cache_enabled:
            return
        with open(self._cache_path(cache_key), "w") as f:
            json.dump(data, f, ensure_ascii=False)

    def get(self, path: str, params: dict = None,
            cache_ttl_hours: float = 24) -> dict:
        """
        GET请求智兔API

        Args:
            path: API路径，如 "/hs/list/all"
            params: 查询参数字典（不含token）
            cache_ttl_hours: 缓存有效期（小时），0=不使用缓存
        """
        url = f"{self.BASE_URL}{path}"
        request_params = params.copy() if params else {}
        request_params["token"] = self.token

        cache_key = self._cache_key(url + json.dumps(request_params, sort_keys=True))

        # 尝试读缓存
        if cache_ttl_hours > 0:
            cached = self._read_cache(cache_key, cache_ttl_hours)
            if cached is not None:
                return cached

        self._rate_limit()

        try:
            resp = self.session.get(url, params=request_params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as e:
            # 如果有缓存但已过期，在请求失败时仍返回过期缓存
            if cache_ttl_hours > 0:
                stale = self._read_cache(cache_key, 999999)
                if stale is not None:
                    print(f"[WARN] API请求失败，使用过期缓存: {e}")
                    return stale
            raise

        if cache_ttl_hours > 0:
            self._write_cache(cache_key, data)

        return data

    # ⚠️ API代码格式规则:
    #   /hs/gs/*  和  /hs/real/*  → 需要纯数字代码(300750)
    #   /hs/fin/*  和  /hs/history/* → 需要带后缀代码(300750.SZ)

    # ── 股票列表 ─────────────────────────────────────

    def get_stock_list(self) -> list[dict]:
        """获取全A股股票列表"""
        return self.get("/hs/list/all", cache_ttl_hours=24)

    def get_sector_list(self) -> list[dict]:
        """获取概念指数列表"""
        return self.get("/hs/list/sectors", cache_ttl_hours=24)

    def get_industry_list(self) -> list[dict]:
        """获取一级行业板块列表"""
        return self.get("/hs/list/primary", cache_ttl_hours=24)

    def get_sector_stocks(self, sector_name: str) -> list[dict]:
        """获取某行业/板块的成分股"""
        return self.get(f"/hs/sectors/{sector_name}", cache_ttl_hours=24)

    def _raw_code(self, code: str) -> str:
        """提取纯数字代码（去掉 .SZ/.SH 后缀），用于gs/real类API"""
        return code.split(".")[0] if "." in code else code

    def _full_code(self, code: str) -> str:
        """确保代码带后缀格式，用于fin/history类API"""
        if "." in code:
            return code
        # 根据代码范围判断交易所: 60xxxx→SH, 00xxxx→SZ, 30xxxx→SZ, 688xxx→SH
        if code.startswith("60") or code.startswith("688"):
            return f"{code}.SH"
        else:
            return f"{code}.SZ"

    def get_company_profile(self, code: str) -> dict:
        """公司简介 (需纯数字代码)"""
        return self.get(f"/hs/gs/gsjj/{self._raw_code(code)}", cache_ttl_hours=24)

    def get_business_scope(self, code: str) -> dict:
        """经营范围 (需纯数字代码)"""
        return self.get(f"/hs/gs/jyfw/{self._raw_code(code)}", cache_ttl_hours=168)

    def get_financial_indicators(self, code: str) -> dict:
        """近四个季度主要财务指标 (需纯数字代码)"""
        return self.get(f"/hs/gs/cwzb/{self._raw_code(code)}", cache_ttl_hours=24)

    def get_quarterly_profits(self, code: str) -> dict:
        """近一年各季度利润 (需纯数字代码)"""
        return self.get(f"/hs/gs/jdlr/{self._raw_code(code)}", cache_ttl_hours=24)

    def get_quarterly_cashflow(self, code: str) -> dict:
        """近一年各季度现金流 (需纯数字代码)"""
        return self.get(f"/hs/gs/jdxj/{self._raw_code(code)}", cache_ttl_hours=24)

    def get_performance_forecast(self, code: str) -> dict:
        """近年业绩预告 (需纯数字代码)"""
        return self.get(f"/hs/gs/yjyg/{self._raw_code(code)}", cache_ttl_hours=12)

    def get_top_shareholders(self, code: str) -> dict:
        """十大股东 (需纯数字代码)"""
        return self.get(f"/hs/gs/sdgd/{self._raw_code(code)}", cache_ttl_hours=24)

    def get_shareholder_trend(self, code: str) -> dict:
        """股东变化趋势 (需纯数字代码)"""
        return self.get(f"/hs/gs/gdbh/{self._raw_code(code)}", cache_ttl_hours=24)

    # ── 财务报表 ─────────────────────────────────────

    # ── 财务报表 (使用带后缀代码) ─────────────────

    def get_balance_sheet(self, code: str,
                          start: str = None, end: str = None) -> dict:
        """资产负债表（含合同负债、在建工程等）"""
        params = {}
        if start:
            params["st"] = start
        if end:
            params["et"] = end
        return self.get(f"/hs/fin/balance/{self._full_code(code)}", params=params or None,
                        cache_ttl_hours=24)

    def get_income_statement(self, code: str,
                             start: str = None, end: str = None) -> dict:
        """利润表"""
        params = {}
        if start:
            params["st"] = start
        if end:
            params["et"] = end
        return self.get(f"/hs/fin/income/{self._full_code(code)}", params=params or None,
                        cache_ttl_hours=24)

    def get_cashflow_statement(self, code: str,
                               start: str = None, end: str = None) -> dict:
        """现金流量表"""
        params = {}
        if start:
            params["st"] = start
        if end:
            params["et"] = end
        return self.get(f"/hs/fin/cashflow/{self._full_code(code)}", params=params or None,
                        cache_ttl_hours=24)

    def get_financial_ratios(self, code: str,
                             start: str = None, end: str = None) -> dict:
        """财务主要指标（ROE、ROA、毛利率等）"""
        params = {}
        if start:
            params["st"] = start
        if end:
            params["et"] = end
        return self.get(f"/hs/fin/ratios/{self._full_code(code)}", params=params or None,
                        cache_ttl_hours=24)

    # ── 实时交易 (使用纯数字代码) ─────────────────

    def get_realtime_quote(self, code: str) -> dict:
        """实时交易数据（需纯数字代码）"""
        return self.get(f"/hs/real/ssjy/{self._raw_code(code)}", cache_ttl_hours=0)

    def get_realtime_batch(self, codes: list[str]) -> dict:
        """批量实时交易（最多20只）"""
        raw_codes = [self._raw_code(c) for c in codes[:20]]
        codes_str = ",".join(raw_codes)
        return self.get("/hs/public/ssjymore",
                        params={"stock_codes": codes_str}, cache_ttl_hours=0)

    # ── 行情数据 (使用带后缀代码) ─────────────────

    def get_history(self, code: str, freq: str = "d", adj: str = "f",
                    start: str = None, end: str = None,
                    limit: int = None) -> dict:
        """
        历史K线数据

        Args:
            freq: d=日线, w=周线, m=月线
            adj: f=前复权, b=后复权, n=不复权
        """
        params = {}
        if start:
            params["st"] = start
        if end:
            params["et"] = end
        if limit:
            params["lt"] = str(limit)
        return self.get(f"/hs/history/{self._full_code(code)}/{freq}/{adj}",
                        params=params or None, cache_ttl_hours=6)

    def get_indicators(self, code: str,
                       start: str = None, end: str = None) -> dict:
        """历史行情指标（PE、PB、换手率等）"""
        params = {}
        if start:
            params["st"] = start
        if end:
            params["et"] = end
        return self.get(f"/hs/indicators/{self._full_code(code)}",
                        params=params or None, cache_ttl_hours=6)

    def get_capital_flow(self, code: str,
                         start: str = None, end: str = None,
                         limit: int = None) -> dict:
        """资金流向数据"""
        params = {}
        if start:
            params["st"] = start
        if end:
            params["et"] = end
        if limit:
            params["lt"] = str(limit)
        return self.get(f"/hs/history/transaction/{self._full_code(code)}",
                        params=params or None, cache_ttl_hours=6)

    # ── 涨跌股池 ─────────────────────────────────────

    def get_limit_up_pool(self, date: str = None) -> dict:
        """涨停股池"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        return self.get(f"/hs/pool/ztgc/{date}", cache_ttl_hours=6)

    def get_strong_stock_pool(self, date: str = None) -> dict:
        """强势股池"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        return self.get(f"/hs/pool/qsgc/{date}", cache_ttl_hours=6)


if __name__ == "__main__":
    # 测试：获取股票列表
    client = ZhituClient()
    stocks = client.get_stock_list()
    print(f"沪深A股共 {len(stocks)} 只")
    print(f"示例: {stocks[:3]}")
