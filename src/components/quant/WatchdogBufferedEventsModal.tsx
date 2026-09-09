import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "motion/react";
import { 
  Activity, X, Search, Filter, RefreshCw, Copy, Check, 
  Trash2, ShieldCheck, Clock, Terminal, AlertTriangle, 
  CheckCircle2, ArrowDownUp, Zap, Server, Layers, Eye
} from "lucide-react";
import { WatchdogBufferedEvent } from "../../types";

interface WatchdogBufferedEventsModalProps {
  isOpen: boolean;
  onClose: () => void;
  bufferedEvents: WatchdogBufferedEvent[];
  onFlushBuffer?: () => void;
  onRefresh?: () => void;
  bufferCapacity?: number;
}

export function WatchdogBufferedEventsModal({
  isOpen,
  onClose,
  bufferedEvents,
  onFlushBuffer,
  onRefresh,
  bufferCapacity = 512
}: WatchdogBufferedEventsModalProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [severityFilter, setSeverityFilter] = useState<string>("ALL");
  const [typeFilter, setTypeFilter] = useState<string>("ALL");
  const [copied, setCopied] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<WatchdogBufferedEvent | null>(null);
  const [isFlushing, setIsFlushing] = useState(false);

  // Filtered event list
  const filteredEvents = useMemo(() => {
    return bufferedEvents.filter(ev => {
      if (severityFilter !== "ALL" && ev.severity !== severityFilter) return false;
      if (typeFilter !== "ALL" && ev.type !== typeFilter) return false;
      if (searchTerm.trim()) {
        const query = searchTerm.toLowerCase();
        return (
          ev.id.toLowerCase().includes(query) ||
          ev.module.toLowerCase().includes(query) ||
          ev.type.toLowerCase().includes(query) ||
          ev.details.toLowerCase().includes(query) ||
          ev.source.toLowerCase().includes(query)
        );
      }
      return true;
    });
  }, [bufferedEvents, severityFilter, typeFilter, searchTerm]);

  // Copy entire buffer as JSON
  const handleCopyJSON = () => {
    navigator.clipboard.writeText(JSON.stringify(bufferedEvents, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleFlush = () => {
    setIsFlushing(true);
    if (onFlushBuffer) {
      onFlushBuffer();
    }
    setTimeout(() => {
      setIsFlushing(false);
      setSelectedEvent(null);
    }, 400);
  };

  if (!isOpen) return null;

  const fillPercentage = Math.min(100, Math.round((bufferedEvents.length / bufferCapacity) * 100));

  return (
    <div 
      id="watchdog-buffered-events-modal-overlay"
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-zinc-950/85 backdrop-blur-md overflow-y-auto"
      onClick={onClose}
    >
      <motion.div
        id="watchdog-buffered-events-modal-dialog"
        initial={{ opacity: 0, scale: 0.95, y: 15 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 15 }}
        transition={{ duration: 0.22 }}
        onClick={(e) => e.stopPropagation()}
        className="bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl max-w-5xl w-full text-zinc-200 font-mono overflow-hidden flex flex-col max-h-[90vh] my-auto"
      >
        {/* Modal Header */}
        <div className="px-5 py-4 border-b border-zinc-800 flex items-center justify-between bg-zinc-950/70 shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-emerald-950/80 border border-emerald-700/60 text-emerald-400">
              <Activity className="w-5 h-5 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                  M-17 Watchdog Sentinel: Event-Puffer &amp; Hot-Path Telemetrie
                </h3>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-700/60">
                  {bufferedEvents.length} Events aktiv
                </span>
              </div>
              <p className="text-[11px] text-zinc-400 mt-0.5">
                Puffer-Inspektor für nicht-blockierende Heartbeat-Pulse, Frame-Ticks &amp; Latenz-Audits
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCopyJSON}
              className="px-2.5 py-1.5 rounded-lg text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 hover:border-zinc-600 transition-colors flex items-center gap-1.5 cursor-pointer"
              title="Alle Puffer-Events als JSON kopieren"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5 text-zinc-400" />}
              <span className="text-[11px]">{copied ? "Kopiert!" : "Export JSON"}</span>
            </button>
            <button
              id="close-watchdog-events-modal-btn"
              onClick={onClose}
              className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors cursor-pointer"
              title="Schließen"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Telemetry Buffer Metrics Bar */}
        <div className="px-5 py-3 bg-zinc-950/50 border-b border-zinc-800/80 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs shrink-0">
          <div className="bg-zinc-900/90 border border-zinc-800/90 rounded-lg p-2.5">
            <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Ringbuffer Belegung</span>
            <div className="flex items-baseline gap-1.5 mt-1">
              <span className="text-sm font-bold text-cyan-300">{bufferedEvents.length}</span>
              <span className="text-[10px] text-zinc-400">/ {bufferCapacity} Slots</span>
              <span className="text-[10px] font-bold text-cyan-400 ml-auto">({fillPercentage}%)</span>
            </div>
            <div className="w-full bg-zinc-800 h-1 rounded-full overflow-hidden mt-1.5">
              <div 
                className="bg-cyan-400 h-full rounded-full transition-all" 
                style={{ width: `${fillPercentage}%` }}
              />
            </div>
          </div>

          <div className="bg-zinc-900/90 border border-zinc-800/90 rounded-lg p-2.5">
            <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Verlust-Richtlinie</span>
            <div className="flex items-center gap-1.5 mt-1">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span className="text-xs font-bold text-emerald-400">Zero-Drop Safe</span>
            </div>
            <span className="text-[9px] text-zinc-400 block mt-1">0 verworfene Events (100% Retransmit)</span>
          </div>

          <div className="bg-zinc-900/90 border border-zinc-800/90 rounded-lg p-2.5">
            <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Watchdog Gate</span>
            <div className="flex items-center gap-1.5 mt-1">
              <Clock className="w-4 h-4 text-amber-400" />
              <span className="text-xs font-bold text-amber-300">&lt; 150ms Latenz</span>
            </div>
            <span className="text-[9px] text-zinc-400 block mt-1">Heartbeat-Timeout: 10.0s Hard-Lock</span>
          </div>

          <div className="bg-zinc-900/90 border border-zinc-800/90 rounded-lg p-2.5 flex flex-col justify-between">
            <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Puffer-Aktionen</span>
            <button
              onClick={handleFlush}
              disabled={isFlushing || bufferedEvents.length === 0}
              className="mt-1 py-1 px-2 rounded bg-rose-950/60 hover:bg-rose-900/80 text-rose-300 border border-rose-800/60 hover:border-rose-600 transition-colors flex items-center justify-center gap-1.5 text-[11px] font-bold disabled:opacity-40 cursor-pointer"
            >
              <Trash2 className="w-3 h-3 text-rose-400" />
              <span>{isFlushing ? "Flushe Puffer..." : "Puffer leeren (Flush)"}</span>
            </button>
          </div>
        </div>

        {/* Filter and Search Bar */}
        <div className="p-4 border-b border-zinc-800/80 flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between bg-zinc-900/80 shrink-0">
          <div className="relative flex-1 max-w-md">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Filter nach ID, Modul, Typ oder Payload..."
              className="w-full pl-8 pr-3 py-1.5 bg-zinc-950/80 border border-zinc-800 rounded-lg text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-cyan-500 font-mono"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Severity Filter */}
            <div className="flex items-center rounded-lg bg-zinc-950/80 border border-zinc-800 p-0.5 text-[10px]">
              {["ALL", "OK", "INFO", "WARN"].map((sev) => (
                <button
                  key={sev}
                  onClick={() => setSeverityFilter(sev)}
                  className={`px-2 py-1 rounded transition-colors ${
                    severityFilter === sev
                      ? "bg-zinc-800 text-white font-bold"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  {sev}
                </button>
              ))}
            </div>

            {/* Type Filter */}
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="bg-zinc-950/80 border border-zinc-800 rounded-lg px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-cyan-500 font-mono"
            >
              <option value="ALL">Alle Event-Typen</option>
              <option value="HEARTBEAT_ACK">HEARTBEAT_ACK</option>
              <option value="FRAME_BUFFER_TICK">FRAME_BUFFER_TICK</option>
              <option value="LATENCY_PROBE">LATENCY_PROBE</option>
              <option value="QUEUE_DRAIN">QUEUE_DRAIN</option>
              <option value="STREAM_KEEPALIVE">STREAM_KEEPALIVE</option>
              <option value="CIRCUIT_BREAKER_CHECK">CIRCUIT_BREAKER_CHECK</option>
            </select>
          </div>
        </div>

        {/* Event List Table */}
        <div className="flex-1 overflow-y-auto min-h-[250px] divide-y divide-zinc-800/60">
          {filteredEvents.length === 0 ? (
            <div className="p-12 text-center text-zinc-500 flex flex-col items-center justify-center space-y-2">
              <Server className="w-8 h-8 text-zinc-600" />
              <p className="text-sm font-semibold">Keine Watchdog-Events im Puffer gefunden</p>
              <p className="text-xs text-zinc-600 max-w-sm">
                Der Puffer ist entweder geleert oder es passen keine Events zu den gewählten Such- und Filterkriterien.
              </p>
            </div>
          ) : (
            filteredEvents.map((ev) => {
              const isSelected = selectedEvent?.id === ev.id;
              return (
                <div
                  key={ev.id}
                  onClick={() => setSelectedEvent(isSelected ? null : ev)}
                  className={`px-5 py-3 hover:bg-zinc-800/40 cursor-pointer transition-colors ${
                    isSelected ? "bg-zinc-800/60 border-l-2 border-cyan-400" : ""
                  }`}
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 text-xs">
                    <div className="flex items-center gap-2.5 flex-wrap">
                      <span className="font-mono text-zinc-500 text-[10px]">{ev.timeFormatted}</span>
                      <span className="font-mono font-bold text-cyan-400 text-[11px]">{ev.id}</span>
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-zinc-800 border border-zinc-700 text-zinc-300">
                        {ev.module}
                      </span>
                      <span className={`px-1.5 py-0.5 rounded text-[9px] font-mono font-bold ${
                        ev.severity === "OK" 
                          ? "bg-emerald-950/70 text-emerald-300 border border-emerald-800/50" 
                          : ev.severity === "WARN" 
                          ? "bg-amber-950/70 text-amber-300 border border-amber-800/50"
                          : "bg-blue-950/70 text-blue-300 border border-blue-800/50"
                      }`}>
                        {ev.type}
                      </span>
                    </div>

                    <div className="flex items-center gap-3 text-[11px] text-zinc-400 shrink-0">
                      <span className="font-mono">
                        Latenz: <strong className={ev.latency_ms > 0.5 ? "text-amber-400" : "text-emerald-400"}>
                          {ev.latency_ms.toFixed(2)} ms
                        </strong>
                      </span>
                      {ev.payload_bytes && (
                        <span className="font-mono text-zinc-500 text-[10px]">
                          {ev.payload_bytes} B
                        </span>
                      )}
                    </div>
                  </div>

                  <p className="text-xs text-zinc-300 mt-1.5 pl-0.5 leading-relaxed font-sans">
                    {ev.details}
                  </p>

                  {/* Expanded Detail View */}
                  {isSelected && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      className="mt-3 p-3 bg-zinc-950 rounded-lg border border-zinc-800 text-[11px] space-y-2"
                    >
                      <div className="flex items-center justify-between text-zinc-400 border-b border-zinc-850 pb-1">
                        <span>Event Payload &amp; Telemetrie-Metadaten:</span>
                        <span className="font-mono text-[10px] text-zinc-500">Source: {ev.source}</span>
                      </div>
                      <pre className="text-emerald-400 text-[10px] font-mono overflow-x-auto p-2 bg-zinc-900/80 rounded border border-zinc-800/80">
                        {JSON.stringify(ev, null, 2)}
                      </pre>
                    </motion.div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-5 py-3 bg-zinc-950/70 border-t border-zinc-800 flex items-center justify-between text-xs shrink-0">
          <div className="text-[11px] text-zinc-400">
            Zeige <strong className="text-white">{filteredEvents.length}</strong> von {bufferedEvents.length} Events
          </div>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-white font-medium text-xs transition-colors cursor-pointer"
          >
            Schließen
          </button>
        </div>
      </motion.div>
    </div>
  );
}
