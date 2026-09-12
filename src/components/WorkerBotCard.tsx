import React, { useMemo } from "react";
import { 
  Bot, Play, Pause, TrendingUp, TrendingDown, Target, 
  DollarSign, ShieldAlert, Clock, Zap, CheckCircle2, 
  AlertTriangle, ShieldCheck, GitFork, Database, Eye, Code2
} from "lucide-react";
import { WorkerBotData } from "../types/trading";

interface WorkerBotCardProps {
  bot: WorkerBotData;
  onToggleStatus?: (id: string) => void;
  onSelect?: (bot: WorkerBotData) => void;
  onClone?: (bot: WorkerBotData) => void;
  onInspectOrigin?: (bot: WorkerBotData) => void;
  onViewLogic?: (bot: WorkerBotData) => void;
  isSelected?: boolean;
}

export const WorkerBotCard: React.FC<WorkerBotCardProps> = ({
  bot,
  onToggleStatus,
  onSelect,
  onClone,
  onInspectOrigin,
  onViewLogic,
  isSelected = false
}) => {
  const isPositiveUnrealized = bot.unrealizedPnL.value >= 0;
  const isPositiveTotal = bot.totalProfit >= 0;
  const isPositiveRealized = bot.metrics.realizedProfit >= 0;
  const isActive = bot.status === "active";

  // Safe date formatting
  const formattedUpdateTime = useMemo(() => {
    try {
      if (bot.lastUpdate instanceof Date) {
        return bot.lastUpdate.toLocaleTimeString();
      }
      if (typeof bot.lastUpdate === "number" || typeof bot.lastUpdate === "string") {
        return new Date(bot.lastUpdate).toLocaleTimeString();
      }
      return new Date().toLocaleTimeString();
    } catch {
      return "00:00:00";
    }
  }, [bot.lastUpdate]);

  // Liquidation safety metric coloring
  const liqDistance = bot.metrics.liquidationDistancePct;
  const liqSafety = liqDistance > 25 ? "safe" : liqDistance > 12 ? "moderate" : "critical";

  return (
    <div
      id={`worker-bot-card-${bot.id}`}
      onClick={() => onSelect?.(bot)}
      className={`bg-zinc-900 border transition-all rounded-xl p-4 sm:p-5 flex flex-col justify-between font-mono shadow-sm relative overflow-hidden ${
        isSelected
          ? "border-cyan-500/80 shadow-[0_0_20px_rgba(6,182,212,0.12)] bg-zinc-900/95"
          : "border-zinc-800 hover:border-zinc-700/90 hover:bg-zinc-900/90"
      }`}
    >
      {/* Top ambient accent border based on status */}
      <div 
        className={`absolute top-0 left-0 right-0 h-0.5 ${
          isActive 
            ? "bg-gradient-to-r from-emerald-500/60 via-cyan-500/80 to-emerald-500/60" 
            : "bg-zinc-700/60"
        }`} 
      />

      <div className="space-y-3.5">
        {/* ======================================================== */}
        {/* 1. HEADER: Bot Avatar, Name, Exchange, Status Button     */}
        {/* ======================================================== */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div 
              className={`p-2.5 rounded-lg border shrink-0 transition-colors ${
                isActive 
                  ? "bg-emerald-950/70 border-emerald-700/60 text-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.15)]" 
                  : "bg-zinc-950 border-zinc-800 text-zinc-500"
              }`}
            >
              <Bot className="w-5 h-5" />
            </div>

            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-sm font-bold text-white tracking-wide truncate">
                  {bot.name}
                </h3>
                <span className="px-1.5 py-0.2 rounded text-[10px] uppercase font-bold bg-zinc-800/90 border border-zinc-750 text-zinc-300">
                  {bot.exchange}
                </span>
              </div>
              <div className="flex items-center gap-2 text-[11px] text-zinc-400 truncate mt-0.5">
                <span>ID: <strong className="text-zinc-300">{bot.id}</strong></span>
                {bot.spawnedFrom && (
                  <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.2 rounded bg-purple-950/80 border border-purple-800/60 text-purple-300 font-semibold" title={`Spawned from historical session ${bot.spawnedFrom}`}>
                    <GitFork className="w-2.5 h-2.5" />
                    <span>Clone: {bot.spawnedFrom}</span>
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            {onClone && (
              <button
                id={`clone-bot-btn-${bot.id}`}
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onClone(bot);
                }}
                className="px-2 py-1.5 rounded-lg text-xs font-bold border border-zinc-700/80 bg-zinc-800/80 hover:bg-zinc-750 text-zinc-300 transition-all flex items-center gap-1 cursor-pointer"
                title="Diesen Bot als neue Session klonen"
              >
                <GitFork className="w-3.5 h-3.5 text-purple-400" />
              </button>
            )}

            <button
              id={`toggle-status-btn-${bot.id}`}
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onToggleStatus?.(bot.id);
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider border transition-all flex items-center gap-1.5 cursor-pointer shadow-xs active:scale-95 ${
                isActive
                  ? "bg-emerald-950/80 hover:bg-emerald-900 border-emerald-700/70 text-emerald-300"
                  : "bg-zinc-800 hover:bg-zinc-750 border-zinc-700 text-zinc-300"
              }`}
              title={isActive ? "Bot pausieren" : "Bot aktivieren"}
            >
              {isActive ? (
                <>
                  <Pause className="w-3.5 h-3.5 fill-emerald-400 text-emerald-400" />
                  <span>Pause</span>
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 fill-zinc-300 text-zinc-300" />
                  <span>Activate</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* ======================================================== */}
        {/* 2. ASSET BAR: Live Indicator, Pair, Strategy, Dir, Lev   */}
        {/* ======================================================== */}
        <div className="flex items-center justify-between flex-wrap gap-2 p-2.5 rounded-lg bg-zinc-950/70 border border-zinc-850 text-xs">
          <div className="flex items-center gap-2 flex-wrap">
            {/* Live Indicator */}
            <span className="flex items-center gap-1.5">
              <span 
                className={`w-2 h-2 rounded-full ${
                  isActive 
                    ? "bg-emerald-400 animate-pulse shadow-[0_0_8px_rgba(52,211,153,0.8)]" 
                    : "bg-zinc-600"
                }`} 
              />
              <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-semibold">
                {isActive ? "LIVE" : "PAUSED"}
              </span>
            </span>

            <span className="text-zinc-600">•</span>

            {/* Pair & Strategy */}
            <span className="font-bold text-white text-xs">
              {bot.pair}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800/80 border border-zinc-700/60 text-cyan-300 font-semibold">
              {bot.strategy}
            </span>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            {/* Direction Badge */}
            <span 
              className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase flex items-center gap-1 ${
                bot.direction === "LONG"
                  ? "bg-emerald-950/90 border border-emerald-700/70 text-emerald-300"
                  : "bg-rose-950/90 border border-rose-700/70 text-rose-300"
              }`}
            >
              {bot.direction === "LONG" ? (
                <>
                  <TrendingUp className="w-3 h-3 text-emerald-400" />
                  <span>▲ LONG</span>
                </>
              ) : (
                <>
                  <TrendingDown className="w-3 h-3 text-rose-400" />
                  <span>▼ SHORT</span>
                </>
              )}
            </span>

            {/* Leverage Badge */}
            <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-purple-950/80 border border-purple-700/60 text-purple-300">
              {bot.leverage}×
            </span>
          </div>
        </div>

        {/* ======================================================== */}
        {/* 2a. HISTORICAL ORIGIN & DATABASE LINEAGE (ZERO-DUMMY)    */}
        {/* ======================================================== */}
        <div className="p-2.5 rounded-lg bg-zinc-950/80 border border-purple-900/40 text-xs flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <div className="p-1.5 rounded-md bg-purple-950/80 border border-purple-850 text-purple-300 shrink-0">
              <Database className="w-3.5 h-3.5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-[10px] text-zinc-400 font-bold uppercase tracking-wider">
                  Origin:
                </span>
                <span className="text-[11px] font-bold text-purple-300 font-mono truncate">
                  {bot.historicalOrigin?.sessionId || bot.spawnedFrom || "GENESIS_SEED"}
                </span>
                <span className="text-[9px] px-1 py-0.2 rounded bg-purple-950/60 border border-purple-800/60 text-purple-200 uppercase font-semibold">
                  {bot.historicalOrigin?.sourceRegime || bot.regime || "persistent_trending"}
                </span>
              </div>
              <div className="text-[10px] text-zinc-400 truncate mt-0.5">
                {bot.historicalOrigin ? (
                  <span>
                    Baseline: <strong className="text-emerald-400">+{bot.historicalOrigin.sourceRoi}% ROI</strong> (${bot.historicalOrigin.sourcePnl.toFixed(0)}) in <span className="text-zinc-300">bot_history</span>
                  </span>
                ) : (
                  <span>DB Source: <strong className="text-zinc-300">bot_history</strong> (Primary Config)</span>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            {onViewLogic && (
              <button
                id={`card-view-logic-btn-${bot.id}`}
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onViewLogic(bot);
                }}
                className="px-2 py-1 rounded bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-750 text-cyan-200 text-[10px] font-bold transition-all flex items-center gap-1 cursor-pointer shadow-xs active:scale-95"
                title="Spawning-Strategiekonfiguration und Logik anzeigen"
              >
                <Code2 className="w-3 h-3 text-cyan-400" />
                <span>Logic</span>
              </button>
            )}

            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onInspectOrigin?.(bot);
              }}
              className="px-2 py-1 rounded bg-purple-950/70 hover:bg-purple-900 border border-purple-750 text-purple-200 text-[10px] font-bold transition-all flex items-center gap-1 shrink-0 cursor-pointer"
              title="Historischen Ursprung & Orchestrator Klon-Entscheidung analysieren"
            >
              <Eye className="w-3 h-3 text-purple-400" />
              <span>Audit</span>
            </button>
          </div>
        </div>

        {/* ======================================================== */}
        {/* 2b. LIVE P&L & PRICE STRIP                               */}
        {/* ======================================================== */}
        <div className="p-3 rounded-lg bg-zinc-950/90 border border-zinc-800 flex items-center justify-between">
          <div>
            <span className="text-[10px] text-zinc-400 uppercase tracking-wider block font-semibold">
              Unrealized P&amp;L
            </span>
            <div className="flex items-baseline gap-2 mt-0.5">
              <span className={`text-base font-bold tracking-tight ${isPositiveUnrealized ? "text-emerald-400" : "text-rose-400"}`}>
                {isPositiveUnrealized ? "+" : ""}{bot.unrealizedPnL.value.toFixed(2)} {bot.metrics.currency}
              </span>
              <span className={`text-xs font-bold ${isPositiveUnrealized ? "text-emerald-500" : "text-rose-500"}`}>
                ({isPositiveUnrealized ? "+" : ""}{bot.unrealizedPnL.percentage.toFixed(2)}%)
              </span>
            </div>
          </div>

          <div className="text-right text-[11px] space-y-0.5">
            <div className="text-zinc-400">
              Entry: <strong className="text-zinc-200">${bot.entryPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong>
            </div>
            <div className="text-zinc-400">
              Mark: <strong className="text-cyan-300">${bot.currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong>
            </div>
          </div>
        </div>

        {/* ======================================================== */}
        {/* 3. 2x3 METRICS GRID (Requested 6-cell layout)            */}
        {/* ======================================================== */}
        <div className="grid grid-cols-2 gap-2.5 text-xs">
          {/* Item 1: Investment */}
          <div className="p-2.5 rounded-lg bg-zinc-950/60 border border-zinc-800/80 hover:border-zinc-700 transition-colors">
            <div className="flex items-center gap-1.5 text-zinc-400 text-[10px] uppercase tracking-wider mb-1">
              <DollarSign className="w-3 h-3 text-emerald-400" />
              <span>Investment</span>
            </div>
            <span className="text-xs font-bold text-white block">
              {bot.metrics.investment.toFixed(2)} {bot.metrics.currency}
            </span>
          </div>

          {/* Item 2: DCA Range */}
          <div className="p-2.5 rounded-lg bg-zinc-950/60 border border-zinc-800/80 hover:border-zinc-700 transition-colors">
            <div className="flex items-center gap-1.5 text-zinc-400 text-[10px] uppercase tracking-wider mb-1">
              <Target className="w-3 h-3 text-cyan-400" />
              <span>DCA Range</span>
            </div>
            <span className="text-xs font-bold text-zinc-200 block truncate" title={`${bot.metrics.dcaRangeMin} - ${bot.metrics.dcaRangeMax}`}>
              ${bot.metrics.dcaRangeMin.toLocaleString()} - ${bot.metrics.dcaRangeMax.toLocaleString()}
            </span>
            <span className="text-[10px] text-cyan-400/90 block mt-0.5">
              {bot.metrics.dcaSteps} Stufen ({bot.metrics.dcaOrdersTriggered} ausgelöst)
            </span>
          </div>

          {/* Item 3: Realized Profit */}
          <div className="p-2.5 rounded-lg bg-zinc-950/60 border border-zinc-800/80 hover:border-zinc-700 transition-colors">
            <div className="flex items-center gap-1.5 text-zinc-400 text-[10px] uppercase tracking-wider mb-1">
              <CheckCircle2 className="w-3 h-3 text-emerald-400" />
              <span>Realized Profit</span>
            </div>
            <span className={`text-xs font-bold block ${isPositiveRealized ? "text-emerald-400" : "text-rose-400"}`}>
              {isPositiveRealized ? "+" : ""}{bot.metrics.realizedProfit.toFixed(2)} {bot.metrics.currency}
            </span>
          </div>

          {/* Item 4: Funding Fees */}
          <div className="p-2.5 rounded-lg bg-zinc-950/60 border border-zinc-800/80 hover:border-zinc-700 transition-colors">
            <div className="flex items-center gap-1.5 text-zinc-400 text-[10px] uppercase tracking-wider mb-1">
              <Zap className="w-3 h-3 text-amber-400" />
              <span>Funding Fees</span>
            </div>
            <span className="text-xs font-bold text-amber-300 block">
              {bot.metrics.fundingFees >= 0 ? "+" : ""}{bot.metrics.fundingFees.toFixed(2)} {bot.metrics.currency}
            </span>
          </div>

          {/* Item 5: Liquidation Price */}
          <div className="p-2.5 rounded-lg bg-zinc-950/60 border border-zinc-800/80 hover:border-zinc-700 transition-colors">
            <div className="flex items-center gap-1.5 text-zinc-400 text-[10px] uppercase tracking-wider mb-1">
              <ShieldAlert className="w-3 h-3 text-rose-400" />
              <span>Liq. Price</span>
            </div>
            <span className="text-xs font-bold text-rose-300 block">
              ${bot.metrics.liquidationPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>

          {/* Item 6: Liquidation Distance */}
          <div className="p-2.5 rounded-lg bg-zinc-950/60 border border-zinc-800/80 hover:border-zinc-700 transition-colors">
            <div className="flex items-center gap-1.5 text-zinc-400 text-[10px] uppercase tracking-wider mb-1">
              {liqSafety === "safe" ? (
                <ShieldCheck className="w-3 h-3 text-emerald-400" />
              ) : (
                <AlertTriangle className="w-3 h-3 text-amber-400" />
              )}
              <span>Liq. Distance</span>
            </div>
            <div className="flex items-center justify-between">
              <span className={`text-xs font-bold ${
                liqSafety === "safe" ? "text-emerald-400" : liqSafety === "moderate" ? "text-amber-400" : "text-rose-400"
              }`}>
                {bot.metrics.liquidationDistancePct.toFixed(1)}%
              </span>
              <span className="text-[9px] uppercase font-bold text-zinc-400">
                {liqSafety === "safe" ? "SAFE" : liqSafety === "moderate" ? "WARN" : "RISK"}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* ======================================================== */}
      {/* 4. FOOTER: Total Profit, Runtime, Cycles, ROI, APR, Time */}
      {/* ======================================================== */}
      <div className="mt-4 pt-3 border-t border-zinc-800/90 space-y-2.5 text-xs">
        {/* Total Profit Headline */}
        <div className="flex items-center justify-between p-2 rounded-lg bg-zinc-950/90 border border-zinc-850">
          <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-semibold">
            🏆 Total Profit
          </span>
          <span className={`text-sm font-bold ${isPositiveTotal ? "text-emerald-400" : "text-rose-400"}`}>
            {isPositiveTotal ? "+" : ""}{bot.totalProfit.toFixed(2)} {bot.metrics.currency}
          </span>
        </div>

        {/* Runtime & Performance Badges */}
        <div className="grid grid-cols-2 gap-2 text-[11px] text-zinc-400">
          <div className="flex items-center gap-1.5">
            <Clock className="w-3 h-3 text-zinc-500 shrink-0" />
            <span className="truncate">
              {bot.runtime.days}d {bot.runtime.hours}h {bot.runtime.minutes}m
            </span>
          </div>
          <div className="text-right text-zinc-300">
            Zyklen: <strong className="text-white">{bot.runtime.cycles}</strong>
          </div>
        </div>

        <div className="flex items-center justify-between text-[11px] pt-1 border-t border-zinc-850/80">
          <div className="flex items-center gap-2">
            <span className="text-zinc-400">
              ROI: <strong className={bot.roi >= 0 ? "text-emerald-400" : "text-rose-400"}>
                {bot.roi >= 0 ? "+" : ""}{bot.roi.toFixed(2)}%
              </strong>
            </span>
            <span className="text-zinc-600">•</span>
            <span className="text-zinc-400">
              APR: <strong className="text-cyan-300">{bot.apr.toFixed(1)}%</strong>
            </span>
          </div>

          <div className="text-zinc-500 text-[10px]">
            Sync: <strong className="text-zinc-400">{formattedUpdateTime}</strong>
          </div>
        </div>
      </div>
    </div>
  );
};
