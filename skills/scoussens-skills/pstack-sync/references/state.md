# Sync state and administration

Read this for state migration, seed conflicts, name collisions, or changes to
set configuration or extensions. The [ordinary workflow](../SKILL.md#steps)
owns preparation and write authority. Publication and seed contribution remain
separately authorized operations under [publication.md](publication.md).

## Sets, dialects, ports, and extensions

A **set** is one upstream repository, one root plugin whose skills are the
roots, and their dependencies. pstack uses `cursor/plugins` and `pstack/skills`
by default. `--set <name>` selects another set; several sets share one install.
A **dialect** catalogs the source harness's constructs, Cursor for sets from
`cursor/plugins`. Each set can add its own needs.

A **port** names upstream files that need replacement as a unit.
`adapters/<harness>/<port>/` supplies their replacements. Until an adapter
exists, the port is pending and its files are not installed. The profile and
adaptation rules live in [adapting.md](adapting.md).

Portable workflow additions are **extensions**, declared independently of
ports. Each names a `skill`, a `files` map of installed paths to pack-relative
sources, a `reference`, and `entrypoints` that receive a pointer to it. Sync
preserves upstream text and harness transformations, installs the additions,
and records their hashes in the manifest. Upstream claiming an extension's
path stops sync for reconciliation. A locally edited extension is drift, not
overwritten. Change its pack source rather than recording an upstream transform.

## Shipped files

A pack refresh replaces `pstack-sync/`, which holds these seeds and adapters.
It leaves durable install state in `.nthplusio-skills/` at the repository root.

- `dialects/<dialect>.json` holds source constructs, marker regexes, and discovery
  fields. Every set with that dialect shares it.
- `sets/<set>/set.json` holds the upstream, root plugin, skills subdirectory,
  plugin marker, dialect, agents directory, collision prefix, `extra_needs`
  in the catalog shape, and `ports`. Its `exclude` names join the manifest's
  exclusions; `ignore` globs omit files such as upstream tests.
- `sets/<set>/transform.json` holds seed adaptations copied into durable state
  on the first run.
- `adapters/<harness>/<port>/<file>` replaces a port's files for this harness.
- `harness/TEMPLATE.md` and any shipped `harness/<harness>.md` seed the durable
  profile on the first run.

## Durable files

Paths below are relative to `.nthplusio-skills/pstack-sync/` in the repository
that holds the installed skills. Sets have separate state; profiles are shared.

- `sets/<set>/manifest.json` records the set, upstream commit, harness, and
  `exclude`; each skill's upstream `source`; and each file's upstream and
  installed hashes, `pending` adaptation, and owning `port`. A skill with
  unchanged upstream and transforms stays as installed.
- `sets/<set>/transform.json` records per-harness exact find/replace edits,
  replayed until upstream rewrites the passage. Each harness block has a
  same-shaped `local` block for installation-specific entries.
- `sets/<set>/seed.json` records the shipped transform block at the last sync,
  per harness. Sync three-way merges the pack's seed against it. A key changed
  only by the pack takes the pack entry; one changed only by the install keeps
  the install entry. If both changed it, the install entry wins and appears in
  `seed_conflicts`. Without this file, differences take the pack entry and
  appear in `seed_refreshed`.
- `sets/<set>/LICENSE-<plugin>` holds each source plugin's license.
- `harness/<harness>.md` records Destination and sourced rows for needs without
  discovery fields. [Adapting.md](adapting.md#the-harness-profile) defines the rows.
- `harness/<harness>.local.md` holds installation-specific rows in the same
  shape. A local row overrides its shared row.

Shared seeds describe the harness, not a repository or its owners' choices.
Repository-specific companion mappings, exclusions, and workflow wording belong
in local state. `record --local` records those file adaptations; local profile
rows hold those facts. An authorized `seed --out <pack's pstack-sync dir>` exports
only shared transforms and the shared profile, leaving local entries in place.

`harness-discovery` owns `.nthplusio-skills/discovery.json`, keyed by harness.
`sync.py` reads it for needs with discovery fields instead of repeating those
facts in profile rows.

## Ownership, collisions, and migration

The script owns durable manifests and transforms. Only `exclude` names and a
harness's shared or local `accept` regexes permit hand edits.

An upstream skill colliding with an unmanaged skill installs as `pstack-<name>`.
If that name is also taken, the script exits; ask the user what to call it.
An unmanaged skill that already supplies a dependency is left intact. Excluding
a dependency also drops whatever only it needed. Skill dependencies install under
their own names; subagent definitions install as `pstack-agents/<name>.md`, not
as skills. [Adapting.md](adapting.md#hand-offs-and-dependencies) defines transitive
hand-offs and the named-plugin requirement for cross-plugin dependencies.

Before sets existed, pstack state lived directly under
`.nthplusio-skills/pstack-sync/` or inside the skill directory. The next run moves
it into `sets/pstack/`; `status --since` still finds the old baseline paths.

## Publication manifests

`.nthplusio-skills/pack-manifest.json` records what `publish` last copied,
including pack commit, remote, time, and skill names. Only retired skills named
there can be removed; unnamed directories remain untouched.

The separate plugins clone has its own `.nthplusio-skills/pack-manifest.json`.
Publication replaces pack-named plugin directories and removes retired plugins
only when that manifest names them. Other plugin directories remain untouched.
These manifests record ownership, not permission to publish.
