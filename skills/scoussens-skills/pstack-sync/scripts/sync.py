#!/usr/bin/env python3
"""Sync a managed skill set, pstack by default, from its upstream repository, and the skills and subagent
definitions they hand off to, into a skills directory.

  sync.py sync   --harness NAME [--repo DIR] [--root DIR] [--ref BRANCH] [--dry-run]
  sync.py record --harness NAME [--repo DIR] [--root DIR] (SKILL | SKILL/FILE ... | --all)
  sync.py status --harness NAME [--repo DIR] [--root DIR] [--since REV]
  sync.py seed   --harness NAME [--repo DIR] [--root DIR] --out DIR
  sync.py publish --harness NAME --pack DIR --repo DIR [--plugins-repo DIR] [--push] [--verify] [--dry-run]

sync    Adds new upstream skills, updates changed ones, removes retired or excluded
        ones. Each file renders as: upstream -> rename rewrites -> global transforms
        -> file transforms (transform.json). A skill whose upstream tree and
        transforms hash are unchanged is left as installed.
        Prints a JSON report for the agent.
record  Stores the installed content of the given skills or files as file transforms
        (find/replace hunks against the rendered base), accepts the markers left in
        them, and updates manifest hashes. Run after adapting files by hand.
status  Prints a human-readable summary of what changed since REV (default HEAD) in
        the skills repository: transforms first, then new, updated, and removed
        skills, dependencies, then outstanding adaptation and drift.
seed    Writes the shared transforms and profile back into a pack checkout.
publish Refreshes a workspace skills repository from a pack checkout: replaces each
        pack skill with the pack's tracked files, removes skills the previous publish
        copied that the pack retired, runs sync for every set the pack ships, appends
        the profile rows the seed offers for reported gaps, and commits. Refuses to
        commit a node_modules directory or a file over 2 MB. --push pushes the
        branch; --verify asks `amp skill info` for one skill per source; --dry-run
        does everything in a throwaway worktree and leaves the repository untouched.
        Prints a JSON report for the agent.

Dependencies: a skill or subagent definition elsewhere in cursor/plugins that a synced file hands
off to installs beside pstack and is adapted the same way, followed transitively. A file hands
off to a skill by writing `name`, /name, **name**, or ../name/, and to a subagent definition
(<plugin>/agents/<name>.md) by writing its name. The hand-off counts when exactly one plugin in
scope provides the name: the referencing skill's own plugin, plus each plugin it names as
`plugin` or "plugin plugin". Subagent definitions install as pstack-agents/<name>.md. A skill
name an unmanaged skill already has is served by that skill instead.

Shipped with the skill, replaced by a plain copy of the pack:
  sets/<set>/set.json   one managed set: upstream repository, root plugin, skills
                        subdirectory, plugin marker, dialect, agents directory,
                        collision prefix, extra_needs (rows in the catalog shape), ports.
  dialects/<dialect>.json
                        constructs of one source harness; markers per need
                        (harness-independent), and the harness-discovery fields that
                        answer a need. A need with "detect" also gets markers sync.py
                        finds: "unavailable" for each skill, command, or subagent a file
                        hands off to that the skills directory will not have; "agents"
                        for each subagent definition named.
  sets/<set>/transform.json
                        seed adaptations, copied into durable state on first use.
  adapters/<harness>/<port>/<file>
                        this harness's replacement for a port's upstream files.
  harness/TEMPLATE.md   starting profile for a harness the pack does not ship.
  harness/<harness>.md  seed profile, copied into durable state on first use.

Durable state, beside discovery.json, kept across a pack refresh:
  .nthplusio-skills/pstack-sync/sets/<set>/manifest.json
                        set, upstream commit, harness, exclude list (names of pstack skills,
                        dependencies, or subagent definitions); per installed skill: dir,
                        upstream source, tree, transforms hash, per file upstream blob,
                        installed blob, pending adaptation.
  .nthplusio-skills/pstack-sync/sets/<set>/transform.json
                        per harness: "accept" marker regexes, "global" regex transforms,
                        "files" keyed by "<skill>/<rel>" (upstream skill name, or
                        pstack-agents), and a "local" sub-block of the same shape for
                        entries that belong to this install only (record --local). seed
                        exports every block without its local sub-block.
  .nthplusio-skills/pstack-sync/sets/<set>/seed.json
                        per harness, the shipped shared block as of the last sync. sync
                        three-way merges the shipped seed into the durable shared block
                        against it, so a transform the pack ships later reaches the
                        install; a key both sides changed keeps the durable entry and is
                        reported as a seed conflict.
  .nthplusio-skills/pstack-sync/sets/<set>/LICENSE-<plugin>
                        the license of each plugin the installed skills come from.
  .nthplusio-skills/pstack-sync/harness/<harness>.md
                        the harness profile in use: destination, and one row for each
                        need without discovery fields, with support native | keep |
                        substitute | partial | none. A row for a need with discovery
                        fields overrides them. Markers of needs marked native or keep
                        are accepted automatically.
  .nthplusio-skills/pstack-sync/harness/<harness>.local.md
                        rows that hold for this install only; a local row overrides
                        the shared row. seed never exports it.
  .nthplusio-skills/pack-manifest.json
                        what publish copied last: pack commit and remote, when, and the
                        skill names. publish removes only directories named here.

Harness facts (owned by harness-discovery, not pstack-sync):
  .nthplusio-skills/discovery.json at the root of the Git repository holding --repo, or
                        at --root. NAME matches a saved key or its slug. A need is
                        profiled once every field it names is discovered; null means
                        the harness has no such operation.
"""
import argparse, datetime, difflib, fnmatch, hashlib, json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO = os.path.dirname(os.path.dirname(HERE))
SELF = "pstack-sync"
DEFAULT_SET = "pstack"
SET_DEFAULTS = {"ref": "main", "plugin_marker": ".cursor-plugin/plugin.json", "dialect": "cursor",
                "agents_dir": None, "collision_prefix": None, "extra_needs": [], "ports": [],
                "exclude": [], "ignore": []}


def load_set(repo, name):
    """The set's configuration from <repo>/<SELF>/sets/<name>/set.json, with defaults filled."""
    path = os.path.join(repo, SELF, "sets", name, "set.json")
    if not os.path.exists(path):
        sys.exit(f"error: no set {name!r}: {path} is missing")
    with open(path) as f:
        cfg = {**SET_DEFAULTS, **json.load(f)}
    cfg["name"] = name
    cfg.setdefault("skills_subdir", f"{cfg['root_plugin']}/skills")
    cfg["agents_dir"] = cfg["agents_dir"] or f"{name}-agents"
    cfg["collision_prefix"] = cfg["collision_prefix"] or f"{name}-"
    return cfg


DEFAULT_UPSTREAM = "https://github.com/cursor/plugins"


def configure(cfg):
    """Point the module at one set. PSTACK_SYNC_UPSTREAM stands in for cursor/plugins in tests;
    a set from another repository keeps its own upstream."""
    global SET, UPSTREAM, ROOT_PLUGIN, SUBDIR, AGENTS, PREFIX, PLUGIN_MARKER, CACHE
    SET = cfg
    override = os.environ.get("PSTACK_SYNC_UPSTREAM")
    UPSTREAM = override if override and cfg["upstream"] == DEFAULT_UPSTREAM else cfg["upstream"]
    ROOT_PLUGIN = cfg["root_plugin"]
    SUBDIR = cfg["skills_subdir"]
    AGENTS = cfg["agents_dir"]
    PREFIX = cfg["collision_prefix"]
    PLUGIN_MARKER = cfg["plugin_marker"]
    CACHE = os.path.expanduser("~/.cache/pstack-sync/%s.git" % hashlib.sha1(UPSTREAM.encode()).hexdigest()[:12])


if os.path.exists(os.path.join(DEFAULT_REPO, SELF, "sets", DEFAULT_SET, "set.json")):
    configure(load_set(DEFAULT_REPO, DEFAULT_SET))
else:  # a copy of this script outside the skill directory: pstack's shape until main() configures a set
    configure({**SET_DEFAULTS, "name": DEFAULT_SET, "upstream": "https://github.com/cursor/plugins",
               "root_plugin": "pstack", "skills_subdir": "pstack/skills", "agents_dir": "pstack-agents",
               "collision_prefix": "pstack-"})
SUPPORT = ("native", "keep", "substitute", "partial", "none")
STATE_DIR = ".nthplusio-skills"
MISSING = object()
NAME = r"[a-z0-9]+(?:-[a-z0-9]+)*"
MENTION = re.compile(rf"`/?({NAME})`|(?<![\w./-])/({NAME})(?![\w/-])|\*\*({NAME})\*\*|\.\./({NAME})/")
HANDOFF = re.compile("|".join([
    rf"`(?P<tick>{NAME})` (?:skill|command|subagent)s?\b",
    rf"\*\*(?P<bold>{NAME})\*\* (?P<principle>principle )?(?:skill|command|subagent)s?\b",
    rf"`/(?P<slash>{NAME})(?:\s[^`\n]*)?`",
    rf"\bbuilt-in `/?(?P<builtin>{NAME})`",
    rf"\bbuilt-in (?P<builtin_word>{NAME}) (?:skill|command)\b",
    rf"subagent_type: [\"'](?P<subagent>{NAME})[\"']",
]))


# ---------- git / upstream ----------

def git(*args, input=None):
    r = subprocess.run(["git", "--git-dir", CACHE, *args], input=input, capture_output=True, check=True)
    return r.stdout


def fetch(ref):
    if not os.path.isdir(CACHE):
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        subprocess.run(["git", "init", "-q", "--bare", CACHE], check=True)
        git("remote", "add", "origin", UPSTREAM)
    try:
        git("fetch", "-q", "--depth", "1", "origin", ref)
    except subprocess.CalledProcessError as error:
        sys.exit(f"error: cannot fetch {ref} from {UPSTREAM} for the {SET['name']} set: "
                 f"{(error.stderr or b'').decode(errors='replace').strip()}")
    return git("rev-parse", "FETCH_HEAD").decode().strip()


def ensure_commit(sha):
    if subprocess.run(["git", "--git-dir", CACHE, "cat-file", "-e", f"{sha}^{{commit}}"],
                      capture_output=True).returncode:
        git("fetch", "-q", "--depth", "1", "origin", sha)


