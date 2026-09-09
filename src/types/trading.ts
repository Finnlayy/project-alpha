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
  regime?: string;
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

export interface SpawnFromHistoryPayload {
  historical_bot_id: string;
  modifier?: Partial<WorkerBotData> & {
    leverage?: number;
    metrics?: Partial<WorkerBotMetrics>;
    [key: string]: any;
  };
}
