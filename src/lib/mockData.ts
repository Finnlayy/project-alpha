import { TradingStrategy, MarketTicker, ExecutionLog, TradeOrder, RunnerMetrics, StrategyPnL, QueueMatrixData, KrakenAccountLedgers, KrakenDualCredentialsStatus } from "../types";

export const defaultMockCredentialsStatus: KrakenDualCredentialsStatus = {
  hasSpotCredentials: true,
  hasFuturesCredentials: true,
  bothConfigured: true,
  anyConfigured: true,
  spot: {
    configured: true,
    keyPreview: "9sPOYD8Z...Qvjo8Z",
    source: "simulated",
    apiDomain: "api.kraken.com",
    displayName: "Spot-Trading-API",
    description: "Spot & Margin Trading, Fiat Balances (EUR/USD), Cash Funding",
    permissions: ["Query Funds", "Query Open Orders & Trades", "Create & Modify Orders"],
    lastValidated: new Date().toISOString()
  },
  futures: {
    configured: true,
    keyPreview: "7EG7xEU0...JToFpf+",
    source: "simulated",
    apiDomain: "futures.kraken.com",
    displayName: "Futures-Trading-API (Kraken Pro)",
    description: "Perpetual Swaps (PF_XBTUSD, PF_ETHUSD), Derivatives Margin & Liquidation Monitoring",
    permissions: ["Allgemeine API (Voller Zugriff)", "Positionen & Margin Read/Write"],
    lastValidated: new Date().toISOString()
  }
};

export const mockDashboardInit = {
  status: "online",
  uptime: 142850,
  timestamp: new Date().toISOString(),
  isPaperTrading: true,
  hasCredentials: true,
  hasSpotCredentials: true,
  hasFuturesCredentials: true,
  bothConfigured: true,
  credentialsStatus: defaultMockCredentialsStatus,
  default_timeframe: "5m",
  symbols: ["BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD"],
  activeStrategiesCount: 3,
  totalStrategiesCount: 4,
  lake_status: "synced"
};

export const mockKrakenStatus = {
  connected: true,
  hasCredentials: true,
  hasSpotCredentials: true,
  hasFuturesCredentials: true,
  bothConfigured: true,
  paperTrading: true,
  mode: "paper" as const,
  credentialsStatus: defaultMockCredentialsStatus
};

export const mockTickers: MarketTicker[] = [
  {
    pair: "BTC/USD",
    symbol: "BTC/USD",
    price: 77160.10,
    lastPrice: 77160.10,
    change24h: 3.42,
    high: 77800.00,
    low: 75400.00,
    volume: 18240.50,
    timestamp: new Date().toISOString()
  },
  {
    pair: "ETH/USD",
    symbol: "ETH/USD",
    price: 2513.15,
    lastPrice: 2513.15,
    change24h: 2.10,
    high: 2560.00,
    low: 2470.00,
    volume: 64200.80,
    timestamp: new Date().toISOString()
  },
  {
    pair: "SOL/USD",
    symbol: "SOL/USD",
    price: 102.31,
    lastPrice: 102.31,
    change24h: -1.25,
    high: 106.80,
    low: 99.40,
    volume: 245100.20,
    timestamp: new Date().toISOString()
  },
  {
    pair: "XRP/USD",
    symbol: "XRP/USD",
    price: 1.3540,
    lastPrice: 1.3540,
    change24h: 4.85,
    high: 1.4200,
    low: 1.2850,
    volume: 852000.00,
    timestamp: new Date().toISOString()
  }
];

