/**
 * Backtesting & genetic optimizer MCP tools.
 *
 * Backend contract (all POST JSON, camelCase):
 * - /api/backtest/run: {strategyType|strategyId, assetPair, interval, candleCount, initialBalance, parameters}
 * - /api/backtest/ai-analyze: {result:<backtest result>} OR flat strategy params (backend runs the backtest inline)
 * - /api/genetic/run: {strategyType|baselineStrategyId, assetPair, interval, candleCount, maxGenerations, populationSize, survivorsCount, seed}
 * - /api/genetic/deploy-to-orchestrator: {individual:{genes|parameters}, strategyType, strategyName, assetPair, interval}
 */
import { McpServer } from "@modelcontextprotocol/server";
import * as z from "zod/v4";
import { AlphaClient } from "../alphaClient.js";

export function registerBacktestTools(server: McpServer, client: AlphaClient) {
  // ---------- run backtest ----------
  server.registerTool(
    "alpha_backtest_run",
    {
      description:
        "Run a backtest on historical data. Returns equity curve, trade log, and performance metrics " +
        "(Sharpe, Sortino, Calmar, max drawdown, profit factor, Deflated Sharpe Ratio). " +
        "Uses next-bar-open fills, maker/taker fees, slippage, and funding (perps).",
      inputSchema: {
        strategy: z.string().describe("Strategy template name — see alpha_strategy_templates"),
        pair: z.string().default("BTC/USD").describe("Trading pair"),
        interval: z.number().default(5).describe("Candle interval in minutes"),
        params: z.record(z.string(), z.any()).optional().describe("Strategy parameters"),
        initialCapital: z.number().default(10000).describe("Starting capital in USD"),
        candleCount: z.number().default(600).describe("Historic bars to backtest (>= 100)"),
        strategyId: z.string().optional().describe("Existing instance ID to backtest instead of ad-hoc params"),
      },
    },
    async ({ strategy, pair, interval, params, initialCapital, candleCount, strategyId }) => {
      try {
        const data = await client.post("/api/backtest/run", {
          strategyType: strategy,
          strategyId,
          assetPair: pair,
          interval,
          parameters: params,
          initialBalance: initialCapital,
          candleCount,
        });
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- AI backtest analysis ----------
  server.registerTool(
    "alpha_backtest_analyze",
    {
      description:
        "Run AI-assisted analysis on backtest results — sensitivity re-runs, overfit detection (IS/OOS), " +
        "and parameter improvement suggestions. Deterministic statistical diagnostics, not LLM-based. " +
        "The backend runs the backtest inline when no prior result is supplied.",
      inputSchema: {
        strategy: z.string().describe("Strategy template name — see alpha_strategy_templates"),
        pair: z.string().default("BTC/USD").describe("Trading pair"),
        interval: z.number().default(5).describe("Candle interval in minutes"),
        params: z.record(z.string(), z.any()).optional().describe("Strategy parameters"),
        initialCapital: z.number().default(10000).describe("Starting capital in USD"),
        candleCount: z.number().default(600).describe("Historic bars (>= 200 for diagnostics)"),
        strategyId: z.string().optional().describe("Existing instance ID to analyze"),
      },
    },
    async ({ strategy, pair, interval, params, initialCapital, candleCount, strategyId }) => {
      try {
        const data = await client.post("/api/backtest/ai-analyze", {
          strategyType: strategy,
          strategyId,
          assetPair: pair,
          interval,
          parameters: params,
          initialBalance: initialCapital,
          candleCount,
        });
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- genetic optimizer ----------
  server.registerTool(
    "alpha_genetic_run",
    {
      description:
        "Run the genetic optimizer — evolves strategy parameters using elitism, tournament selection, " +
        "blend crossover, and Gaussian mutation. Returns Pareto-optimal genomes with walk-forward IS/OOS validation.",
      inputSchema: {
        strategy: z.string().describe("Strategy template name — see alpha_strategy_templates"),
        pair: z.string().default("BTC/USD").describe("Trading pair"),
        interval: z.number().default(5).describe("Candle interval in minutes"),
        populationSize: z.number().default(24).describe("Population size per generation"),
        generations: z.number().default(20).describe("Number of generations to evolve"),
        survivors: z.number().default(3).describe("Elite survivors kept per generation"),
        candleCount: z.number().default(2400).describe("Historic bars (>= 600 for walk-forward)"),
        seed: z.number().optional().describe("RNG seed for reproducibility"),
      },
    },
    async ({ strategy, pair, interval, populationSize, generations, survivors, candleCount, seed }) => {
      try {
        const data = await client.post("/api/genetic/run", {
          strategyType: strategy,
          assetPair: pair,
          interval,
          populationSize,
          maxGenerations: generations,
          survivorsCount: survivors,
          candleCount,
          seed,
        });
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );

  // ---------- deploy genetic result ----------
  server.registerTool(
    "alpha_genetic_deploy",
    {
      description:
        "Deploy a genetically optimized genome to the orchestrator as a new paper strategy instance.",
      inputSchema: {
        genome: z.record(z.string(), z.any()).describe("The genome (parameters) from genetic optimizer output"),
        strategy: z.string().describe("Strategy template name"),
        pair: z.string().default("BTC/USD").describe("Trading pair"),
        strategyName: z.string().optional().describe("Display name for the new instance"),
        interval: z.number().optional().describe("Bar interval in minutes"),
      },
    },
    async ({ genome, strategy, pair, strategyName, interval }) => {
      try {
        const data = await client.post("/api/genetic/deploy-to-orchestrator", {
          individual: { genes: genome },
          strategyType: strategy,
          assetPair: pair,
          strategyName,
          interval,
        });
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );
}
