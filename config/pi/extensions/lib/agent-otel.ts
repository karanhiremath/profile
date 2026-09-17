/**
 * agent.otel.v1 file emit + optional OTLP logs payload.
 */
import { appendFileSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";

export const OTEL_SCHEMA = "agent.otel.v1";

export type OtelEvent = {
	schema_version: typeof OTEL_SCHEMA;
	observed_at: string;
	event_time: string;
	event_type: string;
	runtime: string;
	privacy_domain: string;
	session_id?: string;
	project?: string;
	job_id?: string;
	stream?: string;
	status?: string;
	summary?: string;
	raw_ref?: string;
	[key: string]: unknown;
};

export function otelEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
	const raw = String(env.PI_AGENT_OTEL || "").trim().toLowerCase();
	if (["0", "false", "no", "off"].includes(raw)) return false;
	if (["1", "true", "yes", "on"].includes(raw)) return true;
	return Boolean(env.PI_FLEET_WORKSPACE || env.PI_AGENT_OTEL_FILE);
}

export function otelFilePath(home = homedir(), env: NodeJS.ProcessEnv = process.env): string {
	const override = String(env.PI_AGENT_OTEL_FILE || "").trim();
	if (override) return override;
	return join(home, ".pi", "agent", "otel", "agent-events.jsonl");
}

export function redactSummary(text: string, limit = 240): string {
	let raw = String(text || "").replace(/\s+/g, " ");
	raw = raw
		.replace(/(?:sk-[A-Za-z0-9_-]+|AKIA[A-Z0-9]+|gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|xox[baprs]-[A-Za-z0-9-]+)/g, "[redacted]")
		.replace(/Bearer\s+[^\s,;]+/gi, "Bearer [redacted]")
		.replace(/((?:api[_-]?key|token|password|secret)\s*[:=]\s*)[^\s,;]+/gi, "$1[redacted]");
	return raw.slice(0, limit);
}

export function makeOtelEvent(
	eventType: string,
	fields: Partial<OtelEvent> = {},
): OtelEvent {
	const now = new Date().toISOString();
	const event: OtelEvent = {
		schema_version: OTEL_SCHEMA,
		observed_at: now,
		event_time: fields.event_time || now,
		event_type: eventType,
		runtime: fields.runtime || "pi",
		privacy_domain: fields.privacy_domain || "unknown",
	};
	for (const key of ["session_id", "project", "job_id", "stream", "status", "raw_ref"] as const) {
		const value = fields[key];
		if (value) event[key] = value;
	}
	if (fields.summary) event.summary = redactSummary(String(fields.summary));
	return event;
}

export function appendOtelEvent(event: OtelEvent, file: string): string {
	mkdirSync(dirname(file), { recursive: true });
	appendFileSync(file, `${JSON.stringify(event)}\n`);
	return file;
}

export function otlpLogPayload(event: OtelEvent): Record<string, unknown> {
	const attrs = Object.entries(event)
		.filter(([key, value]) => key !== "summary" && value != null)
		.map(([key, value]) => ({ key, value: { stringValue: String(value) } }));
	return {
		resourceLogs: [
			{
				resource: {
					attributes: [
						{ key: "service.name", value: { stringValue: "job-bus-fleet" } },
						{ key: "service.namespace", value: { stringValue: "agentic" } },
					],
				},
				scopeLogs: [
					{
						logRecords: [
							{
								body: { stringValue: event.summary || event.event_type },
								severityText: "INFO",
								attributes: attrs,
							},
						],
					},
				],
			},
		],
	};
}

export function emitJobOtel(
	eventType: string,
	fields: Partial<OtelEvent> = {},
	opts: { home?: string; env?: NodeJS.ProcessEnv; force?: boolean } = {},
): OtelEvent | undefined {
	const env = opts.env || process.env;
	if (!opts.force && !otelEnabled(env)) return undefined;
	const event = makeOtelEvent(eventType, fields);
	appendOtelEvent(event, otelFilePath(opts.home, env));
	return event;
}