export const mockStrategies: TradingStrategy[] = [
  {
    id: "strat-m8-kelly-1",
    name: "M8 Kelly-Momentum Alpha",
    description: "Adaptive volatility-scaled Kelly sizing with EMA trend bias and churn rate intercept guard.",
    code: `// M8 Kelly Alpha Strategy
function onTick(context) {
  const { rsi, ema20, ema50, price, kelly } = context;
  if (ema20 > ema50 && rsi < 65) {
    const size = kelly.calculateFraction(0.35);
    order.buy({ size, pair: 'BTC/USD', type: 'market' });
  } else if (rsi > 78) {
    order.closeAll('BTC/USD');
  }
}`,
    status: "active",
    assetPair: "BTC/USD",
    interval: 5,
    executionMode: "paper",
    parameters: {
      lookback: 20,
      kellyFraction: 0.35,
      hardStopPercent: 2.5,
      churnLimitPerMinute: 4
    },
    hardStopEnabled: true,
    hardStopPercent: 2.5,
    createdAt: "2026-08-28T10:00:00Z",
    version: 3,
    evolutionGeneration: 14,
    evolutionFitness: 1.84
  },
  {
    id: "strat-dfa-hurst-2",
    name: "DFA Hurst Mean-Reversion",
    description: "Detrended Fluctuation Analysis with anti-persistent Hurst regime detection (H < 0.45).",
    code: `// DFA Hurst Mean-Reversion
function onTick(context) {
  const { hurst, zscore, price } = context;
  if (hurst < 0.42 && zscore < -2.0) {
    order.buy({ size: 1.5, pair: 'ETH/USD', type: 'limit' });
  } else if (zscore > 1.8) {
    order.sell({ size: 1.5, pair: 'ETH/USD', type: 'limit' });
  }
}`,
    status: "active",
    assetPair: "ETH/USD",
    interval: 15,
    executionMode: "paper",
    parameters: {
      windowSize: 120,
      hurstThreshold: 0.45,
      zScoreEntry: 2.0
    },
    hardStopEnabled: true,
    hardStopPercent: 3.0,
    createdAt: "2026-08-30T14:30:00Z",
    version: 2,
    evolutionGeneration: 8,
    evolutionFitness: 1.62
  },
  {
    id: "strat-cadence-bandpass-3",
    name: "Cadence Bandpass Scalper",
    description: "Multi-objective genetic cadence bandpass filtering high-frequency noise and long drifts.",
    code: `// Cadence Scalper
function onTick(context) {
  const { bandpassPower, spreadBps } = context;
  if (bandpassPower > 0.65 && spreadBps < 4) {
    order.quickScalp({ pair: 'SOL/USD', durationSec: 180 });
  }
}`,
    status: "active",
    assetPair: "SOL/USD",
    interval: 1,
    executionMode: "paper",
    parameters: {
      lowFreqCutoff: 0.015,
      highFreqCutoff: 0.12,
      maxSpreadBps: 5
    },
    hardStopEnabled: true,
    hardStopPercent: 1.8,
    createdAt: "2026-09-02T08:15:00Z",
    version: 4,
    evolutionGeneration: 22,
    evolutionFitness: 2.15
  },
  {
    id: "strat-breakout-vault-4",
    name: "Autopsy Volatility Breakout",
    description: "MFE/MAE post-trade autopsy recovery engine with trailing ATR channel breakout.",
    code: `// Autopsy Breakout
function onTick(context) {
  const { atr, high20, price } = context;
  if (price > high20) {
    order.buy({ size: 0.5, pair: 'XRP/USD' });
  }
}`,
    status: "inactive",
    assetPair: "XRP/USD",
    interval: 60,
    executionMode: "paper",
    parameters: {
      atrPeriod: 14,
      rMultipleTarget: 2.8
    },
    hardStopEnabled: false,
    hardStopPercent: 4.0,
    createdAt: "2026-09-04T12:00:00Z",
    version: 1
  }
];

export const mockOrders: TradeOrder[] = [
  {
    id: "ord-1092",
    strategyId: "strat-m8-kelly-1",
    strategyName: "M8 Kelly-Momentum Alpha",
    timestamp: new Date(Date.now() - 1000 * 60 * 12).toISOString(),
    type: "buy",
    price: 63980.20,
    amount: 0.25,
    total: 15995.05,
    pair: "BTC/USD",
    status: "filled",
    executionMode: "paper",
    pnl: 75.05
  },
  {
    id: "ord-1091",
    strategyId: "strat-cadence-bandpass-3",
    strategyName: "Cadence Bandpass Scalper",
    timestamp: new Date(Date.now() - 1000 * 60 * 25).toISOString(),
    type: "sell",
    price: 153.20,
    amount: 25.0,
    total: 3830.00,
    pair: "SOL/USD",
    status: "filled",
    executionMode: "paper",
    pnl: 48.50
  },
  {
    id: "ord-1090",
    strategyId: "strat-dfa-hurst-2",
    strategyName: "DFA Hurst Mean-Reversion",
    timestamp: new Date(Date.now() - 1000 * 60 * 55).toISOString(),
    type: "buy",
    price: 3410.50,
    amount: 2.0,
    total: 6821.00,
    pair: "ETH/USD",
    status: "filled",
    executionMode: "paper",
    pnl: 79.50
  },
  {
    id: "ord-1089",
    strategyId: "strat-m8-kelly-1",
    strategyName: "M8 Kelly-Momentum Alpha",
    timestamp: new Date(Date.now() - 1000 * 60 * 120).toISOString(),
    type: "sell",
    price: 64120.00,
    amount: 0.25,
    total: 16030.00,
    pair: "BTC/USD",
    status: "filled",
    executionMode: "paper",
    pnl: 142.30
  }
];

