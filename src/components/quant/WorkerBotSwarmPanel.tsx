import React, { useState, useEffect, useMemo, useCallback } from "react";
import { motion, AnimatePresence } from "motion/react";
import { 
  Bot, Cpu, Play, Pause, RefreshCw, Plus, GitFork, 
  Layers, ShieldAlert, Sparkles, History, CheckCircle2, 
  Sliders, X, ArrowRight, Zap, TrendingUp, AlertTriangle
} from "lucide-react";
import { WorkerBotData, HistoricalBotSession } from "../../types/trading";
import { WorkerBotCard } from "../WorkerBotCard";
import { safeFetchJson } from "../../lib/api";

interface WorkerBotSwarmPanelProps {
  onSelectBot?: (bot: WorkerBotData) => void;
}

export const WorkerBotSwarmPanel: React.FC<WorkerBotSwarmPanelProps> = ({
  onSelectBot
}) => {
  const [workers, setWorkers] = useState<WorkerBotData[]>([]);
  const [historySessions, setHistorySessions] = useState<HistoricalBotSession[]>([]);
  const [selectedBotId, setSelectedBotId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [filterStatus, setFilterStatus] = useState<"all" | "active" | "paused">("all");
  const [searchPair, setSearchPair] = useState<string>("");
  const [isSpawning, setIsSpawning] = useState<boolean>(false);
  const [notification, setNotification] = useState<{ type: "success" | "error" | "info"; message: string } | null>(null);

  // Historical Respawn Modal State
  const [isHistoryModalOpen, setIsHistoryModalOpen] = useState<boolean>(false);
  const [selectedHistorical, setSelectedHistorical] = useState<HistoricalBotSession | null>(null);
  const [modifierLeverage, setModifierLeverage] = useState<number>(3);
  const [modifierInvestment, setModifierInvestment] = useState<number>(5000);
  const [modifierCustomName, setModifierCustomName] = useState<string>("");

  // Fetch active workers
  const fetchWorkers = useCallback(async () => {
    try {
      const data = await safeFetchJson<{ success: boolean; workers: WorkerBotData[] }>("/api/quant/workers");
      if (data && Array.isArray(data.workers)) {
        setWorkers(data.workers);
      }
    } catch (err) {
      console.error("Failed to fetch worker bots:", err);
    }
  }, []);

  // Fetch historical sessions
  const fetchHistory = useCallback(async () => {
    try {
      const data = await safeFetchJson<{ success: boolean; sessions: HistoricalBotSession[] }>("/api/quant/workers/history");
      if (data && Array.isArray(data.sessions)) {
        setHistorySessions(data.sessions);
      }
    } catch (err) {
      console.error("Failed to fetch historical bot sessions:", err);
    }
  }, []);

  useEffect(() => {
    setIsLoading(true);
    Promise.all([fetchWorkers(), fetchHistory()]).finally(() => {
      setIsLoading(false);
    });

    // Connect to SSE stream for live tick updates
    let eventSource: EventSource | null = null;
    try {
      eventSource = new EventSource("/api/quant/telemetry/stream");
      eventSource.addEventListener("telemetry", (e: MessageEvent) => {
        try {
          const payload = JSON.parse(e.data);
          if (payload.workers && Array.isArray(payload.workers)) {
            setWorkers(payload.workers);
          }
        } catch {
          // ignore malformed frame
        }
      });
    } catch {
      // fallback to polling
    }

    const pollInterval = setInterval(fetchWorkers, 4000);

    return () => {
      if (eventSource) eventSource.close();
      clearInterval(pollInterval);
    };
  }, [fetchWorkers, fetchHistory]);

  const showNotification = (type: "success" | "error" | "info", message: string) => {
    setNotification({ type, message });
    setTimeout(() => {
      setNotification(null);
    }, 4500);
  };

  // Toggle Bot Status
  const handleToggleStatus = async (id: string) => {
    try {
      const res = await safeFetchJson<{ success: boolean; bot: WorkerBotData; message: string }>(
        `/api/quant/workers/${id}/toggle`,
        { method: "POST" }
      );
      if (res && res.success) {
        setWorkers(prev => prev.map(w => (w.id === id ? res.bot : w)));
        showNotification("success", res.message);
      }
    } catch (err) {
      console.error("Toggle error:", err);
      showNotification("error", "Status-Umschaltung fehlgeschlagen.");
    }
  };

  // Autonomous Spawn from History Trigger (The core user request)
  const handleExecuteSpawn = async (historicalBotId: string, customModifier?: any) => {
    setIsSpawning(true);
    try {
      const res = await safeFetchJson<{ success: boolean; message: string; bot: WorkerBotData }>(
        "/api/quant/workers/spawn-from-history",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            historical_bot_id: historicalBotId,
            modifier: customModifier
          })
        }
      );

      if (res && res.success) {
        setWorkers(prev => [res.bot, ...prev.filter(b => b.id !== res.bot.id)]);
        showNotification("success", `Autonomous Respawn: Bot '${res.bot.id}' wurde autonom gestartet!`);
        setIsHistoryModalOpen(false);
        setSelectedHistorical(null);
      } else {
        showNotification("error", "Spawn fehlgeschlagen.");
      }
    } catch (err) {
      console.error("Spawn error:", err);
      showNotification("error", "Verbindungsfehler beim Spawnen des Bots.");
    } finally {
      setIsSpawning(false);
    }
  };

  // Open modal with preselected historical bot
  const handleOpenHistoryModal = (historical?: HistoricalBotSession) => {
    const target = historical || historySessions[0] || null;
    setSelectedHistorical(target);
    if (target) {
      setModifierLeverage(target.config.leverage || 3);
      setModifierInvestment(target.config.investment || 5000);
      setModifierCustomName(`${target.name} [Autonomous Klon]`);
    }
    setIsHistoryModalOpen(true);
  };

  // Filtered workers list
  const filteredWorkers = useMemo(() => {
    return workers.filter(w => {
      const matchesStatus = filterStatus === "all" || w.status === filterStatus;
      const matchesSearch = !searchPair || 
        w.pair.toLowerCase().includes(searchPair.toLowerCase()) ||
        w.name.toLowerCase().includes(searchPair.toLowerCase()) ||
        w.id.toLowerCase().includes(searchPair.toLowerCase());
      return matchesStatus && matchesSearch;
    });
  }, [workers, filterStatus, searchPair]);

  // Aggregate Swarm Metrics
  const aggregateMetrics = useMemo(() => {
    let totalInvested = 0;
    let totalUnrealized = 0;
    let totalRealized = 0;
    let totalProfit = 0;
    let activeCount = 0;

    workers.forEach(w => {
      totalInvested += w.metrics.investment;
      totalUnrealized += w.unrealizedPnL.value;
      totalRealized += w.metrics.realizedProfit;
      totalProfit += w.totalProfit;
      if (w.status === "active") activeCount++;
    });

    const netRoi = totalInvested > 0 ? ((totalProfit / totalInvested) * 100) : 0;

    return {
      totalInvested,
      totalUnrealized,
      totalRealized,
      totalProfit,
      activeCount,
      totalCount: workers.length,
      netRoi
    };
  }, [workers]);

  return (
    <div id="worker-bot-swarm-panel" className="space-y-5 font-mono">
      {/* ======================================================== */}
      {/* 1. AUTONOMOUS SWARM CONTROLLER & REGIME STATUS           */}
      {/* ======================================================== */}
      <div className="bg-gradient-to-r from-zinc-900 via-zinc-900 to-zinc-950 border border-zinc-800 rounded-xl p-4 sm:p-5 shadow-sm relative overflow-hidden">
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className="p-2 rounded-lg bg-emerald-950/70 border border-emerald-700/60 text-emerald-400">
                <Cpu className="w-5 h-5" />
              </span>
              <h2 className="text-base font-bold text-white tracking-wide">
                The Swarm: Autonomous Multi-Agent Trading Fleet
              </h2>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-900/60 border border-emerald-700/70 text-emerald-300 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                <span>AGENT RESPOND ENGINE LIVE</span>
              </span>
            </div>

            <p className="text-xs text-zinc-400 max-w-3xl leading-relaxed">
              Autonome Orchestrierung via <strong>Neo_Fable / KimiSwarm</strong>. Erkennt Regimewechsel (DFA Hurst &amp; Ampel-Indikator) 
              und klont erprobte historische Bot-Sessions vollautomatisch mit adaptiven Volatilitäts-Parametern.
            </p>
          </div>

          <div className="flex items-center gap-2.5 flex-wrap shrink-0">
            <button
              id="open-history-library-btn"
              type="button"
              onClick={() => handleOpenHistoryModal()}
              className="px-3 py-2 rounded-lg bg-purple-950/70 hover:bg-purple-900/80 border border-purple-800/80 text-purple-200 text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer shadow-xs active:scale-95"
            >
              <History className="w-4 h-4 text-purple-400" />
              <span>Session History ({historySessions.length})</span>
            </button>

            <button
              id="autonomous-spawn-quick-btn"
              type="button"
              disabled={isSpawning}
              onClick={() => {
                const best = historySessions[0];
                if (best) {
                  handleExecuteSpawn(best.id, {
                    leverage: 3,
                    name: `${best.name} [Neo_Fable Autonomous Auto-Respawn]`
                  });
                }
              }}
              className="px-3.5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-zinc-950 font-bold text-xs transition-all flex items-center gap-2 cursor-pointer shadow-md active:scale-95 disabled:opacity-50"
            >
              <Sparkles className="w-4 h-4 fill-zinc-950" />
              <span>{isSpawning ? "AI Spawning..." : "AI Auto-Respawn (Tool Call)"}</span>
            </button>

            <button
              id="refresh-swarm-btn"
              type="button"
              onClick={() => {
                fetchWorkers();
                fetchHistory();
              }}
              className="p-2 rounded-lg border border-zinc-700 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-all cursor-pointer"
              title="Aktualisieren"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin text-cyan-400" : ""}`} />
            </button>
          </div>
        </div>

        {/* Notifications */}
        <AnimatePresence>
          {notification && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className={`mt-3 p-2.5 rounded-lg border text-xs flex items-center justify-between gap-2 ${
                notification.type === "success"
                  ? "bg-emerald-950/90 border-emerald-700 text-emerald-200"
                  : notification.type === "error"
                  ? "bg-rose-950/90 border-rose-700 text-rose-200"
                  : "bg-blue-950/90 border-blue-700 text-blue-200"
              }`}
            >
              <div className="flex items-center gap-2">
                {notification.type === "success" ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                ) : (
                  <AlertTriangle className="w-4 h-4 text-rose-400" />
                )}
                <span>{notification.message}</span>
              </div>
              <button
                type="button"
                onClick={() => setNotification(null)}
                className="text-zinc-400 hover:text-white"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ======================================================== */}
      {/* 2. AGGREGATE METRICS BANNER                              */}
      {/* ======================================================== */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
        <div className="p-3.5 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-between">
          <div>
            <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">
              Active Workers
            </span>
            <div className="text-xl font-bold text-white mt-0.5">
              {aggregateMetrics.activeCount} <span className="text-xs text-zinc-400 font-normal">/ {aggregateMetrics.totalCount} active</span>
            </div>
          </div>
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_10px_rgba(52,211,153,0.6)]" />
        </div>

        <div className="p-3.5 rounded-xl bg-zinc-900 border border-zinc-800">
          <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">
            Total Capital Deployed
          </span>
          <div className="text-xl font-bold text-white mt-0.5">
            ${aggregateMetrics.totalInvested.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>

        <div className="p-3.5 rounded-xl bg-zinc-900 border border-zinc-800">
          <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">
            Unrealized P&amp;L
          </span>
          <div className={`text-xl font-bold mt-0.5 ${aggregateMetrics.totalUnrealized >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {aggregateMetrics.totalUnrealized >= 0 ? "+" : ""}${aggregateMetrics.totalUnrealized.toFixed(2)}
          </div>
        </div>

        <div className="p-3.5 rounded-xl bg-zinc-900 border border-zinc-800">
          <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">
            Cumulative Swarm P&amp;L (ROI)
          </span>
          <div className={`text-xl font-bold mt-0.5 ${aggregateMetrics.totalProfit >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {aggregateMetrics.totalProfit >= 0 ? "+" : ""}${aggregateMetrics.totalProfit.toFixed(2)}
            <span className="text-xs ml-1 font-semibold text-cyan-300">({aggregateMetrics.netRoi.toFixed(1)}%)</span>
          </div>
        </div>
      </div>

      {/* ======================================================== */}
      {/* 3. FILTER & SEARCH CONTROLS                              */}
      {/* ======================================================== */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-3 bg-zinc-900/60 border border-zinc-800 rounded-xl">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-zinc-400 font-bold mr-1">Status:</span>
          {(["all", "active", "paused"] as const).map(mode => (
            <button
              key={mode}
              type="button"
              onClick={() => setFilterStatus(mode)}
              className={`px-3 py-1 rounded-lg text-xs font-bold uppercase transition-all ${
                filterStatus === mode
                  ? "bg-zinc-800 text-white border border-zinc-700 shadow-xs"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-850"
              }`}
            >
              {mode === "all" ? `Alle (${workers.length})` : mode === "active" ? `Active (${workers.filter(w => w.status === "active").length})` : `Paused (${workers.filter(w => w.status === "paused").length})`}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Search pair, name or ID..."
            value={searchPair}
            onChange={(e) => setSearchPair(e.target.value)}
            className="px-3 py-1.5 rounded-lg bg-zinc-950 border border-zinc-800 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-hidden focus:border-cyan-500 w-full sm:w-60"
          />
        </div>
      </div>

      {/* ======================================================== */}
      {/* 4. LIVE WORKER BOTS GRID (DURABLE & FULLY DYNAMIC)      */}
      {/* ======================================================== */}
      {filteredWorkers.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-2 gap-5">
          {filteredWorkers.map(bot => (
            <WorkerBotCard
              key={bot.id}
              bot={bot}
              isSelected={selectedBotId === bot.id}
              onSelect={(selected) => {
                setSelectedBotId(selected.id);
                onSelectBot?.(selected);
              }}
              onToggleStatus={handleToggleStatus}
              onClone={(clonedBot) => {
                const hist = historySessions.find(h => h.id === clonedBot.spawnedFrom) || {
                  id: clonedBot.id,
                  name: clonedBot.name,
                  pair: clonedBot.pair,
                  regime: "live_clone",
                  final_pnl: clonedBot.totalProfit,
                  roi: clonedBot.roi,
                  stopped_at: new Date().toISOString(),
                  config: { ...clonedBot }
                };
                handleOpenHistoryModal(hist);
              }}
            />
          ))}
        </div>
      ) : (
        <div className="p-8 rounded-xl border border-dashed border-zinc-800 text-center space-y-3 bg-zinc-950/40">
          <Bot className="w-8 h-8 text-zinc-600 mx-auto" />
          <p className="text-xs text-zinc-400">
            Keine Worker-Bots für die aktuellen Filterkriterien gefunden.
          </p>
          <button
            type="button"
            onClick={() => handleOpenHistoryModal()}
            className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-zinc-950 text-xs font-bold transition-colors inline-flex items-center gap-1.5 cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Historische Session wiederbeleben</span>
          </button>
        </div>
      )}

      {/* ======================================================== */}
      {/* 5. HISTORICAL SESSION CLONING / RESPAWN MODAL            */}
      {/* ======================================================== */}
      <AnimatePresence>
        {isHistoryModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="bg-zinc-900 border border-zinc-800 rounded-xl max-w-2xl w-full p-5 sm:p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto"
            >
              <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
                <div className="flex items-center gap-2">
                  <div className="p-2 rounded-lg bg-purple-950/80 border border-purple-800/80 text-purple-300">
                    <History className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-white">
                      Historische Bot-Sessions (bot_history)
                    </h3>
                    <p className="text-[11px] text-zinc-400">
                      Wähle eine historische Session, passe Parameter (AI Modifier) an und starte den Bot als neue Live-Session.
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setIsHistoryModalOpen(false)}
                  className="p-1 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Session Selector List */}
              <div className="space-y-2">
                <label className="text-[10px] uppercase font-bold text-zinc-400 tracking-wider">
                  Verfügbare historische Sessions:
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                  {historySessions.map(session => {
                    const isSelected = selectedHistorical?.id === session.id;
                    return (
                      <div
                        key={session.id}
                        onClick={() => {
                          setSelectedHistorical(session);
                          setModifierLeverage(session.config.leverage || 3);
                          setModifierInvestment(session.config.investment || 5000);
                          setModifierCustomName(`${session.name} [Autonomous Klon]`);
                        }}
                        className={`p-3 rounded-lg border text-xs cursor-pointer transition-all ${
                          isSelected
                            ? "bg-purple-950/60 border-purple-600/80 text-white ring-1 ring-purple-500/40"
                            : "bg-zinc-950/70 border-zinc-800 hover:border-zinc-700 text-zinc-300"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-bold truncate">{session.pair}</span>
                          <span className="text-[10px] text-emerald-400 font-bold">+{session.roi}%</span>
                        </div>
                        <span className="text-[10px] text-zinc-400 block truncate">{session.name}</span>
                        <div className="flex items-center justify-between text-[10px] text-zinc-500 mt-1.5 pt-1 border-t border-zinc-800/80">
                          <span>Profit: ${session.final_pnl.toFixed(0)}</span>
                          <span className="uppercase text-purple-400">{session.regime}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Parameter Modifier Section */}
              {selectedHistorical && (
                <div className="space-y-3 p-4 rounded-xl bg-zinc-950/80 border border-zinc-800/90 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-cyan-300 flex items-center gap-1.5">
                      <Sliders className="w-3.5 h-3.5" />
                      <span>AI Parameter Modifier (Neo_Fable Anpassungen)</span>
                    </span>
                    <span className="text-[10px] text-zinc-400">
                      ID Vorbild: <strong className="text-zinc-200">{selectedHistorical.id}</strong>
                    </span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="text-[10px] text-zinc-400 block mb-1">
                        Bot-Bezeichnung:
                      </label>
                      <input
                        type="text"
                        value={modifierCustomName}
                        onChange={(e) => setModifierCustomName(e.target.value)}
                        className="w-full px-2.5 py-1.5 rounded bg-zinc-900 border border-zinc-700 text-xs text-white focus:outline-hidden focus:border-cyan-500"
                      />
                    </div>

                    <div>
                      <label className="text-[10px] text-zinc-400 block mb-1">
                        Hebel (Leverage Multiplier): <strong className="text-white">{modifierLeverage}×</strong>
                      </label>
                      <div className="flex items-center gap-2">
                        <input
                          type="range"
                          min={1}
                          max={20}
                          step={1}
                          value={modifierLeverage}
                          onChange={(e) => setModifierLeverage(Number(e.target.value))}
                          className="flex-1 accent-purple-500 cursor-pointer"
                        />
                        <span className="w-8 text-right font-bold text-purple-300">{modifierLeverage}×</span>
                      </div>
                    </div>

                    <div>
                      <label className="text-[10px] text-zinc-400 block mb-1">
                        Investment-Allokation:
                      </label>
                      <input
                        type="number"
                        min={100}
                        max={100000}
                        step={500}
                        value={modifierInvestment}
                        onChange={(e) => setModifierInvestment(Number(e.target.value))}
                        className="w-full px-2.5 py-1.5 rounded bg-zinc-900 border border-zinc-700 text-xs text-white focus:outline-hidden focus:border-cyan-500"
                      />
                    </div>

                    <div>
                      <label className="text-[10px] text-zinc-400 block mb-1">
                        Strategie-Typ &amp; Basis-Paar:
                      </label>
                      <div className="px-2.5 py-1.5 rounded bg-zinc-900/60 border border-zinc-800 text-zinc-300 truncate">
                        {selectedHistorical.config.strategy || "M8 KELLY DCA"} • {selectedHistorical.pair}
                      </div>
                    </div>
                  </div>

                  <div className="pt-2 border-t border-zinc-850 flex items-center justify-between text-[11px] text-zinc-400">
                    <span>DCA Stufen: <strong className="text-zinc-200">{selectedHistorical.config.dcaSteps || 5}</strong></span>
                    <span>Range: <strong className="text-zinc-200">${selectedHistorical.config.dcaRangeMin} - ${selectedHistorical.config.dcaRangeMax}</strong></span>
                    <span>Est. Liq-Distanz: <strong className="text-emerald-400">{selectedHistorical.config.liquidationDistancePct || 25}%</strong></span>
                  </div>
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsHistoryModalOpen(false)}
                  className="px-4 py-2 rounded-lg text-xs font-bold text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
                >
                  Abbrechen
                </button>

                <button
                  id="confirm-respawn-modal-btn"
                  type="button"
                  disabled={!selectedHistorical || isSpawning}
                  onClick={() => {
                    if (selectedHistorical) {
                      handleExecuteSpawn(selectedHistorical.id, {
                        name: modifierCustomName,
                        leverage: modifierLeverage,
                        metrics: {
                          investment: modifierInvestment
                        }
                      });
                    }
                  }}
                  className="px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-zinc-950 font-bold text-xs transition-all flex items-center gap-2 cursor-pointer shadow-md active:scale-95 disabled:opacity-50"
                >
                  <Sparkles className="w-4 h-4 fill-zinc-950" />
                  <span>{isSpawning ? "Klone Bot..." : "Als neuen Live-Worker spawnen"}</span>
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};
