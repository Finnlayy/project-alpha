/**
 * Backtesting & genetic optimizer MCP tools.
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
        strategy: z.string().describe("Strategy template name"),
        pair: z.string().default("BTC/USD").describe("Trading pair"),
        interval: z.number().default(5).describe("Candle interval in minutes"),
        params: z.record(z.string(), z.any()).optional().describe("Strategy parameters"),
        initialCapital: z.number().default(10000).describe("Starting capital in USD"),
      },
    },
    async ({ strategy, pair, interval, params, initialCapital }) => {
      try {
        const data = await client.post("/api/backtest/run", {
          strategy,
          pair,
          interval,
          params,
          initial_capital: initialCapital,
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
        "and parameter improvement suggestions. Deterministic statistical diagnostics, not LLM-based.",
      inputSchema: {
        strategy: z.string().describe("Strategy template name"),
        pair: z.string().default("BTC/USD").describe("Trading pair"),
        interval: z.number().default(5).describe("Candle interval in minutes"),
        params: z.record(z.string(), z.any()).optional().describe("Strategy parameters"),
        initialCapital: z.number().default(10000).describe("Starting capital in USD"),
      },
    },
    async ({ strategy, pair, interval, params, initialCapital }) => {
      try {
        const data = await client.post("/api/backtest/ai-analyze", {
          strategy,
          pair,
          interval,
          params,
          initial_capital: initialCapital,
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
        strategy: z.string().describe("Strategy template name"),
        pair: z.string().default("BTC/USD").describe("Trading pair"),
        interval: z.number().default(5).describe("Candle interval in minutes"),
        populationSize: z.number().default(50).describe("Population size per generation"),
        generations: z.number().default(20).describe("Number of generations to evolve"),
      },
    },
    async ({ strategy, pair, interval, populationSize, generations }) => {
      try {
        const data = await client.post("/api/genetic/run", {
          strategy,
          pair,
          interval,
          population_size: populationSize,
          generations,
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
        "Deploy a genetically optimized genome to the orchestrator as a live strategy instance.",
      inputSchema: {
        genome: z.record(z.string(), z.any()).describe("The genome (parameters) from genetic optimizer output"),
        strategy: z.string().describe("Strategy template name"),
        pair: z.string().describe("Trading pair"),
      },
    },
    async ({ genome, strategy, pair }) => {
      try {
        const data = await client.post("/api/genetic/deploy-to-orchestrator", {
          genome,
          strategy,
          pair,
        });
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (e: any) {
        return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
      }
    }
  );
}