def inventory(sha):
    """Every skill and subagent definition in cursor/plugins at sha, from one ls-tree call.

    {"plugins": {plugin dir}, "skills": {name: [item]}, "agents": {name: [item]},
     "licenses": {plugin dir: blob}}, where an item is {"path", "name", "plugin",
    "files": {rel: (mode, blob)}}, plus "tree" for a skill. A skill belongs to the deepest
    plugin dir above it; an agent is <plugin>/agents/<name>.md, its one file <name>.md."""
    plugins, trees, files, agents, licenses = set(), {}, {}, [], {}
    for line in git("ls-tree", "-r", "-t", sha).decode().splitlines():
        meta, path = line.split("\t", 1)
        mode, kind, obj = meta.split()
        if path.endswith("/" + PLUGIN_MARKER):
            plugins.add(path[:-len("/" + PLUGIN_MARKER)])
        elif m := re.fullmatch(r"(.+?/skills/[^/]+)(?:/(.+))?", path):
            if m.group(2) is None and kind == "tree":
                trees[m.group(1)] = obj
            elif m.group(2) and kind == "blob":
                files.setdefault(m.group(1), {})[m.group(2)] = (mode, obj)
        elif m := re.fullmatch(r"(.+)/agents/([^/]+)\.md", path):
            agents.append((m.group(1), m.group(2), path, mode, obj))
        elif path.endswith("/LICENSE"):
            licenses[path[:-len("/LICENSE")]] = obj
    inv = {"plugins": plugins, "skills": {}, "agents": {},
           "licenses": {p: b for p, b in licenses.items() if p in plugins}}
    for path, fs in files.items():
        base, name = path.rsplit("/skills/", 1)
        plugin = max((p for p in plugins if base == p or base.startswith(p + "/")), key=len, default=None)
        if plugin and "SKILL.md" in fs and path in trees:
            inv["skills"].setdefault(name, []).append(
                {"path": path, "name": name, "plugin": plugin, "tree": trees[path], "files": fs})
    for plugin, name, path, mode, obj in agents:
        if plugin in plugins:
            inv["agents"].setdefault(name, []).append(
                {"path": path, "name": name, "plugin": plugin, "files": {f"{name}.md": (mode, obj)}})
    stems = "|".join(map(re.escape, sorted(inv["agents"], key=len, reverse=True)))
    inv["agent_re"] = re.compile(rf"(?<![\w-])({stems})(?![\w-])") if stems else None
    return inv


def roots_of(inv):
    """pstack's own skills, the ones under SUBDIR, by name."""
    return {n: s for n, items in inv["skills"].items() for s in items if s["path"] == f"{SUBDIR}/{n}"}


def mentions(text):
    """Names written the way skills refer to one another: `name`, /name, **name**, or a ../name/ link."""
    return {next(filter(None, m.groups())) for m in MENTION.finditer(text)}


def handoff_names(text):
    """Names the text hands off to as a skill, command, or subagent, whether or not cursor/plugins has
    them: `name` skill, **name** skill, `/name ...`, built-in `name`, subagent_type: "name". A
    **name** principle skill is principle-name."""
    out = set()
    for m in HANDOFF.finditer(text):
        g = m.groupdict()
        if g["slash"] and os.path.isdir("/" + g["slash"]):
            continue  # an absolute path such as /tmp, not a command
        name = next(v for k, v in g.items() if v and k != "principle")
        out.add(f"principle-{name}" if g["principle"] else name)
    return out


def agent_hits(text, inv):
    """Subagent definition names the text contains as whole words."""
    return set(inv["agent_re"].findall(text)) if inv["agent_re"] else set()


def closure(inv, roots, root_names, exclude, served, read):
    """Follow hand-offs from pstack's skills through cursor/plugins, transitively.

    Returns {"skills", "agents"}: the dependencies to install, by name; "ambiguous": names more
    than one in-scope plugin provides, with their paths; "existing": names served skills
    answer; "follows": {item key: {rel: dependency names its upstream text hands off to}}.
    Names in exclude, and in root_names (pstack's own skills), are never dependencies."""
    bases = {}
    for p in inv["plugins"]:
        bases.setdefault(p.rsplit("/", 1)[-1], set()).add(p)
    alt = "|".join(map(re.escape, sorted(bases, key=len, reverse=True)))
    named = re.compile(rf"`({alt})`|\b({alt}) plugin\b") if alt else None
    out = {"skills": {}, "agents": {}, "ambiguous": {}, "existing": set(), "follows": {}}
    queue = [(s["name"], s) for s in roots]
    while queue:
        texts = read(obj for _, s in queue for rel, (_, obj) in s["files"].items() if rel.endswith(".md"))
        nxt = []
        for key, s in queue:
            md = {rel: texts[obj].decode("utf-8", "replace")
                  for rel, (_, obj) in s["files"].items() if rel.endswith(".md")}
            scope = {s["plugin"]}
            if named:
                scope |= {p for m in named.finditer("\n".join(md.values())) for p in bases[m.group(1) or m.group(2)]}
            for rel, text in md.items():
                for kind, names in (("skills", mentions(text) - root_names), ("agents", agent_hits(text, inv))):
                    for name in sorted(names & set(inv[kind])):
                        cands = [c for c in inv[kind][name] if c["plugin"] in scope]
                        if len(cands) > 1:
                            out["ambiguous"][name] = sorted(c["path"] for c in cands)
                        elif not cands or name in exclude:
                            continue
                        elif kind == "skills" and name in served:
                            out["existing"].add(name)
                        else:
                            out["follows"].setdefault(key, {}).setdefault(rel, set()).add(name)
                            if name not in out[kind]:
                                out[kind][name] = cands[0]
                                nxt.append((name if kind == "skills" else AGENTS, cands[0]))
        queue = nxt
    out["ambiguous"] = {n: p for n, p in out["ambiguous"].items() if n not in out["skills"] and n not in out["agents"]}
    out["existing"] = sorted(out["existing"])
    return out


def own_agent(key, rel):
    """The subagent a file defines: <name> for pstack-agents/<name>.md, else None."""
    return rel[:-len(".md")] if key == AGENTS else None


def port_of(name, rel):
    """The set's port that owns upstream file rel of skill name, or None."""
    for port in SET["ports"]:
        if port.get("skill") == name and rel in port.get("files", []):
            return port
    return None


def adapter_path(repo, harness, port, rel):
    """Where this harness's replacement for a port file lives inside the skill directory."""
    return os.path.join(repo, SELF, "adapters", harness, port["name"], rel)


def install_items(roots, found):
    """{key: {"source" or "sources", "plugins", "tree", "files"}} for pstack's skills, their
    dependency skills, and one pstack-agents item holding every subagent definition."""
    items = {n: {"source": s["path"], "plugins": [s["plugin"]], "tree": s["tree"], "files": s["files"]}
             for n, s in {**roots, **found["skills"]}.items()}
    if found["agents"]:
        files = {rel: f for a in found["agents"].values() for rel, f in a["files"].items()}
        items[AGENTS] = {"sources": {f"{n}.md": a["path"] for n, a in found["agents"].items()},
                         "plugins": sorted({a["plugin"] for a in found["agents"].values()}),
                         "tree": hashlib.sha1(json.dumps(sorted(files.items())).encode()).hexdigest(),
                         "files": files}
    return items


def read_blobs(shas):
    shas = list(dict.fromkeys(shas))
    if not shas:
        return {}
    out, data, pos = {}, git("cat-file", "--batch", input=("\n".join(shas) + "\n").encode()), 0
    for sha in shas:
        nl = data.index(b"\n", pos)
        size = int(data[pos:nl].split()[2])
        out[sha] = data[nl + 1:nl + 1 + size]
        pos = nl + 1 + size + 1
    return out


def blob_reader():
    """read_blobs with a cache shared across calls; returns the cache, which holds every blob asked for."""
    cache = {}

    def read(shas):
        cache.update(read_blobs(s for s in shas if s not in cache))
        return cache
    return read


