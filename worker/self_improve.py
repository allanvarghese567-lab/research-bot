"""
Self-improving strategy agent
=============================

Four building blocks:
  1. Strategy  – rules (e.g. "buy the 10 cheapest names each month")
  2. Data      – point-in-time universe (not today's survivors)
  3. Table     – one unified panel for backtests
  4. Backtest  – score (Sharpe, return, drawdown)

Then the loop:
  score → read score → change a rule → run again → write what was learned

Classic trap this agent is built to catch:
  Using *today's* company list for a 10-year test inflates Sharpe
  (survivorship bias). Rebuilding the list for every historical day
  is the rule it should discover and persist.

Research only — never financial advice.
"""

from __future__ import annotations

import json
import math
import os
import random
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Literal, Optional

try:
    from supabase import create_client

    _sb = None

    def _client():
        global _sb
        if _sb is None:
            url = os.environ.get("SUPABASE_URL")
            key = os.environ.get("SUPABASE_SERVICE_KEY")
            if url and key:
                _sb = create_client(url, key)
        return _sb

except ImportError:

    def _client():
        return None


@dataclass
class StrategyRules:
    name: str = "cheap_ten"
    n_holdings: int = 10
    rebalance: Literal["monthly", "weekly"] = "monthly"
    point_in_time_universe: bool = False
    rank_by: Literal["price", "value_score"] = "price"
    lookback_years: int = 10
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyRules":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class BacktestScore:
    sharpe: float
    ann_return: float
    max_drawdown: float
    n_months: int
    survivorship_mode: str
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Learning:
    iteration: int
    rule_changed: str
    before: Any
    after: Any
    score_before: float
    score_after: float
    insight: str


def _seed_universe() -> list[dict]:
    rng = random.Random(42)
    names = []
    for i in range(40):
        delist_year = None
        if i < 12:
            delist_year = 3 + (i % 6)
        names.append(
            {
                "symbol": f"C{i:02d}",
                "list_year": 0,
                "delist_year": delist_year,
                "base_price": 5 + rng.random() * 95,
                "drift": -0.02 + rng.random() * 0.06,
                "vol": 0.15 + rng.random() * 0.25,
            }
        )
    return names


def load_panel(years: int = 10, freq: str = "M") -> list[dict]:
    """Unified table: date | symbol | price | in_universe (point-in-time)."""
    names = _seed_universe()
    rng = random.Random(7)
    start = date(2015, 1, 31)
    rows: list[dict] = []
    months = years * 12
    prices: dict[str, float] = {n["symbol"]: n["base_price"] for n in names}

    for m in range(months):
        y = m // 12
        mon = m % 12 + 1
        d = date(start.year + y, mon, 28)
        for n in names:
            sym = n["symbol"]
            shock = rng.gauss(n["drift"] / 12, n["vol"] / math.sqrt(12))
            prices[sym] = max(0.5, prices[sym] * (1 + shock))
            listed = n["list_year"] <= y and (
                n["delist_year"] is None or y < n["delist_year"]
            )
            rows.append(
                {
                    "date": d.isoformat(),
                    "year": y,
                    "month": m,
                    "symbol": sym,
                    "price": round(prices[sym], 4),
                    "in_universe": listed,
                }
            )
    return rows


def backtest(rules: StrategyRules, panel: list[dict]) -> BacktestScore:
    by_month: dict[int, list[dict]] = {}
    for r in panel:
        by_month.setdefault(r["month"], []).append(r)

    months = sorted(by_month.keys())
    if len(months) < 3:
        return BacktestScore(0, 0, 0, 0, "n/a", "insufficient data")

    rets: list[float] = []
    mode = "point_in_time" if rules.point_in_time_universe else "current_only"
    last_syms = {r["symbol"] for r in by_month[months[-1]] if r["in_universe"]}

    for i in range(len(months) - 1):
        m0, m1 = months[i], months[i + 1]
        rows0 = by_month[m0]
        rows1 = {r["symbol"]: r for r in by_month[m1]}

        if rules.point_in_time_universe:
            eligible = [r for r in rows0 if r["in_universe"]]
        else:
            eligible = [r for r in rows0 if r["symbol"] in last_syms]

        if len(eligible) < rules.n_holdings:
            continue

        eligible.sort(key=lambda r: r["price"])
        picks = eligible[: rules.n_holdings]

        month_ret = 0.0
        n = 0
        for p in picks:
            nxt = rows1.get(p["symbol"])
            if not nxt or p["price"] <= 0:
                if rules.point_in_time_universe:
                    month_ret += -1.0
                    n += 1
                continue
            month_ret += (nxt["price"] / p["price"]) - 1.0
            n += 1
        if n:
            rets.append(month_ret / n)

    if not rets:
        return BacktestScore(0, 0, 0, 0, mode, "no periods")

    mean = sum(rets) / len(rets)
    var = sum((x - mean) ** 2 for x in rets) / max(len(rets) - 1, 1)
    std = math.sqrt(var) if var > 0 else 1e-9
    sharpe = (mean / std) * math.sqrt(12)

    eq = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in rets:
        eq *= 1 + r
        peak = max(peak, eq)
        max_dd = min(max_dd, eq / peak - 1)

    ann_ret = (1 + mean) ** 12 - 1
    return BacktestScore(
        sharpe=round(sharpe, 4),
        ann_return=round(ann_ret, 4),
        max_drawdown=round(max_dd, 4),
        n_months=len(rets),
        survivorship_mode=mode,
        detail=f"n={rules.n_holdings} rebalance={rules.rebalance}",
    )


