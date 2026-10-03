/**
 * Paper-only genetic optimizer panel.
 * The panel asks for more than 600 candles.
 * A route refusal stays visible.
 * While a run is in flight the panel shows that it is running, not a generation number.
 * Generation, genome count, and rows come only from the response.
 * If there is no result yet, the panel does not show Generation 50 or 30 Genomes.
 */
import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Dna, Play, Pause, RotateCcw, CheckCircle2, AlertTriangle, ArrowRight,
  TrendingUp, TrendingDown, Shield, Zap, Sliders, BarChart3, Code2,
  ExternalLink, Layers, Sparkles, Filter, Activity, Copy, Check,
  Award, Eye, RefreshCw, Cpu, Flame, Target, Compass
} from "lucide-react";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
  Legend, AreaChart, Area, BarChart, Bar
} from "recharts";

import { 
  GeneticConfig, 
  GeneticIndividual, 
  GeneticOptimizationResult, 
  GenerationHistoryPoint,
  TradingStrategy,
  GeneticChromosome 
} from "../types";

function refusalDetail(payload: unknown): string {
  if (payload === null || typeof payload !== "object" || !("detail" in payload)) {
    return "";
  }
  const detail = (payload as { detail: unknown }).detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === "string" ? item : JSON.stringify(item)))
      .join("; ");
  }
  if (detail === null || detail === undefined) {
    return "";
  }
  return JSON.stringify(detail);
}