def blob_sha(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


# ---------- needs and harness profile ----------

def load_needs(repo):
    """The set's dialect catalog plus the set's own rows, in one list."""
    with open(os.path.join(repo, SELF, "dialects", f"{SET['dialect']}.json")) as f:
        needs = json.load(f)["needs"]
    return needs + list(SET["extra_needs"])


def compose_profile(shipped, durable):
    """A seed profile: the shipped file's text above its needs table (links, notes) with the
    install's table rows. Without a shipped file the durable profile is exported as is."""
    head = re.match(r"(?s)\A(.*?\n\| Need \|[^\n]*\n\|[ -|]*\|\n)", shipped)
    if not head:
        return durable
    rows = re.findall(r"(?m)^\|\s*`?[\w-]+`?\s*\|\s*(?:%s)\b.*$" % "|".join(SUPPORT), durable)
    return head.group(1) + ("\n".join(rows) + "\n" if rows else "")


def parse_profile_rows(text):
    """{need id: the full table row} for every row the profile holds."""
    return {m.group(1): m.group(0) for m in re.finditer(rf"(?m)^\|\s*`?([\w-]+)`?\s*\|\s*(?:{'|'.join(SUPPORT)})\b.*$", text)}


def parse_profile(text):
    """{need id: support} from rows like | `subagents` | substitute | ... |"""
    rows = {}
    for m in re.finditer(r"(?m)^\|\s*`?([\w-]+)`?\s*\|\s*(%s)\b" % "|".join(SUPPORT), text or ""):
        rows[m.group(1)] = m.group(2)
    return rows


def slug(name):
    """A harness key's file-safe name, as harness-discovery derives it: Claude Code -> claude-code."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def discovery_root(repo, root):
    if root:
        return os.path.abspath(root)
    r = subprocess.run(["git", "-C", repo, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else repo


def durable_dir(repo, root):
    """Install state beside discovery.json, outside the skill directory a pack refresh replaces.
    The harness profiles live here; each set's manifest, transforms, and licenses live under
    sets/<set>/."""
    return os.path.join(discovery_root(repo, root), STATE_DIR, SELF)


def adopt_durable(repo, root, harness):
    """Make the durable layout for this set, taking seeds and older layouts across.

    manifest.json and LICENSE-* only exist as install state. transform.json and
    harness/<harness>.md also ship as seeds; the durable copy wins once it exists. An
    install from before sets kept the default set's files directly under the durable
    directory, or inside the skill directory; both move into sets/<set>/ once.
    """
    dest = durable_dir(repo, root)
    set_dir = os.path.join(dest, "sets", SET["name"])
    os.makedirs(os.path.join(dest, "harness"), exist_ok=True)
    os.makedirs(set_dir, exist_ok=True)
    skill = os.path.join(repo, SELF)
    seed_dir = os.path.join(skill, "sets", SET["name"])

    def take(target, source, move=False):
        if os.path.exists(target) or not os.path.exists(source):
            return
        (shutil.move if move else shutil.copy2)(source, target)

    older = [dest, skill] if SET["name"] == DEFAULT_SET else []
    for old in older:
        take(os.path.join(set_dir, "manifest.json"), os.path.join(old, "manifest.json"), move=True)
        take(os.path.join(set_dir, "transform.json"), os.path.join(old, "transform.json"), move=(old == dest))
        if os.path.isdir(old):
            for fn in os.listdir(old):
                if fn.startswith("LICENSE-"):
                    take(os.path.join(set_dir, fn), os.path.join(old, fn), move=True)
    take(os.path.join(set_dir, "transform.json"), os.path.join(seed_dir, "transform.json"))
    take(os.path.join(dest, "harness", f"{harness}.md"), os.path.join(skill, "harness", f"{harness}.md"))
    return dest, set_dir


def harness_facts(path, harness, needs):
    """(saved harness key, {need id: {field: value}}) for each need whose discovery fields are all
    recorded. A missing field, or the template's "unknown", is not yet discovered."""
    if not os.path.exists(path):
        return None, {}
    try:
        with open(path) as f:
            harnesses = json.load(f)["harnesses"]
        keys = [k for k in harnesses if k == harness] or [k for k in harnesses if slug(k) == slug(harness)]
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        sys.exit(f"error: {path} is not valid discovery ({error}); repair it with harness-discovery")
    if len(keys) != 1:
        return None, {}
    entry, facts = harnesses[keys[0]], {}
    for n in needs:
        values = {}
        for field in n.get("discovery", []):
            node = entry
            for part in field.split("."):
                node = node.get(part, MISSING) if isinstance(node, dict) else MISSING
            values[field] = node
        if values and all(v is not MISSING and v != "unknown" for v in values.values()):
            facts[n["id"]] = values
    return keys[0], facts


def needs_in(text, needs):
    """{need id: sorted markers} found in text."""
    found = {}
    for n in needs:
        hits = {m.group(0) for p in n["markers"] for m in re.finditer(p, text)}
        if hits:
            found[n["id"]] = sorted(hits)
    return found


def flatten(found):
    return sorted({m for ms in found.values() for m in ms})


# ---------- rendering ----------

def rewrite_refs(text, renames):
    for old, new in renames.items():
        o = re.escape(old)
        text = re.sub(rf"(?<![\w./-])/{o}(?![\w-])", f"/{new}", text)
        text = re.sub(rf"\*\*{o}\*\*", f"**{new}**", text)
        text = re.sub(rf"`{o}`", f"`{new}`", text)
        text = re.sub(rf"\.\./{o}/", f"../{new}/", text)
    return text


def set_name(text, name):
    if not text.startswith("---"):
        return f"---\nname: {name}\n---\n\n{text}"
    end = text.index("\n---", 3)
    fm, body = text[:end], text[end:]
    if re.search(r"(?m)^name:.*$", fm):
        fm = re.sub(r"(?m)^name:.*$", f"name: {name}", fm, count=1)
    else:
        fm = fm.replace("---", f"---\nname: {name}", 1)
    return fm + body


def base_render(key, rel, data, target, renames, tf):
    """Upstream text through rename rewrites and global transforms; None if binary."""
    if b"\0" in data[:8192]:
        return None
    text = data.decode("utf-8")
    if rel.endswith(".md"):
        text = rewrite_refs(text, renames)
    if rel == "SKILL.md":
        text = set_name(text, target)
    for g in tf.get("global", []):
        if fnmatch.fnmatch(key, g.get("files", "*")):
            text = re.sub(g["pattern"], g["replace"], text)
    return text


def apply_file_transforms(text, transforms):
    """Returns (text or None if deleted, list of stale transforms)."""
    stale = []
    for t in transforms:
        if t.get("delete"):
            return None, []
        if text.count(t["find"]) == 1:
            text = text.replace(t["find"], t["replace"])
        else:
            stale.append({"find": t["find"], "replace": t["replace"]})
    return text, stale


def upstream_diff(old, new, path):
    """Unified diff of a file's rendered upstream text between two syncs."""
    return "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                        f"a/{path}", f"b/{path}", n=1))


def hunks(base, new):
    """Minimal unique find/replace hunks turning base into new."""
    a, b = base.splitlines(keepends=True), new.splitlines(keepends=True)
    ops = [o for o in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if o[0] != "equal"]
    ranges = []
    for _, i1, i2, j1, j2 in ops:
        lo, hi = i1, i2
        while True:
            find = "".join(a[lo:hi])
            if find and base.count(find) == 1:
                break
            if lo == 0 and hi == len(a):
                break
            lo, hi = max(lo - 1, 0), min(hi + 1, len(a))
        if ranges and lo <= ranges[-1][1]:
            ranges[-1][1] = max(ranges[-1][1], hi)
            ranges[-1][2].append((i1, i2, j1, j2))
        else:
            ranges.append([lo, hi, [(i1, i2, j1, j2)]])
    out = []
    for lo, hi, group in ranges:
        rep, cur = [], lo
        for i1, i2, j1, j2 in group:
            rep += a[cur:i1] + b[j1:j2]
            cur = i2
        rep += a[cur:hi]
        out.append({"find": "".join(a[lo:hi]), "replace": "".join(rep)})
    return out


# ---------- state ----------

def read_text(path):
    if not os.path.exists(path):
        return ""
    with open(path) as f:
        return f.read()


def load_json(path, default):
    return json.load(open(path)) if os.path.exists(path) else default


def save_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def norm_skills(skills):
    return {k: (v if isinstance(v, dict) else {"dir": v}) for k, v in skills.items()}


class State:
    def __init__(self, repo, harness, root=None):
        self.repo = repo
        self.harness = harness
        self.discovery_root = discovery_root(repo, root)
        self.durable, self.set_dir = adopt_durable(repo, root, harness)
        self.manifest_path = os.path.join(self.set_dir, "manifest.json")
        self.transform_path = os.path.join(self.set_dir, "transform.json")
        self.seed_path = os.path.join(self.set_dir, "seed.json")
        self.seed_next = None  # seed.json to write once the refresh is saved
        self.profile_path = os.path.join(self.durable, "harness", f"{harness}.md")
        self.manifest = load_json(self.manifest_path, {"skills": {}})
        self.transforms = load_json(self.transform_path, {})
        self.shared = self.transforms.setdefault(harness, {"accept": [], "global": [], "files": {}})
        self.shared.setdefault("files", {})
        self.local = self.shared.setdefault("local", {"accept": [], "global": [], "files": {}})
        for k, v in (("accept", []), ("global", []), ("files", {})):
            self.local.setdefault(k, type(v)())
        self.managed = norm_skills(self.manifest["skills"])
        self.manifest_exclude = sorted(set(self.manifest.get("exclude", [])))  # the install's own, hand edited
        self.exclude = set(self.manifest_exclude) | set(SET["exclude"])  # applied together; the set's stays in set.json
        self.needs = load_needs(repo)
        self.local_profile_path = os.path.join(self.durable, "harness", f"{harness}.local.md")
        self.profile_exists = os.path.exists(self.profile_path)
        shared_text = read_text(self.profile_path)
        local_text = read_text(self.local_profile_path)
        self.profile_text = shared_text + "\n" + local_text
        self.profile = {**parse_profile(shared_text), **parse_profile(local_text)}
        self.auto_accept = {i for i, s in self.profile.items() if s in ("native", "keep")}
        self.discovery_path = os.path.join(self.discovery_root, STATE_DIR, "discovery.json")
        self.discovery_key, self.facts = harness_facts(self.discovery_path, harness, self.needs)
        managed_dirs = {v["dir"] for v in self.managed.values()}
        skills = {d for d in os.listdir(repo) if os.path.isfile(os.path.join(repo, d, "SKILL.md"))}
        self.foreign = skills - managed_dirs - {SELF}  # includes directories other sets manage
        self.handoff_need = next((n["id"] for n in self.needs if n.get("detect") == "unavailable"), None)
        self.command_markers = [p for n in self.needs if n["id"] != self.handoff_need for p in n["markers"]]
        self.inv, self.available = None, set()

    @property
    def tf(self):
        """One view of the shared and local blocks: local rows come last and win on a file key."""
        return {"accept": self.shared["accept"] + self.local["accept"],
                "global": self.shared["global"] + self.local["global"],
                "files": {**self.shared["files"], **self.local["files"]}}

    def set_file(self, key, entry, local):
        """Record a file's adaptation in one home, local or shared, and drop it from the other."""
        (self.shared if local else self.local)["files"].pop(key, None)
        (self.local if local else self.shared)["files"][key] = entry

    def pop_file(self, key):
        self.shared["files"].pop(key, None)
        self.local["files"].pop(key, None)

    def use(self, inv, available):
        """Detect hand-offs against cursor/plugins at one commit, given the names the skills
        directory will have: skill dirs, upstream skill names, and subagent definitions."""
        self.inv, self.available = inv, set(available)

    def installed_names(self):
        """The names the skills directory has once a sync is done, as cmd_sync passes to use()."""
        names = self.foreign | {SELF}
        for key, entry in self.managed.items():
            names |= {key, entry["dir"]} | {rel[:-len(".md")] for rel in entry.get("sources", {})}
        return names

    def unavailable(self, text):
        """Skills, commands, and subagents the text hands off to that the skills directory will not
        have. A name whose /name another need's markers cover belongs to that need (/loop)."""
        names = (mentions(text) & set(self.inv["skills"])) | handoff_names(text) | agent_hits(text, self.inv)
        return {n for n in names - self.available
                if not any(re.search(p, "/" + n) for p in self.command_markers)}

    def needs_found(self, text, own=None):
        """needs_in, plus the markers detected for needs with "detect" once use() has run. own is
        the subagent a pstack-agents file defines, which naming itself does not dispatch."""
        found = needs_in(text, self.needs)
        if self.inv is None:
            return found
        for n in self.needs:
            if n.get("detect") == "unavailable":
                extra = self.unavailable(text)
            elif n.get("detect") == "agents":
                extra = agent_hits(text, self.inv) - {own}
            else:
                continue
            if extra:
                found[n["id"]] = sorted(set(found.get(n["id"], [])) | extra)
        return found

    def gaps(self, flagged):
        """Flagged needs with neither a profile row nor discovered facts."""
        return sorted(set(flagged) - set(self.profile) - set(self.facts))

    def flagged_facts(self, flagged):
        """Discovered facts for the flagged needs no profile row overrides."""
        return {nid: self.facts[nid] for nid in sorted(flagged) if nid in self.facts and nid not in self.profile}

    def skill_tf_hash(self, name, renames):
        files = {k: v for k, v in self.tf.get("files", {}).items() if k.startswith(name + "/")}
        upstream = sorted(self.inv["skills"]) + sorted(self.inv["agents"]) if self.inv else []
        adapters = {}
        for port in SET["ports"]:
            if port.get("skill") == name:
                for rel in port.get("files", []):
                    data = read_installed(adapter_path(self.repo, self.harness, port, rel))
                    adapters[f"{port['name']}/{rel}"] = blob_sha(data) if data is not None else None
        blob = json.dumps([self.tf.get("global", []), self.tf.get("accept", []), files, renames,
                           sorted(self.auto_accept), self.needs, sorted(self.available), upstream, adapters],
                          sort_keys=True)
        return hashlib.sha1(blob.encode()).hexdigest()

    def outstanding(self, text, accepted, own=None):
        """Needs with markers not accepted by profile, accept regexes, or the file's list."""
        out = {}
        for nid, ms in self.needs_found(text, own).items():
            if nid in self.auto_accept:
                continue
            ms = [m for m in ms if m not in accepted and not any(re.search(p, m) for p in self.tf.get("accept", []))]
            if ms:
                out[nid] = ms
        return out

    def targets(self, roots, deps=(), agents=False):
        """Install dir per item key. A pstack skill whose name an unmanaged skill has becomes
        pstack-<name>; a dependency keeps its name, because closure() leaves such names to the
        unmanaged skill."""
        targets = {}
        for name in roots:
            if name in self.managed:
                targets[name] = self.managed[name]["dir"]
            elif name in self.foreign or name == SELF:
                targets[name] = f"{PREFIX}{name}"
            else:
                targets[name] = name
            if targets[name] in self.foreign:
                sys.exit(f"error: {name} -> {targets[name]} collides with a skill outside the {SET['name']} set")
        targets.update({name: name for name in deps})
        if agents:
            if AGENTS not in self.managed and os.path.exists(os.path.join(self.repo, AGENTS)):
                sys.exit(f"error: {AGENTS}/ exists and pstack-sync does not manage it")
            targets[AGENTS] = AGENTS
        dirs = sorted(targets.values())
        clash = sorted({d for d in dirs if dirs.count(d) > 1})
        if clash:
            sys.exit(f"error: more than one skill installs to {', '.join(clash)}")
        return targets

    def installed_upstream(self, inv):
        """{key: {"files": ...}} for each managed item at the inventory's commit, by recorded source."""
        by_path = {s["path"]: s for kind in ("skills", "agents") for items in inv[kind].values() for s in items}
        out = {}
        for key, entry in self.managed.items():
            if "sources" in entry:
                out[key] = {"files": {rel: f for p in entry["sources"].values() if p in by_path
                                      for rel, f in by_path[p]["files"].items()}}
            elif entry.get("source", f"{SUBDIR}/{key}") in by_path:
                out[key] = by_path[entry.get("source", f"{SUBDIR}/{key}")]
        return out

    def dependency_report(self, found, needs_adaptation):
        """The sync report's "dependencies": what installed, and the hand-offs still outstanding
        that name an excluded skill or have no mapping in the harness profile."""
        marks = {}
        for target, files in sorted(needs_adaptation.items()):
            for rel, p in sorted(files.items()):
                for name in p.get("needs", {}).get(self.handoff_need, []):
                    marks.setdefault(name, []).append(f"{target}/{rel}")

        def mapped(name):
            return re.search(rf"`/?{re.escape(name)}[`\s]", self.profile_text)
        return {
            "installed": {**{n: s["path"] for n, s in sorted(found["skills"].items())},
                          **{f"{AGENTS}/{n}.md": s["path"] for n, s in sorted(found["agents"].items())}},
            "existing": found["existing"],
            "unresolved": {n: fs for n, fs in sorted(marks.items())
                           if n not in self.exclude and n not in found["ambiguous"] and not mapped(n)},
            "excluded": {n: fs for n, fs in sorted(marks.items()) if n in self.exclude},
            "ambiguous": found["ambiguous"],
        }


def read_installed(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


# ---------- seed refresh ----------

def entry_key(item):
    """An accept regex or a global transform as a dict key."""
    return item if isinstance(item, str) else json.dumps(item, sort_keys=True)


def merge_seed_part(durable, seed, shipped, label, refreshed, conflicts):
    """Three-way merge of one part of a harness block, {key: entry} each, against the seed
    adopted last time. None for seed is the bootstrap: the shipped entry wins wherever the
    durable one differs. Keys the seed never had and the pack does not ship stay as recorded."""
    out = {}
    keys = list(durable) + [k for k in shipped if k not in durable]
    if seed:
        keys += [k for k in seed if k not in durable and k not in shipped]
    for key in keys:
        d, s1 = durable.get(key, MISSING), shipped.get(key, MISSING)
        if seed is None:
            pick = s1 if s1 is not MISSING else d
            if s1 is not MISSING and s1 != d:
                refreshed.append(label(key))
        else:
            s0 = seed.get(key, MISSING)
            if s1 == s0 or d == s1:
                pick = d
            elif d == s0:
                pick = s1
                refreshed.append(label(key))
            else:
                pick = d
                conflicts.append(label(key))
        if pick is not MISSING:
            out[key] = pick
    return out


def refresh_seed(st):
    """Bring the shipped seed's changes since the last sync into the durable shared block.
    Returns (refreshed keys, conflicting keys); the local block is never read or written."""
    shipped_all = load_json(os.path.join(st.repo, SELF, "sets", SET["name"], "transform.json"), None)
    if not isinstance(shipped_all, dict) or st.harness not in shipped_all:
        return [], []
    shipped = shipped_all[st.harness]
    seeds = load_json(st.seed_path, {})
    seed = seeds.get(st.harness)
    refreshed, conflicts = [], []
    for part in ("accept", "global"):
        merged = merge_seed_part({entry_key(i): i for i in st.shared.get(part, [])},
                                 {entry_key(i): i for i in seed.get(part, [])} if seed is not None else None,
                                 {entry_key(i): i for i in shipped.get(part, [])},
                                 lambda k, part=part: f"{part}: {k}", refreshed, conflicts)
        st.shared[part] = list(merged.values())
    st.shared["files"] = merge_seed_part(st.shared["files"], seed.get("files", {}) if seed is not None else None,
                                         shipped.get("files", {}), lambda k: k, refreshed, conflicts)
    seeds[st.harness] = {k: v for k, v in shipped.items() if k != "local"}
    st.seed_next = seeds
    return refreshed, conflicts


# ---------- commands ----------

def cmd_sync(a, st):
    seed_refreshed, seed_conflicts = refresh_seed(st)
    sha = fetch(a.ref)
    inv = inventory(sha)
    read = blob_reader()
    roots = roots_of(inv)
    keep = {n: s for n, s in roots.items() if n not in st.exclude}
    found = closure(inv, keep.values(), set(roots), st.exclude, st.foreign | {SELF}, read)
    ups = install_items(keep, found)
    targets = st.targets(keep, found["skills"], bool(found["agents"]))
    renames = {u: t for u, t in targets.items() if u != t}
    st.use(inv, st.foreign | {SELF} | set(ups) | set(targets.values()) | set(found["agents"]))
    had_agents = st.managed.get(AGENTS, {}).get("sources", {})
    newly = ({n for n in found["skills"] if n not in st.managed}
             | {n for n in found["agents"] if f"{n}.md" not in had_agents})
    harness_changed = st.manifest.get("harness") != a.harness

    report = {"upstream_commit": sha, "previous_commit": st.manifest.get("commit"),
              "harness": a.harness, "harness_changed": harness_changed,
              "profile_missing": not st.profile_exists, "profile_gaps": [], "dry_run": a.dry_run,
              "discovery": {"path": st.discovery_path, "harness": st.discovery_key}, "harness_facts": {},
              "added": [], "updated": [], "removed": [], "unchanged_count": 0,
              "renamed_for_collision": renames, "skipped_binary_files": [], "local_drift": [],
              "needs_security_review": [], "needs_adaptation": {}, "dependencies": {},
              "ports_pending": {}, "stale_ports": {}, "ignored_count": 0,
              "seed_refreshed": seed_refreshed, "seed_conflicts": seed_conflicts}
    new_skills = {}
    prev_fetched = []

    def previous_blob(obj):
        """A blob from the previous sync's commit, or None if it can no longer be fetched."""
        if not prev_fetched and st.manifest.get("commit"):
            prev_fetched.append(True)
            try:
                ensure_commit(st.manifest["commit"])
            except subprocess.CalledProcessError:
                pass
        try:
            return read_blobs([obj])[obj]
        except (subprocess.CalledProcessError, ValueError, IndexError):
            return None

    def flag(target, rel, pending):
        report["needs_adaptation"].setdefault(target, {})[rel] = pending

    for name, up in sorted(ups.items()):
        target, entry = targets[name], st.managed.get(name, {})
        origin = {k: up[k] for k in ("source", "sources") if k in up}
        dst = os.path.join(st.repo, target)
        tfh = st.skill_tf_hash(name, renames)
        adapters_in_place = all(
            os.path.exists(os.path.join(dst, rel))
            for port in SET["ports"] if port.get("skill") == name
            for rel in port.get("files", [])
            if os.path.exists(adapter_path(st.repo, a.harness, port, rel)))
        if (not harness_changed and entry.get("tree") == up["tree"] and adapters_in_place
                and entry.get("transforms") == tfh and os.path.isdir(dst)):
            report["unchanged_count"] += 1
            new_skills[name] = {**entry, **origin}
            for rel, f in entry.get("files", {}).items():
                if f.get("pending"):
                    flag(target, rel, f["pending"])
                if f.get("port") and f.get("installed") is None:
                    report["ports_pending"].setdefault(f["port"], []).append(f"{target}/{rel}")
            continue

        blobs = read(obj for _, obj in up["files"].values())
        files, changed = {}, not os.path.isdir(dst)
        recorded = entry.get("files", {})
        for rel, (mode, obj) in sorted(up["files"].items()):
            key = f"{name}/{rel}"
            if any(fnmatch.fnmatch(rel, g) for g in SET["ignore"]):
                report["ignored_count"] += 1
                stale_path = os.path.join(dst, rel)
                if os.path.exists(stale_path):
                    changed = True
                    if not a.dry_run:
                        os.remove(stale_path)
                continue
            port = port_of(name, rel)
            if port:
                path = os.path.join(dst, rel)
                current = read_installed(path)
                previous = recorded.get(rel, {}).get("upstream")
                if previous and previous != obj:
                    report["stale_ports"].setdefault(port["name"], []).append(f"{target}/{rel}")
                adapter = read_installed(adapter_path(st.repo, a.harness, port, rel))
                if adapter is None:
                    report["ports_pending"].setdefault(port["name"], []).append(f"{target}/{rel}")
                    if current is not None:
                        changed = True
                        if not a.dry_run:
                            os.remove(path)
                    files[rel] = {"upstream": obj, "installed": None, "port": port["name"]}
                    continue
                if current != adapter:
                    changed = True
                    if not a.dry_run:
                        os.makedirs(os.path.dirname(path), exist_ok=True)
                        with open(path, "wb") as f:
                            f.write(adapter)
                        os.chmod(path, 0o755 if mode == "100755" else 0o644)
                files[rel] = {"upstream": obj, "installed": blob_sha(adapter), "port": port["name"]}
                continue
            base = base_render(key, rel, blobs[obj], target, renames, st.tf)
            if base is None:
                report["skipped_binary_files"].append(f"{target}/{rel}")
                continue
            ftf = st.tf["files"].get(key, {})
            text, stale = apply_file_transforms(base, ftf.get("transforms", []))
            path = os.path.join(dst, rel)
            current = read_installed(path)
            if (current is not None and rel in recorded
                    and blob_sha(current) != recorded[rel].get("installed")):
                report["local_drift"].append(f"{target}/{rel}")
                files[rel] = {**recorded[rel], "upstream": obj}
                continue
            if text is None:
                if current is not None:
                    changed = True
                    if not a.dry_run:
                        os.remove(path)
                continue
            new = text.encode("utf-8")
            todo = st.outstanding(text, ftf.get("accepted", []), own_agent(name, rel))
            follows = found["follows"].get(name, {}).get(rel, set())
            prior = recorded.get(rel, {}).get("pending", {}).get("dependencies", [])
            fresh = sorted(follows & (newly | set(prior))) if ftf.get("transforms") else []
            pending = {k: v for k, v in (("stale_transforms", stale), ("needs", todo), ("dependencies", fresh)) if v}
            if pending:
                flag(target, rel, pending)
                old_obj = recorded.get(rel, {}).get("upstream")
                if stale and old_obj and old_obj != obj:
                    old = previous_blob(old_obj)
                    if old is not None and b"\0" not in old[:8192]:
                        old_base = base_render(key, rel, old, target, renames, st.tf)
                        report["needs_adaptation"][target][rel] = {
                            **pending, "upstream_diff": upstream_diff(old_base, base, f"{target}/{rel}")}
            if current != new:
                changed = True
                if rel.startswith("scripts/") or rel == "mcp.json" or (
                        rel == "SKILL.md" and re.search(r"(?m)^mcpServers:", text)):
                    report["needs_security_review"].append(f"{target}/{rel}")
                if not a.dry_run:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "wb") as f:
                        f.write(new)
                    os.chmod(path, 0o755 if mode == "100755" else 0o644)
            files[rel] = {"upstream": obj, "installed": blob_sha(new)}
            if pending:
                files[rel]["pending"] = pending

        for port in SET["ports"]:  # adapter files a port adds that upstream does not have
            if port.get("skill") != name:
                continue
            for rel in port.get("files", []):
                if rel in up["files"]:
                    continue
                adapter = read_installed(adapter_path(st.repo, a.harness, port, rel))
                path = os.path.join(dst, rel)
                if adapter is None:
                    continue
                if read_installed(path) != adapter:
                    changed = True
                    if not a.dry_run:
                        os.makedirs(os.path.dirname(path), exist_ok=True)
                        with open(path, "wb") as f:
                            f.write(adapter)
                files[rel] = {"upstream": None, "installed": blob_sha(adapter), "port": port["name"]}

        port_files = {rel for port in SET["ports"] if port.get("skill") == name for rel in port.get("files", [])}
        if os.path.isdir(dst):  # files present locally but gone upstream
            for dp, _, fns in os.walk(dst):
                for fn in fns:
                    rel = os.path.relpath(os.path.join(dp, fn), dst)
                    if rel in port_files:
                        continue
                    ignored = any(fnmatch.fnmatch(rel, g) for g in SET["ignore"])
                    if ignored and rel not in up["files"]:
                        continue  # a local file the set leaves alone, such as installed dependencies
                    if rel not in up["files"] or ignored:
                        changed = True
                        if not a.dry_run:
                            os.remove(os.path.join(dp, fn))

        if not entry:
            report["added"].append(target)
        elif changed:
            report["updated"].append(target)
        else:
            report["unchanged_count"] += 1
        new_skills[name] = {"dir": target, **origin, "tree": up["tree"], "transforms": tfh, "files": files}

    for name, entry in sorted(st.managed.items()):
        if name not in targets:
            report["removed"].append(entry["dir"])
            if not a.dry_run and entry["dir"] not in targets.values():
                shutil.rmtree(os.path.join(st.repo, entry["dir"]), ignore_errors=True)

    flagged = {nid for files in report["needs_adaptation"].values() for p in files.values()
               for nid in p.get("needs", {})}
    report["profile_gaps"] = st.gaps(flagged)
    seed_rows = parse_profile_rows(read_text(os.path.join(st.repo, SELF, "harness", f"{a.harness}.md")))
    report["profile_gaps_in_seed"] = {g: seed_rows[g] for g in report["profile_gaps"] if g in seed_rows}
    report["harness_facts"] = st.flagged_facts(flagged)
    report["dependencies"] = st.dependency_report(found, report["needs_adaptation"])

    if not a.dry_run:
        plugins = {p for up in ups.values() for p in up["plugins"]} | {ROOT_PLUGIN}
        licenses = {f"LICENSE-{p.replace('/', '-')}": inv["licenses"][p] for p in plugins if p in inv["licenses"]}
        texts = read(licenses.values())
        state_dir = st.set_dir
        for fn in os.listdir(state_dir):
            if fn.startswith("LICENSE-") and fn not in licenses:
                os.remove(os.path.join(state_dir, fn))
        for fn, obj in licenses.items():
            with open(os.path.join(state_dir, fn), "wb") as f:
                f.write(texts[obj])
        st.manifest = {"set": SET["name"], "upstream": f"{UPSTREAM}/tree/{a.ref}/{SUBDIR}", "commit": sha,
                       "harness": a.harness, "exclude": st.manifest_exclude, "skills": new_skills}
        save_json(st.manifest_path, st.manifest)
        save_json(st.transform_path, st.transforms)
        if st.seed_next is not None:
            save_json(st.seed_path, st.seed_next)
    return report


def cmd_record(a, st):
    sha = st.manifest.get("commit")
    if not sha or st.manifest.get("harness") != a.harness:
        sys.exit("error: run `sync --harness %s` first" % a.harness)
    ensure_commit(sha)
    inv = inventory(sha)
    ups = st.installed_upstream(inv)
    st.use(inv, st.installed_names())
    by_dir = {v["dir"]: k for k, v in st.managed.items()}
    picks = {}  # upstream name -> set of rels, or None for every file
    for arg in (sorted(st.managed) if a.all else a.skills):
        skill, _, rel = arg.partition("/")
        name = by_dir.get(skill, skill)
        if rel:
            if picks.get(name, set()) is not None:
                picks.setdefault(name, set()).add(rel)
        else:
            picks[name] = None
    renames = {u: v["dir"] for u, v in st.managed.items() if u != v["dir"]}
    summary = {}
    for name in sorted(picks):
        if name not in st.managed or name not in ups:
            sys.exit(f"error: {name} is not a managed upstream skill")
        entry, up = st.managed[name], ups[name]
        target = entry["dir"]
        dst = os.path.join(st.repo, target)
        blobs = read_blobs(obj for _, obj in up["files"].values())
        extra = [os.path.relpath(os.path.join(dp, fn), dst) for dp, _, fns in os.walk(dst) for fn in fns]
        extra = [r for r in extra if r not in up["files"] and not port_of(name, r)
                 and not any(fnmatch.fnmatch(r, g) for g in SET["ignore"])]
        if extra:
            sys.exit(f"error: {target} has files not in upstream: {extra}")
        files, counts = dict(entry.get("files", {})), {}
        for rel, (mode, obj) in sorted(up["files"].items()):
            if picks[name] is not None and rel not in picks[name]:
                continue
            key = f"{name}/{rel}"
            if any(fnmatch.fnmatch(rel, g) for g in SET["ignore"]):
                continue
            if port_of(name, rel):
                files[rel] = entry.get("files", {}).get(rel, {"upstream": obj, "installed": None, "port": port_of(name, rel)["name"]})
                continue
            base = base_render(key, rel, blobs[obj], target, renames, st.tf)
            if base is None:
                continue
            current = read_installed(os.path.join(dst, rel))
            if current is None:
                st.set_file(key, {"transforms": [{"delete": True}], "accepted": []}, a.local)
                files.pop(rel, None)
                counts[rel] = "deleted"
                continue
            text = current.decode("utf-8")
            ts = hunks(base, text) if text != base else []
            rebuilt, stale = apply_file_transforms(base, ts)
            if stale or rebuilt != text:
                ts = [{"find": base, "replace": text}]  # whole-file fallback
            accepted = flatten(st.outstanding(text, [], own_agent(name, rel)))
            if ts or accepted:
                st.set_file(key, {"transforms": ts, "accepted": accepted}, a.local)
                counts[rel] = {"transforms": len(ts), "accepted": accepted, "home": "local" if a.local else "shared"}
            else:
                st.pop_file(key)
            files[rel] = {"upstream": obj, "installed": blob_sha(current)}
        for rel, f in entry.get("files", {}).items():
            if f.get("port") and rel not in up["files"]:
                files[rel] = f
        entry.update({"files": files, "transforms": st.skill_tf_hash(name, renames)})
        summary[target] = counts
    st.manifest["skills"] = st.managed
    save_json(st.manifest_path, st.manifest)
    save_json(st.transform_path, st.transforms)
    return {"recorded": summary}


def cmd_seed(a, st):
    """Write the pack's seeds: every harness block without its local sub-block, and this harness's
    shared profile. Local entries and the local profile never leave the install."""
    os.makedirs(os.path.join(a.out, "harness"), exist_ok=True)
    os.makedirs(os.path.join(a.out, "sets", SET["name"]), exist_ok=True)
    seed = {h: {k: v for k, v in block.items() if k != "local"} for h, block in st.transforms.items()}
    rel = os.path.join("sets", SET["name"], "transform.json")
    save_json(os.path.join(a.out, rel), seed)
    written = [rel]
    if st.profile_exists:
        shipped = read_text(os.path.join(st.repo, SELF, "harness", f"{st.harness}.md"))
        durable = read_text(st.profile_path)
        with open(os.path.join(a.out, "harness", f"{st.harness}.md"), "w") as f:
            f.write(compose_profile(shipped, durable))
        written.append(f"harness/{st.harness}.md")
    return {"seeded": written, "out": a.out, "local_entries_kept_back": sorted(st.local["files"])}


def cmd_status(a, st):
    def at_rev(path, default):
        """The file at --since, also looking where an install before sets kept it."""
        rel = os.path.relpath(path, st.discovery_root)
        candidates = [rel]
        if f"/sets/{SET['name']}/" in f"/{rel}" and SET["name"] == DEFAULT_SET:
            candidates.append(rel.replace(f"sets/{SET['name']}/", "", 1))
        for cand in candidates:
            r = subprocess.run(["git", "-C", st.discovery_root, "show", f"{a.since}:{cand}"], capture_output=True, text=True)
            if r.returncode == 0:
                return r.stdout
        return default

    old_m = json.loads(at_rev(st.manifest_path, '{"skills": {}}'))
    old_tf = json.loads(at_rev(st.transform_path, "{}")).get(a.harness, {}).get("files", {})
    old_profile = parse_profile(at_rev(st.profile_path, ""))
    old_s, new_s = norm_skills(old_m.get("skills", {})), st.managed
    new_tf = st.tf.get("files", {})
    dir_of = {**{k: v["dir"] for k, v in old_s.items()}, **{k: v["dir"] for k, v in new_s.items()}}

    def upstream_changed(key):
        name, rel = key.split("/", 1)
        o = old_s.get(name, {}).get("files", {}).get(rel, {}).get("upstream")
        n = new_s.get(name, {}).get("files", {}).get(rel, {}).get("upstream")
        return o != n

    def addressed(ts):
        """Needs whose markers an edit removes."""
        ids = set()
        for t in ts:
            if t.get("delete"):
                continue
            before, after = needs_in(t["find"], st.needs), needs_in(t["replace"], st.needs)
            ids |= {i for i, ms in before.items() if set(ms) - set(after.get(i, []))}
        return sorted(ids)

    def describe(key, ts):
        name, rel = key.split("/", 1)
        if any(t.get("delete") for t in ts):
            what = "file removed"
        else:
            what = "%d edit%s" % (len(ts), "" if len(ts) == 1 else "s")
        ids = addressed(ts)
        return f"{dir_of.get(name, name)}/{rel}: {what}" + (f" (needs: {', '.join(ids)})" if ids else "")

    groups = {"new": [], "changed": [], "replayed": [], "dropped": []}
    kept = 0
    for key in sorted(set(old_tf) | set(new_tf)):
        o, n = old_tf.get(key, {}).get("transforms", []), new_tf.get(key, {}).get("transforms", [])
        if key.split("/", 1)[0] not in new_s:
            continue
        if n and not o:
            groups["new"].append(describe(key, n))
        elif o and not n:
            groups["dropped"].append(describe(key, o))
        elif n and o != n:
            groups["changed"].append(describe(key, n))
        elif n and upstream_changed(key):
            groups["replayed"].append(describe(key, n))
        elif n:
            kept += 1

    added = sorted(new_s[k]["dir"] for k in set(new_s) - set(old_s))
    removed = sorted(old_s[k]["dir"] for k in set(old_s) - set(new_s))
    updated = []
    for k in sorted(set(new_s) & set(old_s)):
        if new_s[k].get("tree") != old_s[k].get("tree"):
            n = sum(1 for rel in new_s[k].get("files", {}) if upstream_changed(f"{k}/{rel}"))
            updated.append(f"{new_s[k]['dir']} ({n} file{'s' if n != 1 else ''})")

    pending, drift = [], []
    for k, e in sorted(new_s.items()):
        for rel, f in sorted(e.get("files", {}).items()):
            if f.get("pending"):
                p = f["pending"]
                bits = list(p.get("needs", {}))
                if p.get("stale_transforms"):
                    bits.append("stale transform")
                if p.get("dependencies"):
                    bits.append("hands off to newly installed " + ", ".join(p["dependencies"]))
                pending.append(f"{e['dir']}/{rel}: {', '.join(bits)}")
            cur = read_installed(os.path.join(st.repo, e["dir"], rel))
            if cur is not None and blob_sha(cur) != f.get("installed") and not f.get("port"):
                drift.append(f"{e['dir']}/{rel}")

    prof_new = sorted(i for i in st.profile if i not in old_profile)
    prof_changed = sorted(i for i in st.profile if i in old_profile and old_profile[i] != st.profile[i])

    out = [f"# {SET['name']} sync status ({a.harness})", ""]
    oc, nc = (old_m.get("commit") or "none")[:7], (st.manifest.get("commit") or "none")[:7]
    label = re.sub(r"^https?://github\.com/", "", SET["upstream"].rstrip("/"))
    out.append(f"Upstream {label}: {oc} -> {nc}" if oc != nc else f"Upstream {label}: {nc} (unchanged)")
    out.append(f"Harness facts: {st.discovery_key or 'none'} in {st.discovery_path}")
    out.append("")
    total = sum(len(v) for v in groups.values())
    counts = ", ".join(f"{len(groups[g])} {g}" for g in ("new", "changed", "replayed", "dropped") if groups[g])
    out.append(f"## Transforms: {total} file{'s' if total != 1 else ''} touched" + (f" ({counts})" if counts else "")
               + f", {kept} carried over unchanged")
    labels = {"new": "New adaptations", "changed": "Changed adaptations",
              "replayed": "Replayed onto new upstream text", "dropped": "Dropped adaptations"}
    for g in ("new", "changed", "replayed", "dropped"):
        if groups[g]:
            out.append(f"{labels[g]} ({len(groups[g])}):")
            out += [f"- {x}" for x in groups[g]]
    if not total:
        out.append("No transform changes.")
    out.append("")
    out.append("## Skills")
    for label, items in (("New", added), ("Updated upstream", updated), ("Removed", removed)):
        out.append(f"{label} ({len(items)}): " + (", ".join(items) if items else "none"))
    deps = [f"{e['dir']} from {e['source']}" for k, e in sorted(new_s.items())
            if e.get("source", f"{SUBDIR}/{k}") != f"{SUBDIR}/{k}"]
    deps += [f"{AGENTS}/{rel} from {src}" for rel, src in sorted(new_s.get(AGENTS, {}).get("sources", {}).items())]
    out.append("")
    out.append(f"## Dependencies ({len(deps)})")
    out += [f"- {x}" for x in deps] or ["None installed."]
    if prof_new or prof_changed:
        out.append("")
        out.append("## Harness profile")
        if prof_new:
            out.append("Needs mapped: " + ", ".join(f"{i} ({st.profile[i]})" for i in prof_new))
        if prof_changed:
            out.append("Support changed: " + ", ".join(f"{i} {old_profile[i]} -> {st.profile[i]}" for i in prof_changed))
    out.append("")
    out.append(f"## Outstanding ({len(pending)} file{'s need' if len(pending) != 1 else ' needs'} adaptation, {len(drift)} drifted)")
    out += [f"- {x}" for x in pending] or ["Nothing outstanding."]
    out += [f"- drift: {x}" for x in drift]
    print("\n".join(out))


# ---------- publish ----------

PACK_SKILLS = os.path.join("skills", "scoussens-skills")
PACK_MANIFEST = "pack-manifest.json"
MAX_PUBLISH_BYTES = 2 * 1024 * 1024  # the pack validator's limit; the skill index omits larger files


def run_git(cwd, *args, check=True):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"error: git {' '.join(args)} in {cwd}: {(r.stderr or r.stdout).strip()}")
    return r.stdout


