/**
 * Amp port: a file-based Andon source.
 *
 * Upstream ships one `AndonSource`, the Slack reaction on the kickoff
 * message, and `andon raise` / `andon clear` talk to Slack. A loop without a
 * Slack token therefore had no way to raise Andon at all. This source lets
 * the root planner's loop read the stop signal from `<workspace>/andon.json`
 * instead:
 *
 *   raise   write `{"reason": "<why>", "raisedBy": "<who>"}` to the file
 *   clear   delete the file
 *
 * The poller in `core/andon.ts` owns the transitions and writes the cached
 * state children read through git; this class only reports what the file
 * says. It implements `AndonSource` structurally so it has no upstream
 * import and the pack's tests can load it on its own.
 */

import { existsSync, readFileSync, statSync } from "node:fs";

export const ANDON_FILE_NAME = "andon.json";

export type FileAndonSnapshot =
  | {
      active: true;
      raisedAt: string;
      raisedBy?: string;
      reason?: string;
      lastCheckedAt: string;
    }
  | { active: false; lastCheckedAt: string };

export class FileAndonSource {
  constructor(readonly path: string) {}

  async snapshot(): Promise<FileAndonSnapshot> {
    const lastCheckedAt = new Date().toISOString();
    if (!existsSync(this.path)) return { active: false, lastCheckedAt };
    const raw = readFileSync(this.path, "utf8");
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch (err) {
      throw new Error(
        `${this.path} is not JSON (${err instanceof Error ? err.message : String(err)}); write {"reason": "..."} to raise Andon or delete the file to clear it`
      );
    }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      throw new Error(`${this.path} must hold a JSON object such as {"reason": "..."}`);
    }
    const rec = parsed as Record<string, unknown>;
    const fromFile = typeof rec.raisedAt === "string" ? Date.parse(rec.raisedAt) : Number.NaN;
    const raisedAt = Number.isFinite(fromFile)
      ? new Date(fromFile).toISOString()
      : statSync(this.path).mtime.toISOString();
    const snapshot: FileAndonSnapshot = { active: true, raisedAt, lastCheckedAt };
    if (typeof rec.raisedBy === "string" && rec.raisedBy.trim()) snapshot.raisedBy = rec.raisedBy.trim();
    else snapshot.raisedBy = ANDON_FILE_NAME;
    if (typeof rec.reason === "string" && rec.reason.trim()) snapshot.reason = rec.reason.trim();
    return snapshot;
  }
}
