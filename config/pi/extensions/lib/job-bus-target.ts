/**
 * Session-targeted job-bus routing. Named lanes are opt-in project dashboards;
 * auto-steer belongs on the owner/target session inbox only.
 */
import { isForeignProjectFile, recordProject } from "./job-bus-project.ts";

export type JobRecord = {
	jobId?: string;
	type?: string;
	status?: string;
	agent?: string;
	task?: string;
	message?: string;
	stream?: string;
	ts?: string;
	exitCode?: number;
	statusPath?: string;
	eventsPath?: string;
	ownerSid?: string;
	targetSid?: string;
	steerSid?: string;
	sessionId?: string;
	source?: string;
	project?: string;
	cwd?: string;
	extra?: {
		targetSid?: string;
		steerSid?: string;
		sessionId?: string;
		ownerSid?: string;
		stream?: string;
		project?: string;
		[key: string]: unknown;
	};
};

export type SteerDecisionInput = {
	autoSteer: boolean;
	cursor: boolean;
	steerCursor: boolean;
	boundSid: string;
	inboxDir: string;
	filePath: string;
	record: JobRecord;
	boundProject?: string;
};

function safeSid(raw: string): string {
	return raw.replace(/[^A-Za-z0-9._:-]/g, "_").slice(0, 128);
}

export function resolveTargetSid(record: JobRecord): string {
	const extra = record.extra && typeof record.extra === "object" ? record.extra : {};
	for (const value of [
		record.targetSid,
		record.steerSid,
		extra.targetSid,
		extra.steerSid,
		record.sessionId,
		extra.sessionId,
	]) {
		const text = String(value || "").trim();
		if (text) return safeSid(text);
	}
	return "";
}

export function resolveOwnerSid(record: JobRecord): string {
	const extra = record.extra && typeof record.extra === "object" ? record.extra : {};
	for (const value of [record.ownerSid, extra.ownerSid]) {
		const text = String(value || "").trim();
		if (text) return safeSid(text);
	}
	return "";
}

export function isInboxPath(filePath: string, inboxDir: string): boolean {
	if (!inboxDir) return false;
	const prefix = inboxDir.endsWith("/") ? inboxDir : `${inboxDir}/`;
	return filePath === inboxDir || filePath.startsWith(prefix);
}

export function configuredSubscriptions(opts: {
	cursor: boolean;
	fileSubs?: string[];
	envSubs?: string[];
	runtimeSubs?: string[];
	scope?: string;
}): string[] {
	const runtime = (opts.runtimeSubs || []).map(String);
	if (opts.cursor) {
		return runtime.map((s) => s.trim()).filter(Boolean);
	}
	const fromFile = (opts.fileSubs || []).map(String);
	const fromEnv = (opts.envSubs || []).map(String);
	const extra = opts.scope === "global" ? ["legacy"] : [];
	return [...fromFile, ...fromEnv, ...runtime, ...extra].map((s) => s.trim()).filter(Boolean);
}

export function shouldSteerSelf(input: SteerDecisionInput): boolean {
	if (!input.autoSteer) return false;
	if (input.cursor && !input.steerCursor) return false;
	const target = resolveTargetSid(input.record);
	if (target && target !== input.boundSid) return false;
	if (isInboxPath(input.filePath, input.inboxDir)) return true;
	if (input.cursor) return false;
	if (target) return target === input.boundSid;
	const owner = resolveOwnerSid(input.record);
	if (owner) return owner === input.boundSid;
	// Named lanes are dashboards. Without target/owner, do not inject a turn.
	return false;
}

export function isTerminalStatus(status?: string): boolean {
	return status === "succeeded" || status === "failed";
}

export function isHeartbeat(record: JobRecord): boolean {
	return record.type === "job.heartbeat";
}

export type DeliveryKind = "none" | "display" | "steer";

export type Delivery = {
	kind: DeliveryKind;
	self: boolean;
};

export function classifyDelivery(
	input: SteerDecisionInput & { steerHeartbeats?: boolean; implementorSid?: string },
): Delivery {
	if (isHeartbeat(input.record) && !input.steerHeartbeats) {
		return { kind: "none", self: false };
	}
	if (
		isForeignProjectFile({
			filePath: input.filePath,
			inboxDir: input.inboxDir,
			boundProject: input.boundProject || "",
			recordProject: recordProject(input.record),
		})
	) {
		return { kind: "none", self: false };
	}
	const self = shouldSteerSelf(input);
	const terminal = isTerminalStatus(input.record.status);
	const redirect =
		Boolean(input.implementorSid) && input.implementorSid !== input.boundSid;
	if (terminal && (self || redirect)) {
		return { kind: "steer", self };
	}
	return { kind: "display", self };
}

export function formatSteer(record: JobRecord, _opts?: { implementorCue?: boolean }): string {
	const job = record.jobId || "unknown";
	const status = record.status || record.type || "update";
	const stream = record.stream || "-";
	const project = recordProject(record);
	const parts = [`job=${job}`, `stream=${stream}`];
	if (project) parts.push(`project=${project}`);
	parts.push(`status=${status}`);
	return parts.join(" ");
}

export function formatPointerBatch(records: JobRecord[], limit = 12): string {
	const unique: JobRecord[] = [];
	const seen = new Set<string>();
	for (const record of records) {
		const key = [record.jobId || "", record.type || "", record.status || ""].join("|");
		if (seen.has(key)) continue;
		seen.add(key);
		unique.push(record);
	}
	if (unique.length === 1) return formatSteer(unique[0]);
	const shown = unique.slice(0, limit);
	const extra = unique.length - shown.length;
	const lines = [`Job bus: ${unique.length} terminal updates`, ...shown.map((record) => `- ${formatSteer(record)}`)];
	if (extra > 0) lines.push(`- +${extra} more`);
	return lines.join("\n");
}