def pack_label(remote):
    """owner/repo from a GitHub remote, for the commit subject; else the remote as written."""
    m = re.match(r"^(?:https?://github\.com/|git@github\.com:)([^/]+/[^/]+?)(?:\.git)?/?$", remote or "")
    return m.group(1) if m else remote


def pack_skill_files(pack, skill):
    """{rel: mode} for the files git tracks under one pack skill, without node_modules.
    Untracked scratch and anything the pack's .gitignore ignores are never listed."""
    prefix = f"{PACK_SKILLS}/{skill}/"
    files, skipped = {}, 0
    for line in run_git(pack, "ls-files", "-z", "-s", "--", prefix).split("\0"):
        if not line:
            continue
        meta, path = line.split("\t", 1)
        rel = path[len(prefix):]
        if "node_modules" in rel.split("/"):
            skipped += 1
            continue
        files[rel] = meta.split()[0]
    return files, skipped


def tree_blobs(path):
    """{rel: blob sha} of every file under a directory, the shape a copy is compared against."""
    out = {}
    for dp, _, fns in os.walk(path):
        for fn in fns:
            full = os.path.join(dp, fn)
            out[os.path.relpath(full, path)] = blob_sha(read_installed(full) or b"")
    return out


def copy_pack_files(source, files, dest):
    """Replace dest with the listed pack files; a merge would keep files the pack dropped."""
    shutil.rmtree(dest, ignore_errors=True)
    for rel, mode in sorted(files.items()):
        src = os.path.join(source, rel)
        dst = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if mode == "120000":
            os.symlink(os.readlink(src), dst)
        else:
            shutil.copy2(src, dst)
            os.chmod(dst, 0o755 if mode == "100755" else 0o644)


