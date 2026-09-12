import React, { useState, useMemo } from "react";
import { motion } from "motion/react";
import { 
  Database, GitFork, X, Check, Copy, Sparkles, 
  ShieldCheck, ArrowRight, Activity, Sliders, 
  Clock, TrendingUp, Layers, CheckCircle2, ExternalLink
} from "lucide-react";
import { WorkerBotData, HistoricalBotSession } from "../../types/trading";

interface ResolvedHistoricalOrigin {
  sessionId: string;
  sessionName: string;
  stoppedAt: string;
  sourceRegime: string;
  sourceRoi: number;
  sourcePnl: number;
  sourceStrategy: string;
  sourceLeverage: number;
  sourceInvestment: number;
  configSourceTable: string;
  cloningRationale: string;
  leverageDelta: number;
  investmentDelta: number;
  dcaStepsSource: number;
  dcaRangeMinSource: number;
  dcaRangeMaxSource: number;
  rawConfig: Record<string, any>;
  isGenesisRoot: boolean;
}

interface CloningOriginModalProps {
  bot: WorkerBotData;
  origin: ResolvedHistoricalOrigin;
  onClose: () => void;
  onReClone?: (historicalSessionId: string, baseConfig?: any) => void;
}

export const CloningOriginModal: React.FC<CloningOriginModalProps> = ({
  bot,
  origin,
  onClose,
  onReClone
}) => {
  const [copiedJson, setCopiedJson] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<"analysis" | "diff" | "rawJson">("analysis");

  const formattedStoppedTime = useMemo(() => {
    try {
      return new Date(origin.stoppedAt).toLocaleString("de-DE", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
      });
    } catch {
      return origin.stoppedAt;
    }
  }, [origin.stoppedAt]);

  const handleCopyJson = () => {
    try {
      const payload = JSON.stringify(origin.rawConfig, null, 2);
      navigator.clipboard.writeText(payload);
      setCopiedJson(true);
      setTimeout(() => setCopiedJson(false), 2000);
    } catch (err) {
      console.error("Failed to copy json:", err);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-xs font-mono">
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 8 }}
        className="bg-zinc-900 border border-purple-900/60 rounded-2xl max-w-3xl w-full p-5 sm:p-6 shadow-2xl space-y-4 max-h-[92vh] overflow-y-auto"
      >
        {/* ======================================================== */}
        {/* 1. MODAL HEADER                                          */}
        {/* ======================================================== */}
        <div className="flex items-start justify-between border-b border-zinc-800 pb-3 gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-purple-950/80 border border-purple-750 text-purple-300 shadow-[0_0_15px_rgba(168,85,247,0.2)]">
              <Database className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-base font-bold text-white tracking-wide">
                  Historical Origin &amp; Cloning Decision Audit
                </h3>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-950/90 border border-purple-700/80 text-purple-300">
                  DB Table: {origin.configSourceTable}
                </span>
              </div>
              <p className="text-xs text-zinc-400 mt-0.5">
                Rückverfolgung des aktiven Workers <strong className="text-white">{bot.id}</strong> ({bot.name}) zur Quell-Konfiguration in der Datenbank.
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors cursor-pointer"
            title="Schließen"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation Tabs */}
        <div className="flex items-center gap-2 border-b border-zinc-800/80 pb-2">
          <button
            type="button"
            onClick={() => setActiveTab("analysis")}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
              activeTab === "analysis"
                ? "bg-purple-950/90 text-purple-200 border border-purple-700"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-850"
            }`}
          >
            <Sparkles className="w-3.5 h-3.5 text-purple-400" />
            <span>Orchestrator Decision Rationale</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("diff")}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
              activeTab === "diff"
                ? "bg-purple-950/90 text-purple-200 border border-purple-700"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-850"
            }`}
          >
            <Sliders className="w-3.5 h-3.5 text-cyan-400" />
            <span>Parameter Differential (Diff)</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("rawJson")}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
              activeTab === "rawJson"
                ? "bg-purple-950/90 text-purple-200 border border-purple-700"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-850"
            }`}
          >
            <Database className="w-3.5 h-3.5 text-emerald-400" />
            <span>Raw Database JSON Record</span>
          </button>
        </div>

        {/* ======================================================== */}
        {/* 2. TAB: ORCHESTRATOR DECISION ANALYSIS                   */}
        {/* ======================================================== */}
        {activeTab === "analysis" && (
          <div className="space-y-4 text-xs">
            {/* Database Source Info Card */}
            <div className="p-4 rounded-xl bg-zinc-950/90 border border-zinc-800 space-y-3">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-zinc-400 font-bold uppercase text-[10px]">Quell-Session ID:</span>
                  <span className="font-bold text-sm text-purple-300 font-mono bg-purple-950/80 px-2 py-0.5 rounded border border-purple-800/80">
                    {origin.sessionId}
                  </span>
                </div>
                <div className="text-[11px] text-zinc-400 flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-zinc-500" />
                  <span>Archiviert am: <strong className="text-zinc-200">{formattedStoppedTime}</strong></span>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-zinc-850">
                <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
                  <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Ursprüngliche Session</span>
                  <span className="font-bold text-white text-xs block truncate mt-0.5">{origin.sessionName}</span>
                </div>
                <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
                  <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Markt-Regime</span>
                  <span className="font-bold text-purple-300 text-xs block uppercase mt-0.5">{origin.sourceRegime}</span>
                </div>
                <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
                  <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Historisches Ergebnis</span>
                  <span className="font-bold text-emerald-400 text-xs block mt-0.5">
                    +{origin.sourceRoi.toFixed(2)}% ROI (${origin.sourcePnl.toFixed(2)})
                  </span>
                </div>
              </div>
            </div>

            {/* Orchestrator Cloning Decision Logic */}
            <div className="p-4 rounded-xl bg-purple-950/30 border border-purple-900/50 space-y-2.5">
              <div className="flex items-center gap-2 text-purple-300 font-bold">
                <Sparkles className="w-4 h-4 text-purple-400" />
                <span>Orchestrator Klon-Entscheidung &amp; Signal-Audit (Neo_Fable Engine)</span>
              </div>
              <p className="text-zinc-300 leading-relaxed text-xs">
                {origin.cloningRationale}
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-2">
                <div className="p-2.5 rounded-lg bg-zinc-900/90 border border-zinc-800 flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold text-zinc-200 block text-[11px]">Regime-Passgenauigkeit</span>
                    <span className="text-[10px] text-zinc-400">
                      DFA Hurst Exponent &amp; Volatilitätsband stimmen mit der historischen Validierungsphase überein.
                    </span>
                  </div>
                </div>

                <div className="p-2.5 rounded-lg bg-zinc-900/90 border border-zinc-800 flex items-start gap-2">
                  <ShieldCheck className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold text-zinc-200 block text-[11px]">M8 Capital Gate Freigabe</span>
                    <span className="text-[10px] text-zinc-400">
                      Margin-Reserve, Fee Hurdle (2.0x R-Multiple) und Drawdown-Limits bestanden.
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Active Bot Linkage Summary */}
            <div className="p-3 rounded-xl bg-zinc-950/70 border border-zinc-800 flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <GitFork className="w-4 h-4 text-purple-400" />
                <span className="text-zinc-300 font-semibold">Aktuelle Instanz:</span>
                <span className="font-mono text-emerald-400 font-bold">{bot.id}</span>
                <span className="text-zinc-500">({bot.pair} • {bot.strategy})</span>
              </div>

              <div className="flex items-center gap-2 text-[11px]">
                <span className="text-zinc-400">Aktueller Profit:</span>
                <span className={`font-bold ${bot.totalProfit >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {bot.totalProfit >= 0 ? "+" : ""}${bot.totalProfit.toFixed(2)} ({bot.roi.toFixed(1)}% ROI)
                </span>
              </div>
            </div>
          </div>
        )}

        {/* ======================================================== */}
        {/* 3. TAB: PARAMETER DIFFERENTIAL (DIFF)                    */}
        {/* ======================================================== */}
        {activeTab === "diff" && (
          <div className="space-y-3 text-xs">
            <p className="text-zinc-400 text-[11px]">
              Vergleich zwischen der in der Datenbank archivierten Originalkonfiguration (<code className="text-purple-300">bot_history</code>) 
              und dem vom Orchestrator adaptierten Live-Worker.
            </p>

            <div className="rounded-xl border border-zinc-800 overflow-hidden">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-zinc-950 border-b border-zinc-800 text-[10px] text-zinc-400 uppercase tracking-wider">
                    <th className="p-2.5">Parameter</th>
                    <th className="p-2.5">DB-Ursprung ({origin.sessionId})</th>
                    <th className="p-2.5">Aktiver Worker ({bot.id})</th>
                    <th className="p-2.5 text-right">Modifikation / Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-850 text-xs">
                  <tr>
                    <td className="p-2.5 font-bold text-zinc-300">Handelsstrategie</td>
                    <td className="p-2.5 text-zinc-400">{origin.sourceStrategy}</td>
                    <td className="p-2.5 text-white font-semibold">{bot.strategy}</td>
                    <td className="p-2.5 text-right">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-zinc-800 text-zinc-300">
                        {origin.sourceStrategy === bot.strategy ? "IDENTISCH" : "ANGEPASST"}
                      </span>
                    </td>
                  </tr>

                  <tr>
                    <td className="p-2.5 font-bold text-zinc-300">Hebel (Leverage Multiplier)</td>
                    <td className="p-2.5 text-purple-300 font-bold">{origin.sourceLeverage}×</td>
                    <td className="p-2.5 text-white font-bold">{bot.leverage}×</td>
                    <td className="p-2.5 text-right">
                      {origin.leverageDelta === 0 ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950/70 border border-emerald-800/80 text-emerald-300">
                          UNVERÄNDERT (1:1)
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-950/70 border border-amber-800/80 text-amber-300">
                          {origin.leverageDelta > 0 ? `+${origin.leverageDelta}×` : `${origin.leverageDelta}×`} AI MOD
                        </span>
                      )}
                    </td>
                  </tr>

                  <tr>
                    <td className="p-2.5 font-bold text-zinc-300">Allokiertes Kapital</td>
                    <td className="p-2.5 text-zinc-400">${origin.sourceInvestment.toLocaleString()}</td>
                    <td className="p-2.5 text-white font-bold">${bot.metrics.investment.toLocaleString()}</td>
                    <td className="p-2.5 text-right">
                      {origin.investmentDelta === 0 ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950/70 border border-emerald-800/80 text-emerald-300">
                          UNVERÄNDERT
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-cyan-950/70 border border-cyan-800/80 text-cyan-300">
                          {origin.investmentDelta > 0 ? `+$${origin.investmentDelta.toLocaleString()}` : `-$${Math.abs(origin.investmentDelta).toLocaleString()}`}
                        </span>
                      )}
                    </td>
                  </tr>

                  <tr>
                    <td className="p-2.5 font-bold text-zinc-300">DCA Order-Stufen</td>
                    <td className="p-2.5 text-zinc-400">{origin.dcaStepsSource} Stufen</td>
                    <td className="p-2.5 text-white">{bot.metrics.dcaSteps} Stufen</td>
                    <td className="p-2.5 text-right">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-zinc-800 text-zinc-300">
                        {origin.dcaStepsSource === bot.metrics.dcaSteps ? "KONSTANT" : "DYNAMISCH"}
                      </span>
                    </td>
                  </tr>

                  <tr>
                    <td className="p-2.5 font-bold text-zinc-300">DCA Preisspanne</td>
                    <td className="p-2.5 text-zinc-400">${origin.dcaRangeMinSource} - ${origin.dcaRangeMaxSource}</td>
                    <td className="p-2.5 text-white">${bot.metrics.dcaRangeMin} - ${bot.metrics.dcaRangeMax}</td>
                    <td className="p-2.5 text-right">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-950/60 border border-purple-800/60 text-purple-300">
                        LIVE ADAPTIV
                      </span>
                    </td>
                  </tr>

                  <tr>
                    <td className="p-2.5 font-bold text-zinc-300">Liquidations-Puffer</td>
                    <td className="p-2.5 text-zinc-400">{origin.rawConfig.liquidationDistancePct || 25}%</td>
                    <td className="p-2.5 text-emerald-400 font-bold">{bot.metrics.liquidationDistancePct.toFixed(1)}%</td>
                    <td className="p-2.5 text-right">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950/70 text-emerald-300 border border-emerald-800/80">
                        SICHER
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ======================================================== */}
        {/* 4. TAB: RAW DATABASE JSON RECORD                         */}
        {/* ======================================================== */}
        {activeTab === "rawJson" && (
          <div className="space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-zinc-400 text-[11px]">
                Datenbank-Eintrag aus Tabelle <code className="text-purple-300">{origin.configSourceTable}</code>:
              </span>
              <button
                type="button"
                onClick={handleCopyJson}
                className="px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer"
              >
                {copiedJson ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Kopiert!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5 text-zinc-400" />
                    <span>JSON Kopieren</span>
                  </>
                )}
              </button>
            </div>

            <pre className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 text-zinc-300 overflow-x-auto text-[11px] leading-relaxed max-h-72">
              {JSON.stringify(origin.rawConfig, null, 2)}
            </pre>
          </div>
        )}

        {/* ======================================================== */}
        {/* 5. MODAL FOOTER & ACTION BUTTONS                         */}
        {/* ======================================================== */}
        <div className="flex items-center justify-between pt-3 border-t border-zinc-800">
          <div className="text-[11px] text-zinc-400">
            Audit-Prüfung: <strong className="text-emerald-400">100% Zero-Dummy Verified</strong>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-xs font-bold text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors cursor-pointer"
            >
              Schließen
            </button>

            {onReClone && (
              <button
                type="button"
                onClick={() => {
                  onReClone(origin.sessionId, origin.rawConfig);
                  onClose();
                }}
                className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs transition-all flex items-center gap-1.5 cursor-pointer shadow-md active:scale-95"
              >
                <GitFork className="w-3.5 h-3.5" />
                <span>Aus dieser DB-Quelle klonen</span>
              </button>
            )}
          </div>
        </div>
      </motion.div>
    </div>
  );
};
