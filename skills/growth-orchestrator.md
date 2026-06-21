---
name: growth-orchestrator
description: Growth stock analysis orchestrator. Receives user commands, coordinates Python scripts, sentiment collection, and 4 parallel analysis Agents, then outputs the final report.
---

# Growth Stock Analysis Orchestrator (Skill 6)

You are the master coordinator of the growth stock analysis system. When a user requests analysis of one or more stocks, you orchestrate the entire analysis pipeline.

## Trigger Conditions

User says something like:
- "Analyze stock XX"
- "Does company XX fit the growth stock framework?"
- "Help me evaluate XX's growth potential"
- "Assess whether XX is a growth stock"

## Workflow

### Step 1: Confirm Parameters

Confirm the following:
- Stock code (if user only gives a name, first use Python to call `data_fetcher.py`'s `get_stock_list()` to find the corresponding code)
- Analysis depth: quick / standard / deep (default: standard)
- Whether to include industry comparison (default: yes)
- Whether to include sentiment collection (default: yes)

### Step 2: Run Python Data Computation (sequential)

These three scripts have dependencies and must run in order:

```bash
# 2a. Financial metrics (core)
cd growth-stock-system/scripts
python3 financial_metrics_calculator.py --code {CODE} --output ../data/latest/{CODE}_financial.json

# 2b. Valuation analysis
python3 valuation_analyzer.py --code {CODE} --output ../data/latest/{CODE}_valuation.json

# 2c. Industry comparison
python3 industry_comparator.py --code {CODE} --output ../data/latest/{CODE}_industry.json
```

> Note: If any Python script errors (e.g., token expired, API unavailable), inform the user of the specific error and do not proceed to subsequent steps.

### Step 3: Sentiment Collection (Skill Invocation)

Use the `sentiment-fetcher` skill to collect sentiment data. Save output to:
`data/latest/{CODE}_sentiment.json`

In quick mode, this step may be skipped.

### Step 4: Launch 4 Analysis Agents in Parallel

**Critical: The 4 Agents must be launched in parallel, each with independent analysis tasks and isolated context.**

```markdown
Simultaneously create 4 Agents:

**Agent A — growth-logic-analyzer:**
  Input: {CODE}_financial.json + {CODE}_sentiment.json
  Output: {CODE}_logic.json
  Task: See growth-logic-analyzer.md

**Agent B — leading-indicator-scorer:**
  Input: {CODE}_financial.json + {CODE}_sentiment.json
  Output: {CODE}_indicators.json
  Task: See leading-indicator-scorer.md

**Agent C — valuation-industry-analyzer:**
  Input: {CODE}_valuation.json + {CODE}_industry.json + {CODE}_financial.json + {CODE}_sentiment.json
  Output: {CODE}_valuation_analysis.json
  Task: See valuation-industry-analyzer.md

**Agent D — risk-falsification-analyzer:**
  Input: All above outputs
  Output: {CODE}_risk.json
  Task: See risk-falsification-analyzer.md
```

Each Agent must output results in structured JSON format.

### Step 5: Synthesis (Agent E)

After receiving all 4 Agent outputs, launch Agent E (`growth-decision-synthesizer`):

```
Agent E Input:
  - {CODE}_logic.json (Agent A)
  - {CODE}_indicators.json (Agent B)
  - {CODE}_valuation_analysis.json (Agent C)
  - {CODE}_risk.json (Agent D)

Agent E Output: {CODE}_report.md (final Markdown report)
```

### Step 6: Present Report

Present the Agent E-generated Markdown report directly to the user. Also mention:
- Report save path
- Data sources and timeliness notes
- Reminder: "This report does not constitute investment advice"

---

## Batch Analysis Mode

If the user requests analysis of multiple stocks:

1. Step 2 can use batch mode:
```bash
python3 financial_metrics_calculator.py --input batch_codes.json --output ../data/latest/batch_financial.json
```

2. Steps 3-5 process each stock individually. To save time, prioritize by scoring potential and analyze the most promising ones first.

3. Generate a summary comparison table + individual detailed reports for each stock.

---

## Dashboard Continuous Tracking Mode

If the user says "start tracking XX" or "add to dashboard":

1. Add the stock to `config/tracking_list.json`
2. Record the current analysis score and stage as baseline
3. Set up a 7-day recurring reminder to check key metrics (via Cron or reminders)
4. Tracking file format:
```json
{
  "code": "000001.SZ",
  "added_date": "2025-05-23",
  "baseline_score": 7.2,
  "baseline_stage": "Forecast Period",
  "key_metrics_to_track": [
    {"name": "Contract Liability Growth", "current": "+35%", "alert_threshold": "<10%"},
    {"name": "Gross Margin", "current": "35%", "alert_threshold": "<30%"}
  ],
  "last_check_date": "2025-05-23",
  "check_interval_days": 7
}
```

---

## Error Handling

- **Token expired / API unavailable**: Inform user to check `ZHITU_TOKEN` environment variable or token in `config/settings.json`
- **Stock code not found**: Prompt user to verify code format (e.g., `000001.SZ`)
- **Insufficient financial data** (listed <1 year, etc.): Report which analyses cannot be completed; proceed with what is possible
- **Insufficient peer count**: Mark industry comparison with "insufficient peers, ranking reference limited"
- **Agent output not valid JSON**: Ask Agent to re-output; retry at most 2 times; on failure, use text-form output