def pack_plugin_files(pack, harness):
    """Tracked files grouped by plugin name for the selected harness."""
    prefix = f"{PACK_SKILLS}/{SELF}/adapters/{harness}/plugin/"
    plugins = {}
    for line in run_git(pack, "ls-files", "-z", "-s", "--", prefix).split("\0"):
        if not line:
            continue
        meta, path = line.split("\t", 1)
        name, sep, rel = path[len(prefix):].partition("/")
        if sep:
            plugins.setdefault(name, {})[rel] = meta.split()[0]
    return prefix, dict(sorted(plugins.items()))


def publish_refusal(detail):
    sys.stderr.write(f"error: {detail}\n")
    sys.exit(2)


def plugin_preflight(pack, prefix, files, repo, dry_run, report):
    """Reject unsafe source files and removal targets before either destination changes."""
    offenders = {"node_modules": [], "oversized": []}
    for name, entries in files.items():
        for rel in entries:
            path = f"{name}/{rel}"
            if "node_modules" in path.split("/"):
                offenders["node_modules"].append(path)
            size = os.lstat(os.path.join(pack, prefix, path)).st_size
            if size > MAX_PUBLISH_BYTES:
                offenders["oversized"].append({"path": path, "bytes": size})
    if offenders["node_modules"] or offenders["oversized"]:
        report["plugins"]["refused"] = offenders
        print(json.dumps(report, indent=2))
        publish_refusal("refusing plugin files: " + json.dumps(offenders))
    manifest = os.path.join(STATE_DIR, PACK_MANIFEST)
    if dry_run:
        previous = run_git(repo, "show", f"HEAD:{manifest}", check=False)
    else:
        previous = read_text(os.path.join(repo, manifest))
    try:
        names = json.loads(previous).get("plugins", []) if previous else []
        if not isinstance(names, list):
            raise ValueError("plugins must be a list")
        for name in [*names, *files]:
            if (not isinstance(name, str) or not name or os.path.basename(name) != name
                    or name in (".", "..", ".git", STATE_DIR)):
                raise ValueError(f"unsafe plugin name: {name!r}")
    except (ValueError, AttributeError) as error:
        publish_refusal(f"invalid plugins manifest or source: {error}")
    for entry in run_git(repo, "ls-tree", "-z", "HEAD", "--", STATE_DIR, manifest, *names, *files).split("\0"):
        if not entry:
            continue
        meta, path = entry.split("\t", 1)
        allowed = ("100644", "100755") if path == manifest else ("040000",)
        if meta.split()[0] not in allowed:
            publish_refusal(f"{repo}/{path} must be a regular {'file' if path == manifest else 'directory'}")


