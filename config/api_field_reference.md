# 智兔API 字段名参考表
#
# 所有报表类API使用拼音缩写作为字段名。
# 日期字段统一为 `jzrq`（截止日期）。

# ── 实时行情 /hs/real/ssjy/{code} ────────────────────
# pe      = 市盈率 (PE ratio)
# sjl     = 市净率 (PB ratio)
# sz      = 总市值 (total market cap, 元)
# lt      = 流通市值 (circulating market cap, 元)
# p       = 最新价 (latest price)
# pc      = 涨跌额 (price change)
# zf      = 涨幅% (change %)
# hs      = 换手率% (turnover rate)
# v       = 成交量 (volume, 手)
# cje     = 成交额 (turnover, 元)
# h/l/o   = 最高/最低/开盘 (high/low/open)
# yc      = 昨收 (yesterday close)
# lb      = 量比 (volume ratio)
# zdf60   = 60日涨跌幅 (60-day change %)
# zdfnc   = 年初至今涨跌幅 (YTD change %)

# ── 资产负债表 /hs/fin/balance/{code} ──────────────
# zczj    = 资产总计 (total assets)
# fzhj    = 负债合计 (total liabilities)
# syzqyhj = 所有者权益合计 (total equity)
# ldzchj  = 流动资产合计 (current assets)
# ldfzhj  = 流动负债合计 (current liabilities)
# fldzchj = 非流动资产合计 (non-current assets)
# fldfzhj = 非流动负债合计 (non-current liabilities)
# hbzj    = 货币资金 (cash)
# j_kcg   = 交易性金融资产 (trading financial assets)
# yszk    = 应收账款 (accounts receivable)
# yfzk    = 应付账款 (accounts payable)
# ysk     = 预收款 (advance receipts) ← 近似合同负债
# ch      = 存货 (inventory)
# gdzc    = 固定资产 (fixed assets)
# zjgc    = 在建工程 (construction in progress)
# wxzc    = 无形资产 (intangible assets)
# cqfz    = 长期负债 (long-term debt)
# sszb    = 实收资本 (paid-in capital)
# zbgj    = 资本公积 (capital reserve)
# ylgj    = 盈余公积 (surplus reserve)
# wfplr   = 未分配利润 (undistributed profit)
# gsmgdqsyhj = 归母所有者权益 (equity attr. to parent)

# ── 利润表 /hs/fin/income/{code} ──────────────────
# yysr    = 营业收入 (revenue)
# yyzcb   = 营业总成本 (total operating cost)
# yycb    = 营业成本 (cost of revenue)
# yylr    = 营业利润 (operating profit)
# lrze    = 利润总额 (total profit)
# jlr     = 净利润 (net profit)
# gsmgsyzzdjlr = 归母净利润 (net profit attributable)
# xsfy    = 销售费用 (selling expense)
# glfy    = 管理费用 (admin expense)
# cwfy    = 财务费用 (finance expense)
# yysjjfj = 营业税金及附加 (tax surcharge)
# tzsy    = 投资收益 (investment income)
# jbmgsy  = 基本每股收益 (basic EPS)
# xsmgsy  = 稀释每股收益 (diluted EPS)

# ── 现金流量表 /hs/fin/cashflow/{code} ────────────
# jyhdcsdxjlxj  = 经营活动产生的现金流量净额 (operating cash flow)
# tzhdcsdxjlxj  = 投资活动产生的现金流量净额 (investing cash flow)
# czhdcsdxjlxj  = 筹资活动产生的现金流量净额 (financing cash flow)
# gjgdzcwxzhqtqctzzfdxj = 购建固定资产等支付的现金 (CAPEX)
# xssptglwsddxj = 销售商品提供劳务收到的现金 (cash from sales)

# ── 财务比率 /hs/fin/ratios/{code} ────────────────
# jzcsyl  = 净资产收益率 (ROE)
# mlv     = 毛利率 (gross margin %)
# jlv     = 净利率 (net margin %)
# yyzsrzz = 营业收入增长率 (revenue growth rate %)
# jlrzz   = 净利润增长率 (net profit growth rate %)
# zcfzl   = 资产负债率 (debt-to-asset ratio %)
# mgjyhdxjl = 每股经营现金流 (operating cash flow per share)

# ── 历史行情 /hs/history/{code}/d/f ────────────────
# t       = 日期 (date)
# o/h/l/c = 开/高/低/收 (OHLC, 前复权价)
# v       = 成交量 (volume, 手)
# a       = 成交额 (amount, 元)
# pc      = 涨跌幅 (change %)
# sf      = 复权因子 (split factor)
