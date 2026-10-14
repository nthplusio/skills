#!/usr/bin/env python3
"""Sync pstack skills from github.com/cursor/plugins (pstack/skills), and the skills and subagent
definitions they hand off to, into a skills directory.

  sync.py sync   --harness NAME [--repo DIR] [--root DIR] [--ref BRANCH] [--dry-run]
  sync.py record --harness NAME [--repo DIR] [--root DIR] (SKILL | SKILL/FILE ... | --all)
  sync.py status --harness NAME [--repo DIR] [--root DIR] [--since REV]

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

Harness facts (owned by harness-discovery, not pstack-sync):
  .nthplusio-skills/discovery.json at the root of the Git repository holding --repo, or
                        at --root. NAME matches a saved key or its slug. A need is
                        profiled once every field it names is discovered; null means
                        the harness has no such operation.
"""
import argparse, difflib, fnmatch, hashlib, json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO = os.path.dirname(os.path.dirname(HERE))
SELF = "pstack-sync"
DEFAULT_SET = "pstack"
SET_DEFAULTS = {"ref": "main", "plugin_marker": ".cursor-plugin/plugin.json", "dialect": "cursor",
                "agents_dir": None, "collision_prefix": None, "extra_needs": [], "ports": []}


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


def configure(cfg):
    """Point the module at one set. PSTACK_SYNC_UPSTREAM overrides the upstream URL for tests."""
    global SET, UPSTREAM, ROOT_PLUGIN, SUBDIR, AGENTS, PREFIX, PLUGIN_MARKER, CACHE
    SET = cfg
    UPSTREAM = os.environ.get("PSTACK_SYNC_UPSTREAM") or cfg["upstream"]
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
    git("fetch", "-q", "--depth", "1", "origin", ref)
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
        self.profile_path = os.path.join(self.durable, "harness", f"{harness}.md")
        self.manifest = load_json(self.manifest_path, {"skills": {}})
        self.transforms = load_json(self.transform_path, {})
        self.shared = self.transforms.setdefault(harness, {"accept": [], "global": [], "files": {}})
        self.shared.setdefault("files", {})
        self.local = self.shared.setdefault("local", {"accept": [], "global": [], "files": {}})
        for k, v in (("accept", []), ("global", []), ("files", {})):
            self.local.setdefault(k, type(v)())
        self.managed = norm_skills(self.manifest["skills"])
        self.exclude = set(self.manifest.get("exclude", []))
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
        self.foreign = (skills | self.other_sets_dirs()) - managed_dirs - {SELF}
        self.handoff_need = next((n["id"] for n in self.needs if n.get("detect") == "unavailable"), None)
        self.command_markers = [p for n in self.needs if n["id"] != self.handoff_need for p in n["markers"]]
        self.inv, self.available = None, set()

    def other_sets_dirs(self):
        """Directories the other sets in this install manage. To this set they are unmanaged
        skills, so a dependency one set installed shows as existing to another."""
        sets_dir = os.path.join(self.durable, "sets")
        dirs = set()
        for name in os.listdir(sets_dir) if os.path.isdir(sets_dir) else []:
            if name == SET["name"]:
                continue
            manifest = load_json(os.path.join(sets_dir, name, "manifest.json"), {"skills": {}})
            dirs |= {v["dir"] for v in norm_skills(manifest["skills"]).values()}
        return dirs

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


# ---------- commands ----------

def cmd_sync(a, st):
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
              "ports_pending": {}, "stale_ports": {}}
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
        if (not harness_changed and entry.get("tree") == up["tree"]
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

        if os.path.isdir(dst):  # files present locally but gone upstream
            for dp, _, fns in os.walk(dst):
                for fn in fns:
                    rel = os.path.relpath(os.path.join(dp, fn), dst)
                    if rel not in up["files"]:
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
                       "harness": a.harness, "exclude": sorted(st.exclude), "skills": new_skills}
        save_json(st.manifest_path, st.manifest)
        save_json(st.transform_path, st.transforms)
    print(json.dumps(report, indent=2))


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
        extra = [r for r in extra if r not in up["files"]]
        if extra:
            sys.exit(f"error: {target} has files not in upstream: {extra}")
        files, counts = dict(entry.get("files", {})), {}
        for rel, (mode, obj) in sorted(up["files"].items()):
            if picks[name] is not None and rel not in picks[name]:
                continue
            key = f"{name}/{rel}"
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
        entry.update({"files": files, "transforms": st.skill_tf_hash(name, renames)})
        summary[target] = counts
    st.manifest["skills"] = st.managed
    save_json(st.manifest_path, st.manifest)
    save_json(st.transform_path, st.transforms)
    print(json.dumps({"recorded": summary}, indent=2))


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
        shutil.copy2(st.profile_path, os.path.join(a.out, "harness", f"{st.harness}.md"))
        written.append(f"harness/{st.harness}.md")
    print(json.dumps({"seeded": written, "out": a.out,
                      "local_entries_kept_back": sorted(st.local["files"])}, indent=2))


def cmd_status(a, st):
    def at_rev(path, default):
        rel = os.path.relpath(path, st.discovery_root)
        r = subprocess.run(["git", "-C", st.discovery_root, "show", f"{a.since}:{rel}"], capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else default

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


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("sync", "record", "status", "seed"):
        p = sub.add_parser(c)
        p.add_argument("--harness", required=True, help="agent harness the skills are adapted for, e.g. amp")
        p.add_argument("--repo", default=DEFAULT_REPO)
        p.add_argument("--root", help="repository holding .nthplusio-skills/; defaults to --repo's Git repository")
        p.add_argument("--set", default=DEFAULT_SET, help="the managed skill set, a directory under sets/ (default pstack)")
    sub.choices["sync"].add_argument("--ref", default="main")
    sub.choices["sync"].add_argument("--dry-run", action="store_true")
    sub.choices["record"].add_argument("skills", nargs="*")
    sub.choices["record"].add_argument("--all", action="store_true")
    sub.choices["record"].add_argument("--local", action="store_true",
                                       help="record under the local block, which seed never exports")
    sub.choices["seed"].add_argument("--out", required=True, help="directory to write transform.json and harness/ into")
    sub.choices["status"].add_argument("--since", default="HEAD")
    a = ap.parse_args()
    configure(load_set(os.path.abspath(a.repo), a.set))
    st = State(os.path.abspath(a.repo), a.harness, a.root)
    {"sync": cmd_sync, "record": cmd_record, "status": cmd_status, "seed": cmd_seed}[a.cmd](a, st)


if __name__ == "__main__":
    main()
