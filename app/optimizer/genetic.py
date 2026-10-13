"""
Real genetic walk-forward optimizer.

- Population of gene vectors over the strategy's declared param space
- Fitness from REAL backtests (in-sample) + walk-forward OOS degradation
- Elitism, tournament selection, blend crossover, Gaussian mutation with
  cooling schedule, Pareto front (return / drawdown / Sharpe non-domination)
- Deterministic: fully reproducible for a given (seed, data, config)
"""
from __future__ import annotations

import hashlib
import json
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.backtest.engine import BacktestConfig, run_backtest
from app.optimizer.fitness import evaluate_fitness, evaluate_cadence
from app.strategies.base import Strategy



def _genome_id(genes: Dict[str, Any]) -> str:
    payload = json.dumps(genes, sort_keys=True, separators=(",", ":"), default=str)
    return "g-" + hashlib.sha256(payload.encode()).hexdigest()[:12]


def _summary_metric(summary: Optional[Dict[str, Any]], key: str):
    """Return a computed summary number, or None when that field was not computed."""
    if not isinstance(summary, dict) or key not in summary:
        return None
    value = summary[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _population_row(
    genes: Dict[str, Any],
    result: Any,
    fitness_detail: Optional[Dict[str, Any]],
    rank: int,
    best_fitness: float,
) -> Dict[str, Any]:
    summary = result.summary if result is not None and getattr(result, "ok", False) else None
    score = None
    rejection = None
    if isinstance(fitness_detail, dict):
        if "fitnessScore" in fitness_detail:
            score = fitness_detail.get("fitnessScore")
            rejection = fitness_detail.get("rejectionReason")
    robustness = None
    if isinstance(score, (int, float)) and not isinstance(score, bool) and best_fitness > 0:
        robustness = round(100.0 * (float(score) / best_fitness), 1)
    return {
        "id": _genome_id(genes),
        "rank": rank,
        "genes": genes,
        "fitness": score,
        "inSampleSummary": summary,
        "outOfSampleSummary": None,
        "overallReturn": _summary_metric(summary, "totalReturnPercent"),
        "overallDrawdown": _summary_metric(summary, "maxDrawdownPercent"),
        "sharpeRatio": _summary_metric(summary, "sharpeRatio"),
        "winRate": _summary_metric(summary, "winRate"),
        "tradesCount": _summary_metric(summary, "totalTrades"),
        "robustnessIndex": robustness,
        "rejectionReason": rejection if isinstance(rejection, str) else None,
    }


def _population_note(rows: List[Dict[str, Any]]) -> Optional[str]:
    if not rows:
        return None
    scores = [row.get("fitness") for row in rows]
    if any(isinstance(score, (int, float)) and not isinstance(score, bool) and score > 0 for score in scores):
        return None
    if not scores or not all(score == 0 or score == 0.0 for score in scores):
        return None
    reasons = [row.get("rejectionReason") for row in rows]
    if reasons and all(isinstance(reason, str) and "TRADE STARVATION" in reason for reason in reasons):
        return "Every genome scored fitness 0 because each in-sample backtest had fewer than 30 trades."
    return None


def _non_dominated(items: List[Tuple[float, float, float]]) -> List[int]:
    """Return indices of the non-dominated set. Objective vector:
    (netReturn, -maxDD, sharpe) — all maximized."""
    n = len(items)
    dominated = [False] * n
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            a, b = items[i], items[j]
            if all(b[k] >= a[k] for k in range(3)) and any(b[k] > a[k] for k in range(3)):
                dominated[i] = True
                break
    return [i for i in range(n) if not dominated[i]]


class GeneticOptimizer:
    def __init__(self, strategy: Strategy, seed: int = 42):
        self.strategy = strategy
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)

    # ----------------------------------------------------------------- genes
    def _random_genes(self) -> Dict[str, Any]:
        genes = {}
        for k, (lo, hi, is_int) in self.strategy.param_space.items():
            v = self.rng.uniform(lo, hi)
            genes[k] = int(round(v)) if is_int else v
        return genes

    def _crossover(self, a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        out = {}
        for k in self.strategy.param_space:
            alpha = self.rng.uniform(0.0, 1.0)
            out[k] = a[k] * alpha + b[k] * (1 - alpha)
        return self.strategy.clamp_genes(out)

    def _mutate(self, genes: Dict[str, Any], rate: float, scale: float) -> Dict[str, Any]:
        out = dict(genes)
        for k, (lo, hi, is_int) in self.strategy.param_space.items():
            if self.rng.random() < rate:
                width = (hi - lo) * scale
                out[k] = out[k] + self.rng.gauss(0.0, width)
        return self.strategy.clamp_genes(out)

    # ----------------------------------------------------------------- run
    def run(
        self,
        candles: List[Dict[str, Any]],
        config: BacktestConfig,
        population_size: int = 24,
        generations: int = 20,
        is_fraction: float = 0.7,
        n_trials: int = 250,
        survivors: int = 3,
        on_generation=None,
    ) -> Dict[str, Any]:
        if len(candles) < 300:
            return {"ok": False, "error": f"insufficient data for walk-forward ({len(candles)} candles < 300)"}

        split = int(len(candles) * is_fraction)
        is_candles = candles[:split]
        oos_candles = candles[split:]
        days_is = len(is_candles) * config.bar_minutes / 1440.0
        days_oos = len(oos_candles) * config.bar_minutes / 1440.0
        started = time.time()

        population = [self._random_genes() for _ in range(population_size)]
        generation_history: List[Dict[str, Any]] = []
        best_ever: Dict[str, Any] = {"fitness": -1.0}

        for gen in range(1, generations + 1):
            evaluated = []
            for genes in population:
                result = run_backtest(self.strategy, genes, is_candles, config, pair="")
                if not result.ok:
                    evaluated.append((genes, None, None))
                    continue
                fit = evaluate_fitness(result.summary, self.strategy.active_rule_count, days_is)
                cad = evaluate_cadence([t.exit_epoch for t in result.trades], days_is)
                evaluated.append((genes, result, {"fitness": fit, "cadence": cad}))

            valid = [(g, r, f) for g, r, f in evaluated if r is not None and f["fitness"]["fitnessScore"] > 0]
            if valid:
                valid.sort(key=lambda x: x[2]["fitness"]["fitnessScore"], reverse=True)

            gen_best = None
            if valid:
                g, r, f = valid[0]
                gen_best = {
                    "bestFitness": f["fitness"]["fitnessScore"],
                    "avgFitness": round(np.mean([x[2]["fitness"]["fitnessScore"] for x in valid]), 4),
                    "bestReturn": r.summary["totalReturnPercent"],
                    "bestSharpe": r.summary["sharpeRatio"],
                    "bestDrawdown": r.summary["maxDrawdownPercent"],
                }
                if f["fitness"]["fitnessScore"] > best_ever["fitness"]:
                    best_ever = {
                        "fitness": f["fitness"]["fitnessScore"],
                        "genes": g,
                        "result": r,
                        "fitness_detail": f["fitness"],
                        "cadence": f["cadence"],
                    }
            generation_history.append({"generation": gen, **(gen_best or {"bestFitness": 0.0, "avgFitness": 0.0, "bestReturn": 0.0, "bestSharpe": 0.0, "bestDrawdown": 0.0})})
            if on_generation:
                on_generation(gen, generation_history[-1])

            # ---- build next generation ----
            next_pop: List[Dict[str, Any]] = []
            elite = valid[: min(3, len(valid))]
            next_pop.extend(g for g, _, _ in elite)

            mutation_rate = 0.35 * (0.7 ** (gen / max(1, generations))) + 0.05
            pool = [g for g, _, _ in evaluated] or [self._random_genes()]
            while len(next_pop) < population_size:
                # tournament of 3 over valid (fallback to pool)
                if valid:
                    tourney = max(self.rng.sample(valid, min(3, len(valid))), key=lambda x: x[2]["fitness"]["fitnessScore"])
                    parent = tourney[0]
                else:
                    parent = self.rng.choice(pool)
                other = self.rng.choice(pool) if len(pool) > 1 else parent
                child = self._crossover(parent, other)
                child = self._mutate(child, mutation_rate, scale=0.15)
                next_pop.append(child)

            population = next_pop[:population_size]

        # ---- evaluate survivors in-sample + OOS ----
        survivors_list = []
        valid_all = []
        for genes in population:
            result = run_backtest(self.strategy, genes, is_candles, config, pair="")
            if not result.ok:
                continue
            fit = evaluate_fitness(result.summary, self.strategy.active_rule_count, days_is)
            valid_all.append((genes, result, fit))
        valid_all.sort(key=lambda x: x[2]["fitnessScore"], reverse=True)

        for rank, (genes, result, fit) in enumerate(valid_all[:survivors]):
            oos = run_backtest(self.strategy, genes, oos_candles, config, pair="")
            oos_fit = evaluate_fitness(oos.summary, self.strategy.active_rule_count, days_oos) if oos.ok else None
            survivors_list.append(
                {
                    "rank": rank + 1,
                    "genes": genes,
                    "inSample": result.summary,
                    "outOfSample": oos.summary if oos.ok else None,
                    "fitness": fit,
                    "oosFitness": oos_fit,
                    "isBaselineSeed": rank == 0,
                }
            )

        # Pareto front over the final evaluated population
        pareto = []
        if valid_all:
            vectors = [(x[1].summary["totalReturnPercent"], -x[1].summary["maxDrawdownPercent"], x[1].summary["sharpeRatio"]) for x in valid_all]
            for idx in _non_dominated(vectors):
                g, r, f = valid_all[idx]
                pareto.append({"genes": g, "return": r.summary["totalReturnPercent"], "dd": r.summary["maxDrawdownPercent"], "sharpe": r.summary["sharpeRatio"]})

        best_fitness = float(best_ever["fitness"]) if best_ever["fitness"] > 0 else 0.0
        population_rows = [
            _population_row(g, r, f, rank + 1, best_fitness)
            for rank, (g, r, f) in enumerate(valid_all[:population_size])
        ]
        population_note = _population_note(population_rows)
        best_individual = None
        if best_ever["fitness"] >= 0 and "result" in best_ever:
            best_individual = _population_row(
                best_ever["genes"],
                best_ever["result"],
                best_ever.get("fitness_detail"),
                1,
                best_fitness,
            )
            matched = next((row for row in population_rows if row["id"] == best_individual["id"]), None)
            if matched is not None:
                best_individual["rank"] = matched["rank"]
        elif population_rows:
            best_individual = dict(population_rows[0])
        return {
            "ok": True,
            "strategy": self.strategy.name,
            "populationSize": population_size,
            "generations": generations,
            "splitInSample": split,
            "splitOutOfSample": len(candles) - split,
            "durationMs": int((time.time() - started) * 1000),
            "generationHistory": generation_history,
            "bestIndividual": best_individual,
            "population": population_rows,
            "populationNote": population_note,
            "survivors": survivors_list,
            "paretoFront": pareto,
        }