def append_profile_rows(path, rows):
    """Append the seed's rows for needs the durable profile lacks; returns the ids appended."""
    text = read_text(path)
    have = parse_profile_rows(text)
    new = {i: r for i, r in rows.items() if i not in have}
    if new:
        if text and not text.endswith("\n"):
            text += "\n"
        with open(path, "w") as f:
            f.write(text + "".join(r + "\n" for r in new.values()))
    return sorted(new)


def publish_sync(work, harness, name):
    """cmd_sync for one set of the workspace's pack copy, as `sync --set name` would run it."""
    configure(load_set(work, name))
    a = argparse.Namespace(cmd="sync", harness=harness, repo=work, root=None, set=name, ref=SET["ref"], dry_run=False)
    return cmd_sync(a, State(work, harness)), SET["upstream"]


def merge_passes(first, second):
    """The second pass's report with the first pass's skill changes, which the second saw as unchanged."""
    updated = sorted((set(first["updated"]) | set(second["updated"])) - set(first["added"]))
    extra = len(set(updated) - set(first["updated"]))
    return {**second, "previous_commit": first["previous_commit"], "added": first["added"], "updated": updated,
            "removed": first["removed"], "unchanged_count": first["unchanged_count"] - extra,
            "seed_refreshed": first["seed_refreshed"], "seed_conflicts": first["seed_conflicts"]}


