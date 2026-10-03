# Self-improving strategy agent

An agent that improves itself needs four things:

1. **Strategy** – the rules (e.g. buy the ten cheapest names each month)
2. **Data** – the universe *as it was on each day* (not today’s survivors)
3. **One table** – a unified panel (`date | symbol | price | in_universe`)
4. **Backtest** – a score (Sharpe, return, drawdown)

Then it **loops**: score → read the score → change a rule → run again → write what it learned.

## The trap

Using *today’s* company list for a ten-year test drops delisted names.  
That inflates Sharpe (example pattern: ~1.33 biased vs ~0.55 point-in-time).  
A human notices; a naive agent keeps the highest score.  
This agent is built to **discover and store** the rule:

> Rebuild the list for every day you test (point-in-time universe).

## Run locally

```bash
cd worker
python self_improve.py          # default 6 iterations
python self_improve.py 4        # fewer iterations
```

## Wire into Research Bot worker

From chat / research requests that match self-improve keywords, call:

```python
from self_improve import run_loop, format_report_markdown

report = run_loop(max_iters=6, user_id=req.get("user_id"), persist=True)
text = format_report_markdown(report)
# insert into tickets / agent_messages
```

## Schema

```bash
# Supabase SQL Editor
# run supabase/self_improve_migration.sql
```

Table: `strategy_improve_runs` (summary, biased vs PIT scores, learnings, iterations).

## MCP data platform (optional)

Swap `load_panel()` for a real point-in-time MCP / vendor feed when available.  
The loop and learning format stay the same; only the panel builder changes.

## Disclaimer

Research only — not financial advice. The default panel is **synthetic** for demos and CI.