export const mockLogs: ExecutionLog[] = [
  {
    id: "log-501",
    timestamp: new Date(Date.now() - 1000 * 15).toISOString(),
    level: "info",
    message: "[M8StateEngine] Redis Lua state transition: ACTIVE status confirmed. Idempotency verified.",
    strategyId: "strat-m8-kelly-1"
  },
  {
    id: "log-502",
    timestamp: new Date(Date.now() - 1000 * 45).toISOString(),
    level: "trade",
    message: "[TransientBuffer] Filled paper order #ord-1092: 0.25 BTC/USD @ 63,980.20 (slippage: 0.01 bps).",
    strategyId: "strat-m8-kelly-1"
  },
  {
    id: "log-503",
    timestamp: new Date(Date.now() - 1000 * 90).toISOString(),
    level: "info",
    message: "[CadenceBandpass] Resampling 1s ticks -> 1m candle. Bandpass filter SNR = 14.2 dB.",
    strategyId: "strat-cadence-bandpass-3"
  },
  {
    id: "log-504",
    timestamp: new Date(Date.now() - 1000 * 180).toISOString(),
    level: "warn",
    message: "[FeeEngine] Maker/Taker spread approaching 4.2 bps on SOL/USD. Churn guard engaged.",
    strategyId: "strat-cadence-bandpass-3"
  }
];

export const mockBalances: Record<string, number> = {
  USD: 42580.40,
  BTC: 0.452,
  ETH: 4.85,
  SOL: 45.2,
  EUR: 1200.00
};

export const mockMetrics: RunnerMetrics = {
  cpuUsage: 24.5,
  memoryUsage: 38.2,
  latencyMs: 14,
  activeWorkers: 3,
  paperWorkers: 3,
  liveWorkers: 0,
  totalTrades: 124,
  profitLossPercentage: 1.64,
  balanceUSD: 88420.50,
  balanceBTC: 0.452,
  portfolioUSD: 88420.50,
  baselineUSD: 80000.00,
  initialPaperBalanceUSD: 80000.00,
  automationLevel: 4,
  automationLevelLabel: "L4 Autonomous Execution",
  activeLedgerMode: "paper",
  hasCredentials: true
};

export const mockStrategyPnL: StrategyPnL[] = [
  {
    strategyId: "strat-m8-kelly-1",
    strategyName: "M8 Kelly-Momentum Alpha",
    realizedPnL: 840.50,
    unrealizedPnL: 185.20,
    totalPnL: 1025.70,
    totalTrades: 58,
    winningTrades: 42,
    losingTrades: 16,
    winRate: 72.4,
    volumeTradedUSD: 485000,
    executionMode: "paper"
  },
  {
    strategyId: "strat-dfa-hurst-2",
    strategyName: "DFA Hurst Mean-Reversion",
    realizedPnL: 340.20,
    unrealizedPnL: 45.10,
    totalPnL: 385.30,
    totalTrades: 34,
    winningTrades: 22,
    losingTrades: 12,
    winRate: 64.7,
    volumeTradedUSD: 184000,
    executionMode: "paper"
  },
  {
    strategyId: "strat-cadence-bandpass-3",
    strategyName: "Cadence Bandpass Scalper",
    realizedPnL: 215.10,
    unrealizedPnL: -12.40,
    totalPnL: 202.70,
    totalTrades: 56,
    winningTrades: 38,
    losingTrades: 18,
    winRate: 67.8,
    volumeTradedUSD: 245000,
    executionMode: "paper"
  }
];

export const mockQueueMatrices: { paper: QueueMatrixData; live: QueueMatrixData } = {
  paper: {
    queue: "paper",
    queueLabel: "Paper Trading Simulation Matrix",
    automationLevel: 4,
    totalRealizedPnL: 1395.80,
    totalUnrealizedPnL: 217.90,
    totalPnL: 1613.70,
    cumulativeReturnPercent: 8.42,
    totalClosedTrades: 148,
    totalAllTrades: 152,
    winningTrades: 102,
    losingTrades: 46,
    winRate: 68.9,
    volumeTradedUSD: 914000,
    profitFactor: 2.18,
    sharpeRatio: 2.14,
    sortinoRatio: 2.85,
    maxDrawdownPercent: 3.82,
    averageTradeReturn: 10.90,
    bestTradeUSD: 184.50,
    worstTradeUSD: -62.10,
    activeWorkers: 3,
    strategies: [],
    allTimeTrades: mockOrders,
    pnlTrajectory: [
      { tradeIndex: 1, time: "10:00", tradePnL: 25.0, cumPnL: 25.0, pair: "BTC/USD", type: "buy", strategyName: "M8 Kelly" },
      { tradeIndex: 2, time: "11:30", tradePnL: 45.0, cumPnL: 70.0, pair: "ETH/USD", type: "buy", strategyName: "DFA Hurst" },
      { tradeIndex: 3, time: "13:00", tradePnL: -15.0, cumPnL: 55.0, pair: "SOL/USD", type: "sell", strategyName: "Cadence Scalper" },
      { tradeIndex: 4, time: "14:45", tradePnL: 88.0, cumPnL: 143.0, pair: "BTC/USD", type: "buy", strategyName: "M8 Kelly" },
      { tradeIndex: 5, time: "16:20", tradePnL: 52.0, cumPnL: 195.0, pair: "ETH/USD", type: "sell", strategyName: "DFA Hurst" }
    ],
    assetBreakdown: [
      { pair: "BTC/USD", volumeUSD: 485000, tradesCount: 58, netPnL: 1025.70, winRate: 72.4 },
      { pair: "ETH/USD", volumeUSD: 184000, tradesCount: 34, netPnL: 385.30, winRate: 64.7 },
      { pair: "SOL/USD", volumeUSD: 245000, tradesCount: 56, netPnL: 202.70, winRate: 67.8 }
    ]
  },
  live: {
    queue: "live",
    queueLabel: "Live Execution Matrix (Protected)",
    automationLevel: 4,
    totalRealizedPnL: 0,
    totalUnrealizedPnL: 0,
    totalPnL: 0,
    cumulativeReturnPercent: 0,
    totalClosedTrades: 0,
    totalAllTrades: 0,
    winningTrades: 0,
    losingTrades: 0,
    winRate: 0,
    volumeTradedUSD: 0,
    profitFactor: 0,
    sharpeRatio: 0,
    sortinoRatio: 0,
    maxDrawdownPercent: 0,
    averageTradeReturn: 0,
    bestTradeUSD: 0,
    worstTradeUSD: 0,
    activeWorkers: 0,
    strategies: [],
    allTimeTrades: [],
    pnlTrajectory: [],
    assetBreakdown: []
  }
};

