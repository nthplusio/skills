import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync, unlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ANDON_FILE_NAME, FileAndonSource } from "../agent-runtime/scripts/core/andon-file.ts";

let dir: string;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "os4-andon-"));
});

afterEach(() => {
  rmSync(dir, { recursive: true, force: true });
});

describe("FileAndonSource", () => {
  test("no file means Andon is not raised", async () => {
    const source = new FileAndonSource(join(dir, ANDON_FILE_NAME));
    const snap = await source.snapshot();
    expect(snap.active).toBe(false);
    expect(Number.isFinite(Date.parse(snap.lastCheckedAt))).toBe(true);
  });

  test("a JSON object raises it, carrying reason and raisedBy; deleting the file clears it", async () => {
    const path = join(dir, ANDON_FILE_NAME);
    writeFileSync(path, JSON.stringify({ reason: "  upstream API is down ", raisedBy: "seth" }));
    const source = new FileAndonSource(path);
    const raised = await source.snapshot();
    expect(raised.active).toBe(true);
    if (raised.active) {
      expect(raised.reason).toBe("upstream API is down");
      expect(raised.raisedBy).toBe("seth");
      expect(Number.isFinite(Date.parse(raised.raisedAt))).toBe(true);
    }
    unlinkSync(path);
    expect((await source.snapshot()).active).toBe(false);
  });

  test("an explicit raisedAt is kept; missing fields get defaults", async () => {
    const path = join(dir, ANDON_FILE_NAME);
    writeFileSync(path, JSON.stringify({ raisedAt: "2026-10-14T02:14:24Z" }));
    const snap = await new FileAndonSource(path).snapshot();
    expect(snap).toMatchObject({ active: true, raisedAt: "2026-10-14T02:14:24.000Z", raisedBy: ANDON_FILE_NAME });
    expect(snap.active && snap.reason).toBeUndefined();
  });

  test("a file that is not a JSON object is an error the poller logs, not a raise", async () => {
    const path = join(dir, ANDON_FILE_NAME);
    writeFileSync(path, "stop!");
    await expect(new FileAndonSource(path).snapshot()).rejects.toThrow("is not JSON");
    writeFileSync(path, "[1]");
    await expect(new FileAndonSource(path).snapshot()).rejects.toThrow("must hold a JSON object");
  });
});
