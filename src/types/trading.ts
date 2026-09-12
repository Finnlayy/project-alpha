/**
 * Quantitative Trading & Worker Bot Engine Data Types
 * Clean separation of UI view models and market engine states.
 */

export type WorkerBotStatus = 'active' | 'paused';
export type WorkerTradeDirection = 'LONG' | 'SHORT';

export interface WorkerBotMetrics {
  investment: number;
  currency: string;
  realizedProfit: number;
  dcaRangeMin: number;
  dcaRangeMax: number;
  dcaSteps: number;
  dcaOrdersTriggered: number;
  fundingFees: number;
  liquidationPrice: number;
  liquidationDistancePct: number;
}

export interface WorkerBotRuntime {
  days: number;
  hours: number;
  minutes: number;
  cycles: number;
}

export interface WorkerBotData {
  id: string;
  name: string;
  exchange: string;
  status: WorkerBotStatus;
  pair: string;
  strategy: string; // z.B. "DCA STRATEGY", "M8 KELLY DCA", "MEAN REVERSION"
  direction: WorkerTradeDirection;
  leverage: number;
  
  // Live P&L & Price Trackers
  unrealizedPnL: { 
    value: number; 
    percentage: number 
  };
  entryPrice: number;
  currentPrice: number;
  
  // 2x3 Metrik-Raster
  metrics: WorkerBotMetrics;
  
  // Footer & Lifecycle Metrics
  runtime: WorkerBotRuntime;
  totalProfit: number;
  roi: number;
  apr: number;
  lastUpdate: Date | string | number;

  // Respawn / Lineage Telemetry
  spawnedFrom?: string;
  spawnedAt?: string | Date;
  regime?: string;
  historicalOrigin?: BotHistoricalOrigin;
}

export interface BotHistoricalOrigin {
  sessionId: string;
  sessionName: string;
  stoppedAt: string;
  sourceRegime: string;
  sourceRoi: number;
  sourcePnl: number;
  sourceStrategy: string;
  sourceLeverage: number;
  sourceInvestment: number;
  configSourceTable: string; // e.g. "bot_history (SQLite/Parquet Lake)"
  cloningRationale?: string;
  leverageDelta?: number; // e.g. 0 or -2
  investmentDelta?: number;
}

export interface HistoricalBotSession {
  id: string;
  name: string;
  pair: string;
  regime: string;
  final_pnl: number;
  roi: number;
  stopped_at: string;
  config: Partial<WorkerBotData> & Record<string, any>;
}

export interface StrategyConfigAtSpawn {
  botId: string;
  botName: string;
  pair: string;
  exchange: string;
  status: WorkerBotStatus;
  direction: WorkerTradeDirection;
  strategy: string;
  leverage: number;
  investment: number;
  spawnedAt: string;
  spawnedFrom: string;
  historicalRecord: {
    id: string;
    name: string;
    pair: string;
    regime: string;
    final_pnl: number;
    roi: number;
    stopped_at: string;
    sourceStrategy: string;
    configSourceTable: string;
    rawConfig: Record<string, any>;
  };
  entryLogic: {
    regimeCondition: string;
    signalFilter: string;
    hurstThreshold: string;
    kellyFraction: string;
    orderType: string;
    initialEntryPrice?: number;
  };
  executionLogic: {
    dcaSteps: number;
    dcaRangeMin: number;
    dcaRangeMax: number;
    distributionModel: string;
    takeProfitTarget: string;
    stopLossCutoff: string;
    maxDrawdownLimit: string;
    rebalanceCadence: string;
  };
  riskControls: {
    marginType: string;
    liquidationPrice: number;
    liquidationDistancePct: number;
    feeHurdleRatio: string;
    maxLeverageCap: number;
  };
  rationale: string;
  rawConfig: Record<string, any>;
}

export interface SpawnFromHistoryPayload {
  historical_bot_id: string;
  modifier?: Partial<WorkerBotData> & {
    leverage?: number;
    metrics?: Partial<WorkerBotMetrics>;
    [key: string]: any;
  };
}