export const mockLedgers: KrakenAccountLedgers = {
  mode: "paper",
  hasCredentials: true,
  hasSpotCredentials: true,
  hasFuturesCredentials: true,
  credentialsStatus: defaultMockCredentialsStatus,
  lastSync: new Date().toISOString(),
  spot: {
    totalValueUSD: 88420.50,
    freeCashUSD: 42580.40,
    cryptoValueUSD: 45840.10,
    change24hUSD: 1425.80,
    change24hPercent: 1.64,
    assets: [
      {
        asset: "BTC",
        name: "Bitcoin",
        amount: 0.452,
        available: 0.452,
        inOrders: 0,
        unitPriceUSD: 64280.50,
        totalValueUSD: 29054.78,
        portfolioPercentage: 32.86,
        change24h: 2.84,
        type: "crypto"
      },
      {
        asset: "ETH",
        name: "Ethereum",
        amount: 4.85,
        available: 4.85,
        inOrders: 0,
        unitPriceUSD: 3450.25,
        totalValueUSD: 16733.71,
        portfolioPercentage: 18.92,
        change24h: 1.45,
        type: "crypto"
      },
      {
        asset: "USD",
        name: "US Dollar",
        amount: 42580.40,
        available: 42580.40,
        inOrders: 0,
        unitPriceUSD: 1.0,
        totalValueUSD: 42580.40,
        portfolioPercentage: 48.15,
        change24h: 0.0,
        type: "fiat"
      }
    ]
  },
  pro: {
    totalCollateralUSD: 50000.00,
    freeMarginUSD: 38500.00,
    usedMarginUSD: 11500.00,
    marginLevelPercent: 434.78,
    totalUnrealizedPnL: 345.50,
    unrealizedPnLPercent: 2.24,
    effectiveLeverage: 1.85,
    positions: [
      {
        id: "pos-btc-01",
        pair: "BTC/USD",
        type: "long",
        contractType: "perpetual",
        size: 0.5,
        notionalValueUSD: 32140.25,
        leverage: 3,
        entryPrice: 63800.00,
        markPrice: 64280.50,
        liquidationPrice: 48200.00,
        collateralUSD: 10713.41,
        marginRequirementUSD: 10713.41,
        unrealizedPnLUSD: 240.25,
        unrealizedPnLPercent: 2.24,
        fundingRate: 0.000105,
        status: "open"
      },
      {
        id: "pos-eth-02",
        pair: "ETH/USD",
        type: "short",
        contractType: "perpetual",
        size: 4.0,
        notionalValueUSD: 13801.00,
        leverage: 2,
        entryPrice: 3480.00,
        markPrice: 3450.25,
        liquidationPrice: 4950.00,
        collateralUSD: 6900.50,
        marginRequirementUSD: 6900.50,
        unrealizedPnLUSD: 119.00,
        unrealizedPnLPercent: 3.42,
        fundingRate: -0.000080,
        status: "open"
      },
      {
        id: "pos-sol-03",
        pair: "SOL/USD",
        type: "long",
        contractType: "perpetual",
        size: 25.0,
        notionalValueUSD: 3750.00,
        leverage: 5,
        entryPrice: 151.20,
        markPrice: 150.65,
        liquidationPrice: 122.50,
        collateralUSD: 750.00,
        marginRequirementUSD: 750.00,
        unrealizedPnLUSD: -13.75,
        unrealizedPnLPercent: -1.82,
        fundingRate: 0.000120,
        status: "open"
      }
    ]
  }
};