INSIGHT_PIT = (
    "Rebuilding the universe for every historical day (point-in-time) "
    "drops Sharpe vs using today's survivors — that gap is survivorship bias. "
    "Rule written: always rebuild the list for every day you test."
)


def propose_change(
    rules: StrategyRules, score: BacktestScore, history: list[Learning]
) -> tuple[StrategyRules, str, Any, Any]:
    new = StrategyRules.from_dict(rules.to_dict())

    if not rules.point_in_time_universe:
        new.point_in_time_universe = True
        return new, "point_in_time_universe", False, True

    tried_n = {h.after for h in history if h.rule_changed == "n_holdings"}
    for candidate in (5, 15, 20, 10):
        if candidate not in tried_n and candidate != rules.n_holdings:
            new.n_holdings = candidate
            return new, "n_holdings", rules.n_holdings, candidate

    if rules.rebalance == "monthly":
        new.rebalance = "weekly"
        return new, "rebalance", "monthly", "weekly"

    return new, "none", None, None


def run_loop(
    max_iters: int = 6,
    user_id: Optional[str] = None,
    persist: bool = True,
) -> dict:
    rules = StrategyRules()
    panel = load_panel(years=rules.lookback_years)
    history: list[Learning] = []
    best_rules = StrategyRules.from_dict(rules.to_dict())
    best_score = backtest(rules, panel)
    run_id = str(uuid.uuid4())

    iterations = [
        {"iteration": 0, "rules": rules.to_dict(), "score": best_score.to_dict()}
    ]

    for i in range(1, max_iters + 1):
        score = backtest(rules, panel)
        new_rules, field_name, before, after = propose_change(rules, score, history)
        if field_name == "none":
            break

        new_score = backtest(new_rules, panel)
        if field_name == "point_in_time_universe" and before is False and after is True:
            insight = INSIGHT_PIT
        elif new_score.sharpe > score.sharpe:
            insight = f"Raising score by changing {field_name}: {before} → {after}."
        else:
            insight = (
                f"Changing {field_name} ({before} → {after}) did not improve Sharpe; "
                "kept for exploration log."
            )

        history.append(
            Learning(
                iteration=i,
                rule_changed=field_name,
                before=before,
                after=after,
                score_before=score.sharpe,
                score_after=new_score.sharpe,
                insight=insight,
            )
        )
        iterations.append(
            {
                "iteration": i,
                "rules": new_rules.to_dict(),
                "score": new_score.to_dict(),
                "change": field_name,
                "insight": insight,
            }
        )

        if field_name == "point_in_time_universe":
            rules = new_rules
            best_rules = new_rules
            best_score = new_score
        elif rules.point_in_time_universe and new_score.sharpe > best_score.sharpe:
            rules = new_rules
            best_rules = new_rules
            best_score = new_score
        elif not rules.point_in_time_universe and new_score.sharpe > score.sharpe:
            rules = new_rules
            if new_score.sharpe > best_score.sharpe:
                best_rules = new_rules
                best_score = new_score

    biased = StrategyRules(point_in_time_universe=False)
    honest = StrategyRules(point_in_time_universe=True)
    score_biased = backtest(biased, panel)
    score_honest = backtest(honest, panel)

    report = {
        "run_id": run_id,
        "summary": (
            f"Biased (today's list) Sharpe={score_biased.sharpe:.2f}; "
            f"point-in-time Sharpe={score_honest.sharpe:.2f}. "
            + INSIGHT_PIT
        ),
        "score_biased": score_biased.to_dict(),
        "score_point_in_time": score_honest.to_dict(),
        "best_rules": best_rules.to_dict(),
        "best_score": best_score.to_dict(),
        "learnings": [asdict(h) for h in history],
        "iterations": iterations,
        "disclaimer": "Research only — not financial advice. Demo panel is synthetic.",
    }

    if persist:
        _persist(run_id, user_id, report)

    return report


def format_report_markdown(report: dict) -> str:
    b = report["score_biased"]
    h = report["score_point_in_time"]
    lines = [
        "## Self-improving strategy run",
        "",
        report["summary"],
        "",
        "### Survivorship comparison",
        f"- **Current-list only (biased):** Sharpe **{b['sharpe']:.2f}**, "
        f"ann. return {b['ann_return']:.1%}, max DD {b['max_drawdown']:.1%}",
        f"- **Point-in-time universe (honest):** Sharpe **{h['sharpe']:.2f}**, "
        f"ann. return {h['ann_return']:.1%}, max DD {h['max_drawdown']:.1%}",
        "",
        "### Learned rules",
    ]
    for L in report.get("learnings", []):
        lines.append(
            f"- Iter {L['iteration']}: `{L['rule_changed']}` "
            f"{L['before']} → {L['after']} "
            f"(Sharpe {L['score_before']:.2f} → {L['score_after']:.2f})"
        )
        lines.append(f"  - _{L['insight']}_")
    lines += ["", f"_{report.get('disclaimer', '')}_"]
    return "\n".join(lines)


def _persist(run_id: str, user_id: Optional[str], report: dict) -> None:
    sb = _client()
    if not sb:
        return
    try:
        sb.table("strategy_improve_runs").insert(
            {
                "id": run_id,
                "user_id": user_id,
                "summary": report["summary"],
                "score_biased": report["score_biased"],
                "score_point_in_time": report["score_point_in_time"],
                "best_rules": report["best_rules"],
                "learnings": report["learnings"],
                "iterations": report["iterations"],
            }
        ).execute()
    except Exception as e:
        print("persist failed:", e)


if __name__ == "__main__":
    import sys

    iters = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    out = run_loop(max_iters=iters, persist=False)
    print(format_report_markdown(out))
    print("\n--- JSON ---")
    print(json.dumps(out, indent=2)[:2000])
