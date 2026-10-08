"""Priority Nexus Transparency Ledger: an append-only public record of what was done, and when.

LEDGER.md holds one row per entry:  date | action | project | what | fingerprint | note | chain
  action       one of: Added, Edited, Corrected, Reviewed, Deleted, Published
  fingerprint  SHA-256 (first 12 characters) of the file or item the entry is about, or a commit id
  chain        SHA-256 (first 16) of the previous row's chain + this row, so changing or removing any past row
               breaks every chain value after it

Commands (Python 3 standard library only):
  python ledger.py add ACTION "WHAT" [--project P] [--file PATH] [--note TEXT]
  python ledger.py sync-git              add an entry for each new commit in the Priority Nexus GitHub repos
  python ledger.py sync-reports FOLDER   add a Reviewed entry for each report that passed the independent review
  python ledger.py verify                re-check every chain value; names the first broken row
  python ledger.py stats [YYYY-MM]       write the monthly summary to STATS/YYYY-MM.md
Rows are only ever appended. Mistakes are fixed by adding a Corrected row, never by editing an old one.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
from collections import Counter
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "LEDGER.md")
STATS = os.path.join(HERE, "STATS")
ACTIONS = ["Added", "Edited", "Corrected", "Reviewed", "Deleted", "Published"]
OWNER = "PriorityNexusLLC"
HEADER = ("# Transparency Ledger\n\n"
          "Everything Priority Nexus LLC adds, edits, corrects, reviews, deletes or publishes, in order. Rows are only "
          "ever added; a mistake is fixed by a new **Corrected** row, never by changing an old one. Each row's *chain* "
          "value is built from the row before it, so any change to history shows: run `python ledger.py verify`.\n\n"
          "| Date | Action | Project | What | Fingerprint | Note | Chain |\n"
          "|---|---|---|---|---|---|---|\n")
ROW = re.compile(r"^\| (\d{4}-\d{2}-\d{2}) \| (\w+) \| (.*?) \| (.*?) \| (.*?) \| (.*?) \| ([0-9a-f]{16}) \|$")


def clean(s):
    return re.sub(r"\s+", " ", str(s or "")).replace("|", "/").strip()[:180]


def rows():
    if not os.path.exists(LEDGER):
        return []
    out = []
    for line in open(LEDGER, encoding="utf-8"):
        m = ROW.match(line.rstrip("\n"))
        if m:
            out.append(m.groups())
    return out


def chain_of(prev, fields):
    return hashlib.sha256((prev + "|" + "|".join(fields)).encode("utf-8")).hexdigest()[:16]


def fingerprint_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def append(day, action, project, what, fp, note):
    if action not in ACTIONS:
        sys.exit(f"action must be one of {', '.join(ACTIONS)}")
    existing = rows()
    prev = existing[-1][6] if existing else "0" * 16
    fields = [day, action, clean(project), clean(what), clean(fp), clean(note)]
    c = chain_of(prev, fields)
    if not os.path.exists(LEDGER):
        open(LEDGER, "w", encoding="utf-8", newline="\n").write(HEADER)
    with open(LEDGER, "a", encoding="utf-8", newline="\n") as f:
        f.write("| " + " | ".join(fields + [c]) + " |\n")
    return c


def verify():
    prev, n = "0" * 16, 0
    for i, r in enumerate(rows(), 1):
        if chain_of(prev, list(r[:6])) != r[6]:
            print(f"BROKEN at row {i} ({r[0]} {r[1]} {r[3]}): this row or one before it was changed or removed")
            return 1
        prev, n = r[6], i
    print(f"ledger intact: {n} rows, every chain value checks out; latest chain {prev}")
    return 0


def api(path):
    req = urllib.request.Request("https://api.github.com/" + path, headers={"User-Agent": "PN-ledger",
                                                                          "Accept": "application/vnd.github+json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def sync_git():
    seen = {r[4] for r in rows()}
    new = []
    for repo in api(f"users/{OWNER}/repos?per_page=100"):
        commits = api(f"repos/{OWNER}/{repo['name']}/commits?per_page=100")
        for i, c in enumerate(reversed(commits)):
            sha = c["sha"][:12]
            if sha in seen:
                continue
            day = c["commit"]["committer"]["date"][:10]
            msg = c["commit"]["message"].splitlines()[0]
            low = msg.lower()
            action = "Added" if i == 0 else "Corrected" if re.search(r"\b(fix|correct|clarif|wrong|error|mistake)", low) \
                else "Deleted" if re.search(r"\b(delete|remove)", low) else "Edited"
            new.append((c["commit"]["committer"]["date"], day, action, repo["name"], msg, sha))
    for _, day, action, project, msg, sha in sorted(new):
        append(day, action, project, msg, sha, "GitHub commit")
    print(f"sync-git: {len(new)} new entries")


def sync_reports(folder):
    """Priority Nexus reports that went through the independent review: one Reviewed row each (titles only;
    the review's own fingerprint is the fingerprint)."""
    seen, n = {r[4] for r in rows()}, 0
    items = []
    for fn in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not fn.endswith(".json") or fn.startswith("auto_state"):
            continue
        try:
            sc = json.load(open(os.path.join(folder, fn), encoding="utf-8"))
        except ValueError:
            continue
        rv = sc.get("review") or {}
        if rv.get("state") != "done" or (rv.get("sha256") or "")[:12] in seen:
            continue
        items.append((rv.get("finished_at", "")[:10], sc.get("subject_label", sc.get("report_id")), rv))
    latest = {}                                       # one row per report subject per day (re-runs collapse)
    for day, label, rv in sorted(items, key=lambda x: (x[0], x[2].get("finished_at", ""))):
        latest[(day, label)] = (day, label, rv)
    # Unpublished reports are listed WITHOUT their subject: naming who is being examined before they've had a right of
    # reply would be unfair. The fingerprint proves later which report it was; the name appears in its Published row.
    already = {r[4] for r in rows()}
    items = [v for v in latest.values() if v[2]["sha256"][:12] not in already]
    for day, label, rv in sorted(items, key=lambda v: (v[0], v[2]["sha256"])):
        append(day or date.today().isoformat(), "Reviewed", "PNMaster-Graph", "Report (unpublished): independent second check",
               rv["sha256"][:12], f"{rv.get('verdict', '').split(':')[0]}; sources {rv.get('sources_ok')}/{rv.get('sources')} confirmed")
        n += 1
    print(f"sync-reports: {n} new entries")


def stats(month):
    rs = [r for r in rows() if r[0].startswith(month)]
    by_action = Counter(r[1] for r in rs)
    by_project = Counter(r[2] for r in rs)
    ok = verify() == 0
    L = [f"# Ledger summary: {datetime.strptime(month, '%Y-%m').strftime('%B %Y')}", "",
         f"**{len(rs)} entries** · chain intact: **{'yes' if ok else 'NO'}**", "",
         "| " + " | ".join(ACTIONS) + " |", "|" + "---|" * len(ACTIONS),
         "| " + " | ".join(str(by_action.get(a, 0)) for a in ACTIONS) + " |", ""]
    for kind, title in (("Corrected", "Corrections: our mistakes, fixed in the open"), ("Deleted", "Deletions")):
        items = [r for r in rs if r[1] == kind]
        L += [f"## {title} ({len(items)})", ""] + ([f"- {r[0]} · {r[2]} · {r[3]}" + (f" ({r[5]})" if r[5] else "")
                                                   for r in items] or ["- none"]) + [""]
    L += ["## By project", "", "| Project | Entries |", "|---|---|"] + [f"| {p} | {n} |" for p, n in by_project.most_common()]
    os.makedirs(STATS, exist_ok=True)
    path = os.path.join(STATS, f"{month}.md")
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
    print(f"stats: {path}")


def main():
    ap = argparse.ArgumentParser(description="Priority Nexus Transparency Ledger")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("action", choices=ACTIONS)
    a.add_argument("what")
    a.add_argument("--project", default="Priority Nexus LLC")
    a.add_argument("--file")
    a.add_argument("--note", default="")
    a.add_argument("--date", default=date.today().isoformat())
    sub.add_parser("sync-git")
    r = sub.add_parser("sync-reports")
    r.add_argument("folder")
    sub.add_parser("verify")
    s = sub.add_parser("stats")
    s.add_argument("month", nargs="?", default=date.today().strftime("%Y-%m"))
    x = ap.parse_args()
    if x.cmd == "add":
        fp = fingerprint_file(x.file) if x.file else hashlib.sha256(x.what.encode("utf-8")).hexdigest()[:12]
        print("added, chain", append(x.date, x.action, x.project, x.what, fp, x.note))
    elif x.cmd == "sync-git":
        sync_git()
    elif x.cmd == "sync-reports":
        sync_reports(x.folder)
    elif x.cmd == "verify":
        return verify()
    else:
        stats(x.month)
    return 0


if __name__ == "__main__":
    sys.exit(main())
