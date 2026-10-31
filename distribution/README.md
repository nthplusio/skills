# Distribution contract

The catalog describes packaging, not a runtime adapter or a second skill index.
Names and descriptions come from canonical `SKILL.md` files. `package.json`
owns the version. All target-client support is unverified until a result from
that client and mode is recorded. `needs` uses the discovery template vocabulary;
`runtime` states prerequisites that vocabulary does not model.

`manual-only` requires explicit host skill invocation. `task-intent` allows a
clear natural-language request for the task. `context-helper` also allows use
within another authorized task. Neither implicit activation nor an explicit
invocation grants permission for external writes.

Required companions enter dependency closure. Optional helpers do not. The
questionnaire has self-contained intake; nine other callers require
`explain-to`. Its prose helper and destination discovery remain conditional.
No host metadata here declares an invented skill-install dependency API.

## Design and source boundaries

The chosen design is a reviewed catalog plus one builder using existing skill
discovery. The alternative—per-host lists and copy scripts—would duplicate
membership, dependency closure and policy checks. Reusing pstack-sync would
bring installation authority and state migration into a local export operation.
Neither is necessary.

`npm run distribution:sync` generates tracked Codex policy sidecars and thin
source manifests. `npm run validate` checks for drift without writing. Stage
reviewed source changes before building: export reads only Git-tracked owned
resources, rejects symlinks and suspicious private paths, and preserves licenses.
Untracked personal files are never swept into an archive. Review tracked data
and run the private-terms check before any publication; filename guards cannot
prove arbitrary text contains no secrets.

The source Claude marketplace entry restricts root plugin discovery to the
curated paths. A manifest's `skills` field alone adds to Claude's default scan.
OpenAI's source catalog uses the documented Claude-compatible manifest fallback;
its actual client selection behavior is unverified. Conventional generated
exports contain only the selected closure, so have no default-scan ambiguity.

## Host references checked 2026-10-31

- [Agent Plugins 1.0.0 schema](https://agent-plugins.org/schemas/1.0.0/plugin.schema.json):
  root `plugin.json` requires `$schema` and `name`; no portable `skills` field.
- [OpenAI packaging and marketplace metadata](https://developers.openai.com/plugins/build/plugins):
  local `source: {source: "local", path: "./"}`, policy installation and
  authentication fields, category, and marketplace-level `interface.displayName`.
  Paths resolve from the marketplace root, not `.agents/plugins`.
- [Codex skill policy](https://learn.chatgpt.com/codex/build-skills):
  `policy.allow_implicit_invocation: false` in `agents/openai.yaml`.
- [Claude manifest reference](https://code.claude.com/docs/en/plugins-reference):
  explicit skill directory arrays and root marketplace selection behavior.
- [Claude surface support](https://claude.com/docs/plugins/platform-support.md):
  chat, Cowork and Code have separate component and installation contracts.

The builder emits only the small documented schema subset it needs. It does not
claim full host-schema validation or client acceptance. Claude's pinned CLI
validator is an additional manifest check, not an agent workflow test.
