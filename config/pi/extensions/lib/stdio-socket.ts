/**
 * stdout/stderr capture + AF_UNIX lifecycle for agent.comms.v1.
 */
import { createConnection, createServer, type Server, type Socket } from "node:net";
import { chmodSync, existsSync, lstatSync, mkdirSync, unlinkSync } from "node:fs";
import { dirname } from "node:path";
import { decodeFrame, encodeFrame, makeEnvelope, type CommsEnvelope } from "./agent-comms.ts";

const SECRET_RE = /(sk-[A-Za-z0-9]{8,}|AKIA[0-9A-Z]{8,}|ghp_[A-Za-z0-9]{8,}|xox[baprs]-[A-Za-z0-9-]{8,})/gi;

export function redactText(text: string): string {
	return String(text || "").replace(SECRET_RE, "[redacted]");
}

export function captureText(text: string, maxBytes = 4096, stream = "stdout"): {
	stream: string;
	text: string;
	bytes: number;
	truncated: boolean;
} {
	const raw = Buffer.from(text, "utf8");
	const truncated = raw.length > maxBytes;
	const chunk = raw.subarray(0, maxBytes).toString("utf8");
	return { stream, text: redactText(chunk), bytes: Math.min(raw.length, maxBytes), truncated };
}

export function listenUnix(
	path: string,
	onEnvelope?: (env: CommsEnvelope, reply: (env: CommsEnvelope) => void) => void,
): Server {
	mkdirSync(dirname(path), { recursive: true });
	if (existsSync(path)) {
		const stat = lstatSync(path);
		if (!stat.isSocket()) {
			throw new Error("unix listen path exists and is not a socket");
		}
		unlinkSync(path);
	}
	const server = createServer((sock: Socket) => {
		const chunks: Buffer[] = [];
		sock.on("data", (data) => {
			chunks.push(Buffer.isBuffer(data) ? data : Buffer.from(data));
			const buf = Buffer.concat(chunks);
			try {
				const { envelope, rest } = decodeFrame(buf);
				chunks.length = 0;
				if (rest.length) chunks.push(rest);
				const reply = (env: CommsEnvelope) => sock.write(encodeFrame(env));
				if (onEnvelope) onEnvelope(envelope, reply);
				else if (envelope.kind === "ping") reply(makeEnvelope("pong", { id: envelope.id }));
				else reply(makeEnvelope("ack", { id: envelope.id, kind: envelope.kind }));
			} catch (err) {
				if (err instanceof Error && err.message.startsWith("incomplete")) return;
				sock.destroy();
			}
		});
	});
	server.listen(path);
	server.on("listening", () => {
		try {
			chmodSync(path, 0o600);
		} catch {
			/* best effort */
		}
	});
	return server;
}

export function pingUnix(path: string, timeoutMs = 1500): Promise<CommsEnvelope> {
	return new Promise((resolve, reject) => {
		const sock = createConnection(path);
		const chunks: Buffer[] = [];
		const timer = setTimeout(() => {
			sock.destroy();
			reject(new Error("unix ping timeout"));
		}, timeoutMs);
		sock.on("connect", () => sock.write(encodeFrame(makeEnvelope("ping"))));
		sock.on("data", (data) => {
			chunks.push(Buffer.isBuffer(data) ? data : Buffer.from(data));
			try {
				const { envelope } = decodeFrame(Buffer.concat(chunks));
				clearTimeout(timer);
				sock.end();
				resolve(envelope);
			} catch (err) {
				if (err instanceof Error && err.message.startsWith("incomplete")) return;
				clearTimeout(timer);
				sock.destroy();
				reject(err);
			}
		});
		sock.on("error", (err) => {
			clearTimeout(timer);
			reject(err);
		});
	});
}
