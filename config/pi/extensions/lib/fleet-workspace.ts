/**
 * fleet-workspace.v1 loader.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { formatHarnessLines, HARNESS_NAMES, probeHarnesses, type HarnessName } from "./harness-remotes.ts";

export const WORKSPACE_SCHEMA = "fleet-workspace.v1";

export type FleetWorkspaceSpec = {
	schema: typeof WORKSPACE_SCHEMA;
	fleet: string;
	enabled?: boolean;
	privacy_domain?: string;
	mission?: string;
	observability?: {
		otel?: { enabled?: boolean; endpoint?: string; file?: string };
		stdio?: { capture?: boolean; dir?: string; maxChunkBytes?: number };
	};
	comms?: {
		unix?: { enabled?: boolean; socket?: string };
		http?: { enabled?: boolean; bind?: string; port?: number };
		tailscale_serve?: { enabled?: boolean; https?: boolean };
	};
	harnesses?: Array<{ name: HarnessName; enabled?: boolean; remote?: string }>;
};

export type InstantiatedWorkspace = {
	ok: boolean;
	schema: typeof WORKSPACE_SCHEMA;
	fleet: string;
	privacy_domain: string;
	state_dir: string;
	unix_socket: string;
	stdio_dir: string;
	otel_file: string;
	otel_endpoint: string;
	http_bind: string;
	http_port: number;
	http_urls: Record<string, string>;
	inject_env: Record<string, string>;
	tailscale_serve: { enabled: boolean; command: string[] };
	harnesses: ReturnType<typeof probeHarnesses>;
	instantiated_path?: string;
	error?: string;
};

function expand(path: string, home: string): string {
	if (path.startsWith("~/")) return join(home, path.slice(2));
	return path;
}

export function workspacePath(env: NodeJS.ProcessEnv = process.env, home = homedir()): string {
	const explicit = String(env.PI_FLEET_WORKSPACE || "").trim();
	if (explicit) return expand(explicit, home);
	return join(home, ".pi", "agent", "fleet-workspace.json");
}

export function validateWorkspace(spec: FleetWorkspaceSpec): FleetWorkspaceSpec {
	if (spec.schema !== WORKSPACE_SCHEMA) throw new Error("schema must be fleet-workspace.v1");
	if (!/^[a-z0-9][a-z0-9._-]{1,127}$/.test(String(spec.fleet || ""))) throw new Error("invalid fleet id");
	const bind = spec.comms?.http?.bind;
	if (bind && bind !== "127.0.0.1" && bind !== "localhost") {
		throw new Error("http.bind must be 127.0.0.1");
	}
	return spec;
}

export function loadWorkspaceFile(path: string): FleetWorkspaceSpec | undefined {
	if (!existsSync(path)) return undefined;
	try {
		return validateWorkspace(JSON.parse(readFileSync(path, "utf8")) as FleetWorkspaceSpec);
	} catch {
		return undefined;
	}
}

export function composeServeCommand(port: number, https = true): string[] {
	const proto = https ? "https" : "http";
	return ["tailscale", "serve", "--bg", proto, "/", `http://127.0.0.1:${port}/`];
}

export function instantiateWorkspace(
	spec: FleetWorkspaceSpec,
	opts: { home?: string; env?: NodeJS.ProcessEnv; httpPort?: number } = {},
): InstantiatedWorkspace {
	const home = opts.home || homedir();
	const env = opts.env || process.env;
	validateWorkspace(spec);
	if (spec.enabled === false) {
		return {
			ok: false,
			error: "workspace disabled",
			schema: WORKSPACE_SCHEMA,
			fleet: spec.fleet,
			privacy_domain: spec.privacy_domain || "local-only",
			state_dir: "",
			unix_socket: "",
			stdio_dir: "",
			otel_file: "",
			otel_endpoint: "",
			http_bind: "127.0.0.1",
			http_port: 0,
			http_urls: {},
			inject_env: {},
			tailscale_serve: { enabled: false, command: [] },
			harnesses: [],
		};
	}
	const stateDir = join(home, ".pi", "agent", "fleet-workspaces", spec.fleet);
	const unix = spec.comms?.unix || {};
	const http = spec.comms?.http || {};
	const serve = spec.comms?.tailscale_serve || {};
	const otel = spec.observability?.otel || {};
	const stdio = spec.observability?.stdio || {};
	const socket = expand(unix.socket || join(home, ".pi", "agent", "comms", `${spec.fleet}.sock`), home);
	const stdioDir = expand(stdio.dir || join(stateDir, "stdio"), home);
	const otelFile = expand(otel.file || join(home, ".pi", "agent", "otel", "agent-events.jsonl"), home);
	mkdirSync(dirname(socket), { recursive: true });
	mkdirSync(stdioDir, { recursive: true });
	mkdirSync(dirname(otelFile), { recursive: true });
	mkdirSync(stateDir, { recursive: true });
	const port = opts.httpPort ?? Number(http.port || 0);
	const urls =
		port > 0
			? {
					health: `http://127.0.0.1:${port}/health`,
					sse: `http://127.0.0.1:${port}/events`,
					ws: `ws://127.0.0.1:${port}/ws`,
				}
			: {};
	const names = (spec.harnesses || HARNESS_NAMES.map((name) => ({ name, enabled: true })))
		.filter((h) => h.enabled !== false)
		.map((h) => h.name);
	const instantiated: InstantiatedWorkspace = {
		ok: true,
		schema: WORKSPACE_SCHEMA,
		fleet: spec.fleet,
		privacy_domain: spec.privacy_domain || "local-only",
		state_dir: stateDir,
		unix_socket: unix.enabled === false ? "" : socket,
		stdio_dir: stdioDir,
		otel_file: otelFile,
		otel_endpoint: otel.endpoint || String(env.OTEL_EXPORTER_OTLP_ENDPOINT || ""),
		http_bind: "127.0.0.1",
		http_port: port,
		http_urls: urls,
		inject_env: port
			? {
					FLEET_COMMS_LOCAL_SSE: urls.sse,
					FLEET_COMMS_LOCAL_WS: urls.ws,
					FLEET_COMMS_HEALTH: urls.health,
				}
			: {},
		tailscale_serve: {
			enabled: Boolean(serve.enabled),
			command: port && serve.enabled ? composeServeCommand(port, serve.https !== false) : [],
		},
		harnesses: probeHarnesses(env, home, names),
	};
	const out = join(stateDir, "instantiated.json");
	writeFileSync(out, `${JSON.stringify(instantiated, null, 2)}\n`);
	instantiated.instantiated_path = out;
	return instantiated;
}

export function tryInstantiateFromDisk(
	env: NodeJS.ProcessEnv = process.env,
	home = homedir(),
): InstantiatedWorkspace | undefined {
	const spec = loadWorkspaceFile(workspacePath(env, home));
	if (!spec) return undefined;
	return instantiateWorkspace(spec, { home, env });
}

export function workspaceSummary(ws?: InstantiatedWorkspace): string {
	if (!ws) return "workspace: (none — set PI_FLEET_WORKSPACE or ~/.pi/agent/fleet-workspace.json)";
	if (!ws.ok) return `workspace: ${ws.fleet} disabled`;
	const lines = [
		`workspace: ${ws.fleet} ${ws.privacy_domain}`,
		`otel file: ${ws.otel_file}`,
		`unix: ${ws.unix_socket || "(off)"}`,
		`http: ${ws.http_port ? `127.0.0.1:${ws.http_port}` : "(off until serve)"}`,
		`harnesses:`,
		...formatHarnessLines(ws.harnesses),
	];
	if (ws.tailscale_serve.command.length) lines.push(`serve: ${ws.tailscale_serve.command.join(" ")}`);
	return lines.join("\n");
}
