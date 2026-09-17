/**
 * agent.comms.v1 length-prefixed JSON frames.
 */
export const COMMS_SCHEMA = "agent.comms.v1";
export const MAX_FRAME_BYTES = 1_048_576;
export const COMMS_KINDS = [
	"hello",
	"ping",
	"pong",
	"job.event",
	"steer",
	"stdio.chunk",
	"otel.export",
	"health",
	"ack",
	"error",
] as const;

export type CommsKind = (typeof COMMS_KINDS)[number];

export type CommsPeer = {
	host?: string;
	runtime?: string;
	sid?: string;
	workspace?: string;
};

export type CommsEnvelope = {
	schema: typeof COMMS_SCHEMA;
	id: string;
	ts: string;
	kind: CommsKind;
	src?: CommsPeer;
	dst?: CommsPeer;
	payload?: Record<string, unknown>;
};

export class FrameError extends Error {}

function sortedValue(value: unknown): unknown {
	if (Array.isArray(value)) return value.map(sortedValue);
	if (value && typeof value === "object") {
		const out: Record<string, unknown> = {};
		for (const key of Object.keys(value as Record<string, unknown>).sort()) {
			out[key] = sortedValue((value as Record<string, unknown>)[key]);
		}
		return out;
	}
	return value;
}

export function dumpCanonical(value: unknown): string {
	return JSON.stringify(sortedValue(value));
}

export function makeEnvelope(
	kind: CommsKind,
	payload?: Record<string, unknown>,
	opts: { src?: CommsPeer; dst?: CommsPeer; id?: string; ts?: string } = {},
): CommsEnvelope {
	if (!COMMS_KINDS.includes(kind)) throw new FrameError(`unknown kind ${kind}`);
	const env: CommsEnvelope = {
		schema: COMMS_SCHEMA,
		id: opts.id || `${Date.now().toString(16)}-${Math.random().toString(36).slice(2, 10)}`,
		ts: opts.ts || new Date().toISOString(),
		kind,
	};
	if (opts.src) env.src = opts.src;
	if (opts.dst) env.dst = opts.dst;
	if (payload) env.payload = payload;
	return env;
}

export function encodeFrame(envelope: CommsEnvelope): Buffer {
	if (envelope.schema !== COMMS_SCHEMA) throw new FrameError("envelope schema must be agent.comms.v1");
	if (!COMMS_KINDS.includes(envelope.kind)) throw new FrameError(`unknown kind ${envelope.kind}`);
	const body = Buffer.from(dumpCanonical(envelope), "utf8");
	if (body.length > MAX_FRAME_BYTES) throw new FrameError(`frame too large: ${body.length}`);
	const header = Buffer.alloc(4);
	header.writeUInt32BE(body.length, 0);
	return Buffer.concat([header, body]);
}

export function decodeFrame(buf: Buffer): { envelope: CommsEnvelope; rest: Buffer } {
	if (buf.length < 4) throw new FrameError("incomplete length prefix");
	const n = buf.readUInt32BE(0);
	if (n > MAX_FRAME_BYTES) throw new FrameError(`frame too large: ${n}`);
	if (buf.length < 4 + n) throw new FrameError("incomplete frame");
	let parsed: unknown;
	try {
		parsed = JSON.parse(buf.subarray(4, 4 + n).toString("utf8"));
	} catch (err) {
		throw new FrameError(`invalid json: ${err}`);
	}
	const envelope = parsed as CommsEnvelope;
	if (!envelope || envelope.schema !== COMMS_SCHEMA) throw new FrameError("envelope schema must be agent.comms.v1");
	if (!COMMS_KINDS.includes(envelope.kind)) throw new FrameError(`unknown kind ${envelope.kind}`);
	return { envelope, rest: buf.subarray(4 + n) };
}

export function defaultSrc(workspace = ""): CommsPeer {
	const src: CommsPeer = {
		host: process.env.HOSTNAME || "",
		runtime: process.env.FLEET_COMMS_RUNTIME || (process.env.CURSOR_AGENT ? "cursor" : "pi"),
		sid: process.env.PI_SESSION_ID || process.env.CDEV_SESSION_ID || "",
	};
	if (workspace) src.workspace = workspace;
	return Object.fromEntries(Object.entries(src).filter(([, v]) => v)) as CommsPeer;
}
