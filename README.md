# 分析系统1.0版本

基于《过去的一些股投资思想》方法论的自动化分析系统主要是为了更快速的筛选一个值得研究的股票范围。使用 Python 进行数据计算，Claude Code Skills + 多 Agent 进行并行分析。

## 快速开始

### 1. 配置 API Token

```bash
# 方式一：环境变量
export ZHITU_TOKEN="你的智兔API Token"

# 方式二：修改配置文件
# 编辑 config/settings.json 中的 api.token
```

### 2. 分析单只股票

在 Claude Code 中直接说：
```
分析 300750.SZ 的成长股逻辑
```

这将自动触发主编排器，依次运行 Python 计算 → 舆情采集 → 4 Agent 并行分析 → 综合报告。

### 3. 手动运行 Python 脚本

```bash
cd scripts

# 计算财务指标
python3 financial_metrics_calculator.py --code 000001.SZ --output ../data/latest/000001_financial.json

# 估值分析
python3 valuation_analyzer.py --code 000001.SZ --output ../data/latest/000001_valuation.json

# 行业对比
python3 industry_comparator.py --code 000001.SZ --output ../data/latest/000001_industry.json
```

## 系统架构

```
Layer 1 (Python):  数据获取 + 财务指标计算 + 估值分析 + 行业对比
Layer 2 (Skill):   舆情/研报/新闻采集
Layer 3 (4 Agent): 成长逻辑 | 前置指标 | 估值行业 | 风险证伪  [并行]
Layer 4 (Agent E): 阶段判定 + 仓位框架 + 卖出标准 + 报告生成
```

## 文件结构

```
growth-stock-system/
├── config/
│   ├── settings.json              # API配置、缓存设置
│   ├── industry_mapping.json      # 行业分类映射（待完善）
│   └── tracking_list.json         # Dashboard跟踪列表
├── scripts/
│   ├── data_fetcher.py            # 智兔API客户端
│   ├── financial_metrics_calculator.py  # 财务指标计算
│   ├── valuation_analyzer.py      # 估值分析
│   └── industry_comparator.py     # 行业对比
├── skills/
│   ├── sentiment-fetcher.md       # Skill 1: 舆情采集
│   ├── growth-logic-analyzer.md   # Agent A: 成长逻辑提取
│   ├── leading-indicator-scorer.md # Agent B: 前置指标评分
│   ├── valuation-industry-analyzer.md # Agent C: 估值行业分析
│   ├── risk-falsification-analyzer.md # Agent D: 风险证伪分析
│   ├── growth-orchestrator.md     # Skill 6: 主编排器
│   └── growth-decision-synthesizer.md # Agent E: 综合决策
├── data/
│   ├── cache/                     # API缓存
│   ├── latest/                    # 最新分析结果
│   └── reports/                   # Markdown报告
└── tests/
    ├── test_financial_metrics.py
    ├── test_valuation.py
    └── test_industry_comparator.py
```

## 方法论


- **核心**: 用合同负债、收钱订单、产能扩张、行业景气、渠道扩张等前置指标下注未来业绩
- **买入**: 前置指标出现、逻辑未兑现时
- **持有**: 只跟踪成长是否持续
- **卖出**: 逻辑兑现或证伪，不追求逃顶
- **仓位**: 小仓位(≤5%)组合优先，加仓依据是确定性增强而非价格更低

## 依赖

- Python 3.8+
- pandas, numpy, requests
- 智兔沪深API Token (https://www.zhituapi.com)

## 免责声明

本系统基于公开信息和方法论框架进行自动化分析，所有输出不构成投资建议。
成长股投资胜率可能低于30-50%，投资者应独立判断。

觉得有用可以请我冲原神