export const mockWatchdogBufferedEvents: import("../types").WatchdogBufferedEvent[] = [
  {
    id: "WDG-EVT-1048",
    timestamp: Date.now() - 120,
    timeFormatted: new Date(Date.now() - 120).toISOString().substr(11, 12),
    module: "M-17 (SSE Watchdog)",
    type: "HEARTBEAT_ACK",
    severity: "OK",
    latency_ms: 0.12,
    details: "Watchdog heartbeat pulse acknowledged across fast-path shared memory barrier (14.2 µs)",
    source: "watchdog_sentinel.py::pulse_monitor",
    payload_bytes: 128
  },
  {
    id: "WDG-EVT-1047",
    timestamp: Date.now() - 450,
    timeFormatted: new Date(Date.now() - 450).toISOString().substr(11, 12),
    module: "M-01 (SHM Ringbuffer)",
    type: "FRAME_BUFFER_TICK",
    severity: "INFO",
    latency_ms: 0.18,
    details: "Kraken OHLC 1m candle frame locked into L1 ringbuffer slot 0x4E80",
    source: "ringbuffer_allocator.cpp::slot_commit",
    payload_bytes: 256
  },
  {
    id: "WDG-EVT-1046",
    timestamp: Date.now() - 890,
    timeFormatted: new Date(Date.now() - 890).toISOString().substr(11, 12),
    module: "Kraken WS OHLC Feeder",
    type: "LATENCY_PROBE",
    severity: "OK",
    latency_ms: 0.45,
    details: "Round-trip probe to Kraken Pro WebSocket feeder: 12.4ms (within 50ms guardrail)",
    source: "kraken_stream_client.ts::ping_guard",
    payload_bytes: 64
  },
  {
    id: "WDG-EVT-1045",
    timestamp: Date.now() - 1450,
    timeFormatted: new Date(Date.now() - 1450).toISOString().substr(11, 12),
    module: "M-08 (M8 Judge Gate)",
    type: "QUEUE_DRAIN",
    severity: "INFO",
    latency_ms: 0.22,
    details: "M-08 Order execution queue drained 4 shadow limit orders to L2 memory barrier",
    source: "m8_gate_controller.py::drain_queue",
    payload_bytes: 512
  },
  {
    id: "WDG-EVT-1044",
    timestamp: Date.now() - 2100,
    timeFormatted: new Date(Date.now() - 2100).toISOString().substr(11, 12),
    module: "M-17 (SSE Stream)",
    type: "STREAM_KEEPALIVE",
    severity: "OK",
    latency_ms: 0.09,
    details: "SSE stream connection confirmed alive; client heartbeat interval 3000ms",
    source: "telemetry_sse_server.ts::keepalive",
    payload_bytes: 96
  },
  {
    id: "WDG-EVT-1043",
    timestamp: Date.now() - 2800,
    timeFormatted: new Date(Date.now() - 2800).toISOString().substr(11, 12),
    module: "M-00 (State Machine)",
    type: "CIRCUIT_BREAKER_CHECK",
    severity: "OK",
    latency_ms: 0.15,
    details: "Circuit breaker status confirmed NORMAL; zero threshold breaches detected",
    source: "state_machine.py::circuit_guard",
    payload_bytes: 128
  },
  {
    id: "WDG-EVT-1042",
    timestamp: Date.now() - 3600,
    timeFormatted: new Date(Date.now() - 3600).toISOString().substr(11, 12),
    module: "M-01 (DuckDB Parquet)",
    type: "MEMORY_SYNC",
    severity: "INFO",
    latency_ms: 0.35,
    details: "DuckDB micro-batch parquet write flushed (128 KB) without lock contention",
    source: "duckdb_parquet_tier.py::batch_sync",
    payload_bytes: 1024
  },
  {
    id: "WDG-EVT-1041",
    timestamp: Date.now() - 4400,
    timeFormatted: new Date(Date.now() - 4400).toISOString().substr(11, 12),
    module: "Kraken Futures Feeder",
    type: "FRAME_BUFFER_TICK",
    severity: "INFO",
    latency_ms: 0.19,
    details: "Kraken Perpetual swap PF_XBTUSD mark price feed buffered: $64,280.50",
    source: "futures_market_listener.py::mark_tick",
    payload_bytes: 192
  },
  {
    id: "WDG-EVT-1040",
    timestamp: Date.now() - 5200,
    timeFormatted: new Date(Date.now() - 5200).toISOString().substr(11, 12),
    module: "M-11 (Resource Guard)",
    type: "LATENCY_PROBE",
    severity: "OK",
    latency_ms: 0.28,
    details: "Resource Guard CPU jitter check: thread pool delta 0.08ms; memory utilization 36.5%",
    source: "resource_guard.py::load_shedder",
    payload_bytes: 160
  },
  {
    id: "WDG-EVT-1039",
    timestamp: Date.now() - 6100,
    timeFormatted: new Date(Date.now() - 6100).toISOString().substr(11, 12),
    module: "M-17 (SSE Watchdog)",
    type: "HEARTBEAT_ACK",
    severity: "OK",
    latency_ms: 0.11,
    details: "Core engine loop iteration #142850 validated; zero task starvation detected",
    source: "watchdog_sentinel.py::iteration_tick",
    payload_bytes: 128
  },
  {
    id: "WDG-EVT-1038",
    timestamp: Date.now() - 7300,
    timeFormatted: new Date(Date.now() - 7300).toISOString().substr(11, 12),
    module: "M-11 (Resource Guard)",
    type: "QUEUE_DRAIN",
    severity: "OK",
    latency_ms: 0.14,
    details: "Telemetry ringbuffer sweep completed; 0 dropped events (Zero-Drop policy)",
    source: "resource_guard.py::ringbuffer_sweep",
    payload_bytes: 64
  },
  {
    id: "WDG-EVT-1037",
    timestamp: Date.now() - 8500,
    timeFormatted: new Date(Date.now() - 8500).toISOString().substr(11, 12),
    module: "M-17 (SSE Watchdog)",
    type: "STREAM_KEEPALIVE",
    severity: "OK",
    latency_ms: 0.08,
    details: "Watchdog sentinel confirmed active; watchdog_running=true; heartbeat_healthy=true",
    source: "watchdog_sentinel.py::self_test",
    payload_bytes: 128
  },
  {
    id: "WDG-EVT-1036",
    timestamp: Date.now() - 9800,
    timeFormatted: new Date(Date.now() - 9800).toISOString().substr(11, 12),
    module: "M-08 (M8 Judge Gate)",
    type: "CIRCUIT_BREAKER_CHECK",
    severity: "WARN",
    latency_ms: 0.62,
    details: "Futures margin check warning check: margin level 482.4% (above safe minimum threshold 150%)",
    source: "m8_gate_controller.py::margin_audit",
    payload_bytes: 384
  },
  {
    id: "WDG-EVT-1035",
    timestamp: Date.now() - 11200,
    timeFormatted: new Date(Date.now() - 11200).toISOString().substr(11, 12),
    module: "Kraken WS OHLC Feeder",
    type: "FRAME_BUFFER_TICK",
    severity: "INFO",
    latency_ms: 0.16,
    details: "Kraken ETH/USD 1m candle frame ingested: close $3,450.25 (volume 214.2 ETH)",
    source: "kraken_stream_client.ts::candle_frame",
    payload_bytes: 256
  },
  {
    id: "WDG-EVT-1034",
    timestamp: Date.now() - 12800,
    timeFormatted: new Date(Date.now() - 12800).toISOString().substr(11, 12),
    module: "M-17 (SSE Watchdog)",
    type: "HEARTBEAT_ACK",
    severity: "OK",
    latency_ms: 0.10,
    details: "Fast-path IPC pipe pinged successfully; zero backpressure",
    source: "watchdog_sentinel.py::ipc_ping",
    payload_bytes: 96
  }
];

