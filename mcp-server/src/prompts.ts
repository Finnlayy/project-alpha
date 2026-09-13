/**
 * MCP Prompts — pre-built prompt templates for common workflows.
 *
 * Prompts give the LLM ready-made interaction patterns for
 * multi-step analysis tasks.
 */
import { McpServer } from "@modelcontextprotocol/server";
import * as z from "zod/v4";

export function registerPrompts(server: McpServer) {
  // ---------- Market analysis ----------
  server.registerPrompt(
    "analyze-market",
    {
      title: "Market Analysis",
      description:
        "Run a comprehensive quantitative analysis on a trading pair — Hurst exponent, regime classification, sentiment, and M8 state.",
      argsSchema: {
        symbol: z.string().default("BTC/USD").describe("Trading pair to analyze"),
      },
    },
    ({ symbol }) => ({
      messages: [
        {
          role: "user" as const,
          content: {
            type: "text" as const,
            text: [
              `Perform a comprehensive quantitative market analysis for ${symbol}.`,
              "",
              "1. Read the system status resource (alpha://system/status) to check overall health.",
              `2. Call alpha_quant_hurst with symbol="${symbol}" to determine if the market is trending or mean-reverting.`,
              `3. Call alpha_quant_regime with symbol="${symbol}" to get the current regime classification.`,
              `4. Call alpha_quant_sentiment with symbol="${symbol}" to check funding-rate sentiment.`,
              "5. Call alpha_quant_m8_judge (no instance) to get the global M8 state engine judgement.",
              "6. Synthesize findings: Is this a good time to open positions? What strategy type fits the current regime?",
              "",
              "Remember: the system has a Zero-Dummy Guarantee — if data is unavailable, report that explicitly.",
            ].join("\n"),
          },
        },
      ],
    })
  );

  // ---------- Strategy backtest ----------
  server.registerPrompt(
    "backtest-strategy",
    {
      title: "Backtest a Strategy",
      description:
        "Run a backtest with AI-assisted analysis — includes sensitivity checks and overfit detection.",
      argsSchema: {
        strategy: z.string().describe("Strategy name (e.g. momentum_crossover, mean_reversion)"),
        pair: z.string().default("BTC/USD").describe("Trading pair"),
      },
    },
    ({ strategy, pair }) => ({
      messages: [
        {
          role: "user" as const,
          content: {
            type: "text" as const,
            text: [
              `Run a comprehensive backtest analysis for the "${strategy}" strategy on ${pair}.`,
              "",
              "1. Call alpha_backtest_run with the strategy and pair to get baseline performance.",
              "2. Call alpha_backtest_analyze with the same parameters for AI-assisted diagnostics:",
              "   - Sensitivity re-runs with perturbed parameters",
              "   - IS/OOS overfit detection",
              "   - Parameter improvement suggestions",
              "3. Report the key metrics: Sharpe, Sortino, Calmar, max drawdown, profit factor, DSR.",
              "4. Assess: Is this strategy robust enough for live deployment?",
              "5. If the results look good, consider running alpha_genetic_run to optimize parameters further.",
            ].join("\n"),
          },
        },
      ],
    })
  );

  // ---------- System diagnostics ----------
  server.registerPrompt(
    "system-diagnostics",
    {
      title: "Full System Diagnostics",
      description:
        "Run a complete system health check — all engines, connections, strategies, and risk metrics.",
    },
    () => ({
      messages: [
        {
          role: "user" as const,
          content: {
            type: "text" as const,
            text: [
              "Run a complete system diagnostics check for Projekt:Alpha.",
              "",
              "1. Call alpha_health for the basic health check.",
              "2. Call alpha_dashboard_status for full system status.",
              "3. Call alpha_kraken_status for Kraken connection state.",
              "4. Call alpha_kraken_credentials to verify API key configuration.",
              "5. Call alpha_strategies_list to review all active strategy instances.",
              "6. Call alpha_workers_list to review the worker bot swarm.",
              "7. Call alpha_queue_matrices for the strategy queue overview.",
              "8. Call alpha_quant_watchdog to check for any pending risk events.",
              "9. Call alpha_logs to review recent system events.",
              "",
              "Summarize the system health: what's working, what needs attention, and any recommendations.",
            ].join("\n"),
          },
        },
      ],
    })
  );

  // ---------- Optimize and deploy ----------
  server.registerPrompt(
    "optimize-deploy",
    {
      title: "Optimize & Deploy Strategy",
      description:
        "Run the genetic optimizer and deploy the best genome as a live strategy.",
      argsSchema: {
        strategy: z.string().describe("Strategy name"),
        pair: z.string().default("BTC/USD").describe("Trading pair"),
      },
    },
    ({ strategy, pair }) => ({
      messages: [
        {
          role: "user" as const,
          content: {
            type: "text" as const,
            text: [
              `Optimize the "${strategy}" strategy for ${pair} and prepare it for deployment.`,
              "",
              "1. First, run alpha_backtest_run with default parameters to establish a baseline.",
              "2. Run alpha_genetic_run to evolve optimal parameters (population=50, generations=20).",
              "3. Review the Pareto-optimal genomes — look for high Sharpe with reasonable drawdown.",
              "4. Run alpha_backtest_analyze on the best genome to check for overfitting.",
              "5. If the results are robust, call alpha_genetic_deploy to deploy as a live strategy.",
              "6. Finally, call alpha_quant_m8_judge to verify the M8 state engine approves.",
              "",
              "Important: only deploy if the IS/OOS analysis shows no significant overfitting.",
            ].join("\n"),
          },
        },
      ],
    })
  );
}
