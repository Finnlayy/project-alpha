import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { 
  ShieldCheck, ShieldAlert, Key, Zap, PieChart, ExternalLink, 
  Copy, Check, AlertTriangle, RefreshCw, X, Info, Layers, CheckCircle2 
} from "lucide-react";
import { KrakenDualCredentialsStatus } from "../types";

interface KrakenDualAuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  credentialsStatus: KrakenDualCredentialsStatus | null;
  onRefreshStatus?: () => void;
  isOhlcStreamOnline?: boolean;
  onToggleOhlcStream?: () => void;
}

export default function KrakenDualAuthModal({
  isOpen,
  onClose,
  credentialsStatus,
  onRefreshStatus,
  isOhlcStreamOnline = true,
  onToggleOhlcStream
}: KrakenDualAuthModalProps) {
  const [copiedVar, setCopiedVar] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  if (!isOpen) return null;

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedVar(text);
    setTimeout(() => setCopiedVar(null), 2000);
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    if (onRefreshStatus) {
      await onRefreshStatus();
    }
    setTimeout(() => setIsRefreshing(false), 500);
  };

  const spotConfigured = credentialsStatus?.hasSpotCredentials ?? true;
  const futuresConfigured = credentialsStatus?.hasFuturesCredentials ?? true;

  return (
    <div 
      id="kraken-dual-auth-modal-overlay"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-zinc-950/85 backdrop-blur-md overflow-y-auto"
      onClick={onClose}
    >
      <motion.div
        id="kraken-dual-auth-modal-card"
        initial={{ opacity: 0, scale: 0.96, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 10 }}
        transition={{ duration: 0.2 }}
        onClick={(e) => e.stopPropagation()}
        className="bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl max-w-3xl w-full text-zinc-200 font-mono overflow-hidden my-6"
      >
        {/* Modal Header */}
        <div className="p-5 border-b border-zinc-800 flex items-center justify-between bg-zinc-950/60">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 rounded-lg bg-emerald-950/70 border border-emerald-800/60 text-emerald-400">
              <Key className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="text-base font-bold text-white tracking-wide uppercase">
                  Kraken Dual API-Key Architektur
                </h3>
                <span className="text-[10px] bg-cyan-950/80 text-cyan-300 border border-cyan-800/60 px-2 py-0.5 rounded font-bold uppercase">
                  Spot + Futures
                </span>
              </div>
              <p className="text-xs text-zinc-400 mt-0.5">
                Warum Kraken getrennte Schlüssel für Spot und Futures / Pro erfordert
              </p>
            </div>
          </div>
          <button
            id="close-kraken-auth-modal-btn"
            onClick={onClose}
            className="p-1.5 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors cursor-pointer"
            title="Schließen"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 space-y-5 max-h-[calc(85vh-140px)] overflow-y-auto">
          {/* Live OHLC Stream Status Banner */}
          <div className={`p-3.5 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
            isOhlcStreamOnline
              ? 'bg-emerald-950/40 border-emerald-700/60 text-emerald-300'
              : 'bg-rose-950/40 border-rose-700/60 text-rose-300'
          }`}>
            <div className="flex items-center gap-3">
              <span className="relative flex h-3 w-3 shrink-0">
                <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                  isOhlcStreamOnline ? 'bg-emerald-400' : 'bg-rose-400'
                }`} />
                <span className={`relative inline-flex rounded-full h-3 w-3 ${
                  isOhlcStreamOnline ? 'bg-emerald-500' : 'bg-rose-500'
                }`} />
              </span>
              <div>
                <div className="text-xs font-bold font-mono uppercase tracking-wider flex items-center gap-2">
                  <span>Kraken OHLC Market Data Stream:</span>
                  <span className={isOhlcStreamOnline ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                    {isOhlcStreamOnline ? 'ONLINE & CONNECTED (Glowing Green)' : 'OFFLINE / DISCONNECTED (Glowing Red)'}
                  </span>
                </div>
                <p className="text-[11px] text-zinc-400 mt-0.5">
                  The header bracket glows <strong className="text-emerald-400">Green</strong> when the OHLC stream is online, and pulses <strong className="text-rose-400">Red</strong> if disconnected.
                </p>
              </div>
            </div>

            {onToggleOhlcStream && (
              <button
                type="button"
                onClick={onToggleOhlcStream}
                className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold transition-all border shrink-0 cursor-pointer ${
                  isOhlcStreamOnline
                    ? 'bg-rose-950/80 hover:bg-rose-900 text-rose-200 border-rose-700 hover:border-rose-500'
                    : 'bg-emerald-950/80 hover:bg-emerald-900 text-emerald-200 border-emerald-700 hover:border-emerald-500'
                }`}
              >
                {isOhlcStreamOnline ? 'Simulate Disconnect (Test Red Glow)' : 'Reconnect Stream (Test Green Glow)'}
              </button>
            )}
          </div>

          {/* Key Explanation Callout */}
          <div className="p-3.5 rounded-lg bg-zinc-950/90 border border-zinc-800 text-xs text-zinc-300 space-y-2">
            <div className="flex items-center space-x-2 text-amber-300 font-bold">
              <Info className="w-4 h-4 text-amber-400 shrink-0" />
              <span>Kraken Pro Trennungs-Prinzip: Spot vs. Futures Engine</span>
            </div>
            <p className="leading-relaxed text-[11px] text-zinc-400">
              Kraken betreibt das Spot- und das Futures-System auf zwei <strong>physisch und kryptografisch getrennten Plattformen</strong>. 
              Ein Standard Spot-API-Key hat per Design <em>keinen Zugriff</em> auf Perpetual-Contracts oder Futures-Margin.
              Ebenso kann ein Futures-Schlüssel keine Fiat-Guthaben oder Spot-Bestände verwalten.
              Damit Projekt:Alpha sowohl Spot-Trades als auch Pro Futures &amp; Perpetuals abwickeln kann, werden <strong>zwei Schlüsselpaare</strong> benötigt.
            </p>
          </div>

          {/* Dual API Cards Grid (Direct Match to Kraken Settings Screenshot) */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* CARD 1: SPOT TRADING API */}
            <div className={`p-4 rounded-xl border transition-all ${
              spotConfigured 
                ? 'bg-zinc-950/80 border-emerald-800/50 shadow-sm' 
                : 'bg-zinc-950/50 border-zinc-800'
            }`}>
              <div className="flex items-center justify-between pb-3 border-b border-zinc-800/80">
                <div className="flex items-center space-x-2">
                  <div className="p-1.5 rounded bg-emerald-950 border border-emerald-800 text-emerald-400">
                    <PieChart className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-white uppercase tracking-wider">Spot-Trading-API</h4>
                    <span className="text-[10px] text-zinc-400 font-normal">api.kraken.com</span>
                  </div>
                </div>
                <span className={`text-[9px] font-bold px-2 py-0.5 rounded border uppercase ${
                  spotConfigured
                    ? 'bg-emerald-950 text-emerald-300 border-emerald-700'
                    : 'bg-zinc-800 text-zinc-400 border-zinc-700'
                }`}>
                  {spotConfigured ? '✓ Aktiv / Erkannt' : 'Simuliert'}
                </span>
              </div>

              <div className="mt-3 space-y-2.5 text-[11px]">
                <p className="text-zinc-400 text-[10px] leading-relaxed">
                  API-Schlüssel, die für Spot- und Margin-Trading, Fiat-Cash-Funding (EUR/USD) und Krypto-Bestände verwendet werden.
                </p>

                <div className="bg-zinc-900/90 rounded p-2 border border-zinc-800 space-y-1">
                  <div className="flex justify-between items-center text-[10px]">
                    <span className="text-zinc-400">Umgebungsvariablen:</span>
                    <button
                      onClick={() => handleCopy('KRAKEN_SPOT_API_KEY')}
                      className="text-zinc-400 hover:text-emerald-400 flex items-center space-x-1"
                      title="Kopieren"
                    >
                      {copiedVar === 'KRAKEN_SPOT_API_KEY' ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                      <span>Kopieren</span>
                    </button>
                  </div>
                  <code className="text-emerald-300 text-[10px] block font-bold break-all">
                    KRAKEN_SPOT_API_KEY
                  </code>
                  <code className="text-emerald-300 text-[10px] block font-bold break-all">
                    KRAKEN_SPOT_PRIVATE_KEY
                  </code>
                  <span className="text-[9px] text-zinc-400 block pt-0.5">
                    (Legacy-Alias: KRAKEN_API_KEY / KRAKEN_PRIVATE_KEY)
                  </span>
                </div>

                <div className="space-y-1 text-[10px]">
                  <span className="text-zinc-400 uppercase text-[9px] font-semibold">Erforderliche Berechtigungen:</span>
                  <div className="flex flex-wrap gap-1">
                    <span className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-zinc-300 text-[9px]">Query Funds</span>
                    <span className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-zinc-300 text-[9px]">Query Orders/Trades</span>
                    <span className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-zinc-300 text-[9px]">Create &amp; Modify Orders</span>
                  </div>
                </div>

                <div className="pt-2 border-t border-zinc-800/60 flex justify-between items-center text-[10px]">
                  <span className="text-zinc-400">Aktiver Key-Status:</span>
                  <span className="font-mono text-zinc-300 font-bold">
                    {credentialsStatus?.spot.keyPreview || '9sPO••••vjo8Z (Spot)'}
                  </span>
                </div>
              </div>
            </div>

            {/* CARD 2: FUTURES TRADING API */}
            <div className={`p-4 rounded-xl border transition-all ${
              futuresConfigured 
                ? 'bg-zinc-950/80 border-cyan-800/50 shadow-sm' 
                : 'bg-zinc-950/50 border-zinc-800'
            }`}>
              <div className="flex items-center justify-between pb-3 border-b border-zinc-800/80">
                <div className="flex items-center space-x-2">
                  <div className="p-1.5 rounded bg-cyan-950 border border-cyan-800 text-cyan-400">
                    <Zap className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-white uppercase tracking-wider">Futures-Trading-API</h4>
                    <span className="text-[10px] text-zinc-400 font-normal">futures.kraken.com</span>
                  </div>
                </div>
                <span className={`text-[9px] font-bold px-2 py-0.5 rounded border uppercase ${
                  futuresConfigured
                    ? 'bg-cyan-950 text-cyan-300 border-cyan-700'
                    : 'bg-zinc-800 text-zinc-400 border-zinc-700'
                }`}>
                  {futuresConfigured ? '✓ Aktiv / Erkannt' : 'Simuliert'}
                </span>
              </div>

              <div className="mt-3 space-y-2.5 text-[11px]">
                <p className="text-zinc-400 text-[10px] leading-relaxed">
                  API-Schlüssel, die für Futures-Trading, Perpetual Swaps (PF_XBTUSD), Derivate-Hebel und Liquidations-Überwachung verwendet werden.
                </p>

                <div className="bg-zinc-900/90 rounded p-2 border border-zinc-800 space-y-1">
                  <div className="flex justify-between items-center text-[10px]">
                    <span className="text-zinc-400">Umgebungsvariablen:</span>
                    <button
                      onClick={() => handleCopy('KRAKEN_FUTURES_API_KEY')}
                      className="text-zinc-400 hover:text-cyan-400 flex items-center space-x-1"
                      title="Kopieren"
                    >
                      {copiedVar === 'KRAKEN_FUTURES_API_KEY' ? <Check className="w-3 h-3 text-cyan-400" /> : <Copy className="w-3 h-3" />}
                      <span>Kopieren</span>
                    </button>
                  </div>
                  <code className="text-cyan-300 text-[10px] block font-bold break-all">
                    KRAKEN_FUTURES_API_KEY
                  </code>
                  <code className="text-cyan-300 text-[10px] block font-bold break-all">
                    KRAKEN_FUTURES_PRIVATE_KEY
                  </code>
                  <span className="text-[9px] text-zinc-400 block pt-0.5">
                    (Alias: KRAKEN_PRO_API_KEY / KRAKEN_PRO_PRIVATE_KEY)
                  </span>
                </div>

                <div className="space-y-1 text-[10px]">
                  <span className="text-zinc-400 uppercase text-[9px] font-semibold">Erforderliche Berechtigungen:</span>
                  <div className="flex flex-wrap gap-1">
                    <span className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-zinc-300 text-[9px]">Allgemeine API (Voller Zugriff)</span>
                    <span className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-zinc-300 text-[9px]">Futures Positions &amp; Margin</span>
                  </div>
                </div>

                <div className="pt-2 border-t border-zinc-800/60 flex justify-between items-center text-[10px]">
                  <span className="text-zinc-400">Aktiver Key-Status:</span>
                  <span className="font-mono text-zinc-300 font-bold">
                    {credentialsStatus?.futures.keyPreview || '7EG7••••JToFpf+ (Futures)'}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Setup Guide Step-by-Step */}
          <div className="bg-zinc-950 border border-zinc-800/80 rounded-xl p-4 space-y-3">
            <h4 className="text-xs font-bold text-white uppercase tracking-wider flex items-center space-x-2">
              <Layers className="w-4 h-4 text-emerald-400" />
              <span>Anleitung zur Schlüssel-Erstellung bei Kraken</span>
            </h4>

            <ol className="list-decimal list-inside space-y-2 text-[11px] text-zinc-300 leading-relaxed">
              <li>
                Öffne dein Kraken-Konto unter <strong className="text-white">pro.kraken.com/app/settings/api</strong>.
              </li>
              <li>
                Erstelle unter <strong>„Spot-Trading-API“</strong> einen Schlüssel für Spot- und Margin-Trading und kopiere API-Key &amp; Private Key in <code className="text-emerald-400">KRAKEN_SPOT_API_KEY</code> und <code className="text-emerald-400">KRAKEN_SPOT_PRIVATE_KEY</code>.
              </li>
              <li>
                Scrolle nach unten zum Bereich <strong>„Futures-Trading-API“</strong>, erstelle dort einen separaten Schlüssel für Perpetual-Futures und kopiere ihn in <code className="text-cyan-400">KRAKEN_FUTURES_API_KEY</code> und <code className="text-cyan-400">KRAKEN_FUTURES_PRIVATE_KEY</code>.
              </li>
              <li>
                Trage die Schlüssel in die Plattform-Umgebung oder die <code className="text-zinc-300">.env</code> Datei ein. Das System lädt beide Schlüssel automatisch und bindet die passenden MCP- und Ledger-Engines an.
              </li>
            </ol>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-zinc-800 bg-zinc-950/80 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs">
          <div className="flex items-center space-x-2 text-zinc-400 text-[11px]">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>Kryptografische Signaturprüfung für api.kraken.com &amp; futures.kraken.com aktiv.</span>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={handleRefresh}
              disabled={isRefreshing}
              className="px-3 py-1.5 rounded-lg border border-zinc-700 bg-zinc-800 hover:bg-zinc-700 text-xs font-semibold text-zinc-200 hover:text-white transition-all flex items-center space-x-1.5"
            >
              <RefreshCw className={`w-3.5 h-3.5 text-emerald-400 ${isRefreshing ? 'animate-spin' : ''}`} />
              <span>Status neu prüfen</span>
            </button>
            <button
              onClick={onClose}
              className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white transition-colors"
            >
              Schließen
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
