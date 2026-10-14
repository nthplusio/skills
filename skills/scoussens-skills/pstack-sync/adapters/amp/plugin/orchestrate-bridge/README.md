# orchestrate-bridge

An Amp plugin that gives the orchestrate loop a way to create threads nested under the thread that runs the loop. The `amp` CLI cannot set a parent thread, so a run's workers spawned with `amp -ox` lie loose in the thread list. The plugin API can (`createThread({ parentThreadID })`), and this plugin exposes that through a loopback HTTP endpoint inside the Amp process of the current thread. The adapter's `agent-runtime.ts` uses the endpoint when it finds the bridge file and falls back to `amp -ox` when it does not.

## What it does

1. On `session.start`, the plugin listens on an ephemeral port of `127.0.0.1`, mints a random 48-hex-character bearer token, and writes `<working dir>/.orchestrate/bridge.json` with mode `0600`:

   ```json
   {
     "url": "http://127.0.0.1:41234/spawn",
     "token": "<hex>",
     "thread": "T-...",
     "startedAt": "2026-10-14T10:00:00.000Z"
   }
   ```

   The working directory is `AMP_WORKING_DIRECTORY` when set, else the plugin system's `workspaceRoot`, else the process's current directory. An orb exports `AMP_WORKING_DIRECTORY` as the repository checkout, so there the file is `<checkout>/.orchestrate/bridge.json` whatever directory `amp` was started from; set the variable yourself to choose another path. `thread` is the session thread: the default parent of every spawn.

2. `POST <url>` with `Authorization: Bearer <token>` and a JSON body:

   | Field | Rule |
   | --- | --- |
   | `name` | Non-empty string, at most 200 characters. Logged, not sent to Amp (the plugin API has no rename; titles come from the first reply). |
   | `prompt` | Non-empty string under 200 kB. Appended as the thread's first user message. |
   | `project` | Non-empty string, as `amp --project` accepts it: a repository URL, `owner/repo`, `namespace/name`, or a project id. |
   | `mode` | `low`, `medium`, `high`, or `ultra`. |
   | `labels` | Array of strings matching `[A-Za-z0-9][A-Za-z0-9-]*`, each at most 32 characters, at most 20 of them. May be empty or omitted. |
   | `parent` | Optional thread id (`T-...`). Defaults to the session thread. |
   | `nodeType` | Optional: `planner`, `subplanner`, `worker`, or `verifier`, what the thread is in the orchestrate tree. Becomes the label `node-<type>` ahead of `labels` (once, when `labels` already holds it) and names the thread in the log line. A bridge built before this field ignores it, so the loop also sends the same label in `labels`. |

   The plugin creates the thread with `getBuiltinAgent(mode).createThread({ parentThreadID, executor: 'orb', project, visibility: 'private' })`, adds the labels, appends the prompt, and answers `200 {"threadID": "T-...", "parent": "T-..."}`. Spawns run one at a time; a second request waits for the first.

3. Refusals are JSON with one `error` string and never a stack: `401` for a missing or wrong token (checked before the route, so an unauthenticated caller learns nothing), `400` for bad input with the field named, `404` or `405` for a wrong path or method, and `500` with the message when Amp refuses the thread (for example a project the user cannot access).

4. On dispose the server closes and the file is removed. A second `session.start` in the same plugin process closes the old bridge and writes a new file for the new thread.

## Where to install it

Use the Workspace Plugins repository so the kickoff thread and every planner thread can spawn through the bridge. Publish it from the pack with the skills refresh. Discover the writable repository and clone it, or reuse its clone:

```bash
amp plugins repositories
amp clone workspace-plugins <plugins-clone>
python3 <pack>/skills/scoussens-skills/pstack-sync/scripts/sync.py publish --pack <pack> --repo <skills-clone> --plugins-repo <plugins-clone> --harness amp --dry-run
```

The dry run previews both repositories in throwaway worktrees without changing either clone, committing, or pushing. Publishing replaces directories named by the pack, including a same-named plugin installed by hand. The separate plugins clone records ownership in `.nthplusio-skills/pack-manifest.json`; only retired plugins named in that manifest are removed. Other plugin directories remain untouched.

Review the report and obtain authorization to push both workspace repositories before running:

```bash
python3 <pack>/skills/scoussens-skills/pstack-sync/scripts/sync.py publish --pack <pack> --repo <skills-clone> --plugins-repo <plugins-clone> --harness amp --push --verify
```

The command commits changes with each clone's identity and pushes each branch. Verification uses `amp plugins list` to report active plugins, alongside the skill checks. If `amp` is missing from `PATH`, verification reports the limitation. Confirm that `orchestrate-bridge` is active before running the loop.

For one project or a local check, copy this directory to `.amp/plugins/orchestrate-bridge/`, with `index.ts` directly inside it. `index.ts` imports nothing from the rest of the adapter. Node built-ins (`node:http`, `node:fs`, `node:crypto`) are available to plugins.

## The file it writes

`<working dir>/.orchestrate/bridge.json`, mode `0600`, written atomically (temporary file then rename), so a reader never sees half of it. The loop reads it from `ORCHESTRATE_AMP_BRIDGE`, else `<cwd>/.orchestrate/bridge.json`, else `$AMP_WORKING_DIRECTORY/.orchestrate/bridge.json`. Add `.orchestrate/` to the project's `.gitignore`; the file holds the token.

Dispose callbacks do not run when the plugin process is killed, so a stale file can survive a crash. `startedAt` says when it was written, and a caller that gets no answer on the URL treats the bridge as absent and falls back to the CLI.

## Security model

- **Loopback only.** The server binds `127.0.0.1` on a port the kernel picks. Only processes in the same orb (or on the same machine) can reach it.
- **Bearer token.** Every request must carry the token from the file, compared in constant time. The file is `0600`, so only the user that runs Amp reads it. The plugin never logs the token.
- **Input validated.** Every field is checked before Amp is called (the table above). The parent must look like a thread id, so a value such as `--last` cannot become an argument. The body is capped at the prompt limit plus 16 kB.
- **The project is the caller's choice.** The thread is created in whatever project the request names, with that project's secrets and orb settings, as long as the signed-in user can access it. That is the same authority the `amp -ox --project` path already has, and the only caller is the orchestrate loop running as that user; do not expose the endpoint beyond the loopback.
- **Private threads.** Every child is created with `visibility: 'private'`, not the parent's visibility.

## Test

```sh
cd skills/scoussens-skills/pstack-sync/adapters/amp && bun test __tests__/bridge-plugin.test.ts
```

The test drives the default export with a fake `PluginAPI` (a stub `getBuiltinAgent` whose fake thread records `addLabels` and `append`) over real loopback HTTP: the file is written and removed, a good request creates the child with the right options in order, a `nodeType` becomes its label once, bad token, bad label, bad mode, bad node type, and oversized prompt are refused with the right codes, an Amp failure is a `500` without a stack, and dispose closes the server.
