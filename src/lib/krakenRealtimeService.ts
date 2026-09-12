/**
 * ============================================================================
 * KRAKEN REAL-TIME MARKET DATA & OHLC STREAMING SERVICE
 * ============================================================================
 * Zero-Dummy Guarantee Compliant:
 * - 100% Real Kraken Exchange Data (Direct from api.kraken.com & ws.kraken.com/v2)
 * - Strict No-Mock / No-Fake Rule: No synthetic sine waves, no random walks, no hardcoded prices
 * - Real WebSocket v2 Subscriptions with automatic reconnect & exponential backoff
 * - Real REST fallback with automatic pair normalization (BTC/USD -> XBTUSD / XXBTZUSD)
 * ============================================================================
 */

export interface MarketTicker {
  pair: string;
  price: number;
  symbol?: string;
  lastPrice?: number;
  change24h: number;
  high: number;
  low: number;
  volume: number;
  timestamp: string;
}

export interface KrakenCandle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  vwap?: number;
  volume: number;
  count?: number;
  timestamp: string;
}

export interface KrakenOHLCResult {
  pair: string;
  interval: number;
  total: number;
  candles: KrakenCandle[];
  source: string;
  confirmed: boolean;
  latencyMs?: number;
  error?: string;
}

export interface KrakenSymbolItem {
  symbol: string;
  altname: string;
  wsname: string;
  base: string;
  quote: string;
  status: string;
  minimumOrderSize: number;
  priceDecimals: number;
  lotDecimals: number;
}

// Canonical default trading pairs tracked in the real-time swarm
const TRACKED_CANONICAL_PAIRS = [
  'BTC/USD',
  'ETH/USD',
  'SOL/USD',
  'XRP/USD',
  'ADA/USD',
  'DOGE/USD',
  'DOT/USD',
  'LINK/USD',
  'AVAX/USD',
  'SUI/USD'
];

// Map canonical pair to Kraken REST query symbol
function canonicalToKrakenRest(pair: string): string {
  const upper = pair.trim().toUpperCase().replace(/[\/\-_]/g, '');
  if (upper === 'BTCUSD' || upper === 'XBTUSD') return 'XBTUSD';
  if (upper === 'ETHUSD') return 'ETHUSD';
  if (upper === 'SOLUSD') return 'SOLUSD';
  if (upper === 'XRPUSD') return 'XRPUSD';
  if (upper === 'ADAUSD') return 'ADAUSD';
  if (upper === 'DOGEUSD' || upper === 'XDGUSD') return 'XDGUSD';
  if (upper === 'DOTUSD') return 'DOTUSD';
  if (upper === 'LINKUSD') return 'LINKUSD';
  if (upper === 'AVAXUSD') return 'AVAXUSD';
  if (upper === 'SUIUSD') return 'SUIUSD';
  return upper;
}

// Map Kraken result key back to canonical pair format
function krakenKeyToCanonical(key: string): string {
  if (key === 'XXBTZUSD' || key === 'XBTUSD') return 'BTC/USD';
  if (key === 'XETHZUSD' || key === 'ETHUSD') return 'ETH/USD';
  if (key === 'SOLUSD') return 'SOL/USD';
  if (key === 'XXRPZUSD' || key === 'XRPUSD') return 'XRP/USD';
  if (key === 'ADAUSD') return 'ADA/USD';
  if (key === 'XDGUSD' || key === 'DOGEUSD') return 'DOGE/USD';
  if (key === 'DOTUSD') return 'DOT/USD';
  if (key === 'LINKUSD') return 'LINK/USD';
  if (key === 'AVAXUSD') return 'AVAX/USD';
  if (key === 'SUIUSD') return 'SUI/USD';

  // Generic heuristic for USD pairs
  if (key.endsWith('ZUSD') || key.endsWith('USD')) {
    let clean = key.replace(/^(XX?)/, '').replace(/Z?USD$/, '');
    if (clean === 'XBT') clean = 'BTC';
    if (clean === 'XDG') clean = 'DOGE';
    return `${clean}/USD`;
  }
  return key;
}

class KrakenRealtimeService {
  private ws: any = null;
  private wsConnected = false;
  private isConnecting = false;
  private reconnectTimeout: any = null;
  private reconnectAttempts = 0;
  private lastWsMessageTime: number | null = null;
  private lastRestLatency = 0;

