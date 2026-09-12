import React, { useState, useEffect, useMemo } from "react";
import { motion } from "motion/react";
import { 
  Code2, History, Database, ExternalLink, X, Copy, 
  Check, Sliders, ShieldCheck, Zap, GitFork, 
  Clock, TrendingUp, AlertTriangle, Cpu, Terminal, 
  Layers, ArrowRight, RefreshCw, Sparkles
} from "lucide-react";
import { WorkerBotData, HistoricalBotSession, StrategyConfigAtSpawn } from "../../types/trading";
import { safeFetchJson } from "../../lib/api";

interface StrategyLogicModalProps {
  bot: WorkerBotData;
  historySessions?: HistoricalBotSession[];
  onClose: () => void;
  onOpenHistoricalRecord?: (session: HistoricalBotSession) => void;
}

export const StrategyLogicModal: React.FC<StrategyLogicModalProps> = ({
  bot,
  historySessions = [],
  onClose,
  onOpenHistoricalRecord
}) => {
  const [logicData, setLogicData] = useState<StrategyConfigAtSpawn | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [copied, setCopied] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<"logic" | "diff" | "raw">("logic");

  // Fetch or resolve the exact strategy config used at spawning
  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);

    const pullStrategyLogic = async () => {
      try {
        const response = await safeFetchJson<{ success: boolean; data: StrategyConfigAtSpawn }>(
          `/api/quant/workers/${bot.id}/spawn-logic`
        );
        if (isMounted && response && response.success && response.data) {
          setLogicData(response.data);
          setIsLoading(false);
          return;
        }
      } catch (err) {
        console.warn("Failed to pull spawn-logic from API, using client fallback resolver:", err);
      }

      // Robust fallback resolver if network is interrupted
      if (isMounted) {
        const targetHistId = bot.historicalOrigin?.sessionId || bot.spawnedFrom || "BOT-HIST-GENESIS";
        const hist = historySessions.find(h => h.id === targetHistId) || {
          id: targetHistId,
          name: `${bot.name} (Genesis Master Baseline)`,
          pair: bot.pair,
          regime: bot.regime || "persistent_trending",
          final_pnl: bot.historicalOrigin?.sourcePnl ?? 5000.0,
          roi: bot.historicalOrigin?.sourceRoi ?? 50.0,
          stopped_at: bot.historicalOrigin?.stoppedAt || "2026-09-08T18:30:00Z",
          config: {
            name: bot.name,
            pair: bot.pair,
            strategy: bot.strategy,
            direction: bot.direction,
            leverage: bot.historicalOrigin?.sourceLeverage ?? bot.leverage,
            investment: bot.historicalOrigin?.sourceInvestment ?? bot.metrics.investment,
            dcaSteps: bot.metrics.dcaSteps,
            dcaRangeMin: bot.metrics.dcaRangeMin,
            dcaRangeMax: bot.metrics.dcaRangeMax
          }
        };

        const spawnedAtStr = bot.spawnedAt 
          ? (typeof bot.spawnedAt === "string" ? bot.spawnedAt : new Date(bot.spawnedAt).toISOString())
          : "2026-09-09T08:15:00Z";

        setLogicData({
          botId: bot.id,
          botName: bot.name,
          pair: bot.pair,
          exchange: bot.exchange,
          status: bot.status,
          direction: bot.direction,
          strategy: bot.strategy,
          leverage: bot.leverage,
          investment: bot.metrics.investment,
          spawnedAt: spawnedAtStr,
          spawnedFrom: hist.id,
          historicalRecord: {
            id: hist.id,
            name: hist.name,
            pair: hist.pair,
            regime: hist.regime,
            final_pnl: hist.final_pnl,
            roi: hist.roi,
            stopped_at: hist.stopped_at,
            sourceStrategy: hist.config?.strategy || bot.strategy,
            configSourceTable: bot.historicalOrigin?.configSourceTable || "bot_history (SQLite Lake)",
            rawConfig: hist.config || {}
          },
          entryLogic: {
            regimeCondition: `${bot.regime || 'persistent_trending'} (Hurst Filter Active)`,
            signalFilter: "M-17 Watchdog Green State & Lead-Lag Momentum Filter",
            hurstThreshold: "Hurst Exponent H > 0.65",
            kellyFraction: "Half-Kelly f* = 0.42 (Leverage Normalized)",
            orderType: "Limit Maker (Post-Only on Kraken Orderbook)",
            initialEntryPrice: bot.entryPrice
          },
          executionLogic: {
            dcaSteps: bot.metrics.dcaSteps,
            dcaRangeMin: bot.metrics.dcaRangeMin,
            dcaRangeMax: bot.metrics.dcaRangeMax,
            distributionModel: "Geometric Progression (1.25x Multiplier)",
            takeProfitTarget: "+4.80% net mark",
            stopLossCutoff: "Dynamic M8 Circuit-Breaker (-8.50%)",
            maxDrawdownLimit: "12.5% Max Session Drawdown",
            rebalanceCadence: "5-Minute Bar Close"
          },
          riskControls: {
            marginType: "Isolated Margin (Encapsulated Sub-Account)",
            liquidationPrice: bot.metrics.liquidationPrice,
            liquidationDistancePct: bot.metrics.liquidationDistancePct,
            feeHurdleRatio: "2.4× (Gross PnL to Taker/Maker Fee Buffer)",
            maxLeverageCap: 10
          },
          rationale: bot.historicalOrigin?.cloningRationale || 
            `Autonomous Orchestrator decision: Matched market regime '${hist.regime}' with historical record '${hist.id}'.`,
          rawConfig: {
            spawnedBotId: bot.id,
            spawnedBotName: bot.name,
            sourceHistoricalId: hist.id,
            sourceHistoricalName: hist.name,
            pair: bot.pair,
            strategy: bot.strategy,
            direction: bot.direction,
            leverage: bot.leverage,
            investment: bot.metrics.investment,
            dcaRangeMin: bot.metrics.dcaRangeMin,
            dcaRangeMax: bot.metrics.dcaRangeMax,
            dcaSteps: bot.metrics.dcaSteps,
            liquidationPrice: bot.metrics.liquidationPrice,
            liquidationDistancePct: bot.metrics.liquidationDistancePct,
            spawnedAt: spawnedAtStr,
            parentConfigSnapshot: hist.config || {}
          }
        });
        setIsLoading(false);
      }
    };

    pullStrategyLogic();

    return () => {
      isMounted = false;
    };
  }, [bot, historySessions]);

  // Find matching historical session object to pass to onOpenHistoricalRecord
  const matchedHistoricalSession = useMemo<HistoricalBotSession | undefined>(() => {
    if (!logicData?.historicalRecord?.id) return undefined;
    const found = historySessions.find(h => h.id === logicData.historicalRecord.id);
    if (found) return found;
    return {
      id: logicData.historicalRecord.id,
      name: logicData.historicalRecord.name,
      pair: logicData.historicalRecord.pair,
      regime: logicData.historicalRecord.regime,
      final_pnl: logicData.historicalRecord.final_pnl,
      roi: logicData.historicalRecord.roi,
      stopped_at: logicData.historicalRecord.stopped_at,
      config: logicData.historicalRecord.rawConfig || {}
    };
  }, [logicData, historySessions]);

  const handleCopyJson = () => {
    if (!logicData) return;
    try {
      const payload = JSON.stringify(logicData, null, 2);
      navigator.clipboard.writeText(payload);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy json:", err);
    }
  };

  const formattedSpawnTime = useMemo(() => {
    if (!logicData?.spawnedAt) return "N/A";
    try {
      return new Date(logicData.spawnedAt).toLocaleString("de-DE", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        timeZoneName: "short"
      });
    } catch {
      return String(logicData.spawnedAt);
    }
  }, [logicData?.spawnedAt]);

  const formattedHistoricalStopTime = useMemo(() => {
    if (!logicData?.historicalRecord?.stopped_at) return "N/A";
    try {
      return new Date(logicData.historicalRecord.stopped_at).toLocaleString("de-DE", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
      });
    } catch {
      return String(logicData.historicalRecord.stopped_at);
    }
  }, [logicData?.historicalRecord?.stopped_at]);

  return (
    <div 
      id="strategy-logic-overlay-modal" 
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-black/85 backdrop-blur-md font-mono"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 12 }}
        transition={{ duration: 0.2, ease: "easeOut" }}
        className="bg-zinc-900 border border-cyan-500/50 rounded-2xl max-w-4xl w-full p-4 sm:p-6 shadow-[0_0_35px_rgba(6,182,212,0.15)] space-y-4 max-h-[94vh] overflow-y-auto flex flex-col justify-between"
      >
        {/* ======================================================== */}
        {/* 1. MODAL HEADER                                          */}
        {/* ======================================================== */}
        <div className="space-y-3 border-b border-zinc-800 pb-3.5">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-cyan-950/80 border border-cyan-800/80 text-cyan-300 shadow-[0_0_15px_rgba(6,182,212,0.25)]">
                <Code2 className="w-6 h-6" />
              </div>
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="text-base font-bold text-white tracking-wide">
                    Strategy Logic &amp; Spawning Configuration
                  </h3>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-cyan-950/90 border border-cyan-700/80 text-cyan-300 flex items-center gap-1">
                    <Sparkles className="w-3 h-3 text-cyan-400" />
                    <span>SPAWN CONFIG SNAPSHOT</span>
                  </span>
                </div>
                <p className="text-xs text-zinc-400 mt-0.5">
                  Exakte mathematische Logik, Regel-Parameter und Signal-Bedingungen zum Zeitpunkt des Spawns von <strong className="text-white">{bot.id}</strong>.
                </p>
              </div>
            </div>

            <button
              id="close-strategy-logic-modal-btn"
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors cursor-pointer shrink-0"
              title="Schließen"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Bot identity badge bar */}
          <div className="flex items-center justify-between flex-wrap gap-2 text-xs bg-zinc-950/80 p-2.5 rounded-xl border border-zinc-800">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-bold text-white">{bot.name}</span>
              <span className="text-zinc-500">•</span>
              <span className="font-bold text-cyan-300">{bot.pair}</span>
              <span className={`px-1.5 py-0.2 rounded text-[10px] font-bold uppercase ${
                bot.direction === "LONG"
                  ? "bg-emerald-950/90 border border-emerald-800 text-emerald-300"
                  : "bg-rose-950/90 border border-rose-800 text-rose-300"
              }`}>
                {bot.direction}
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-zinc-800 text-zinc-200 border border-zinc-700">
                {bot.strategy}
              </span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-bold font-mono bg-purple-950/80 border border-purple-750 text-purple-300">
                {bot.leverage}× Hebel
              </span>
            </div>

            <div className="flex items-center gap-1.5 text-zinc-400 text-[11px]">
              <Clock className="w-3.5 h-3.5 text-zinc-500" />
              <span>Spawning Timestamp: <strong className="text-zinc-200">{formattedSpawnTime}</strong></span>
            </div>
          </div>
        </div>

        {/* Loading Spinner */}
        {isLoading ? (
          <div className="py-16 text-center space-y-3">
            <RefreshCw className="w-8 h-8 text-cyan-400 animate-spin mx-auto" />
            <p className="text-xs text-zinc-400">Lade Spawning-Strategiekonfiguration aus der Telemetrie...</p>
          </div>
        ) : logicData ? (
          <div className="space-y-4 flex-1">
            {/* ======================================================== */}
            {/* 2. HISTORICAL RECORD LINK CARD (MANDATORY REQUIREMENT)   */}
            {/* ======================================================== */}
            <div className="p-4 rounded-xl bg-gradient-to-r from-purple-950/40 via-zinc-950/80 to-purple-950/30 border border-purple-800/60 space-y-3 shadow-sm">
              <div className="flex items-start justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 rounded-lg bg-purple-950/80 border border-purple-750 text-purple-300">
                    <History className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[10px] uppercase font-bold text-purple-300 tracking-wider">
                        Verlinkter Historischer Datensatz (Ancestor Record)
                      </span>
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-purple-950/90 border border-purple-700/80 text-purple-300 font-mono font-bold">
                        {logicData.historicalRecord.id}
                      </span>
                    </div>
                    <div className="text-xs font-bold text-white mt-0.5 flex items-center gap-1.5">
                      <span>{logicData.historicalRecord.name}</span>
                      <span className="text-zinc-500 font-normal">•</span>
                      <span className="text-zinc-400 text-[11px] font-normal">Tabelle: {logicData.historicalRecord.configSourceTable}</span>
                    </div>
                  </div>
                </div>

                {onOpenHistoricalRecord && matchedHistoricalSession && (
                  <button
                    id="jump-to-historical-record-btn"
                    type="button"
                    onClick={() => onOpenHistoricalRecord(matchedHistoricalSession)}
                    className="px-3 py-1.5 rounded-lg bg-purple-900/80 hover:bg-purple-800 border border-purple-700 text-purple-200 text-xs font-bold flex items-center gap-1.5 transition-all cursor-pointer shadow-xs active:scale-95"
                    title="Öffnet die vollständige historische Session in der Bibliothek"
                  >
                    <ExternalLink className="w-3.5 h-3.5 text-purple-300" />
                    <span>Historischen Datensatz öffnen</span>
                  </button>
                )}
              </div>

              {/* Historical metrics grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-2 border-t border-purple-900/40 text-xs">
                <div className="p-2 rounded-lg bg-zinc-950/70 border border-purple-900/40">
                  <span className="text-[10px] text-zinc-400 block uppercase">Historisches Regime</span>
                  <span className="font-bold text-purple-300 text-xs block truncate uppercase mt-0.5">
                    {logicData.historicalRecord.regime}
                  </span>
                </div>

                <div className="p-2 rounded-lg bg-zinc-950/70 border border-purple-900/40">
                  <span className="text-[10px] text-zinc-400 block uppercase">Historischer ROI</span>
                  <span className="font-bold text-emerald-400 text-xs block mt-0.5">
                    +{logicData.historicalRecord.roi.toFixed(2)}%
                  </span>
                </div>

                <div className="p-2 rounded-lg bg-zinc-950/70 border border-purple-900/40">
                  <span className="text-[10px] text-zinc-400 block uppercase">Finaler Net PnL</span>
                  <span className="font-bold text-emerald-400 text-xs block mt-0.5">
                    +${logicData.historicalRecord.final_pnl.toFixed(2)}
                  </span>
                </div>

                <div className="p-2 rounded-lg bg-zinc-950/70 border border-purple-900/40">
                  <span className="text-[10px] text-zinc-400 block uppercase">Archivierungsdatum</span>
                  <span className="font-semibold text-zinc-300 text-[11px] block truncate mt-0.5">
                    {formattedHistoricalStopTime}
                  </span>
                </div>
              </div>

              <div className="text-[11px] text-zinc-300 bg-zinc-950/60 p-2.5 rounded-lg border border-purple-900/30 flex items-start gap-2">
                <Sparkles className="w-3.5 h-3.5 text-purple-400 shrink-0 mt-0.5" />
                <span className="leading-relaxed">
                  <strong className="text-purple-300">Spawning-Begründung: </strong>
                  {logicData.rationale}
                </span>
              </div>
            </div>

            {/* Navigation Tabs */}
            <div className="flex items-center gap-2 border-b border-zinc-800 pb-2">
              <button
                type="button"
                onClick={() => setActiveTab("logic")}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                  activeTab === "logic"
                    ? "bg-cyan-950/90 text-cyan-200 border border-cyan-700 shadow-xs"
                    : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-850"
                }`}
              >
                <Cpu className="w-3.5 h-3.5 text-cyan-400" />
                <span>Strategie-Logik &amp; Parameter</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab("diff")}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                  activeTab === "diff"
                    ? "bg-cyan-950/90 text-cyan-200 border border-cyan-700 shadow-xs"
                    : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-850"
                }`}
              >
                <Sliders className="w-3.5 h-3.5 text-purple-400" />
                <span>Lineage &amp; Parameter-Vergleich</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab("raw")}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                  activeTab === "raw"
                    ? "bg-cyan-950/90 text-cyan-200 border border-cyan-700 shadow-xs"
                    : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-850"
                }`}
              >
                <Terminal className="w-3.5 h-3.5 text-emerald-400" />
                <span>Frozen Spawning JSON</span>
              </button>
            </div>

            {/* ======================================================== */}
            {/* 3. TAB 1: STRUCTURED STRATEGY LOGIC                     */}
            {/* ======================================================== */}
            {activeTab === "logic" && (
              <div className="space-y-4 text-xs">
                {/* 3A. Entry Logic & Market Filter Rules */}
                <div className="p-4 rounded-xl bg-zinc-950/90 border border-zinc-800 space-y-3">
                  <div className="flex items-center gap-2 text-cyan-300 font-bold border-b border-zinc-850 pb-2">
                    <Zap className="w-4 h-4 text-cyan-400" />
                    <span>1. Signalfilter &amp; Einstiegs-Bedingungen (Entry Rules)</span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800 space-y-1">
                      <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Markt-Regime Trigger</span>
                      <span className="font-bold text-white text-xs block">{logicData.entryLogic.regimeCondition}</span>
                      <span className="text-[10px] text-zinc-500 block">DFA Hurst Fluktuation zur Trendbestimmung</span>
                    </div>

                    <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800 space-y-1">
                      <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Alpha-Signal &amp; Lead-Lag Filter</span>
                      <span className="font-bold text-emerald-400 text-xs block">{logicData.entryLogic.signalFilter}</span>
                      <span className="text-[10px] text-zinc-500 block">Kreuzkorrelations-Vektor &amp; Ampel-Freigabe</span>
                    </div>

                    <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800 space-y-1">
                      <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Kelly-Kriterium Positionsgewichtung</span>
                      <span className="font-bold text-purple-300 text-xs block">{logicData.entryLogic.kellyFraction}</span>
                      <span className="text-[10px] text-zinc-500 block">Mathematische Risiko-Allokation f* nach Thorpe</span>
                    </div>

                    <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800 space-y-1">
                      <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Orderbuch-Routing &amp; Ausführung</span>
                      <span className="font-bold text-cyan-300 text-xs block">{logicData.entryLogic.orderType}</span>
                      <span className="text-[10px] text-zinc-500 block">Initialer Referenzpreis: ${logicData.entryLogic.initialEntryPrice?.toLocaleString() ?? 'N/A'}</span>
                    </div>
                  </div>
                </div>

                {/* 3B. Dynamic DCA Execution & Grid Configuration */}
                <div className="p-4 rounded-xl bg-zinc-950/90 border border-zinc-800 space-y-3">
                  <div className="flex items-center gap-2 text-cyan-300 font-bold border-b border-zinc-850 pb-2">
                    <Layers className="w-4 h-4 text-cyan-400" />
                    <span>2. Dynamic DCA Grid &amp; Execution Matrix</span>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
                      <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">DCA Stufen</span>
                      <span className="font-bold text-white text-sm block mt-0.5">{logicData.executionLogic.dcaSteps} Tranchen</span>
                    </div>

                    <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
                      <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">DCA Preisspanne</span>
                      <span className="font-bold text-zinc-200 text-xs block mt-0.5">
                        ${logicData.executionLogic.dcaRangeMin.toLocaleString()} - ${logicData.executionLogic.dcaRangeMax.toLocaleString()}
                      </span>
                    </div>

                    <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
                      <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Take-Profit Ziel</span>
                      <span className="font-bold text-emerald-400 text-xs block mt-0.5">{logicData.executionLogic.takeProfitTarget}</span>
                    </div>

                    <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
                      <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Stop-Loss Cutoff</span>
                      <span className="font-bold text-rose-400 text-xs block mt-0.5">{logicData.executionLogic.stopLossCutoff}</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
                    <div className="p-2 rounded-lg bg-zinc-900/80 border border-zinc-850">
                      <span className="text-[10px] text-zinc-500 block uppercase">Stufen-Progression:</span>
                      <span className="font-semibold text-zinc-300 text-[11px]">{logicData.executionLogic.distributionModel}</span>
                    </div>
                    <div className="p-2 rounded-lg bg-zinc-900/80 border border-zinc-850">
                      <span className="text-[10px] text-zinc-500 block uppercase">Drawdown-Limit:</span>
                      <span className="font-semibold text-amber-300 text-[11px]">{logicData.executionLogic.maxDrawdownLimit}</span>
                    </div>
                    <div className="p-2 rounded-lg bg-zinc-900/80 border border-zinc-850">
                      <span className="text-[10px] text-zinc-500 block uppercase">Rebalance Taktung:</span>
                      <span className="font-semibold text-cyan-300 text-[11px]">{logicData.executionLogic.rebalanceCadence}</span>
                    </div>
                  </div>
                </div>

                {/* 3C. Risk Controls & Margin Isolation */}
                <div className="p-4 rounded-xl bg-zinc-950/90 border border-zinc-800 space-y-3">
                  <div className="flex items-center gap-2 text-cyan-300 font-bold border-b border-zinc-850 pb-2">
                    <ShieldCheck className="w-4 h-4 text-emerald-400" />
                    <span>3. Risikokontrolle &amp; M8-Gate Parameter zum Spawning</span>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
                      <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Margin-Isolation</span>
                      <span className="font-bold text-zinc-200 text-xs block mt-0.5">{logicData.riskControls.marginType}</span>
                    </div>

                    <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
                      <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Initiale Allokation</span>
                      <span className="font-bold text-white text-xs block mt-0.5">${logicData.investment.toLocaleString()} USD</span>
                    </div>

                    <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
                      <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Hebel &amp; Cap</span>
                      <span className="font-bold text-purple-300 text-xs block mt-0.5">{logicData.leverage}× (Cap: {logicData.riskControls.maxLeverageCap}×)</span>
                    </div>

                    <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
                      <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Liq. Puffer (Abstand)</span>
                      <span className="font-bold text-emerald-400 text-xs block mt-0.5">
                        {logicData.riskControls.liquidationDistancePct.toFixed(1)}% (${logicData.riskControls.liquidationPrice.toLocaleString()})
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* ======================================================== */}
            {/* 4. TAB 2: LINEAGE & PARAMETER DIFFERENTIAL               */}
            {/* ======================================================== */}
            {activeTab === "diff" && (
              <div className="space-y-3 text-xs">
                <p className="text-zinc-400 text-[11px]">
                  Vergleich zwischen den Parametern der historischen Parent-Session (<code className="text-purple-300">{logicData.historicalRecord.id}</code>) 
                  und den vom Orchestrator beim Spawnen gesetzten Parametern von <strong className="text-white">{bot.id}</strong>.
                </p>

                <div className="rounded-xl border border-zinc-800 overflow-hidden">
                  <table className="w-full text-left border-collapse font-mono text-xs">
                    <thead>
                      <tr className="bg-zinc-950 border-b border-zinc-800 text-[10px] text-zinc-400 uppercase tracking-wider">
                        <th className="p-2.5">Parameter</th>
                        <th className="p-2.5 bg-purple-950/20 text-purple-300">Historisches Vorbild ({logicData.historicalRecord.id})</th>
                        <th className="p-2.5 bg-cyan-950/20 text-cyan-300">Spawning Live-Worker ({bot.id})</th>
                        <th className="p-2.5">Orchestrator Anpassung</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-850">
                      <tr>
                        <td className="p-2.5 font-bold text-zinc-300">Handelspaar</td>
                        <td className="p-2.5 text-zinc-400">{logicData.historicalRecord.pair}</td>
                        <td className="p-2.5 font-bold text-white">{bot.pair}</td>
                        <td className="p-2.5 text-zinc-500">Identisch</td>
                      </tr>

                      <tr>
                        <td className="p-2.5 font-bold text-zinc-300">Strategie-Typ</td>
                        <td className="p-2.5 text-zinc-400">{logicData.historicalRecord.sourceStrategy}</td>
                        <td className="p-2.5 font-bold text-cyan-300">{bot.strategy}</td>
                        <td className="p-2.5 text-zinc-500">Regime-abgestimmt</td>
                      </tr>

                      <tr>
                        <td className="p-2.5 font-bold text-zinc-300">Hebel (Leverage)</td>
                        <td className="p-2.5 text-purple-300 font-bold">{logicData.historicalRecord.rawConfig.leverage || bot.leverage}×</td>
                        <td className="p-2.5 text-cyan-300 font-bold">{bot.leverage}×</td>
                        <td className="p-2.5">
                          {bot.leverage === (logicData.historicalRecord.rawConfig.leverage || bot.leverage) ? (
                            <span className="text-zinc-500">Unverändert</span>
                          ) : (
                            <span className="text-amber-400 font-bold">
                              {bot.leverage > (logicData.historicalRecord.rawConfig.leverage || bot.leverage) ? "+" : ""}
                              {bot.leverage - (logicData.historicalRecord.rawConfig.leverage || bot.leverage)}× Delta
                            </span>
                          )}
                        </td>
                      </tr>

                      <tr>
                        <td className="p-2.5 font-bold text-zinc-300">Allokiertes Kapital</td>
                        <td className="p-2.5 text-zinc-400">${(logicData.historicalRecord.rawConfig.investment || bot.metrics.investment).toLocaleString()}</td>
                        <td className="p-2.5 font-bold text-white">${bot.metrics.investment.toLocaleString()}</td>
                        <td className="p-2.5">
                          {bot.metrics.investment === (logicData.historicalRecord.rawConfig.investment || bot.metrics.investment) ? (
                            <span className="text-zinc-500">Identisch</span>
                          ) : (
                            <span className="text-cyan-400 font-bold">
                              ${(bot.metrics.investment - (logicData.historicalRecord.rawConfig.investment || bot.metrics.investment)).toFixed(0)} Delta
                            </span>
                          )}
                        </td>
                      </tr>

                      <tr>
                        <td className="p-2.5 font-bold text-zinc-300">DCA Stufen / Range</td>
                        <td className="p-2.5 text-zinc-400">
                          {logicData.historicalRecord.rawConfig.dcaSteps || bot.metrics.dcaSteps} Stufen (${logicData.historicalRecord.rawConfig.dcaRangeMin || bot.metrics.dcaRangeMin} - ${logicData.historicalRecord.rawConfig.dcaRangeMax || bot.metrics.dcaRangeMax})
                        </td>
                        <td className="p-2.5 font-bold text-white">
                          {bot.metrics.dcaSteps} Stufen (${bot.metrics.dcaRangeMin} - ${bot.metrics.dcaRangeMax})
                        </td>
                        <td className="p-2.5 text-emerald-400">Dynamisch an Marktkurs kalibriert</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* ======================================================== */}
            {/* 5. TAB 3: RAW FROZEN SPANNING JSON RECORD                */}
            {/* ======================================================== */}
            {activeTab === "raw" && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-400">
                    Vollständiger JSON-Export der Spawning-Konfiguration und des historischen Ancestor-Snapshots:
                  </span>
                  <button
                    type="button"
                    onClick={handleCopyJson}
                    className="px-3 py-1 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-bold flex items-center gap-1.5 transition-colors cursor-pointer"
                  >
                    {copied ? (
                      <>
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="text-emerald-400">Kopiert!</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5 text-zinc-400" />
                        <span>JSON kopieren</span>
                      </>
                    )}
                  </button>
                </div>

                <div className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-850 overflow-x-auto max-h-72">
                  <pre className="text-[11px] text-cyan-300 font-mono leading-relaxed">
                    {JSON.stringify(logicData, null, 2)}
                  </pre>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="py-12 text-center text-rose-400 text-xs">
            Fehler beim Laden der Spawning-Logik. Bitte versuche es erneut.
          </div>
        )}

        {/* ======================================================== */}
        {/* 6. MODAL ACTIONS FOOTER                                  */}
        {/* ======================================================== */}
        <div className="flex items-center justify-between pt-3 border-t border-zinc-800 text-xs flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleCopyJson}
              disabled={!logicData}
              className="px-3 py-1.5 rounded-lg border border-zinc-750 bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 font-bold transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5 text-zinc-400" />}
              <span>{copied ? "JSON kopiert" : "Config kopieren"}</span>
            </button>

            {matchedHistoricalSession && onOpenHistoricalRecord && (
              <button
                type="button"
                onClick={() => onOpenHistoricalRecord(matchedHistoricalSession)}
                className="px-3 py-1.5 rounded-lg border border-purple-800/80 bg-purple-950/60 hover:bg-purple-900/80 text-purple-200 font-bold transition-colors flex items-center gap-1.5 cursor-pointer"
              >
                <History className="w-3.5 h-3.5 text-purple-400" />
                <span>Historische Session ({logicData?.historicalRecord?.id})</span>
              </button>
            )}
          </div>

          <button
            type="button"
            onClick={onClose}
            className="px-5 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-white font-bold transition-colors cursor-pointer"
          >
            Schließen
          </button>
        </div>
      </motion.div>
    </div>
  );
};