export const mockHistoricalBots: import("../types/trading").HistoricalBotSession[] = [
  {
    id: "BOT-HIST-7742",
    name: "Alpha-Momentum Worker (Genesis Run)",
    pair: "BTC/USD.P",
    regime: "persistent_trending",
    final_pnl: 6000.70,
    roi: 60.01,
    stopped_at: "2026-09-08T18:30:00Z",
    config: {
      name: "Alpha Momentum Worker",
      exchange: "Kraken Futures",
      pair: "BTC/USD.P",
      strategy: "M8 KELLY DCA",
      direction: "LONG",
      leverage: 5,
      investment: 10000.0,
      currency: "USD",
      dcaRangeMin: 60500.0,
      dcaRangeMax: 65200.0,
      dcaSteps: 6,
      liquidationPrice: 51800.0,
      liquidationDistancePct: 19.4,
      apr: 121.8,
      entryPrice: 62840.0,
      currentPrice: 64280.5
    }
  },
  {
    id: "BOT-HIST-8819",
    name: "Sigma Mean-Reversion Bot (Alpha Epoch)",
    pair: "ETH/USD",
    regime: "mean_reverting",
    final_pnl: 2576.25,
    roi: 42.94,
    stopped_at: "2026-09-07T12:15:00Z",
    config: {
      name: "Sigma Mean-Reversion Bot",
      exchange: "Kraken Pro Spot",
      pair: "ETH/USD",
      strategy: "DFA HURST BAND",
      direction: "LONG",
      leverage: 2,
      investment: 6000.0,
      currency: "USD",
      dcaRangeMin: 3200.0,
      dcaRangeMax: 3650.0,
      dcaSteps: 5,
      liquidationPrice: 1750.0,
      liquidationDistancePct: 49.3,
      apr: 60.3,
      entryPrice: 3380.0,
      currentPrice: 3450.25
    }
  },
  {
    id: "BOT-HIST-9901",
    name: "Delta Cadence Scalper (High Vola Cycle)",
    pair: "SOL/USD.P",
    regime: "high_volatility",
    final_pnl: 2135.40,
    roi: 61.01,
    stopped_at: "2026-09-06T22:45:00Z",
    config: {
      name: "Delta Cadence Scalper",
      exchange: "Kraken Futures",
      pair: "SOL/USD.P",
      strategy: "CADENCE BANDPASS",
      direction: "SHORT",
      leverage: 4,
      investment: 3500.0,
      currency: "USD",
      dcaRangeMin: 140.0,
      dcaRangeMax: 156.0,
      dcaSteps: 4,
      liquidationPrice: 182.2,
      liquidationDistancePct: 25.8,
      apr: 247.4,
      entryPrice: 148.5,
      currentPrice: 144.8
    }
  },
  {
    id: "BOT-HIST-6620",
    name: "Gamma Volatility Arbitrageur (Beta Epoch)",
    pair: "AVAX/USD.P",
    regime: "low_volatility_spread",
    final_pnl: 826.10,
    roi: 33.04,
    stopped_at: "2026-09-05T14:20:00Z",
    config: {
      name: "Gamma Volatility Arbitrageur",
      exchange: "Kraken Futures",
      pair: "AVAX/USD.P",
      strategy: "VOLATILITY SPREAD",
      direction: "LONG",
      leverage: 3,
      investment: 2500.0,
      currency: "USD",
      dcaRangeMin: 24.0,
      dcaRangeMax: 32.0,
      dcaSteps: 8,
      liquidationPrice: 19.20,
      liquidationDistancePct: 31.3,
      apr: 86.1,
      entryPrice: 28.50,
      currentPrice: 27.95
    }
  }
];