async function readRouteRefusal(res: Response): Promise<string> {
  let payload: unknown = null;
  try {
    payload = await res.json();
  } catch {
    payload = null;
  }
  const detail = refusalDetail(payload);
  if (detail.length > 0) {
    return `Route refused the run (${res.status}): ${detail}`;
  }
  return `Route refused the run (${res.status})`;
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function showFixed(value: unknown, digits: number): string {
  const n = finiteNumber(value);
  return n === null ? "—" : n.toFixed(digits);
}

function showSignedPercent(value: unknown): string {
  const n = finiteNumber(value);
  if (n === null) {
    return "—";
  }
  return `${n >= 0 ? "+" : ""}${n}%`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function resultField(result: GeneticOptimizationResult, key: string): unknown {
  return (result as unknown as Record<string, unknown>)[key];
}

function populationRows(result: GeneticOptimizationResult): GeneticIndividual[] | null {
  const population = resultField(result, "population");
  if (!Array.isArray(population)) {
    return null;
  }
  return population.filter((row): row is GeneticIndividual => isRecord(row));
}

function completedGenerations(result: GeneticOptimizationResult): number | null {
  return finiteNumber(resultField(result, "totalGenerationsCompleted"))
    ?? finiteNumber(resultField(result, "generations"));
}

function historyPoints(result: GeneticOptimizationResult): GenerationHistoryPoint[] {
  const history = resultField(result, "history");
  const generationHistory = resultField(result, "generationHistory");
  const points = Array.isArray(history) ? history : Array.isArray(generationHistory) ? generationHistory : null;
  if (!points) {
    return [];
  }
  return points.filter((point): point is GenerationHistoryPoint => {
    return isRecord(point) && finiteNumber(point.generation) !== null;
  });
}

function eliteCount(result: GeneticOptimizationResult): number | null {
  const explicit = finiteNumber(resultField(result, "survivorCount"));
  if (explicit !== null) {
    return explicit;
  }
  const survivors = resultField(result, "survivors");
  if (Array.isArray(survivors)) {
    return survivors.length;
  }
  const topSurvivors = resultField(result, "topSurvivors");
  if (Array.isArray(topSurvivors)) {
    return topSurvivors.length;
  }
  return null;
}

function responseCandleCount(result: GeneticOptimizationResult, primary: string, alternate: string): number | null {
  return finiteNumber(resultField(result, primary)) ?? finiteNumber(resultField(result, alternate));
}

function nestedNumber(source: unknown, parent: string, key: string): number | null {
  if (!isRecord(source)) {
    return null;
  }
  const child = source[parent];
  if (!isRecord(child)) {
    return null;
  }
  return finiteNumber(child[key]);
}

function isInspectable(value: unknown): value is GeneticIndividual {
  if (!isRecord(value)) {
    return false;
  }
  return typeof value.id === "string"
    && isRecord(value.genes)
    && isRecord(value.inSampleSummary)
    && isRecord(value.outOfSampleSummary);
}

function RunStatusNotice({
  isRunning,
  refusal,
}: {
  isRunning: boolean;
  refusal: string | null;
}) {
  if (isRunning) {
    return (
      <div
        role="status"
        data-testid="genetic-run-status"
        className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 text-center text-purple-300 font-mono text-xs"
      >
        Running
      </div>
    );
  }
  if (refusal) {
    return (
      <div
        role="alert"
        className="bg-rose-950/70 border border-rose-800/80 rounded-xl p-8 text-center text-rose-300 font-mono text-xs"
      >
        {refusal}
      </div>
    );
  }
  return (
    <div
      data-testid="genetic-run-empty"
      className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 text-center text-zinc-500 font-mono text-xs"
    >
      No result yet.
    </div>
  );
}

interface GeneticOptimizerPanelProps {
  strategies: TradingStrategy[];
  onOpenOrchestrator: (strategy: TradingStrategy) => void;
  onOpenBacktester: (pair: string, interval: number, code: string, params: Record<string, any>) => void;
  onReloadStrategies?: () => void;
}

export function GeneticOptimizerPanel({
  strategies,
  onOpenOrchestrator,
  onOpenBacktester,
  onReloadStrategies
}: GeneticOptimizerPanelProps) {
  // Configuration State (Matching user requirements: 30 Individuals, 50 Generations, 3 Survivors)
  const [config, setConfig] = useState<GeneticConfig>({
    populationSize: 30,
    maxGenerations: 50,
    survivorsCount: 3,
    mutationRate: 0.18,
    crossoverRate: 0.80,
    walkForwardSplitPercent: 70, // 70% In-Sample / 30% Out-of-Sample
    assetPair: "BTC/USD",
    interval: 15,
    candleCount: 2400,
    initialBalance: 10000,
    feePercent: 0.26,
    slippagePercent: 0.05
  });

  // Optimizer Execution State
  const [isRunning, setIsRunning] = useState(false);
  const [optimizationResult, setOptimizationResult] = useState<GeneticOptimizationResult | null>(null);
  const [selectedIndividual, setSelectedIndividual] = useState<GeneticIndividual | null>(null);
  const [selectedFilterTab, setSelectedFilterTab] = useState<'all' | 'atr' | 'volume' | 'trend' | 'fvg' | 'cisd' | 'mtf'>('all');
  const [activeViewTab, setActiveViewTab] = useState<'leaderboard' | 'convergence' | 'walkforward' | 'code'>('leaderboard');
  const [sortBy, setSortBy] = useState<'fitness' | 'return' | 'sharpe' | 'drawdown' | 'robustness'>('fitness');
  const [showBaselineGeneDiff, setShowBaselineGeneDiff] = useState(true);

  // Deployment UI feedback state
  const [deploying, setDeploying] = useState(false);
  const [deploySuccess, setDeploySuccess] = useState<string | null>(null);
  const [runRefusal, setRunRefusal] = useState<string | null>(null);
  const [copiedCode, setCopiedCode] = useState(false);

  // Find active baseline strategy object if one is selected
  const activeBaselineStrategy = config.baselineStrategyId 
    ? strategies.find(s => s.id === config.baselineStrategyId)
    : undefined;

  // Handle Strategy Selection from the Orchestrator
  const handleSelectOrchestratorStrategy = (stratId: string) => {
    if (!stratId || stratId === 'none') {
      setConfig(prev => ({
        ...prev,
        baselineStrategyId: undefined,
        baselineStrategyName: undefined
      }));
      return;
    }

    const strat = strategies.find(s => s.id === stratId);
    if (strat) {
      // Map interval from strategy (if it's in seconds e.g. 60, 300, 900 -> convert to minutes for standard candle backtests or match closest)
      let targetInterval = 15;
      if (strat.interval) {
        if (strat.interval >= 60) {
          targetInterval = Math.round(strat.interval / 60);
        } else {
          targetInterval = strat.interval;
        }
        const validIntervals = [1, 5, 15, 30, 60, 240];
        if (!validIntervals.includes(targetInterval)) {
          targetInterval = validIntervals.reduce((prev, curr) => 
            Math.abs(curr - targetInterval) < Math.abs(prev - targetInterval) ? curr : prev
          );
        }
      }

      setConfig(prev => ({
        ...prev,
        baselineStrategyId: strat.id,
        baselineStrategyName: strat.name,
        assetPair: strat.assetPair || prev.assetPair,
        interval: targetInterval
      }));
    }
  };

  // Update selected individual when result changes
  useEffect(() => {
    if (!optimizationResult) {
      return;
    }
    const rows = populationRows(optimizationResult) ?? [];
    const best = isInspectable(resultField(optimizationResult, "bestIndividual"))
      ? resultField(optimizationResult, "bestIndividual") as GeneticIndividual
      : null;
    const stillVisible = selectedIndividual !== null && rows.some((row) => row.id === selectedIndividual.id);
    if (stillVisible) {
      return;
    }
    const firstInspectable = rows.find((row) => isInspectable(row)) ?? null;
    setSelectedIndividual(best ?? firstInspectable);
  }, [optimizationResult, selectedIndividual]);

  const handleRunOptimization = async (isInitialSeed: boolean = false) => {
    setIsRunning(true);
    setDeploySuccess(null);
    setRunRefusal(null);
    setOptimizationResult(null);
    setSelectedIndividual(null);

    try {
      const res = await fetch("/api/genetic/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config)
      });

      if (!res.ok) {
        const message = await readRouteRefusal(res);
        console.error("Optimization failed:", message);
        setRunRefusal(message);
        return;
      }

      const payload: unknown = await res.json();
      if (!isRecord(payload)) {
        const message = `Route refused the run (${res.status}): response had no result`;
        console.error("Optimization failed:", message);
        setRunRefusal(message);
        return;
      }

      setOptimizationResult(payload as unknown as GeneticOptimizationResult);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Optimization refused";
      console.error("Optimization failed:", message);
      setRunRefusal(message);
    } finally {
      setIsRunning(false);
    }
  };

  // Deploy Evolved Strategy directly into Kraken Strategy Orchestrator
  const handleDeployToOrchestrator = async (individual: GeneticIndividual, autoActivate: boolean = true) => {
    if (!individual) return;
    setDeploying(true);
    setDeploySuccess(null);

    try {
      const isSeeded = config.baselineStrategyId && config.baselineStrategyId !== 'none';
      const baseline = isSeeded ? strategies.find(s => s.id === config.baselineStrategyId) : null;
      const nextVersion = baseline ? (baseline.version || 1) + 1 : 1;
      const generationLabel = finiteNumber(individual.generation);
      const evolvedName = baseline
        ? `${baseline.name.replace(/ \(v\d+\)$/, '')} (v${nextVersion})`
        : generationLabel === null
          ? `Evolved Genome (${config.assetPair.replace('/', '')})`
          : `Evolved Genome (${config.assetPair.replace('/', '')}) - Gen ${generationLabel}`;

      const res = await fetch("/api/genetic/deploy-to-orchestrator", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          individual,
          assetPair: config.assetPair,
          interval: config.interval,
          strategyName: evolvedName,
          autoActivate,
          baselineStrategyId: isSeeded ? config.baselineStrategyId : undefined
        })
      });

      if (!res.ok) {
        throw new Error("Failed to deploy evolved strategy.");
      }

      const data = await res.json();
      if (data.archivedStrategy) {
        setDeploySuccess(`✨ Deployed evolved v${data.strategy.version || nextVersion} strategy "${data.strategy.name}" and archived ancestor "${data.archivedStrategy.name}"!`);
      } else {
        setDeploySuccess(`🚀 Strategy "${data.strategy.name}" successfully deployed to Orchestrator!`);
      }
      
      if (onReloadStrategies) {
        onReloadStrategies();
      }

      setTimeout(() => {
        if (data.strategy) {
          onOpenOrchestrator(data.strategy);
        }
      }, 1200);
    } catch (err: any) {
      console.error("Deployment error:", err);
    } finally {
      setDeploying(false);
    }
  };

  // Hand-off directly to the Strategy Backtesting Tab with current individual's parameters
  const handleHandOffToBacktester = (individual: GeneticIndividual) => {
    if (!individual) return;
    const genes = individual.genes;
    
    // Construct runnable JavaScript code with individual's evolved parameters
    const code = optimizationResult?.generatedCode || "";
    const params = {
      atrPeriod: genes.atrPeriod,
      atrStopMultiplier: genes.atrStopMultiplier,
      atrTakeProfitMultiplier: genes.atrTakeProfitMultiplier,
      trendFastEma: genes.trendFastEma,
      trendSlowEma: genes.trendSlowEma,
      rvolThreshold: genes.rvolThreshold,
      fvgMinGapPercent: genes.fvgMinGapPercent,
      cisdLookback: genes.cisdLookback,
      mtfMultiplier: genes.mtfMultiplier,
      mtfTrendEma: genes.mtfTrendEma,
      riskPerTradePercent: genes.riskPerTradePercent
    };

    onOpenBacktester(config.assetPair, config.interval, code, params);
  };

  const handleCopyCode = () => {
    if (optimizationResult?.generatedCode) {
      navigator.clipboard.writeText(optimizationResult.generatedCode);
      setCopiedCode(true);
      setTimeout(() => setCopiedCode(false), 2000);
    }
  };

  // Apply Pre-configured Archetypes
  const handleApplyPreset = (preset: 'smc_fvg' | 'trend_atr' | 'rvol_mtf' | 'low_dd') => {
    if (preset === 'smc_fvg') {
      setConfig(prev => ({
        ...prev,
        populationSize: 30,
        maxGenerations: 50,
        survivorsCount: 3,
        mutationRate: 0.16,
        walkForwardSplitPercent: 70
      }));
    } else if (preset === 'trend_atr') {
      setConfig(prev => ({
        ...prev,
        populationSize: 30,
        maxGenerations: 50,
        survivorsCount: 3,
        mutationRate: 0.18,
        walkForwardSplitPercent: 70
      }));
    } else if (preset === 'rvol_mtf') {
      setConfig(prev => ({
        ...prev,
        populationSize: 30,
        maxGenerations: 50,
        survivorsCount: 3,
        mutationRate: 0.20,
        walkForwardSplitPercent: 75
      }));
    } else if (preset === 'low_dd') {
      setConfig(prev => ({
        ...prev,
        populationSize: 30,
        maxGenerations: 50,
        survivorsCount: 3,
        mutationRate: 0.12,
        walkForwardSplitPercent: 65
      }));
    }
  };

  const population = optimizationResult ? populationRows(optimizationResult) : null;
  const generationCount = optimizationResult ? completedGenerations(optimizationResult) : null;
  const elites = optimizationResult ? eliteCount(optimizationResult) : null;
  const convergenceHistory = optimizationResult ? historyPoints(optimizationResult) : [];
  const inSampleCandleCount = optimizationResult
    ? responseCandleCount(optimizationResult, "inSampleCandles", "splitInSample")
    : null;
  const outOfSampleCandleCount = optimizationResult
    ? responseCandleCount(optimizationResult, "outOfSampleCandles", "splitOutOfSample")
    : null;
  const bestIndividual = optimizationResult && isRecord(resultField(optimizationResult, "bestIndividual"))
    ? resultField(optimizationResult, "bestIndividual") as GeneticIndividual
    : null;
  const bestReturn = finiteNumber(bestIndividual?.overallReturn);
  const bestIsReturn = nestedNumber(bestIndividual, "inSampleSummary", "totalReturnPercent");
  const bestOosReturn = nestedNumber(bestIndividual, "outOfSampleSummary", "totalReturnPercent");
  const bestSharpe = finiteNumber(bestIndividual?.sharpeRatio);
  const bestSortino = nestedNumber(bestIndividual, "inSampleSummary", "sortinoRatio");
  const bestDrawdown = finiteNumber(bestIndividual?.overallDrawdown);
  const bestPeakDrawdown = nestedNumber(bestIndividual, "inSampleSummary", "maxDrawdownUSD");
  const bestWinRate = finiteNumber(bestIndividual?.winRate);
  const bestTrades = finiteNumber(bestIndividual?.tradesCount);
  const bestRobustness = finiteNumber(bestIndividual?.robustnessIndex);

  const compareMetric = (left: number | null, right: number | null, direction: "asc" | "desc"): number => {
    if (left === null && right === null) {
      return 0;
    }
    if (left === null) {
      return 1;
    }
    if (right === null) {
      return -1;
    }
    return direction === "asc" ? left - right : right - left;
  };

  const sortedPopulation = population ? [...population].sort((a, b) => {
    switch (sortBy) {
      case "fitness":
        return compareMetric(finiteNumber(a.fitness), finiteNumber(b.fitness), "desc");
      case "return":
        return compareMetric(finiteNumber(a.overallReturn), finiteNumber(b.overallReturn), "desc");
      case "sharpe":
        return compareMetric(finiteNumber(a.sharpeRatio), finiteNumber(b.sharpeRatio), "desc");
      case "drawdown":
        return compareMetric(finiteNumber(a.overallDrawdown), finiteNumber(b.overallDrawdown), "asc");
      case "robustness":
        return compareMetric(finiteNumber(a.robustnessIndex), finiteNumber(b.robustnessIndex), "desc");
      default: {
        const unreachable: never = sortBy;
        return unreachable;
      }
    }
  }) : [];

  return (
    <div className="space-y-5 max-w-7xl mx-auto pb-12 font-sans">
      {/* 1. Header Banner */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 shadow-sm">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div>
            <div className="flex items-center space-x-3">
              <div className="p-2.5 bg-purple-950/70 border border-purple-800/60 text-purple-400 rounded-lg shadow-inner">
                <Dna className="w-5 h-5 animate-pulse" />
              </div>
              <div>
                <div className="flex items-center space-x-2.5">
                  <h1 className="text-lg font-mono font-bold text-white tracking-tight">
                    Genetic Walk-Forward Strategy Optimizer
                  </h1>
                  <span className="bg-purple-900/60 text-purple-300 border border-purple-700/60 text-[10px] px-2 py-0.5 rounded font-mono font-bold uppercase tracking-wider">
                    Paper
                  </span>
                  <span className="bg-emerald-950/80 text-emerald-400 border border-emerald-800/60 text-[10px] px-2 py-0.5 rounded font-mono font-semibold">
                    In-Sample (70%) + Out-of-Sample (30%)
                  </span>
                </div>
                <p className="text-xs text-zinc-400 font-mono mt-0.5">
                  Paper genetic walk-forward. Generation, genome count, and rows appear only after the route returns them.
                </p>
              </div>
            </div>
          </div>

          {/* Quick Preset Buttons */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-mono text-zinc-500 uppercase tracking-wider mr-1">Archetypes:</span>
            <button
              onClick={() => handleApplyPreset('smc_fvg')}
              className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 rounded text-xs font-mono transition-colors flex items-center gap-1.5"
            >
              <Sparkles className="w-3 h-3 text-purple-400" />
              <span>ICT FVG + CISD</span>
            </button>
            <button
              onClick={() => handleApplyPreset('trend_atr')}
              className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 rounded text-xs font-mono transition-colors flex items-center gap-1.5"
            >
              <TrendingUp className="w-3 h-3 text-emerald-400" />
              <span>ATR Trend Rider</span>
            </button>
            <button
              onClick={() => handleApplyPreset('rvol_mtf')}
              className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 rounded text-xs font-mono transition-colors flex items-center gap-1.5"
            >
              <Layers className="w-3 h-3 text-blue-400" />
              <span>RVOL + MTF Macro</span>
            </button>
            <button
              onClick={() => handleApplyPreset('low_dd')}
              className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 rounded text-xs font-mono transition-colors flex items-center gap-1.5"
            >
              <Shield className="w-3 h-3 text-amber-400" />
              <span>Low-Drawdown Shield</span>
            </button>
          </div>
        </div>

        {/* Parameter Configuration & Run Action Bar */}
        <div className="mt-4 pt-4 border-t border-zinc-800/80 space-y-3">
          {/* ORCHESTRATOR STRATEGY SELECTION SECTION */}
          <div className="bg-zinc-950/70 border border-purple-900/40 rounded-lg p-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 mb-2">
              <div className="flex items-center space-x-2">
                <Cpu className="w-4 h-4 text-purple-400" />
                <span className="text-xs font-mono font-bold text-zinc-200 uppercase tracking-wider">
                  Seed from Orchestrator Strategy
                </span>
                <span className="text-[10px] font-mono text-zinc-500">
                  (Use an active Kraken strategy as evolutionary baseline)
                </span>
              </div>

              {activeBaselineStrategy && (
                <button
                  onClick={() => handleSelectOrchestratorStrategy('none')}
                  className="text-[10px] font-mono text-zinc-400 hover:text-rose-400 flex items-center gap-1 transition-colors self-start sm:self-auto"
                >
                  <RotateCcw className="w-3 h-3" />
                  <span>Reset to Pure Search</span>
                </button>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-center">
              <div className="md:col-span-8">
                <select
                  value={config.baselineStrategyId || 'none'}
                  onChange={(e) => handleSelectOrchestratorStrategy(e.target.value)}
                  className="w-full bg-zinc-900 border border-purple-800/60 text-zinc-200 rounded px-3 py-2 text-xs font-mono focus:border-purple-400 focus:outline-none shadow-sm"
                >
                  <option value="none">
                    ✨ Pure Genetic Exploration (No Orchestrator Baseline Seed)
                  </option>
                  {strategies.filter(s => (s.status || 'active') !== 'archived').length > 0 && (
                    <optgroup label="Orchestrator Strategies (Active / Inactive):">
                      {strategies.filter(s => (s.status || 'active') !== 'archived').map((strat, idx) => (
                        <option key={strat.id ? `strat-${strat.id}` : `strat-opt-${idx}`} value={strat.id}>
                          ⚡ {strat.name || 'Unnamed Strategy'} {strat.version ? `(v${strat.version})` : ''} ({strat.assetPair || 'BTC/USD'} • {strat.interval || 15}s • {(strat.status || 'active').toUpperCase()})
                        </option>
                      ))}
                    </optgroup>
                  )}
                  {strategies.some(s => s.status === 'archived') && (
                    <optgroup label="Archived Strategies:">
                      {strategies.filter(s => s.status === 'archived').map((strat, idx) => (
                        <option key={strat.id ? `arch-${strat.id}` : `arch-opt-${idx}`} value={strat.id}>
                          📦 [ARCHIVED] {strat.name || 'Archived Strategy'} {strat.version ? `(v${strat.version})` : ''} ({strat.assetPair || 'BTC/USD'})
                        </option>
                      ))}
                    </optgroup>
                  )}
                </select>
              </div>

              {/* Quick-Select Strategy Chips */}
              <div className="md:col-span-4 flex flex-wrap items-center gap-1.5 overflow-x-auto py-0.5">
                <span className="text-[10px] font-mono text-zinc-500 uppercase mr-1">Quick:</span>
                {strategies.filter(s => (s.status || 'active') !== 'archived').slice(0, 3).map((strat, idx) => {
                  const isSelected = config.baselineStrategyId === strat.id;
                  return (
                    <button
                      key={strat.id ? `chip-${strat.id}` : `chip-opt-${idx}`}
                      onClick={() => handleSelectOrchestratorStrategy(strat.id)}
                      className={`px-2 py-1 rounded text-[10px] font-mono transition-all truncate max-w-[140px] ${
                        isSelected
                          ? 'bg-purple-900 text-purple-200 border border-purple-500 font-bold shadow-sm'
                          : 'bg-zinc-900 hover:bg-zinc-800 text-zinc-400 border border-zinc-800'
                      }`}
                      title={`${strat.name} (${strat.assetPair})`}
                    >
                      {strat.name.split(' ')[0]} {strat.version ? `v${strat.version}` : ''} ({strat.assetPair.split('/')[0]})
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Active Seed Info Banner */}
            {activeBaselineStrategy && (
              <div className="mt-2.5 pt-2.5 border-t border-purple-950/80 flex flex-col sm:flex-row sm:items-center justify-between text-[11px] font-mono gap-2">
                <div className="flex items-center space-x-2 text-purple-300">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse flex-shrink-0" />
                  <span>
                    Baseline Active: <strong>{activeBaselineStrategy.name}</strong> ({activeBaselineStrategy.assetPair} • {activeBaselineStrategy.interval}s)
                  </span>
                </div>
                <span className="text-[10px] text-zinc-400">
                  Gen 0 will initialize with this strategy's DNA + 13 targeted mutations
                </span>
              </div>
            )}
          </div>

          {/* Genetic & Execution Parameters */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3 items-end">
            {/* Asset Pair */}
            <div>
              <label className="block text-[10px] font-mono text-zinc-400 uppercase tracking-wider mb-1">
                Asset Pair
              </label>
              <select
                value={config.assetPair}
                onChange={(e) => setConfig({ ...config, assetPair: e.target.value })}
                className="w-full bg-zinc-950 border border-zinc-700 text-white rounded px-2.5 py-1.5 text-xs font-mono focus:border-purple-500 focus:outline-none"
              >
                <option value="BTC/USD">BTC/USD (Kraken)</option>
                <option value="ETH/USD">ETH/USD (Kraken)</option>
                <option value="SOL/USD">SOL/USD (Kraken)</option>
                <option value="XRP/USD">XRP/USD (Kraken)</option>
              </select>
            </div>

            {/* Timeframe */}
            <div>
              <label className="block text-[10px] font-mono text-zinc-400 uppercase tracking-wider mb-1">
                Interval
              </label>
              <select
                value={config.interval}
                onChange={(e) => setConfig({ ...config, interval: Number(e.target.value) })}
                className="w-full bg-zinc-950 border border-zinc-700 text-white rounded px-2.5 py-1.5 text-xs font-mono focus:border-purple-500 focus:outline-none"
              >
                <option value={1}>1m (Scalping)</option>
                <option value={5}>5m (Fast Intraday)</option>
                <option value={15}>15m (Optimal WFO)</option>
                <option value={30}>30m (Swing)</option>
                <option value={60}>1h (Macro)</option>
                <option value={240}>4h (Position)</option>
              </select>
            </div>

            {/* Population Size */}
            <div>
              <label className="block text-[10px] font-mono text-zinc-400 uppercase tracking-wider mb-1">
                Population
              </label>
              <div className="relative">
                <input
                  type="number"
                  value={config.populationSize}
                  disabled
                  className="w-full bg-zinc-950/60 border border-zinc-800 text-zinc-300 rounded px-2.5 py-1.5 text-xs font-mono cursor-not-allowed"
                />
                <span className="absolute right-2 top-1.5 text-[9px] font-mono text-zinc-500 font-bold">REQ: 30</span>
              </div>
            </div>

            {/* Generations */}
            <div>
              <label className="block text-[10px] font-mono text-zinc-400 uppercase tracking-wider mb-1">
                Generations
              </label>
              <div className="relative">
                <input
                  type="number"
                  value={config.maxGenerations}
                  disabled
                  className="w-full bg-zinc-950/60 border border-zinc-800 text-zinc-300 rounded px-2.5 py-1.5 text-xs font-mono cursor-not-allowed"
                />
                <span className="absolute right-2 top-1.5 text-[9px] font-mono text-zinc-500 font-bold">REQ: 50</span>
              </div>
            </div>

            {/* Survivors / Elites */}
            <div>
              <label className="block text-[10px] font-mono text-zinc-400 uppercase tracking-wider mb-1">
                Survivors
              </label>
              <div className="relative">
                <input
                  type="number"
                  value={config.survivorsCount}
                  disabled
                  className="w-full bg-zinc-950/60 border border-zinc-800 text-zinc-300 rounded px-2.5 py-1.5 text-xs font-mono cursor-not-allowed"
                />
                <span className="absolute right-2 top-1.5 text-[9px] font-mono text-zinc-500 font-bold">REQ: 3</span>
              </div>
            </div>

            {/* WFO Split */}
            <div>
              <label className="block text-[10px] font-mono text-zinc-400 uppercase tracking-wider mb-1">
                Walk-Forward Split
              </label>
              <select
                value={config.walkForwardSplitPercent}
                onChange={(e) => setConfig({ ...config, walkForwardSplitPercent: Number(e.target.value) })}
                className="w-full bg-zinc-950 border border-zinc-700 text-white rounded px-2.5 py-1.5 text-xs font-mono focus:border-purple-500 focus:outline-none"
              >
                <option value={70}>70% Train / 30% Test</option>
                <option value={75}>75% Train / 25% Test</option>
                <option value={80}>80% Train / 20% Test</option>
              </select>
            </div>

            {/* Run Button */}
            <div>
              <button
                onClick={() => handleRunOptimization(false)}
                disabled={isRunning}
                className={`w-full py-2 px-3 rounded-md text-xs font-mono font-bold flex items-center justify-center space-x-2 transition-all shadow-md ${
                  isRunning
                    ? 'bg-purple-950/60 text-purple-400 border border-purple-700/60 cursor-wait'
                    : 'bg-purple-600 hover:bg-purple-500 text-white border border-purple-500'
                }`}
              >
                {isRunning ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Running</span>
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>{activeBaselineStrategy ? 'Evolve Strategy' : 'Run GA Evolution'}</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {isRunning && (
          <div className="mt-3 pt-3 border-t border-zinc-800" role="status" data-testid="genetic-run-inflight">
            <div className="flex items-center gap-1.5 text-[11px] font-mono text-purple-400 font-semibold">
              <Dna className="w-3 h-3 animate-spin" />
              <span>Running</span>
            </div>
          </div>
        )}

        {runRefusal && (
          <div
            className="mt-3 p-2.5 bg-rose-950/70 border border-rose-800/80 rounded-lg flex items-start gap-2"
            role="alert"
            data-testid="genetic-run-refusal"
          >
            <AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
            <span className="text-xs font-mono text-rose-300">{runRefusal}</span>
          </div>
        )}

        {/* Persistent Success Banner */}
        {deploySuccess && (
          <div className="mt-3 p-2.5 bg-emerald-950/70 border border-emerald-800/80 rounded-lg flex items-center justify-between">
            <div className="flex items-center space-x-2 text-xs font-mono text-emerald-300">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              <span>{deploySuccess}</span>
            </div>
            <span className="text-[10px] font-mono text-emerald-400 uppercase tracking-widest animate-pulse">
              Transferring to Orchestrator...
            </span>
          </div>
        )}
      </div>

      {/* 2. Top Metric Scorecards & Baseline Comparison */}
      {optimizationResult && (
        <div className="space-y-3">
          {/* ORCHESTRATOR BASELINE COMPARISON BANNER */}
          {optimizationResult.baselineComparison && optimizationResult.baselineIndividual && (
            <div className="bg-gradient-to-r from-purple-950/70 via-indigo-950/60 to-zinc-900 border border-purple-800/70 rounded-xl p-4 shadow-sm">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-purple-900/60">
                <div className="flex items-center space-x-2.5">
                  <div className="p-1.5 bg-purple-900/80 rounded-lg text-purple-300">
                    <Award className="w-5 h-5 text-purple-300" />
                  </div>
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="text-xs font-mono font-bold text-white uppercase tracking-wider">
                        Evolutionary Advantage vs Orchestrator Baseline
                      </span>
                      <span className="bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] px-2 py-0.2 rounded font-mono font-bold">
                        +{optimizationResult.baselineComparison.improvementPercent}% Fitness Delta
                      </span>
                    </div>
                    <p className="text-[11px] font-mono text-purple-200/80 mt-0.5">
                      Comparing Winner Genome <strong>{bestIndividual?.id ?? "returned genome"}</strong> against original orchestrator baseline <strong>"{optimizationResult.baselineStrategyName || "Seeded Strategy"}"</strong>.
                    </p>
                  </div>
                </div>

                <div className="flex items-center space-x-2 self-start md:self-auto">
                  <button
                    onClick={() => {
                      if (isInspectable(bestIndividual)) {
                        handleDeployToOrchestrator(bestIndividual, true);
                      }
                    }}
                    disabled={deploying || !isInspectable(bestIndividual)}
                    className="px-3 py-1.5 bg-purple-600 hover:bg-purple-500 text-white rounded text-xs font-mono font-bold flex items-center gap-1.5 transition-colors shadow-sm"
                  >
                    {deploying ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3 fill-current" />}
                    <span>Deploy Evolved Winner</span>
                  </button>
                </div>
              </div>

              {/* 4 Delta Comparative Metric Pills */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
                <div className="bg-zinc-950/80 border border-purple-900/50 p-2.5 rounded-lg">
                  <span className="text-[10px] font-mono text-zinc-400 uppercase block">Return Delta</span>
                  <div className="text-sm font-mono font-bold text-emerald-400 mt-0.5 flex items-baseline gap-1">
                    <span>{optimizationResult.baselineComparison.returnDelta >= 0 ? '+' : ''}{optimizationResult.baselineComparison.returnDelta}%</span>
                    <span className="text-[10px] text-zinc-500 font-normal">
                      (from +{optimizationResult.baselineIndividual.overallReturn}%)
                    </span>
                  </div>
                </div>

                <div className="bg-zinc-950/80 border border-purple-900/50 p-2.5 rounded-lg">
                  <span className="text-[10px] font-mono text-zinc-400 uppercase block">Sharpe Delta</span>
                  <div className="text-sm font-mono font-bold text-purple-300 mt-0.5 flex items-baseline gap-1">
                    <span>{optimizationResult.baselineComparison.sharpeDelta >= 0 ? '+' : ''}{optimizationResult.baselineComparison.sharpeDelta}</span>
                    <span className="text-[10px] text-zinc-500 font-normal">
                      (from {showFixed(optimizationResult.baselineIndividual.sharpeRatio, 2)})
                    </span>
                  </div>
                </div>

                <div className="bg-zinc-950/80 border border-purple-900/50 p-2.5 rounded-lg">
                  <span className="text-[10px] font-mono text-zinc-400 uppercase block">Max DD Delta</span>
                  <div className="text-sm font-mono font-bold text-rose-300 mt-0.5 flex items-baseline gap-1">
                    <span>{optimizationResult.baselineComparison.drawdownDelta >= 0 ? '-' : '+'}{Math.abs(optimizationResult.baselineComparison.drawdownDelta)}%</span>
                    <span className="text-[10px] text-zinc-500 font-normal">
                      (was -{optimizationResult.baselineIndividual.overallDrawdown}%)
                    </span>
                  </div>
                </div>

                <div className="bg-zinc-950/80 border border-purple-900/50 p-2.5 rounded-lg">
                  <span className="text-[10px] font-mono text-zinc-400 uppercase block">Win Rate Delta</span>
                  <div className="text-sm font-mono font-bold text-zinc-200 mt-0.5 flex items-baseline gap-1">
                    <span>{optimizationResult.baselineComparison.winRateDelta >= 0 ? '+' : ''}{optimizationResult.baselineComparison.winRateDelta}%</span>
                    <span className="text-[10px] text-zinc-500 font-normal">
                      (was {optimizationResult.baselineIndividual.winRate}%)
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Top Metric Scorecards (Best Genome Telemetry) */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {/* Best Genome Return */}
          <div className="bg-zinc-900 border border-zinc-800 p-3.5 rounded-lg shadow-sm">
            <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-wider block">
              Best Genome Return
            </span>
            <div className="text-xl font-mono font-bold text-white mt-1 flex items-baseline gap-1.5">
              <span className={bestReturn !== null && bestReturn >= 0 ? "text-emerald-400" : "text-rose-400"}>
                {bestReturn === null ? "—" : `${bestReturn >= 0 ? "+" : ""}${bestReturn}%`}
              </span>
            </div>
            <span className="text-[10px] font-mono text-zinc-500 mt-1 block">
              {bestIsReturn === null ? "IS: —" : `IS: ${bestIsReturn >= 0 ? "+" : ""}${bestIsReturn}%`}
              {" | "}
              {bestOosReturn === null ? "OOS: —" : `OOS: ${bestOosReturn >= 0 ? "+" : ""}${bestOosReturn}%`}
            </span>
          </div>

          {/* Sharpe Ratio */}
          <div className="bg-zinc-900 border border-zinc-800 p-3.5 rounded-lg shadow-sm">
            <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-wider block">
              Sharpe Ratio
            </span>
            <div className="text-xl font-mono font-bold text-purple-400 mt-1">
              {bestSharpe === null ? "—" : bestSharpe.toFixed(2)}
            </div>
            <span className="text-[10px] font-mono text-zinc-500 mt-1 block">
              {bestSortino === null ? "Sortino: —" : `Sortino: ${bestSortino.toFixed(2)}`}
            </span>
          </div>

          {/* Max Drawdown */}
          <div className="bg-zinc-900 border border-zinc-800 p-3.5 rounded-lg shadow-sm">
            <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-wider block">
              Max Drawdown
            </span>
            <div className="text-xl font-mono font-bold text-rose-400 mt-1">
              {bestDrawdown === null ? "—" : `-${bestDrawdown}%`}
            </div>
            <span className="text-[10px] font-mono text-zinc-500 mt-1 block">
              {bestPeakDrawdown === null ? "Peak DD: —" : `Peak DD: $${bestPeakDrawdown.toFixed(0)}`}
            </span>
          </div>

          {/* Win Rate */}
          <div className="bg-zinc-900 border border-zinc-800 p-3.5 rounded-lg shadow-sm">
            <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-wider block">
              Win Rate
            </span>
            <div className="text-xl font-mono font-bold text-white mt-1">
              {bestWinRate === null ? "—" : `${bestWinRate}%`}
            </div>
            <span className="text-[10px] font-mono text-zinc-500 mt-1 block">
              {bestTrades === null ? "—" : `${bestTrades} total trades`}
            </span>
          </div>

          {/* Walk-Forward Robustness */}
          <div className="bg-zinc-900 border border-zinc-800 p-3.5 rounded-lg shadow-sm">
            <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-wider block">
              WFO Robustness
            </span>
            <div className="text-xl font-mono font-bold text-amber-400 mt-1 flex items-center gap-1">
              <span>{bestRobustness === null ? "—" : `${bestRobustness}%`}</span>
              <Award className="w-4 h-4 text-amber-400" />
            </div>
            <span className="text-[10px] font-mono text-zinc-500 mt-1 block">
              {bestRobustness === null ? "—" : bestRobustness >= 70 ? "Low Overfit Risk" : "Moderate Overfit"}
            </span>
          </div>

          {/* Top Survivors */}
          <div className="bg-gradient-to-br from-purple-950/40 to-zinc-900 border border-purple-800/50 p-3.5 rounded-lg shadow-sm flex flex-col justify-between">
            <div>
              <span className="text-[10px] font-mono text-purple-300 uppercase tracking-wider block">
                Elite Survivors
              </span>
              <div className="text-xl font-mono font-bold text-white mt-1">
                {elites !== null && population !== null
                  ? `${elites} / ${population.length} Elites`
                  : elites !== null
                    ? `${elites} Elites`
                    : "—"}
              </div>
            </div>
            <span className="text-[10px] font-mono text-purple-400">
              Ready for Orchestrator
            </span>
          </div>
        </div>
      </div>
      )}

      {/* 3. Main Workspace: Dual Split Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* LEFT COLUMN: Population Grid & Generational Convergence (7 Cols) */}
        <div className="lg:col-span-7 space-y-5">
          {/* Sub Navigation Bar */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-1.5 flex items-center justify-between">
            <div className="flex items-center space-x-1">
              <button
                onClick={() => setActiveViewTab('leaderboard')}
                className={`px-3 py-1.5 rounded text-xs font-mono font-medium transition-all ${
                  activeViewTab === 'leaderboard'
                    ? 'bg-zinc-800 text-white shadow-sm border border-zinc-700'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                <span>Leaderboard</span>
              </button>
              <button
                onClick={() => setActiveViewTab('convergence')}
                className={`px-3 py-1.5 rounded text-xs font-mono font-medium transition-all ${
                  activeViewTab === 'convergence'
                    ? 'bg-zinc-800 text-white shadow-sm border border-zinc-700'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                <span>Convergence</span>
              </button>
              <button
                onClick={() => setActiveViewTab('walkforward')}
                className={`px-3 py-1.5 rounded text-xs font-mono font-medium transition-all ${
                  activeViewTab === 'walkforward'
                    ? 'bg-zinc-800 text-white shadow-sm border border-zinc-700'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                <span>In-Sample vs Out-of-Sample</span>
              </button>
            </div>

            {/* Sorting for Leaderboard */}
            {activeViewTab === 'leaderboard' && (
              <div className="flex items-center space-x-1 text-xs font-mono text-zinc-400 pr-1">
                <span className="text-[10px] text-zinc-500 uppercase">Sort:</span>
                <select
                  value={sortBy}
                  onChange={(e: any) => setSortBy(e.target.value)}
                  className="bg-zinc-950 border border-zinc-700 text-zinc-300 rounded px-1.5 py-0.5 text-xs font-mono"
                >
                  <option value="fitness">Fitness Score</option>
                  <option value="return">Overall Return</option>
                  <option value="sharpe">Sharpe Ratio</option>
                  <option value="drawdown">Lowest Drawdown</option>
                  <option value="robustness">Robustness Index</option>
                </select>
              </div>
            )}
          </div>

          {activeViewTab === 'leaderboard' && !optimizationResult && (
            <RunStatusNotice isRunning={isRunning} refusal={runRefusal} />
          )}

          {/* Population leaderboard — rows come only from the response */}
          {activeViewTab === 'leaderboard' && optimizationResult && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden shadow-sm">
              <div className="p-3.5 border-b border-zinc-800 flex items-center justify-between bg-zinc-950/40">
                <div className="flex items-center space-x-2">
                  <Flame className="w-4 h-4 text-amber-400" />
                  <h3 className="text-xs font-mono font-bold text-white uppercase tracking-wider">
                    {generationCount === null ? "Evolved Population" : `Evolved Population (Generation ${generationCount})`}
                  </h3>
                  {population !== null && (
                    <span className="bg-zinc-800 text-zinc-400 text-[10px] px-1.5 py-0.2 rounded font-mono" data-testid="genetic-genome-count">
                      {population.length} Genomes
                    </span>
                  )}
                </div>
                <div className="flex items-center space-x-2 text-[11px] font-mono text-zinc-400">
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-amber-400" />
                    <span>{elites === null ? "Survivors" : `Top ${elites} Survivors`}</span>
                  </span>
                </div>
              </div>

              {/* Data Table */}
              <div className="overflow-x-auto max-h-[500px]">
                <table className="w-full text-left border-collapse text-xs font-mono">
                  <thead>
                    <tr className="bg-zinc-950/80 border-b border-zinc-800 text-[10px] text-zinc-400 uppercase tracking-wider sticky top-0 z-10">
                      <th className="py-2.5 px-3">Rank</th>
                      <th className="py-2.5 px-3">Genome ID</th>
                      <th className="py-2.5 px-3 text-right">Fitness</th>
                      <th className="py-2.5 px-3 text-right">Return</th>
                      <th className="py-2.5 px-3 text-right">Sharpe</th>
                      <th className="py-2.5 px-3 text-right">Max DD</th>
                      <th className="py-2.5 px-3 text-right">Win Rate</th>
                      <th className="py-2.5 px-3 text-right">Robustness</th>
                      <th className="py-2.5 px-3 text-center">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60">
                    {sortedPopulation.map((ind, idx) => {
                      const isSelected = selectedIndividual?.id === ind.id;
                      const isSurvivor = ind.isSurvivor === true;
                      const rank = finiteNumber(ind.rank);
                      const fitness = finiteNumber(ind.fitness);
                      const overallReturn = finiteNumber(ind.overallReturn);
                      const sharpeRatio = finiteNumber(ind.sharpeRatio);
                      const overallDrawdown = finiteNumber(ind.overallDrawdown);
                      const winRate = finiteNumber(ind.winRate);
                      const robustnessIndex = finiteNumber(ind.robustnessIndex);
                      const genomeId = typeof ind.id === "string" && ind.id.length > 0 ? ind.id : null;
                      
                      return (
                        <tr
                          key={`${genomeId ?? "row"}-${idx}`}
                          onClick={() => {
                            if (isInspectable(ind)) {
                              setSelectedIndividual(ind);
                            }
                          }}
                          className={`cursor-pointer transition-colors ${
                            isSelected
                              ? 'bg-purple-950/40 border-l-2 border-l-purple-500'
                              : isSurvivor
                              ? 'bg-amber-950/15 hover:bg-zinc-800/60'
                              : 'hover:bg-zinc-800/40'
                          }`}
                        >
                          {/* Rank */}
                          <td className="py-2.5 px-3 font-semibold">
                            <div className="flex items-center space-x-1.5">
                              {ind.isBaselineSeed ? (
                                <span className="bg-purple-950 text-purple-300 border border-purple-700 text-[9px] px-1.5 py-0.2 rounded font-bold flex items-center gap-1">
                                  <span>SEED</span>
                                  <span>⚡</span>
                                </span>
                              ) : isSurvivor ? (
                                <span className="bg-amber-950 text-amber-400 border border-amber-800/80 text-[9px] px-1.5 py-0.2 rounded font-bold">
                                  {rank === null ? "Survivor" : `#${rank}`}
                                </span>
                              ) : (
                                <span className="text-zinc-500 text-[11px]">
                                  {rank === null ? "—" : `#${rank}`}
                                </span>
                              )}
                            </div>
                          </td>

                          {/* ID */}
                          <td className="py-2.5 px-3 text-zinc-300 font-mono">
                            <div className="flex items-center gap-1.5">
                              <Dna className="w-3 h-3 text-purple-400 opacity-70" />
                              <span className="font-semibold">{genomeId ?? "—"}</span>
                              {ind.isBaselineSeed && (
                                <span className="bg-zinc-800 text-purple-300 border border-purple-900/60 text-[9px] px-1 rounded">
                                  Orchestrator Baseline
                                </span>
                              )}
                            </div>
                          </td>

                          {/* Fitness */}
                          <td className="py-2.5 px-3 text-right font-bold text-purple-400">
                            {fitness === null ? "—" : fitness.toFixed(1)}
                          </td>

                          {/* Return */}
                          <td className="py-2.5 px-3 text-right font-semibold">
                            <span className={overallReturn !== null && overallReturn >= 0 ? "text-emerald-400" : "text-rose-400"}>
                              {overallReturn === null ? "—" : `${overallReturn >= 0 ? "+" : ""}${overallReturn}%`}
                            </span>
                          </td>

                          {/* Sharpe */}
                          <td className="py-2.5 px-3 text-right text-zinc-300">
                            {sharpeRatio === null ? "—" : sharpeRatio.toFixed(2)}
                          </td>

                          {/* Max DD */}
                          <td className="py-2.5 px-3 text-right text-rose-400">
                            {overallDrawdown === null ? "—" : `-${overallDrawdown}%`}
                          </td>

                          {/* Win Rate */}
                          <td className="py-2.5 px-3 text-right text-zinc-300">
                            {winRate === null ? "—" : `${winRate}%`}
                          </td>

                          {/* Robustness */}
                          <td className="py-2.5 px-3 text-right">
                            <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                              robustnessIndex === null
                                ? "bg-zinc-900 text-zinc-500 border border-zinc-800"
                                : robustnessIndex >= 70
                                ? "bg-emerald-950/70 text-emerald-400 border border-emerald-800/60"
                                : robustnessIndex >= 50
                                ? "bg-amber-950/70 text-amber-400 border border-amber-800/60"
                                : "bg-rose-950/70 text-rose-400 border border-rose-800/60"
                            }`}>
                              {robustnessIndex === null ? "—" : `${robustnessIndex}%`}
                            </span>
                          </td>

                          {/* Action */}
                          <td className="py-2.5 px-3 text-center">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                if (isInspectable(ind)) {
                                  setSelectedIndividual(ind);
                                }
                              }}
                              className="px-2 py-1 bg-zinc-800 hover:bg-purple-900/60 hover:text-purple-300 text-zinc-400 rounded text-[10px] font-mono transition-colors"
                            >
                              Inspect DNA
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {activeViewTab === 'convergence' && !optimizationResult && (
            <RunStatusNotice isRunning={isRunning} refusal={runRefusal} />
          )}

          {activeViewTab === 'convergence' && optimizationResult && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 shadow-sm">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h3 className="text-xs font-mono font-bold text-white uppercase tracking-wider">
                    {generationCount === null
                      ? "Generational Convergence"
                      : `Generational Convergence (Generation ${generationCount})`}
                  </h3>
                  <p className="text-[11px] font-mono text-zinc-400 mt-0.5">
                    {convergenceHistory.length === 0
                      ? "No generation history in the response."
                      : `Best Fitness vs Average Population Fitness across ${convergenceHistory.length} returned generations.`}
                  </p>
                </div>
                <div className="flex items-center space-x-3 text-[11px] font-mono">
                  <span className="flex items-center gap-1 text-emerald-400">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
                    <span>Best Fitness</span>
                  </span>
                  <span className="flex items-center gap-1 text-purple-400">
                    <span className="w-2.5 h-2.5 rounded-full bg-purple-400" />
                    <span>Avg Fitness</span>
                  </span>
                </div>
              </div>

              {/* Convergence Line Chart */}
              <div className="h-72 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={convergenceHistory}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                    <XAxis 
                      dataKey="generation" 
                      stroke="#71717a" 
                      tick={{ fontSize: 10, fill: '#a1a1aa' }} 
                      label={{ value: 'Generation', position: 'insideBottomRight', offset: -5, fill: '#71717a', fontSize: 10 }}
                    />
                    <YAxis 
                      stroke="#71717a" 
                      tick={{ fontSize: 10, fill: '#a1a1aa' }} 
                    />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#18181b', borderColor: '#3f3f46', borderRadius: '6px', fontSize: '11px' }}
                      itemStyle={{ color: '#e4e4e7' }}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="bestFitness" 
                      name="Best Fitness" 
                      stroke="#34d399" 
                      strokeWidth={2.5} 
                      dot={{ r: 2, fill: '#34d399' }} 
                    />
                    <Line 
                      type="monotone" 
                      dataKey="avgFitness" 
                      name="Avg Population Fitness" 
                      stroke="#c084fc" 
                      strokeWidth={1.5} 
                      strokeDasharray="4 4"
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {activeViewTab === 'walkforward' && !selectedIndividual && (
            optimizationResult ? (
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 text-center text-zinc-500 font-mono text-xs">
                No walk-forward individual in the response.
              </div>
            ) : (
              <RunStatusNotice isRunning={isRunning} refusal={runRefusal} />
            )
          )}

          {/* TAB 3: IN-SAMPLE VS OUT-OF-SAMPLE WALK-FORWARD COMPARISON */}
          {activeViewTab === 'walkforward' && selectedIndividual && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 shadow-sm space-y-4">
              <div>
                <h3 className="text-xs font-mono font-bold text-white uppercase tracking-wider">
                  Walk-Forward In-Sample vs Out-of-Sample Verification
                </h3>
                <p className="text-[11px] font-mono text-zinc-400 mt-0.5">
                  Validates generalization by comparing In-Sample training performance (70% historical OHLC) against unseen Out-of-Sample validation (30%).
                </p>
              </div>

              <div className={`grid grid-cols-1 ${optimizationResult?.baselineIndividual ? 'lg:grid-cols-3' : 'sm:grid-cols-2'} gap-4`}>
                {/* Baseline Card (if seeded from Orchestrator) */}
                {optimizationResult?.baselineIndividual && (
                  <div className="bg-zinc-950 border border-purple-900/40 p-3.5 rounded-lg">
                    <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
                      <span className="text-xs font-mono font-bold text-purple-300 flex items-center gap-1">
                        <span>⚡ Orchestrator Baseline</span>
                      </span>
                      <span className="text-[10px] font-mono text-zinc-500 truncate max-w-[120px]" title={optimizationResult.baselineStrategyName}>
                        {optimizationResult.baselineStrategyName || 'Original'}
                      </span>
                    </div>
                    <div className="mt-3 space-y-2 text-xs font-mono">
                      <div className="flex justify-between">
                        <span className="text-zinc-400">Total Return:</span>
                        <span className={(finiteNumber(optimizationResult.baselineIndividual.overallReturn) ?? -1) >= 0 ? "text-purple-400 font-bold" : "text-rose-400 font-bold"}>
                          {showSignedPercent(optimizationResult.baselineIndividual.overallReturn)}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-zinc-400">Sharpe Ratio:</span>
                        <span className="text-white">{showFixed(optimizationResult.baselineIndividual.sharpeRatio, 2)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-zinc-400">Max Drawdown:</span>
                        <span className="text-rose-400">{finiteNumber(optimizationResult.baselineIndividual.overallDrawdown) === null ? "—" : `-${optimizationResult.baselineIndividual.overallDrawdown}%`}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-zinc-400">Profit Factor:</span>
                        <span className="text-white">{showFixed(nestedNumber(optimizationResult.baselineIndividual, "inSampleSummary", "profitFactor"), 2)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-zinc-400">Win Rate:</span>
                        <span className="text-white">{optimizationResult.baselineIndividual.winRate}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-zinc-400">Total Trades:</span>
                        <span className="text-zinc-300">{optimizationResult.baselineIndividual.tradesCount}</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* In-Sample Card */}
                <div className="bg-zinc-950 border border-zinc-800 p-3.5 rounded-lg">
                  <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
                    <span className="text-xs font-mono font-bold text-emerald-400">
                      In-Sample Train (70% Data)
                    </span>
                    {inSampleCandleCount !== null && (
                      <span className="text-[10px] font-mono text-zinc-500">
                        {inSampleCandleCount} Candles
                      </span>
                    )}
                  </div>
                  <div className="mt-3 space-y-2 text-xs font-mono">
                    <div className="flex justify-between">
                      <span className="text-zinc-400">Total Return:</span>
                      <span className="text-emerald-400 font-bold">{showSignedPercent(selectedIndividual.inSampleSummary.totalReturnPercent)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-400">Sharpe Ratio:</span>
                      <span className="text-white">{showFixed(selectedIndividual.inSampleSummary.sharpeRatio, 2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-400">Max Drawdown:</span>
                      <span className="text-rose-400">{finiteNumber(selectedIndividual.inSampleSummary.maxDrawdownPercent) === null ? "—" : `-${selectedIndividual.inSampleSummary.maxDrawdownPercent}%`}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-400">Profit Factor:</span>
                      <span className="text-white">{showFixed(selectedIndividual.inSampleSummary.profitFactor, 2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-400">Win Rate:</span>
                      <span className="text-white">{selectedIndividual.inSampleSummary.winRate}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-400">Total Trades:</span>
                      <span className="text-zinc-300">{selectedIndividual.inSampleSummary.totalTrades}</span>
                    </div>
                  </div>
                </div>

                {/* Out-of-Sample Card */}
                <div className="bg-zinc-950 border border-purple-900/60 p-3.5 rounded-lg">
                  <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
                    <span className="text-xs font-mono font-bold text-purple-400">
                      Out-of-Sample Test (30% Data)
                    </span>
                    {outOfSampleCandleCount !== null && (
                      <span className="text-[10px] font-mono text-purple-300">
                        {outOfSampleCandleCount} Candles
                      </span>
                    )}
                  </div>
                  <div className="mt-3 space-y-2 text-xs font-mono">
                    <div className="flex justify-between">
                      <span className="text-zinc-400">Total Return:</span>
                      <span className="text-purple-400 font-bold">{showSignedPercent(selectedIndividual.outOfSampleSummary.totalReturnPercent)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-400">Sharpe Ratio:</span>
                      <span className="text-white">{showFixed(selectedIndividual.outOfSampleSummary.sharpeRatio, 2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-400">Max Drawdown:</span>
                      <span className="text-rose-400">{finiteNumber(selectedIndividual.outOfSampleSummary.maxDrawdownPercent) === null ? "—" : `-${selectedIndividual.outOfSampleSummary.maxDrawdownPercent}%`}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-400">Profit Factor:</span>
                      <span className="text-white">{showFixed(selectedIndividual.outOfSampleSummary.profitFactor, 2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-400">Win Rate:</span>
                      <span className="text-white">{selectedIndividual.outOfSampleSummary.winRate}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-400">Total Trades:</span>
                      <span className="text-zinc-300">{selectedIndividual.outOfSampleSummary.totalTrades}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Overfitting Stability Radar Indicator */}
              <div className="p-3 bg-zinc-950 border border-zinc-800 rounded-lg flex items-center justify-between">
                <div>
                  <span className="text-[11px] font-mono text-zinc-400 uppercase tracking-wider block">
                    Curve-Fitting Risk Assessment
                  </span>
                  <p className="text-xs font-mono text-zinc-300 mt-0.5">
                    {finiteNumber(selectedIndividual.robustnessIndex) === null
                      ? "Robustness was not in the response."
                      : selectedIndividual.robustnessIndex >= 70
                      ? "Strategy exhibits high out-of-sample persistence. Low risk of curve-fitting."
                      : "Moderate performance drop in validation. Recommend keeping ATR buffer wide."}
                  </p>
                </div>
                <div className="text-right">
                  <span className="text-xs font-mono text-zinc-500 uppercase">Robustness</span>
                  <div className="text-lg font-mono font-bold text-amber-400">
                    {finiteNumber(selectedIndividual.robustnessIndex) === null ? "—" : `${selectedIndividual.robustnessIndex}%`}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* RIGHT COLUMN: Gene DNA Chromosome Inspector & Hand-Off Hub (5 Cols) */}
        <div className="lg:col-span-5 space-y-4">
          {selectedIndividual ? (
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 shadow-sm space-y-4">
              {/* Individual Header */}
              <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-xs font-mono font-bold text-white">
                      Genome DNA: {selectedIndividual.id}
                    </span>
                    {selectedIndividual.isBaselineSeed && (
                      <span className="bg-purple-950 text-purple-300 border border-purple-700 text-[9px] px-1.5 py-0.2 rounded font-bold uppercase">
                        Orchestrator Baseline
                      </span>
                    )}
                    {selectedIndividual.isSurvivor && (
                      <span className="bg-amber-950 text-amber-400 border border-amber-800/80 text-[9px] px-1.5 py-0.2 rounded font-bold uppercase">
                        {finiteNumber(selectedIndividual.rank) === null ? "Survivor" : `Survivor #${selectedIndividual.rank}`}
                      </span>
                    )}
                  </div>
                  <span className="text-[10px] font-mono text-zinc-500 block mt-0.5">
                    Fitness: {finiteNumber(selectedIndividual.fitness) === null ? "—" : selectedIndividual.fitness}
                    {" | "}
                    {selectedIndividual.isBaselineSeed
                      ? "Seed Ancestor"
                      : finiteNumber(selectedIndividual.generation) === null
                        ? "Returned genome"
                        : `Generation ${selectedIndividual.generation}`}
                  </span>
                </div>

                {/* Hand-Off Actions */}
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => handleHandOffToBacktester(selectedIndividual)}
                    className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-emerald-400 border border-emerald-800/60 rounded text-xs font-mono flex items-center gap-1 transition-colors"
                    title="Send parameters to Strategy Backtesting Tab"
                  >
                    <BarChart3 className="w-3 h-3" />
                    <span>Backtest</span>
                  </button>
                  <button
                    onClick={() => handleDeployToOrchestrator(selectedIndividual, true)}
                    disabled={deploying}
                    className="px-3 py-1 bg-purple-600 hover:bg-purple-500 text-white rounded text-xs font-mono font-bold flex items-center gap-1.5 transition-colors shadow-sm"
                    title="Deploy directly into Strategy Orchestrator"
                  >
                    {deploying ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3 fill-current" />}
                    <span>Deploy</span>
                  </button>
                </div>
              </div>

              {/* Filter Module Tabs */}
              <div className="flex flex-wrap gap-1 border-b border-zinc-800/80 pb-2">
                {[
                  { id: 'all', label: 'All Genes' },
                  { id: 'atr', label: 'ATR Stops' },
                  { id: 'volume', label: 'RVOL Volume' },
                  { id: 'trend', label: 'Trend EMAs' },
                  { id: 'fvg', label: 'FVG Gap' },
                  { id: 'cisd', label: 'CISD SMC' },
                  { id: 'mtf', label: 'MTF Macro' },
                ].map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setSelectedFilterTab(tab.id as any)}
                    className={`px-2 py-1 rounded text-[11px] font-mono transition-colors ${
                      selectedFilterTab === tab.id
                        ? 'bg-purple-950/80 text-purple-300 border border-purple-800/80 font-bold'
                        : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60'
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* 7 Quant Gene Modules Breakdown */}
              <div className="space-y-3 max-h-[420px] overflow-y-auto pr-1">
                {/* 1. ATR Dynamic Stop & Take Profit */}
                {(selectedFilterTab === 'all' || selectedFilterTab === 'atr') && (
                  <div className="bg-zinc-950 border border-zinc-800 p-3 rounded-lg space-y-2">
                    <div className="flex items-center justify-between text-xs font-mono font-semibold text-emerald-400">
                      <span className="flex items-center gap-1.5">
                        <Shield className="w-3.5 h-3.5" />
                        <span>1. ATR Dynamic Stop &amp; Take-Profit</span>
                      </span>
                      <span className="text-[10px] bg-emerald-950 text-emerald-400 px-1.5 py-0.2 rounded border border-emerald-800">
                        Active
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs font-mono text-zinc-300">
                      <div className="bg-zinc-900/80 p-2 rounded">
                        <span className="text-[10px] text-zinc-500 block">ATR Period</span>
                        <span className="font-bold text-white">{selectedIndividual.genes.atrPeriod} bars</span>
                      </div>
                      <div className="bg-zinc-900/80 p-2 rounded">
                        <span className="text-[10px] text-zinc-500 block">Stop-Loss Mult</span>
                        <span className="font-bold text-rose-400">{selectedIndividual.genes.atrStopMultiplier}x ATR</span>
                      </div>
                      <div className="bg-zinc-900/80 p-2 rounded">
                        <span className="text-[10px] text-zinc-500 block">Take-Profit Mult</span>
                        <span className="font-bold text-emerald-400">{selectedIndividual.genes.atrTakeProfitMultiplier}x ATR</span>
                      </div>
                      <div className="bg-zinc-900/80 p-2 rounded">
                        <span className="text-[10px] text-zinc-500 block">Trailing Stop</span>
                        <span className="font-bold text-white">
                          {selectedIndividual.genes.useTrailingAtr ? `${selectedIndividual.genes.trailingAtrStep}x Step` : 'Disabled'}
                        </span>
                      </div>
                    </div>
                  </div>
                )}

                {/* 2. RVOL Volume Filters */}
                {(selectedFilterTab === 'all' || selectedFilterTab === 'volume') && (
                  <div className="bg-zinc-950 border border-zinc-800 p-3 rounded-lg space-y-2">
                    <div className="flex items-center justify-between text-xs font-mono font-semibold text-blue-400">
                      <span className="flex items-center gap-1.5">
                        <BarChart3 className="w-3.5 h-3.5" />
                        <span>2. RVOL Volume &amp; OBV Filters</span>
                      </span>
                      <span className={`text-[10px] px-1.5 py-0.2 rounded border ${
                        selectedIndividual.genes.useVolumeFilter ? 'bg-blue-950 text-blue-400 border-blue-800' : 'bg-zinc-900 text-zinc-500 border-zinc-800'
                      }`}>
                        {selectedIndividual.genes.useVolumeFilter ? 'Enabled' : 'Bypassed'}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs font-mono text-zinc-300">
                      <div className="bg-zinc-900/80 p-2 rounded">
                        <span className="text-[10px] text-zinc-500 block">RVOL Spike Threshold</span>
                        <span className="font-bold text-white">{selectedIndividual.genes.rvolThreshold}x (vs 20-SMA)</span>
                      </div>
                      <div className="bg-zinc-900/80 p-2 rounded">
                        <span className="text-[10px] text-zinc-500 block">OBV Slope Filter</span>
                        <span className="font-bold text-white">{selectedIndividual.genes.useObvTrend ? 'Confirmed' : 'Off'}</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* 3. Trend & ADX Filters */}
                {(selectedFilterTab === 'all' || selectedFilterTab === 'trend') && (
                  <div className="bg-zinc-950 border border-zinc-800 p-3 rounded-lg space-y-2">
                    <div className="flex items-center justify-between text-xs font-mono font-semibold text-purple-400">
                      <span className="flex items-center gap-1.5">
                        <TrendingUp className="w-3.5 h-3.5" />
                        <span>3. Trend Direction &amp; ADX</span>
                      </span>
                      <span className={`text-[10px] px-1.5 py-0.2 rounded border ${
                        selectedIndividual.genes.useTrendFilter ? 'bg-purple-950 text-purple-400 border-purple-800' : 'bg-zinc-900 text-zinc-500 border-zinc-800'
                      }`}>
                        {selectedIndividual.genes.useTrendFilter ? 'Enabled' : 'Bypassed'}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs font-mono text-zinc-300">
                      <div className="bg-zinc-900/80 p-2 rounded">
                        <span className="text-[10px] text-zinc-500 block">Fast EMA Period</span>
                        <span className="font-bold text-white">{selectedIndividual.genes.trendFastEma}</span>
                      </div>
                      <div className="bg-zinc-900/80 p-2 rounded">
                        <span className="text-[10px] text-zinc-500 block">Slow EMA Period</span>
                        <span className="font-bold text-white">{selectedIndividual.genes.trendSlowEma}</span>
                      </div>
                      <div className="bg-zinc-900/80 p-2 rounded">
                        <span className="text-[10px] text-zinc-500 block">ADX Regime Filter</span>
                        <span className="font-bold text-white">
                          {selectedIndividual.genes.adxFilterEnabled ? `ADX >= ${selectedIndividual.genes.adxThreshold}` : 'Off'}
                        </span>
                      </div>
                      <div className="bg-zinc-900/80 p-2 rounded">
                        <span className="text-[10px] text-zinc-500 block">Risk Per Trade</span>
                        <span className="font-bold text-amber-400">{selectedIndividual.genes.riskPerTradePercent}%</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* 4. Fair Value Gap (FVG) Filter */}
                {(selectedFilterTab === 'all' || selectedFilterTab === 'fvg') && (
                  <div className="bg-zinc-950 border border-zinc-800 p-3 rounded-lg space-y-2">
                    <div className="flex items-center justify-between text-xs font-mono font-semibold text-amber-400">
                      <span className="flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5" />
                        <span>4. Fair Value Gap (FVG Imbalance)</span>
                      </span>
                      <span className={`text-[10px] px-1.5 py-0.2 rounded border ${
                        selectedIndividual.genes.useFvgFilter ? 'bg-amber-950 text-amber-400 border-amber-800' : 'bg-zinc-900 text-zinc-500 border-zinc-800'
                      }`}>
                        {selectedIndividual.genes.useFvgFilter ? 'ICT Imbalance' : 'Bypassed'}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs font-mono text-zinc-300">
                      <div className="bg-zinc-900/80 p-2 rounded">
                        <span className="text-[10px] text-zinc-500 block">Min Gap %</span>
                        <span className="font-bold text-white">{selectedIndividual.genes.fvgMinGapPercent}%</span>
                      </div>
                      <div className="bg-zinc-900/80 p-2 rounded">
                        <span className="text-[10px] text-zinc-500 block">Mitigation Retest</span>
                        <span className="font-bold text-white">{selectedIndividual.genes.fvgMitigationStrict ? 'Strict' : 'Standard'}</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* 5. Change In State of Delivery (CISD) Filter */}
                {(selectedFilterTab === 'all' || selectedFilterTab === 'cisd') && (
                  <div className="bg-zinc-950 border border-zinc-800 p-3 rounded-lg space-y-2">
                    <div className="flex items-center justify-between text-xs font-mono font-semibold text-cyan-400">
                      <span className="flex items-center gap-1.5">
                        <Compass className="w-3.5 h-3.5" />
                        <span>5. CISD Market Structure Shift</span>
                      </span>
                      <span className={`text-[10px] px-1.5 py-0.2 rounded border ${
                        selectedIndividual.genes.useCisdFilter ? 'bg-cyan-950 text-cyan-400 border-cyan-800' : 'bg-zinc-900 text-zinc-500 border-zinc-800'
                      }`}>
                        {selectedIndividual.genes.useCisdFilter ? 'SMC Structure' : 'Bypassed'}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs font-mono text-zinc-300">
                      <div className="bg-zinc-900/80 p-2 rounded">
                        <span className="text-[10px] text-zinc-500 block">Swing Lookback</span>
                        <span className="font-bold text-white">{selectedIndividual.genes.cisdLookback} bars</span>
                      </div>
                      <div className="bg-zinc-900/80 p-2 rounded">
                        <span className="text-[10px] text-zinc-500 block">Displacement Multiplier</span>
                        <span className="font-bold text-white">{selectedIndividual.genes.cisdDisplacementMult}x</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* 6. Multi-Timeframe (MTF) Macro Filter */}
                {(selectedFilterTab === 'all' || selectedFilterTab === 'mtf') && (
                  <div className="bg-zinc-950 border border-zinc-800 p-3 rounded-lg space-y-2">
                    <div className="flex items-center justify-between text-xs font-mono font-semibold text-indigo-400">
                      <span className="flex items-center gap-1.5">
                        <Layers className="w-3.5 h-3.5" />
                        <span>6. Multi-Timeframe (MTF) Alignment</span>
                      </span>
                      <span className={`text-[10px] px-1.5 py-0.2 rounded border ${
                        selectedIndividual.genes.useMtfFilter ? 'bg-indigo-950 text-indigo-400 border-indigo-800' : 'bg-zinc-900 text-zinc-500 border-zinc-800'
                      }`}>
                        {selectedIndividual.genes.useMtfFilter ? 'Macro Trend' : 'Bypassed'}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs font-mono text-zinc-300">
                      <div className="bg-zinc-900/80 p-2 rounded">
                        <span className="text-[10px] text-zinc-500 block">Timeframe Multiplier</span>
                        <span className="font-bold text-white">{selectedIndividual.genes.mtfMultiplier}x (Macro)</span>
                      </div>
                      <div className="bg-zinc-900/80 p-2 rounded">
                        <span className="text-[10px] text-zinc-500 block">HTF Trend EMA</span>
                        <span className="font-bold text-white">{selectedIndividual.genes.mtfTrendEma} EMA</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Compiled Executable Strategy Code Preview Box */}
              <div className="border-t border-zinc-800/80 pt-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-mono font-bold text-zinc-300 flex items-center gap-1.5">
                    <Code2 className="w-3.5 h-3.5 text-purple-400" />
                    <span>Compiled Orchestrator Code</span>
                  </span>
                  <button
                    onClick={handleCopyCode}
                    className="px-2 py-0.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded text-[10px] font-mono flex items-center gap-1 transition-colors"
                  >
                    {copiedCode ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                    <span>{copiedCode ? 'Copied' : 'Copy JS'}</span>
                  </button>
                </div>
                <div className="bg-zinc-950 border border-zinc-800 rounded-md p-2.5 max-h-36 overflow-y-auto">
                  <pre className="text-[10px] font-mono text-zinc-400 leading-relaxed select-all">
                    {optimizationResult?.generatedCode || "// Click Run GA Evolution to generate executable strategy code."}
                  </pre>
                </div>
              </div>
            </div>
          ) : (
            population !== null && population.length > 0 ? (
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 text-center text-zinc-500 font-mono text-xs">
                Select an individual to inspect its genetic chromosome.
              </div>
            ) : optimizationResult ? (
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 text-center text-zinc-500 font-mono text-xs">
                No genomes in the response.
              </div>
            ) : (
              <RunStatusNotice isRunning={isRunning} refusal={runRefusal} />
            )
          )}
        </div>
      </div>
    </div>
  );
}