def set_summary(report, upstream):
    """The parts of a sync report the operator acts on; the full report is too long to publish."""
    deps = report["dependencies"]
    return {"upstream": upstream, "upstream_commit": report["upstream_commit"],
            "previous_commit": report["previous_commit"], "added": report["added"],
            "updated": report["updated"], "removed": report["removed"],
            "unchanged_count": report["unchanged_count"], "needs_adaptation": report["needs_adaptation"],
            "local_drift": report["local_drift"], "profile_gaps": report["profile_gaps"],
            "profile_gaps_in_seed": report["profile_gaps_in_seed"],
            "unresolved_dependencies": deps.get("unresolved", {}), "excluded_dependencies": deps.get("excluded", {}),
            "ambiguous_dependencies": deps.get("ambiguous", {}), "ports_pending": report["ports_pending"],
            "stale_ports": report["stale_ports"], "needs_security_review": report["needs_security_review"],
            "seed_refreshed": report["seed_refreshed"], "seed_conflicts": report["seed_conflicts"]}


def staged_offenders(work):
    """Staged additions and modifications the skill index would choke on."""
    out = {"node_modules": [], "oversized": []}
    for path in run_git(work, "diff", "--cached", "--name-only", "-z", "--diff-filter=AM").split("\0"):
        if not path:
            continue
        if "node_modules" in path.split("/"):
            out["node_modules"].append(path)
        size = os.lstat(os.path.join(work, path)).st_size
        if size > MAX_PUBLISH_BYTES:
            out["oversized"].append({"path": path, "bytes": size})
    return out if out["node_modules"] or out["oversized"] else None


def verify_index(names):
    """`amp skill info` for each name: found, missing, or why it could not be asked."""
    amp = shutil.which("amp")
    if not amp:
        return {"amp": None, "note": "amp is not on PATH; run `amp skill info <skill>` where it is", "skills": {}}
    out = {}
    for source, name in names.items():
        try:
            r = subprocess.run([amp, "skill", "info", name], capture_output=True, text=True, timeout=120)
            out[name] = {"source": source, "status": "found" if r.returncode == 0 else "missing",
                         "detail": (r.stdout if r.returncode == 0 else r.stderr or r.stdout).strip().splitlines()[:1]}
        except subprocess.TimeoutExpired:
            out[name] = {"source": source, "status": "timeout", "detail": []}
    return {"amp": amp, "note": "the index reads the pushed repository, so without --push this describes the previous publish",
            "skills": out}