export const mockWorkerBots: import("../types/trading").WorkerBotData[] = [
  {
    id: "BOT-ALPHA-MOM-01",
    name: "Alpha Momentum Worker #01",
    exchange: "Kraken Futures",
    status: "active",
    pair: "BTC/USD.P",
    strategy: "M8 KELLY DCA",
    direction: "LONG",
    leverage: 5,
    spawnedFrom: "BOT-HIST-7742",
    spawnedAt: "2026-09-09T08:15:00Z",
    regime: "persistent_trending",
    historicalOrigin: {
      sessionId: "BOT-HIST-7742",
      sessionName: "Alpha-Momentum Worker (Genesis Run)",
      stoppedAt: "2026-09-08T18:30:00Z",
      sourceRegime: "persistent_trending",
      sourceRoi: 60.01,
      sourcePnl: 6000.70,
      sourceStrategy: "M8 KELLY DCA",
      sourceLeverage: 5,
      sourceInvestment: 10000.00,
      configSourceTable: "bot_history (SQLite/Parquet Lake)",
      cloningRationale: "DFA Hurst 0.68 Trend Confirmation: Cloned high-conviction momentum run with identical 5x Kelly sizing.",
      leverageDelta: 0,
      investmentDelta: 0
    },
    unrealizedPnL: {
      value: 1166.50,
      percentage: 11.67
    },
    entryPrice: 75400.00,
    currentPrice: 77160.10,
    metrics: {
      investment: 10000.00,
      currency: "USD",
      realizedProfit: 4580.20,
      dcaRangeMin: 72000.00,
      dcaRangeMax: 78500.00,
      dcaSteps: 6,
      dcaOrdersTriggered: 3,
      fundingFees: -42.80,
      liquidationPrice: 61800.00,
      liquidationDistancePct: 19.9
    },
    runtime: {
      days: 18,
      hours: 14,
      minutes: 32,
      cycles: 142
    },
    totalProfit: 5746.70,
    roi: 57.47,
    apr: 121.8,
    lastUpdate: new Date()
  },
  {
    id: "BOT-SIGMA-REV-02",
    name: "Sigma Mean-Reversion Bot",
    exchange: "Kraken Pro Spot",
    status: "active",
    pair: "ETH/USD",
    strategy: "DFA HURST BAND",
    direction: "LONG",
    leverage: 2,
    spawnedFrom: "BOT-HIST-8819",
    spawnedAt: "2026-09-08T10:45:00Z",
    regime: "mean_reverting",
    historicalOrigin: {
      sessionId: "BOT-HIST-8819",
      sessionName: "Sigma Mean-Reversion Bot (Alpha Epoch)",
      stoppedAt: "2026-09-07T12:15:00Z",
      sourceRegime: "mean_reverting",
      sourceRoi: 42.94,
      sourcePnl: 2576.25,
      sourceStrategy: "DFA HURST BAND",
      sourceLeverage: 2,
      sourceInvestment: 6000.00,
      configSourceTable: "bot_history (SQLite/Parquet Lake)",
      cloningRationale: "Hurst exponent < 0.42 mean-reverting band detected: Cloned Spot isolation config to minimize liquidation exposure.",
      leverageDelta: 0,
      investmentDelta: 0
    },
    unrealizedPnL: {
      value: 259.27,
      percentage: 4.32
    },
    entryPrice: 2460.00,
    currentPrice: 2513.15,
    metrics: {
      investment: 6000.00,
      currency: "USD",
      realizedProfit: 2190.50,
      dcaRangeMin: 2350.00,
      dcaRangeMax: 2650.00,
      dcaSteps: 5,
      dcaOrdersTriggered: 2,
      fundingFees: 0.00,
      liquidationPrice: 1250.00,
      liquidationDistancePct: 50.2
    },
    runtime: {
      days: 26,
      hours: 8,
      minutes: 19,
      cycles: 308
    },
    totalProfit: 2449.77,
    roi: 40.83,
    apr: 60.3,
    lastUpdate: new Date()
  },
  {
    id: "BOT-DELTA-SCALP-03",
    name: "Delta Cadence Scalper",
    exchange: "Kraken Futures",
    status: "active",
    pair: "SOL/USD.P",
    strategy: "CADENCE BANDPASS",
    direction: "SHORT",
    leverage: 4,
    spawnedFrom: "BOT-HIST-9901",
    spawnedAt: "2026-09-07T14:30:00Z",
    regime: "high_volatility",
    historicalOrigin: {
      sessionId: "BOT-HIST-9901",
      sessionName: "Delta Cadence Scalper (High Vola Cycle)",
      stoppedAt: "2026-09-06T22:45:00Z",
      sourceRegime: "high_volatility",
      sourceRoi: 61.01,
      sourcePnl: 2135.40,
      sourceStrategy: "CADENCE BANDPASS",
      sourceLeverage: 4,
      sourceInvestment: 3500.00,
      configSourceTable: "bot_history (SQLite/Parquet Lake)",
      cloningRationale: "Vol-Spike detected on SOL perpetual: Re-deployed micro-scalp cadence engine with 4x isolated leverage.",
      leverageDelta: 0,
      investmentDelta: 0
    },
    unrealizedPnL: {
      value: 293.45,
      percentage: 8.38
    },
    entryPrice: 104.50,
    currentPrice: 102.31,
    metrics: {
      investment: 3500.00,
      currency: "USD",
      realizedProfit: 1840.00,
      dcaRangeMin: 96.00,
      dcaRangeMax: 108.00,
      dcaSteps: 4,
      dcaOrdersTriggered: 1,
      fundingFees: 18.50,
      liquidationPrice: 126.50,
      liquidationDistancePct: 23.6
    },
    runtime: {
      days: 9,
      hours: 21,
      minutes: 45,
      cycles: 94
    },
    totalProfit: 2133.45,
    roi: 60.96,
    apr: 247.4,
    lastUpdate: new Date()
  },
  {
    id: "BOT-GAMMA-GRID-04",
    name: "Gamma Volatility Arbitrageur",
    exchange: "Kraken Futures",
    status: "paused",
    pair: "AVAX/USD.P",
    strategy: "VOLATILITY SPREAD",
    direction: "LONG",
    leverage: 3,
    spawnedFrom: "BOT-HIST-6620",
    spawnedAt: "2026-09-06T09:00:00Z",
    regime: "low_volatility_spread",
    historicalOrigin: {
      sessionId: "BOT-HIST-6620",
      sessionName: "Gamma Volatility Arbitrageur (Beta Epoch)",
      stoppedAt: "2026-09-05T14:20:00Z",
      sourceRegime: "low_volatility_spread",
      sourceRoi: 33.04,
      sourcePnl: 826.10,
      sourceStrategy: "VOLATILITY SPREAD",
      sourceLeverage: 3,
      sourceInvestment: 2500.00,
      configSourceTable: "bot_history (SQLite/Parquet Lake)",
      cloningRationale: "Range consolidation regime: Grid spread bot cloned from Beta historical archive to capture micro-swings.",
      leverageDelta: 0,
      investmentDelta: 0
    },
    unrealizedPnL: {
      value: -65.36,
      percentage: -2.61
    },
    entryPrice: 7.65,
    currentPrice: 7.45,
    metrics: {
      investment: 2500.00,
      currency: "USD",
      realizedProfit: 890.30,
      dcaRangeMin: 24.00,
      dcaRangeMax: 32.00,
      dcaSteps: 8,
      dcaOrdersTriggered: 4,
      fundingFees: -5.60,
      liquidationPrice: 19.20,
      liquidationDistancePct: 31.3
    },
    runtime: {
      days: 14,
      hours: 5,
      minutes: 10,
      cycles: 67
    },
    totalProfit: 826.10,
    roi: 33.04,
    apr: 86.1,
    lastUpdate: new Date()
  }
];
