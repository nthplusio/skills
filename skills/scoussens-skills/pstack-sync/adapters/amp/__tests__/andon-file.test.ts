import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { existsSync, mkdtempSync, readFileSync, rmSync, unlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  ANDON_FILE_NAME,
  andonFilePath,
  clearAndonFile,
  FileAndonSource,
  raiseAndonFile,
  resolveFileAndonWorkspace,
} from "../agent-runtime/scripts/core/andon-file.ts";

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

describe("the andon commands' file mode", () => {
  test("raise writes what FileAndonSource reads, atomically, and clear removes it", async () => {
    const path = raiseAndonFile({ workspace: dir, reason: "  pause: upstream API is down ", raisedBy: " seth " });
    expect(path).toBe(andonFilePath(dir));
    expect(path).toBe(join(dir, ANDON_FILE_NAME));
    expect(existsSync(`${path}.${process.pid}.tmp`)).toBe(false);
    const record = JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
    expect(record.reason).toBe("pause: upstream API is down");
    expect(record.raisedBy).toBe("seth");
    expect(Number.isFinite(Date.parse(String(record.raisedAt)))).toBe(true);
    const snap = await new FileAndonSource(path).snapshot();
    expect(snap.active).toBe(true);
    if (snap.active) {
      expect(snap.reason).toBe("pause: upstream API is down");
      expect(snap.raisedBy).toBe("seth");
      expect(snap.raisedAt).toBe(String(record.raisedAt));
    }
    // No sender: the file carries no raisedBy and the source falls back to the file name.
    raiseAndonFile({ workspace: dir, reason: "again", raisedBy: "  " });
    expect(JSON.parse(readFileSync(path, "utf8"))).not.toHaveProperty("raisedBy");
    expect(clearAndonFile(dir)).toEqual({ path, cleared: true });
    expect((await new FileAndonSource(path).snapshot()).active).toBe(false);
    expect(clearAndonFile(dir)).toEqual({ path, cleared: false });
  });

  test("resolveFileAndonWorkspace mirrors the manager's choice between Slack and the file", () => {
    const plan = join(dir, "plan.json");
    expect(resolveFileAndonWorkspace(undefined, {})).toBeNull();
    // No plan.json yet: null, so the Slack path reports it.
    expect(resolveFileAndonWorkspace(dir, {})).toBeNull();
    writeFileSync(plan, JSON.stringify({ rootSlug: "demo" }));
    expect(resolveFileAndonWorkspace(dir, { SLACK_BOT_TOKEN: "xoxb-1" })).toBe(dir);
    writeFileSync(plan, JSON.stringify({ rootSlug: "demo", slackKickoffRef: { channel: "C1", ts: "1.2" } }));
    expect(resolveFileAndonWorkspace(dir, { SLACK_BOT_TOKEN: "xoxb-1" })).toBeNull();
    expect(resolveFileAndonWorkspace(dir, {})).toBe(dir);
    writeFileSync(plan, "{");
    expect(resolveFileAndonWorkspace(dir, {})).toBeNull();
  });
});
