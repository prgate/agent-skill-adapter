"""Port-check real skill repos against the committed environment descriptions."""
import collections, json, pathlib, sys, yaml
from agent_skill_adapter.envspec.loader import select, capability, base_specs

# Directory holding the clones of mattpocock-skills and superpowers; override with argv[1].
ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "clones")
SPECS = pathlib.Path("specs")

cc = select(SPECS, "anthropic", "claude-code", "2.1.0", allow_stale=True)
ag = select(SPECS, "google", "antigravity", "2.0.0", allow_stale=True)
# What Claude Code says includes what the open specification it extends says: by declaring
# `extends` it owes those entries whether or not its own description repeats them.
cc_bases = base_specs(cc, SPECS, allow_stale=True)
report = json.loads((SPECS / "gaps/claude-code-to-antigravity.json").read_text())
origin = {}
def walk(o):
    if isinstance(o, dict):
        if "id" in o and "outcome" in o: origin[o["id"]] = o
        for v in o.values(): walk(v)
    elif isinstance(o, list):
        for v in o: walk(v)
walk(report)

def says(spec, fid, bases=()):
    """What one description says about a feature id, across both lists it can live in.

    `capability()` reads `capabilities` alone and answers `unknown` for anything else, which
    would report a place the description does document as though it were silent. A layout
    entry carries no support value: naming the place is the whole statement. `bases` are the
    descriptions `spec` extends, so an entry it inherits rather than repeats is not read as
    silence either.
    """
    for held, label in [(spec, None), *((b, "inherited") for b in bases)]:
        if any(e.id == fid for e in held.capabilities):
            return label or capability(held, fid).value
        if any(e.id == fid for e in held.layout):
            return label or "documented"
    return "-"


def frontmatter(p):
    t = p.read_text(encoding="utf-8", errors="replace")
    if not t.startswith("---"): return {}
    end = t.find("\n---", 3)
    if end < 0: return {}
    d = yaml.safe_load(t[3:end])
    return d if isinstance(d, dict) else {}

used = collections.Counter()          # feature id -> how many skills use it
carriers = collections.defaultdict(list)
unmapped = collections.Counter()

for repo in ("mattpocock-skills", "superpowers"):
    base = ROOT / repo
    for p in sorted(base.rglob("SKILL.md")):
        if ".git" in p.parts: continue
        who = f"{repo}/{p.parent.name}"
        for k in frontmatter(p):
            fid = f"skill.frontmatter.{k}"
            used[fid] += 1; carriers[fid].append(who)
        for d in sorted(p.parent.iterdir()):
            if not d.is_dir(): continue
            # The four the specification names, plus the two Antigravity names instead.
            fid = {"scripts": "skill.dir.scripts", "references": "skill.dir.references",
                   "assets": "skill.dir.assets", "examples": "skill.dir.examples",
                   "resources": "skill.dir.resources"}.get(d.name)
            if fid: used[fid] += 1; carriers[fid].append(who)
            else: unmapped[f"<skill>/{d.name}/"] += 1; carriers[f"<skill>/{d.name}/"].append(who)
    for h in sorted(base.rglob("hooks*.json")):
        if ".git" in h.parts: continue
        try: data = json.loads(h.read_text())
        except Exception: continue
        for event in (data.get("hooks") or {}):
            fid = f"hook.event.{event}"
            used[fid] += 1; carriers[fid].append(f"{repo}/{h.relative_to(base)}")

rows = []
for fid, n in used.most_common():
    e = origin.get(fid, {})
    rows.append((fid, n, says(cc, fid, cc_bases), says(ag, fid),
                 e.get("outcome", "-"), e.get("origin", "-")))

w = max(len(r[0]) for r in rows) + 2
print(f"{'feature used by real skills':{w}}{'skills':>7}  {'claude-code':12}{'antigravity':12}{'outcome':11}origin")
for fid, n, s, t, o, org in rows:
    print(f"{fid:{w}}{n:>7}  {s:12}{t:12}{o:11}{org}")
print()
print("bundled dirs with no entry in either description:")
for k, n in unmapped.most_common():
    print(f"  {k:24}{n:>4}  e.g. {carriers[k][0]}")
print()
blockers = [r for r in rows if r[3] not in ("supported", "documented")]
print(f"features real skills use that Antigravity does not document as supported: {len(blockers)}")
for fid, n, s, t, o, org in blockers:
    print(f"  {fid} ({t}, {org}) — {n} carrier(s): {', '.join(sorted(set(carriers[fid]))[:4])}")
