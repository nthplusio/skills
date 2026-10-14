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
 * import and the pack's tests can load it on its own. The helpers below are
 * what the set's `cli/andon.ts` transforms call, so `andon raise` and
 * `andon clear` write and delete the file instead of a person doing it.
 */

import { existsSync, readFileSync, renameSync, statSync, unlinkSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

export const ANDON_FILE_NAME = "andon.json";

export function andonFilePath(workspace: string): string {
  return join(resolve(workspace), ANDON_FILE_NAME);
}

/**
 * The workspace whose `andon.json` the `andon` commands act on, or null when
 * the run signals through Slack and the commands take upstream's path. The
 * choice mirrors the manager's: Slack when plan.json holds a
 * `slackKickoffRef` and `SLACK_BOT_TOKEN` is set, the file otherwise. No
 * `--workspace` or no readable plan.json is null too, so the Slack path
 * reports what is missing.
 */
export function resolveFileAndonWorkspace(
  workspace: string | undefined,
  env: NodeJS.ProcessEnv = process.env
): string | null {
  if (!workspace) return null;
  const planPath = join(resolve(workspace), "plan.json");
  if (!existsSync(planPath)) return null;
  let plan: unknown;
  try {
    plan = JSON.parse(readFileSync(planPath, "utf8"));
  } catch {
    return null;
  }
  const ref = typeof plan === "object" && plan !== null ? (plan as Record<string, unknown>).slackKickoffRef : undefined;
  if (typeof ref === "object" && ref !== null && env.SLACK_BOT_TOKEN) return null;
  return resolve(workspace);
}

/** Write `{reason, raisedBy, raisedAt}` to the workspace's `andon.json` (atomically) and return its path. */
export function raiseAndonFile(args: { workspace: string; reason: string; raisedBy?: string }): string {
  const path = andonFilePath(args.workspace);
  const raisedBy = args.raisedBy?.trim();
  const record = {
    reason: args.reason.trim(),
    ...(raisedBy ? { raisedBy } : {}),
    raisedAt: new Date().toISOString(),
  };
  const tmp = `${path}.${process.pid}.tmp`;
  writeFileSync(tmp, `${JSON.stringify(record, null, 2)}\n`);
  renameSync(tmp, path);
  return path;
}

/** Delete the workspace's `andon.json`; `cleared` says whether there was one. */
export function clearAndonFile(workspace: string): { path: string; cleared: boolean } {
  const path = andonFilePath(workspace);
  if (!existsSync(path)) return { path, cleared: false };
  unlinkSync(path);
  return { path, cleared: true };
}

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
