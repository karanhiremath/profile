/**
 * Datadog MCP extension for pi
 *
 * Gives pi access to Datadog logs, metrics, monitors, APM, RUM, CI/CD
 * via the @us-all/datadog-mcp MCP server.
 *
 * Requires DD_API_KEY and DD_APP_KEY env vars.
 *
 * Install: symlink or copy to ~/.pi/agent/extensions/datadog-mcp.ts
 *          or project-local .pi/extensions/datadog-mcp.ts
 */
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Type } from "@sinclair/typebox";

export default function datadogMcp(pi: ExtensionAPI) {
  const ddApiKey = process.env.DD_API_KEY;
  const ddAppKey = process.env.DD_APP_KEY;

  if (!ddApiKey || !ddAppKey) {
    // Silently skip on non-work nodes
    return;
  }

  // Register a tool that queries Datadog logs
  pi.registerTool({
    name: "dd_logs",
    description:
      "Search Datadog logs. Use for debugging, incident response, and observability. " +
      "Returns recent log entries matching the query.",
    input: Type.Object({
      query: Type.String({
        description:
          'Datadog log search query (e.g. "service:api status:error", "host:gpu-node-*")',
      }),
      from: Type.Optional(
        Type.String({
          description: 'Time range start (default: "now-15m"). Supports "now-1h", "now-1d", ISO8601.',
        })
      ),
      to: Type.Optional(
        Type.String({ description: 'Time range end (default: "now").' })
      ),
      limit: Type.Optional(
        Type.Number({
          description: "Max results (default: 25, max: 100)",
          minimum: 1,
          maximum: 100,
        })
      ),
    }),
    execute: async (ctx, input) => {
      const from = input.from || "now-15m";
      const to = input.to || "now";
      const limit = Math.min(input.limit || 25, 100);

      const res = await fetch(
        "https://api.datadoghq.com/api/v2/logs/events/search",
        {
          method: "POST",
          headers: {
            "DD-API-KEY": ddApiKey,
            "DD-APPLICATION-KEY": ddAppKey,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            filter: { query: input.query, from, to },
            sort: "timestamp",
            page: { limit },
          }),
        }
      );

      if (!res.ok) {
        const err = await res.text();
        return { error: `Datadog API error (${res.status}): ${err}` };
      }

      const data = await res.json();
      const logs = (data.data || []).map((entry: any) => ({
        timestamp: entry.attributes?.timestamp,
        host: entry.attributes?.host,
        service: entry.attributes?.service,
        status: entry.attributes?.status,
        message: entry.attributes?.message?.substring(0, 500),
        tags: entry.attributes?.tags?.slice(0, 10),
      }));

      return {
        count: logs.length,
        total: data.meta?.page?.after ? "more available" : logs.length,
        logs,
      };
    },
  });

  // Register a tool for Datadog metrics
  pi.registerTool({
    name: "dd_metrics",
    description:
      "Query Datadog metrics. Use for performance analysis, capacity planning, and monitoring.",
    input: Type.Object({
      query: Type.String({
        description:
          'Datadog metrics query (e.g. "avg:system.cpu.user{host:gpu-*}", "sum:trace.http.request.hits{service:api}.as_count()")',
      }),
      from: Type.Optional(
        Type.Number({
          description: "Start time as unix epoch seconds (default: 1 hour ago)",
        })
      ),
      to: Type.Optional(
        Type.Number({
          description: "End time as unix epoch seconds (default: now)",
        })
      ),
    }),
    execute: async (ctx, input) => {
      const now = Math.floor(Date.now() / 1000);
      const from = input.from || now - 3600;
      const to = input.to || now;

      const params = new URLSearchParams({
        query: input.query,
        from: from.toString(),
        to: to.toString(),
      });

      const res = await fetch(
        `https://api.datadoghq.com/api/v1/query?${params}`,
        {
          headers: {
            "DD-API-KEY": ddApiKey,
            "DD-APPLICATION-KEY": ddAppKey,
          },
        }
      );

      if (!res.ok) {
        const err = await res.text();
        return { error: `Datadog API error (${res.status}): ${err}` };
      }

      const data = await res.json();
      const series = (data.series || []).map((s: any) => ({
        metric: s.metric,
        scope: s.scope,
        pointcount: s.pointlist?.length,
        // Return last 5 points for a quick snapshot
        recent: s.pointlist?.slice(-5).map((p: any) => ({
          time: new Date(p[0]).toISOString(),
          value: p[1],
        })),
      }));

      return { series_count: series.length, series };
    },
  });

  // Register a tool for Datadog monitors (alerts)
  pi.registerTool({
    name: "dd_monitors",
    description:
      "List Datadog monitors/alerts. Use to check alert status, find triggered monitors, and triage incidents.",
    input: Type.Object({
      query: Type.Optional(
        Type.String({
          description: 'Filter monitors (e.g. "tag:team:infra", "status:Alert")',
        })
      ),
      states: Type.Optional(
        Type.String({
          description:
            'Comma-separated monitor states to filter (e.g. "Alert,Warn"). Default: all states.',
        })
      ),
    }),
    execute: async (ctx, input) => {
      const params = new URLSearchParams();
      if (input.query) params.set("query", input.query);
      if (input.states) {
        for (const state of input.states.split(",")) {
          params.append("monitor_tags", `status:${state.trim()}`);
        }
      }
      params.set("page_size", "25");

      const res = await fetch(
        `https://api.datadoghq.com/api/v1/monitor?${params}`,
        {
          headers: {
            "DD-API-KEY": ddApiKey,
            "DD-APPLICATION-KEY": ddAppKey,
          },
        }
      );

      if (!res.ok) {
        const err = await res.text();
        return { error: `Datadog API error (${res.status}): ${err}` };
      }

      const monitors = await res.json();
      const summary = (Array.isArray(monitors) ? monitors : []).map(
        (m: any) => ({
          id: m.id,
          name: m.name,
          type: m.type,
          status: m.overall_state,
          message: m.message?.substring(0, 200),
          tags: m.tags?.slice(0, 5),
          modified: m.modified,
        })
      );

      return { count: summary.length, monitors: summary };
    },
  });
}
