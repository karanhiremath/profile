import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, test } from "node:test";
import assert from "node:assert/strict";
import { persistSiblingSessionFile, sessionFileHasAssistant } from "./handoff-sibling-persist.ts";

const tmp = mkdtempSync(join(tmpdir(), "handoff-sibling-"));
after(() => {
	rmSync(tmp, { recursive: true, force: true });
});

test("persistSiblingSessionFile writes header and entries without an assistant", () => {
	const sessionFile = join(tmp, "forced.jsonl");
	const written = persistSiblingSessionFile({
		getSessionFile: () => sessionFile,
		getSessionId: () => "sib-1",
		getHeader: () => ({ type: "session", version: 3, id: "sib-1", cwd: tmp }),
		getEntries: () => [{ type: "custom", customType: "pi.handoff-prep", data: { phase: "prepared" } }],
	});
	assert.equal(written, sessionFile);
	assert.equal(existsSync(sessionFile), true);
	assert.equal(sessionFileHasAssistant(sessionFile), false);
	const body = readFileSync(sessionFile, "utf8");
	assert.match(body, /"type":"session"/);
	assert.match(body, /pi.handoff-prep/);
	assert.doesNotMatch(body, /"role"\s*:\s*"assistant"/);
});

test("persistSiblingSessionFile rejects a missing header", () => {
	assert.throws(
		() =>
			persistSiblingSessionFile({
				getSessionFile: () => join(tmp, "missing.jsonl"),
				getSessionId: () => "sib-2",
				getHeader: () => null,
				getEntries: () => [],
			}),
		/did not persist a file/,
	);
});