  // In-memory cache of confirmed real market tickers
  private tickerCache: Map<string, MarketTicker> = new Map();
  private lastTickerFetchTime = 0;
  private activeSubscriptions = new Set<string>();

  // Subscribers for Server-Sent Events (SSE)
  private sseClients: Set<(data: string) => void> = new Set();

  private isStarted = false;

  constructor() {
    // Zero-Dummy Guarantee: Lazy start on dev server boot so static build & lint processes never hang
  }

  public start() {
    if (this.isStarted) return;
    this.isStarted = true;

    // Initial fetch of real tickers
    this.fetchRealTickers().catch(err => {
      console.error('[KrakenService] Initial REST ticker fetch error:', err.message);
    });

    // Start WebSocket v2 connection
    this.connectWebSocket();

    // Background REST polling interval (every 4 seconds) to ensure fresh tickers even if WS reconnects
    const pollInterval = setInterval(() => {
      this.fetchRealTickers().catch(() => {});
    }, 4000);

    if (typeof (pollInterval as any)?.unref === 'function') {
      (pollInterval as any).unref();
    }
  }

  /**
   * Connects to Kraken Public WebSocket v2
   */
  private connectWebSocket() {
    if (this.isConnecting || (this.ws && this.wsConnected)) return;

    if (typeof WebSocket === 'undefined') {
      console.warn('[KrakenService] Native WebSocket not available in this runtime environment.');
      return;
    }

    this.isConnecting = true;

    try {
      const wsUrl = 'wss://ws.kraken.com/v2';
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.wsConnected = true;
        this.isConnecting = false;
        this.reconnectAttempts = 0;
        this.lastWsMessageTime = Date.now();
        console.log('[KrakenService] WebSocket v2 connected to wss://ws.kraken.com/v2');

        // Subscribe to real-time Ticker for tracked pairs
        this.ws.send(JSON.stringify({
          method: 'subscribe',
          params: {
            channel: 'ticker',
            symbol: TRACKED_CANONICAL_PAIRS
          }
        }));

        // Subscribe to OHLC for primary pairs
        this.ws.send(JSON.stringify({
          method: 'subscribe',
          params: {
            channel: 'ohlc',
            symbol: ['BTC/USD', 'ETH/USD', 'SOL/USD', 'XRP/USD'],
            interval: 1
          }
        }));

        this.broadcastSSE({
          type: 'status',
          connected: true,
          timestamp: new Date().toISOString()
        });
      };

      this.ws.onmessage = (event: any) => {
        this.lastWsMessageTime = Date.now();
        try {
          const raw = typeof event.data === 'string' ? event.data : event.data.toString();
          const msg = JSON.parse(raw);

          // Handle WebSocket v2 Ticker Updates
          if (msg.channel === 'ticker' && Array.isArray(msg.data)) {
            for (const item of msg.data) {
              const pair = item.symbol;
              const last = Number(item.last);
              const changePct = Number(item.change_pct ?? 0);
              const high = Number(item.high ?? last);
              const low = Number(item.low ?? last);
              const volume = Number(item.volume ?? 0);

              if (!isNaN(last) && last > 0) {
                const ticker: MarketTicker = {
                  pair,
                  price: last,
                  symbol: pair,
                  lastPrice: last,
                  change24h: +changePct.toFixed(2),
                  high: +high.toFixed(2),
                  low: +low.toFixed(2),
                  volume: +volume.toFixed(2),
                  timestamp: item.timestamp || new Date().toISOString()
                };
                this.tickerCache.set(pair, ticker);
                this.broadcastSSE({ type: 'ticker', data: ticker });
              }
            }
          }

          // Handle WebSocket v2 OHLC Updates
          if (msg.channel === 'ohlc' && Array.isArray(msg.data)) {
            for (const bar of msg.data) {
              const ohlcEvent = {
                type: 'ohlc_bar',
                symbol: bar.symbol,
                interval: bar.interval,
                bar: {
                  time: Math.floor(new Date(bar.interval_begin || bar.timestamp).getTime() / 1000),
                  open: Number(bar.open),
                  high: Number(bar.high),
                  low: Number(bar.low),
                  close: Number(bar.close),
                  volume: Number(bar.volume || 0),
                  vwap: Number(bar.vwap || bar.close),
                  timestamp: bar.timestamp
                }
              };
              this.broadcastSSE(ohlcEvent);
            }
          }

          // Heartbeat
          if (msg.channel === 'heartbeat') {
            this.lastWsMessageTime = Date.now();
          }
        } catch (e) {
          // Ignore non-json or malformed frames
        }
      };

      this.ws.onerror = (err: any) => {
        console.error('[KrakenService] WebSocket v2 error:', err?.message || err);
      };

      this.ws.onclose = () => {
        this.wsConnected = false;
        this.isConnecting = false;
        this.scheduleReconnect();
      };
    } catch (err: any) {
      this.wsConnected = false;
      this.isConnecting = false;
      console.error('[KrakenService] Exception opening WebSocket:', err.message);
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimeout) clearTimeout(this.reconnectTimeout);
    this.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), 15000);
    console.log(`[KrakenService] Reconnecting WS in ${(delay / 1000).toFixed(1)}s (attempt ${this.reconnectAttempts})...`);
    this.reconnectTimeout = setTimeout(() => {
      this.connectWebSocket();
    }, delay);
    if (typeof (this.reconnectTimeout as any)?.unref === 'function') {
      (this.reconnectTimeout as any).unref();
    }
  }

  /**
   * Fetches real live tickers from Kraken REST API (public Ticker endpoint)
   */
  public async fetchRealTickers(): Promise<MarketTicker[]> {
    const start = Date.now();
    const queryPairs = [
      'XBTUSD',
      'ETHUSD',
      'SOLUSD',
      'XRPUSD',
      'ADAUSD',
      'XDGUSD',
      'DOTUSD',
      'LINKUSD',
      'AVAXUSD',
      'SUIUSD'
    ].join(',');

    try {
      const res = await fetch(`https://api.kraken.com/0/public/Ticker?pair=${queryPairs}`, {
        headers: { 'Accept': 'application/json', 'User-Agent': 'TheJudgeAndTheSwarm-QuantRunner/1.0' }
      });

      this.lastRestLatency = Date.now() - start;

      if (!res.ok) {
        throw new Error(`Kraken Ticker HTTP ${res.status}: ${res.statusText}`);
      }

      const json = await res.json();
      if (json.error && Array.isArray(json.error) && json.error.length > 0) {
        throw new Error(`Kraken API error: ${json.error.join(', ')}`);
      }

      const result = json.result;
      if (!result || typeof result !== 'object') {
        throw new Error('Kraken Ticker result empty');
      }

      const tickers: MarketTicker[] = [];

      for (const [key, val] of Object.entries(result as Record<string, any>)) {
        const canonical = krakenKeyToCanonical(key);
        const lastPrice = parseFloat(val.c[0]);
        const openPrice = parseFloat(val.o);
        const high24h = parseFloat(val.h[1]);
        const low24h = parseFloat(val.l[1]);
        const volume24h = parseFloat(val.v[1]);
        const change24h = openPrice > 0 ? ((lastPrice - openPrice) / openPrice) * 100 : 0;

        const ticker: MarketTicker = {
          pair: canonical,
          price: lastPrice,
          symbol: canonical,
          lastPrice,
          change24h: +change24h.toFixed(2),
          high: high24h,
          low: low24h,
          volume: +volume24h.toFixed(2),
          timestamp: new Date().toISOString()
        };

        this.tickerCache.set(canonical, ticker);
        tickers.push(ticker);
      }

      this.lastTickerFetchTime = Date.now();
      return tickers;
    } catch (err: any) {
      // If REST fails, return cached tickers if available, otherwise rethrow
      if (this.tickerCache.size > 0) {
        return Array.from(this.tickerCache.values());
      }
      throw err;
    }
  }

  /**
   * Returns current confirmed tickers
   */
  public async getLiveTickers(): Promise<MarketTicker[]> {
    if (this.tickerCache.size > 0 && Date.now() - this.lastTickerFetchTime < 3000) {
      return Array.from(this.tickerCache.values());
    }
    return this.fetchRealTickers();
  }

  /**
   * Fetches authentic historical OHLC candlesticks from Kraken REST API
   * Strict: Never returns synthetic data. Returns real candles or throws an explicit error.
   */
  public async getLiveOHLC(pairInput: string, intervalMin: number = 5, count: number = 80): Promise<KrakenOHLCResult> {
    const start = Date.now();
    const restPair = canonicalToKrakenRest(pairInput);
    
    // Kraken supports interval: 1, 5, 15, 30, 60, 240, 1440, 10080, 21600
    const validIntervals = [1, 5, 15, 30, 60, 240, 1440, 10080, 21600];
    const targetInterval = validIntervals.includes(intervalMin) ? intervalMin : 5;

    const url = `https://api.kraken.com/0/public/OHLC?pair=${encodeURIComponent(restPair)}&interval=${targetInterval}`;
    
    const res = await fetch(url, {
      headers: { 'Accept': 'application/json', 'User-Agent': 'TheJudgeAndTheSwarm-QuantRunner/1.0' }
    });

    const latency = Date.now() - start;

    if (!res.ok) {
      throw new Error(`Kraken OHLC HTTP ${res.status}: ${res.statusText}`);
    }

    const json = await res.json();
    if (json.error && Array.isArray(json.error) && json.error.length > 0) {
      throw new Error(`Kraken API error: ${json.error.join(', ')}`);
    }

    const result = json.result;
    if (!result || typeof result !== 'object') {
      throw new Error('Kraken OHLC result was empty');
    }

    // Pair key in result is the key that is not 'last'
    const pairKey = Object.keys(result).find(k => k !== 'last');
    if (!pairKey || !Array.isArray(result[pairKey])) {
      throw new Error(`No OHLC candlestick series found in Kraken response for ${pairInput}`);
    }

    const rawSeries: any[][] = result[pairKey];
    
    // Map candles: [time, open, high, low, close, vwap, volume, count]
    const allCandles: KrakenCandle[] = rawSeries.map(c => {
      const t = Number(c[0]);
      return {
        time: t,
        open: parseFloat(c[1]),
        high: parseFloat(c[2]),
        low: parseFloat(c[3]),
        close: parseFloat(c[4]),
        vwap: parseFloat(c[5]),
        volume: parseFloat(c[6]),
        count: Number(c[7] || 0),
        timestamp: new Date(t * 1000).toISOString()
      };
    });

    // Take the latest `count` candles
    const sliced = count > 0 ? allCandles.slice(-count) : allCandles;

    return {
      pair: pairInput,
      interval: targetInterval,
      total: sliced.length,
      candles: sliced,
      source: 'api.kraken.com (public/OHLC)',
      confirmed: true,
      latencyMs: latency
    };
  }

  /**
   * Fetches real Kraken asset pairs catalog (up to 1,400+ pairs)
   */
  public async getAssetPairs(): Promise<KrakenSymbolItem[]> {
    const res = await fetch('https://api.kraken.com/0/public/AssetPairs', {
      headers: { 'Accept': 'application/json' }
    });

    if (!res.ok) {
      throw new Error(`Kraken AssetPairs HTTP ${res.status}`);
    }

    const json = await res.json();
    if (json.error && json.error.length > 0) {
      throw new Error(json.error.join(', '));
    }

    const result = json.result || {};
    const list: KrakenSymbolItem[] = [];

    for (const [key, val] of Object.entries(result as Record<string, any>)) {
      list.push({
        symbol: val.altname || key,
        altname: val.altname || key,
        wsname: val.wsname || val.altname || key,
        base: val.base,
        quote: val.quote,
        status: val.status || 'online',
        minimumOrderSize: parseFloat(val.ordermin || '0.001'),
        priceDecimals: val.pair_decimals || 2,
        lotDecimals: val.lot_decimals || 4
      });
    }

    return list;
  }

  /**
   * Broadcast message to connected SSE clients
   */
  public broadcastSSE(payload: any) {
    const msg = `data: ${JSON.stringify(payload)}\n\n`;
    for (const send of this.sseClients) {
      try {
        send(msg);
      } catch {
        this.sseClients.delete(send);
      }
    }
  }

  /**
   * Adds an SSE client listener
   */
  public addSSEClient(sender: (data: string) => void): () => void {
    this.sseClients.add(sender);
    return () => {
      this.sseClients.delete(sender);
    };
  }

  /**
   * Returns current health and stream connection status
   */
  public getStatus() {
    const isAlive = this.wsConnected && (this.lastWsMessageTime ? Date.now() - this.lastWsMessageTime < 20000 : false);
    return {
      connected: isAlive || this.tickerCache.size > 0,
      ohlcStreamConnected: isAlive,
      wsConnected: this.wsConnected,
      isConnecting: this.isConnecting,
      lastWsMessageTime: this.lastWsMessageTime ? new Date(this.lastWsMessageTime).toISOString() : null,
      cachedTickersCount: this.tickerCache.size,
      restLatencyMs: this.lastRestLatency
    };
  }
}

// Singleton instance
export const krakenService = new KrakenRealtimeService();