def verify_plugins(names):
    """Read exact plugin headers from one `amp plugins list` invocation."""
    amp = shutil.which("amp")
    if not amp:
        return {"amp": None, "note": "amp is not on PATH; run `amp plugins list` where it is", "plugins": {}}
    try:
        result = subprocess.run([amp, "plugins", "list"], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return {"amp": amp, "plugins": {name: {"status": "timeout"} for name in names}}
    headers = {}
    for line in result.stdout.splitlines():
        line = re.sub(r"\x1b\[[0-9;]*m", "", line)
        match = re.fullmatch(r"\S+ ([^\s]+) \(Workspace Plugins\) (active|disabled|inactive)\s*", line)
        if match:
            headers[match[1]] = match[2]
    return {"amp": amp, "note": "the list reads loaded plugins, so without --push this describes the previous publish",
            "plugins": {name: {"status": headers.get(name, "missing") if result.returncode == 0 else "error"}
                        for name in names},
            "detail": (result.stderr or result.stdout).strip().splitlines()[:1] if result.returncode else []}


def publish_plugins_into(work, pack, prefix, files, a, report):
    """Replace carried plugins and retire only names from the plugins clone's manifest."""
    plugins = report["plugins"]
    manifest_path = os.path.join(work, STATE_DIR, PACK_MANIFEST)
    previous = load_json(manifest_path, {})
    for name, entries in files.items():
        dest = os.path.join(work, name)
        existed = os.path.isdir(dest)
        copy_pack_files(os.path.join(pack, prefix, name), entries, dest)
        if not existed:
            plugins["added"].append(name)
        elif run_git(work, "status", "--porcelain", "--", name).strip():
            plugins["updated"].append(name)
        else:
            plugins["unchanged_count"] += 1
    for name in previous.get("plugins", []):
        if name not in files and os.path.isdir(os.path.join(work, name)):
            shutil.rmtree(os.path.join(work, name))
            plugins["removed"].append(name)
    manifest = {"pack_commit": report["pack"]["commit"], "pack_remote": report["pack"]["remote"],
                "plugins": list(files)}
    if any(previous.get(key) != value for key, value in manifest.items()) or run_git(work, "status", "--porcelain").strip():
        manifest["published_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        save_json(manifest_path, manifest)
    run_git(work, "add", "-A", "--", ".")
    plugins["refused"] = staged_offenders(work)
    if plugins["refused"]:
        run_git(work, "reset", "-q")
        return
    plugins["status"] = "dry run" if a.dry_run else "published"
    if a.dry_run or not run_git(work, "diff", "--cached", "--name-only").strip():
        return
    label = pack_label(report["pack"]["remote"]) or os.path.basename(pack)
    run_git(work, "commit", "-q", "-m", f"Refresh workspace plugins from {label}@{report['pack']['short']}")
    plugins["committed"] = run_git(work, "rev-parse", "HEAD").strip()
    if a.push:
        run_git(work, "push", "origin", plugins["branch"])
        plugins["pushed"] = plugins["branch"]


def publish_into(work, pack, a, report):
    """The publish steps against one working tree; the caller decides whether that tree is the real one."""
    pack_dir = os.path.join(pack, PACK_SKILLS)
    state_dir = os.path.join(work, STATE_DIR)
    manifest_path = os.path.join(state_dir, PACK_MANIFEST)
    previous = load_json(manifest_path, {})
    names = sorted(d for d in os.listdir(pack_dir) if os.path.isfile(os.path.join(pack_dir, d, "SKILL.md")))
    if not names:
        sys.exit(f"error: no skills under {pack_dir}")
    sets = sorted(d for d in os.listdir(os.path.join(pack_dir, SELF, "sets"))
                  if os.path.isfile(os.path.join(pack_dir, SELF, "sets", d, "set.json"))) if SELF in names else []
    managed = set()
    for name in sets:
        m = load_json(os.path.join(state_dir, SELF, "sets", name, "manifest.json"), {"skills": {}})
        managed |= {v["dir"] for v in norm_skills(m["skills"]).values()}
    clash = sorted(set(names) & managed)
    if clash:
        sys.exit(f"error: the pack and a set both install {', '.join(clash)}; exclude one side first")

    skills = report["skills"]
    for name in names:
        files, skipped = pack_skill_files(pack, name)
        skills["skipped_node_modules_files"] += skipped
        if not files:
            sys.exit(f"error: git tracks nothing under {PACK_SKILLS}/{name} in {pack}")
        dest = os.path.join(work, name)
        before = tree_blobs(dest) if os.path.isdir(dest) else None
        copy_pack_files(os.path.join(pack, PACK_SKILLS, name), files, dest)
        if before is None:
            skills["added"].append(name)
        elif before != tree_blobs(dest):
            skills["updated"].append(name)
        else:
            skills["unchanged_count"] += 1
    for name in previous.get("skills", []):
        if name not in names and os.path.isdir(os.path.join(work, name)):
            shutil.rmtree(os.path.join(work, name))
            skills["removed"].append(name)

    gaps_appended = report["profile_rows_appended"]
    profile = os.path.join(state_dir, SELF, "harness", f"{a.harness}.md")
    passes = {}
    for name in sets:
        passes[name] = publish_sync(work, a.harness, name)
        appended = append_profile_rows(profile, passes[name][0]["profile_gaps_in_seed"])
        if appended:
            gaps_appended[name] = appended
    if gaps_appended:  # the profile is shared, and every set's transform hashes include its rows
        for name in sets:
            second, upstream = publish_sync(work, a.harness, name)
            passes[name] = (merge_passes(passes[name][0], second), upstream)
    for name, (out, upstream) in passes.items():
        report["sets"][name] = set_summary(out, upstream)
    for name, summary in report["sets"].items():
        for key in ("needs_adaptation", "local_drift", "profile_gaps", "unresolved_dependencies",
                    "excluded_dependencies", "ambiguous_dependencies", "ports_pending", "stale_ports", "seed_conflicts"):
            n = len(summary[key])
            if n:
                report["attention"].append(f"{name}: {n} {key.replace('_', ' ')}")

    manifest = {"pack_commit": report["pack"]["commit"], "pack_remote": report["pack"]["remote"],
                "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                "skills": names}
    os.makedirs(state_dir, exist_ok=True)
    changed = bool(run_git(work, "status", "--porcelain").strip())
    if changed or previous.get("skills") != names or previous.get("pack_remote") != manifest["pack_remote"]:
        save_json(manifest_path, manifest)
        report["manifest"] = manifest
    else:
        report["manifest"] = previous

    run_git(work, "add", "-A", "--", ".")
    staged = [p for p in run_git(work, "diff", "--cached", "--name-only", "-z").split("\0") if p]
    report["staged_files"] = len(staged)
    report["refused"] = staged_offenders(work)
    if report["refused"]:
        run_git(work, "reset", "-q")
        return
    label = pack_label(report["pack"]["remote"]) or os.path.basename(pack)
    lines = [f"Refresh workspace skills from {label}@{report['pack']['short']}", ""]
    for key in ("added", "updated", "removed"):
        lines.append(f"{key.capitalize()}: " + (", ".join(skills[key]) or "none"))
    for name, summary in report["sets"].items():
        u = re.sub(r"^https?://github\.com/", "", summary["upstream"].rstrip("/"))
        lines.append(f"Set {name}: {u}@{summary['upstream_commit'][:7]} "
                     f"(+{len(summary['added'])} ~{len(summary['updated'])} -{len(summary['removed'])})")
    report["commit_message"] = "\n".join(lines) + "\n"
    if not staged:
        return
    if a.dry_run:
        return
    subprocess.run(["git", "-C", work, "commit", "-q", "-F", "-"], input=report["commit_message"],
                   capture_output=True, text=True, check=True)
    report["committed"] = run_git(work, "rev-parse", "HEAD").strip()
    if a.push:
        run_git(work, "push", "origin", report["repo"]["branch"])
        report["pushed"] = report["repo"]["branch"]


def cmd_publish(a):
    pack, repo = os.path.abspath(a.pack), os.path.abspath(a.repo)
    plugins_repo = os.path.abspath(a.plugins_repo) if a.plugins_repo else None
    destinations = [repo] + ([plugins_repo] if plugins_repo else [])
    if plugins_repo:
        paths = [os.path.realpath(path) for path in [pack, *destinations]]
        for i, path in enumerate(paths):
            for other in paths[i + 1:]:
                if os.path.commonpath([path, other]) in (path, other):
                    publish_refusal(f"publish paths overlap: {path} and {other}")
    for path in [pack, *destinations]:
        if run_git(path, "rev-parse", "--is-inside-work-tree", check=False).strip() != "true":
            publish_refusal(f"{path} is not a git working tree")
        if not run_git(path, "rev-parse", "--verify", "HEAD", check=False).strip():
            publish_refusal(f"{path} has no committed HEAD")
        if plugins_repo and os.path.realpath(run_git(path, "rev-parse", "--show-toplevel").strip()) != os.path.realpath(path):
            publish_refusal(f"{path} is not the root of a git working tree")
    if not os.path.isdir(os.path.join(pack, PACK_SKILLS)):
        sys.exit(f"error: {pack} has no {PACK_SKILLS}/; pass the pack checkout as --pack")
    prefix, plugin_files = pack_plugin_files(pack, a.harness)
    remote = run_git(pack, "remote", "get-url", "origin", check=False).strip() or None
    branch = run_git(repo, "symbolic-ref", "--short", "-q", "HEAD", check=False).strip() or None
    report = {"command": "publish", "dry_run": a.dry_run,
              "pack": {"path": pack, "commit": run_git(pack, "rev-parse", "HEAD").strip(),
                       "short": run_git(pack, "rev-parse", "--short", "HEAD").strip(), "remote": remote,
                       "dirty": sorted(line[3:] for line in run_git(pack, "status", "--porcelain", "--untracked-files=no", "--", PACK_SKILLS).splitlines())},
              "repo": {"path": repo, "branch": branch, "head_before": run_git(repo, "rev-parse", "HEAD").strip()},
              "skills": {"added": [], "updated": [], "removed": [], "unchanged_count": 0, "skipped_node_modules_files": 0},
              "plugins": {"clone": plugins_repo, "carried": list(plugin_files), "status": "not published",
                          "added": [], "updated": [], "removed": [], "unchanged_count": 0,
                          "committed": None, "pushed": None, "verify": None, "refused": None},
              "sets": {}, "profile_rows_appended": {}, "attention": [], "manifest": None, "staged_files": 0,
              "refused": None, "commit_message": None, "committed": None, "pushed": None, "verify": None}
    if not a.dry_run:
        for path in destinations:
            dirty = run_git(path, "status", "--porcelain").strip()
            if dirty:
                publish_refusal(f"{path} has uncommitted changes; commit or stash them first:\n{dirty}")
            if a.push and not run_git(path, "symbolic-ref", "--short", "-q", "HEAD", check=False).strip():
                publish_refusal(f"{path} is not on a branch; --push needs one")
        if report["pack"]["dirty"]:
            publish_refusal(f"{pack} has uncommitted changes under {PACK_SKILLS}; the manifest would name a commit "
                            f"that is not what was copied:\n" + "\n".join(report["pack"]["dirty"]))
    if plugins_repo:
        report["plugins"]["branch"] = run_git(plugins_repo, "symbolic-ref", "--short", "-q", "HEAD", check=False).strip() or None
        plugin_preflight(pack, prefix, plugin_files, plugins_repo, a.dry_run, report)
    tmp = None
    worktrees = {}
    try:
        if a.dry_run:
            tmp = tempfile.mkdtemp(prefix="pstack-publish-")
            for i, path in enumerate(destinations):
                worktrees[path] = os.path.join(tmp, f"worktree-{i}")
                run_git(path, "worktree", "add", "-q", "--detach", worktrees[path], "HEAD")
        else:
            worktrees = {path: path for path in destinations}
        publish_into(worktrees[repo], pack, a, report)
        if plugins_repo and not report["refused"]:
            publish_plugins_into(worktrees[plugins_repo], pack, prefix, plugin_files, a, report)
    finally:
        if tmp:
            for path, work in worktrees.items():
                run_git(path, "worktree", "remove", "--force", work, check=False)
            shutil.rmtree(tmp, ignore_errors=True)
    if a.verify and not report["refused"] and not report["plugins"]["refused"]:
        picks = {"pack": report["manifest"]["skills"][0]} if report["manifest"]["skills"] else {}
        for name in report["sets"]:
            m = load_json(os.path.join(repo, STATE_DIR, SELF, "sets", name, "manifest.json"), {"skills": {}})
            dirs = sorted(v["dir"] for v in norm_skills(m["skills"]).values() if v["dir"] != AGENTS)
            if dirs:
                picks[name] = dirs[0]
        report["verify"] = verify_index(picks)
        if plugins_repo:
            report["plugins"]["verify"] = verify_plugins(plugin_files)
    print(json.dumps(report, indent=2))
    if report["plugins"]["refused"]:
        publish_refusal("refusing plugin files: " + json.dumps(report["plugins"]["refused"]))
    if report["refused"]:
        r = report["refused"]
        offenders = r["node_modules"] + [f"{o['path']} ({o['bytes'] / 1024 / 1024:.1f} MB)" for o in r["oversized"]]
        sys.stderr.write("error: refusing to commit; the skill index would omit or choke on:\n  "
                         + "\n  ".join(offenders) + "\nRemove or ignore them in the workspace and run publish again.\n")
        sys.exit(2)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("sync", "record", "status", "seed"):
        p = sub.add_parser(c)
        p.add_argument("--harness", required=True, help="agent harness the skills are adapted for, e.g. amp")
        p.add_argument("--repo", default=DEFAULT_REPO)
        p.add_argument("--root", help="repository holding .nthplusio-skills/; defaults to --repo's Git repository")
        p.add_argument("--set", default=DEFAULT_SET, help="the managed skill set, a directory under sets/ (default pstack)")
    sub.choices["sync"].add_argument("--ref", default=None, help="upstream ref; defaults to the set's ref")
    sub.choices["sync"].add_argument("--dry-run", action="store_true")
    sub.choices["record"].add_argument("skills", nargs="*")
    sub.choices["record"].add_argument("--all", action="store_true")
    sub.choices["record"].add_argument("--local", action="store_true",
                                       help="record under the local block, which seed never exports")
    sub.choices["seed"].add_argument("--out", required=True, help="directory to write transform.json and harness/ into")
    sub.choices["status"].add_argument("--since", default="HEAD")
    p = sub.add_parser("publish")
    p.add_argument("--harness", required=True, help="agent harness the skills are adapted for, e.g. amp")
    p.add_argument("--pack", required=True, help="checkout of the skills pack to copy from")
    p.add_argument("--repo", required=True, help="clone of the workspace skills repository to publish into")
    p.add_argument("--plugins-repo", help="clone of the workspace plugins repository to publish carried plugins into")
    p.add_argument("--push", action="store_true", help="push each destination's current branch to origin after committing")
    p.add_argument("--verify", action="store_true", help="ask `amp skill info` per source and `amp plugins list` for published plugins")
    p.add_argument("--dry-run", action="store_true", help="run in throwaway worktrees and leave the destinations untouched")
    a = ap.parse_args()
    if a.cmd == "publish":
        cmd_publish(a)
        return
    configure(load_set(os.path.abspath(a.repo), a.set))
    if getattr(a, "ref", None) is None and a.cmd == "sync":
        a.ref = SET["ref"]
    st = State(os.path.abspath(a.repo), a.harness, a.root)
    out = {"sync": cmd_sync, "record": cmd_record, "status": cmd_status, "seed": cmd_seed}[a.cmd](a, st)
    if out is not None:
        print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
