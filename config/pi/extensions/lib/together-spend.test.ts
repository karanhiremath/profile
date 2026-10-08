import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, test } from "node:test";
import assert from "node:assert/strict";
import {
	TogetherSpendBlockedError,
	assertUnderBudget,
	emptyLedger,
	formatStatus,
	isOverBudget,
	loadLedger,
	recordCost,
	remainingUsd,
	saveLedger,
	setBudget,
} from "./together-spend.ts";

const tmp = mkdtempSync(join(tmpdir(), "together-spend-"));
after(() => rmSync(tmp, { recursive: true, force: true }));

test("empty ledger is under a $150 cap", () => {
	const ledger = emptyLedger(150);
	assert.equal(ledger.spentUsd, 0);
	assert.equal(remainingUsd(ledger), 150);
	assert.equal(isOverBudget(ledger), false);
	assertUnderBudget(ledger);
});

test("records Together cost once per key and ignores other providers", () => {
	let ledger = emptyLedger(150);
	ledger = recordCost(ledger, { provider: "cursor", costUsd: 9, key: "c1" }).ledger;
	const first = recordCost(ledger, {
		provider: "together",
		model: "zai-org/GLM-5.3-Flash",
		costUsd: 1.25,
		key: "t1",
	});
	assert.equal(first.added, true);
	const dup = recordCost(first.ledger, {
		provider: "together",
		costUsd: 1.25,
		key: "t1",
	});
	assert.equal(dup.added, false);
	assert.equal(dup.ledger.spentUsd, 1.25);
	assert.equal(remainingUsd(dup.ledger), 148.75);
});

test("blocks when spent reaches budget", () => {
	const { ledger } = recordCost(emptyLedger(1), {
		provider: "together",
		costUsd: 1,
		key: "hit",
	});
	assert.equal(isOverBudget(ledger), true);
	assert.throws(() => assertUnderBudget(ledger), TogetherSpendBlockedError);
	assert.match(formatStatus(ledger), /\$1\.00 \/ \$1\.00/);
});

test("setBudget and persist round-trip", () => {
	const path = join(tmp, "together-spend.json");
	const ledger = setBudget(emptyLedger(10), 150);
	saveLedger(path, ledger);
	const loaded = loadLedger(path);
	assert.equal(loaded.budgetUsd, 150);
	assert.equal(JSON.parse(readFileSync(path, "utf8")).schema, "kh.together-spend.v1");
});
