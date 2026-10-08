"""Priority Nexus Transparency Ledger.

Every project repository keeps its OWN append-only ledger (LEDGER.md in that repo). This repository holds the tool,
the company-wide ledger, and the MONTHLY REPORT that rolls all project ledgers up.

A ledger row:  | date | action | what | fingerprint | note | chain |
  action       Added, Edited, Corrected, Reviewed, Deleted, Published
  fingerprint  first 12 characters of the SHA-256 of the file, commit or report the row is about
  chain        first 16 characters of SHA-256(previous row's chain + this row): changing or removing any past
               row breaks every later chain value
Rows are only ever appended. A mistake is fixed by a new Corrected row, never by editing an old one.

Commands (Python 3, standard library only):
  python ledger.py verify LEDGER.md [more ledgers...]      check every chain value; names the first broken row
  python ledger.py add LEDGER.md ACTION "WHAT" [--file PATH] [--note TEXT]
  python ledger.py monthly                                 the 1st-of-the-month run (see below)
  python ledger.py report YYYY-MM                          write the monthly report from all project ledgers

monthly: for every Priority Nexus repository, record its new commits (and, for PNMaster-Graph, reviewed reports) in
that repository's own LEDGER.md and upload once; then write last month's report here and upload once.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
OWNER = "PriorityNexusLLC"
CENTRAL = os.path.basename(HERE)                            # this repository (the company-wide ledger + reports)
WORK = os.path.join(os.path.dirname(HERE), "PriorityNexus-repos")   # local copies of the project repositories
REPORTS_DIR = os.path.join(os.path.expanduser("~"), "PriorityNexus", "data", "reports")
GIT = r"C:\Program Files\Git\cmd\git.exe" if os.name == "nt" else "git"
ACTIONS = ["Added", "Edited", "Corrected", "Reviewed", "Deleted", "Published"]
LEDGER_COMMIT = "Ledger:"                                   # the ledger's own uploads are never recorded as work
ROW = re.compile(r"^\| (\d{4}-\d{2}-\d{2}) \| (\w+) \| (?:(.*?) \| )?(.*?) \| (.*?) \| (.*?) \| ([0-9a-f]{16}) \|$")


def header(project):
    return (f"# Ledger: {project}\n\n"
            "Append-only record of what was added, edited, corrected, reviewed, deleted or published in this project. "
            "Rows are only ever added; each row's chain value is built from the row before it, so any change to "
            f"history shows. Verify with [`ledger.py`](https://github.com/{OWNER}/{CENTRAL}): "
            "`python ledger.py verify LEDGER.md`. Monthly reports for all projects: "
            f"[{OWNER}/{CENTRAL}](https://github.com/{OWNER}/{CENTRAL}/tree/main/STATS).\n\n"
            "| Date | Action | What | Fingerprint | Note | Chain |\n|---|---|---|---|---|---|\n")


def clean(s):
    return re.sub(r"\s+", " ", str(s or "")).replace("|", "/").strip()[:180]


def rows(path):
    """(date, action, what, fingerprint, note, chain); also reads the older 7-column rows (with a project column)."""
    out = []
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            m = ROW.match(line.rstrip("\n"))
            if m:
                d, a, proj, what, fp, note, c = m.groups()
                out.append((d, a, proj, what, fp, note, c))
    return out


def _fields(r):
    return [x for x in (r[0], r[1], r[2], r[3], r[4], r[5]) if x is not None]


def chain_of(prev, fields):
    return hashlib.sha256((prev + "|" + "|".join(fields)).encode("utf-8")).hexdigest()[:16]


def append(path, project, day, action, what, fp, note):
    if action not in ACTIONS:
        sys.exit(f"action must be one of {', '.join(ACTIONS)}")
    existing = rows(path)
    prev = existing[-1][6] if existing else "0" * 16
    fields = [day, action] + ([clean(project)] if existing and existing[-1][2] is not None else []) + \
             [clean(what), clean(fp), clean(note)]          # keep a ledger's original column layout
    c = chain_of(prev, fields)
    if not existing and (not os.path.exists(path) or not open(path, encoding="utf-8").read().strip()):
        open(path, "w", encoding="utf-8", newline="\n").write(header(project))
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write("| " + " | ".join(fields + [c]) + " |\n")
    return c


def verify(path, quiet=False):
    prev, n = "0" * 16, 0
    for i, r in enumerate(rows(path), 1):
        if chain_of(prev, _fields(r)) != r[6]:
            if not quiet:
                print(f"{path}: BROKEN at row {i} ({r[0]} {r[1]} {r[3]}): this row or one before it was changed or removed")
            return False, i
        prev, n = r[6], i
    if not quiet:
        print(f"{path}: intact, {n} rows, latest chain {prev}")
    return True, n


def fingerprint_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def api(path):
    req = urllib.request.Request("https://api.github.com/" + path, headers={"User-Agent": "PN-ledger",
                                                                          "Accept": "application/vnd.github+json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def git(repo, *a, check=True):
    return subprocess.run([GIT, "-C", repo, *a], capture_output=True, text=True, check=check)


def classify(msg, first):
    low = msg.lower()
    if first:
        return "Added"
    if re.search(r"\b(fix|fixed|correct|corrected|clarif\w*|wrong|error|mistake)", low):
        return "Corrected"
    if re.search(r"\b(delete|deleted|remove|removed)\b", low):
        return "Deleted"
    if re.search(r"\b(publish|published|release)\b", low):
        return "Published"
    return "Edited"


def record_commits(path, project, repo_name):
    seen = {r[4] for r in rows(path)}
    commits = list(reversed(api(f"repos/{OWNER}/{repo_name}/commits?per_page=100")))
    n = 0
    for i, c in enumerate(commits):
        msg = c["commit"]["message"].splitlines()[0]
        if msg.startswith(LEDGER_COMMIT) or c["sha"][:12] in seen:
            continue
        append(path, project, c["commit"]["committer"]["date"][:10], classify(msg, i == 0), msg, c["sha"][:12], "commit")
        n += 1
    return n


def record_reviews(path, project):
    """PNMaster-Graph reports that passed the independent review. Unpublished reports are listed WITHOUT their subject,
    so no one is named before they've had a right of reply; the fingerprint proves later which report it was."""
    if not os.path.isdir(REPORTS_DIR):
        return 0
    seen, latest = {r[4] for r in rows(path)}, {}
    for fn in sorted(os.listdir(REPORTS_DIR)):
        if not fn.endswith(".json") or fn.startswith("auto_state"):
            continue
        try:
            sc = json.load(open(os.path.join(REPORTS_DIR, fn), encoding="utf-8"))
        except ValueError:
            continue
        rv = sc.get("review") or {}
        if rv.get("state") == "done" and rv.get("sha256"):
            latest[(rv.get("finished_at", "")[:10], sc.get("subject"))] = rv
    n = 0
    for (day, _), rv in sorted(latest.items(), key=lambda kv: (kv[0][0], kv[1]["sha256"])):
        if rv["sha256"][:12] in seen:
            continue
        append(path, project, day, "Reviewed", "Report (unpublished): independent second check", rv["sha256"][:12],
               f"{rv.get('verdict', '').split(':')[0]}; sources {rv.get('sources_ok')}/{rv.get('sources')} confirmed")
        n += 1
    return n


KNOWN_DIRS = {"PriorityNexusLLC": "PriorityNexusLLC-profile"}   # repos that already have a working copy in Documents


def repo_dir(name):
    """The existing working copy in Documents if there is one, else a copy under PriorityNexus-repos."""
    d = os.path.join(os.path.dirname(HERE), KNOWN_DIRS.get(name, name))
    return d if os.path.isdir(os.path.join(d, ".git")) else os.path.join(WORK, name)


def local_copy(name):
    os.makedirs(WORK, exist_ok=True)
    d = repo_dir(name)
    if os.path.isdir(os.path.join(d, ".git")):
        git(d, "pull", "-q", "--ff-only")
    else:
        subprocess.run([GIT, "clone", "-q", f"https://github.com/{OWNER}/{name}.git", d], check=True)
        git(d, "config", "user.name", "Priority Nexus LLC")
        git(d, "config", "user.email", "282703525+PriorityNexusLLC@users.noreply.github.com")
    return d


def upload(repo_dir, message):
    git(repo_dir, "add", "LEDGER.md", *(["STATS"] if os.path.isdir(os.path.join(repo_dir, "STATS")) else []))
    if git(repo_dir, "diff", "--cached", "--quiet", check=False).returncode == 0:
        return False
    git(repo_dir, "commit", "-q", "-m", message)
    git(repo_dir, "push", "-q")
    return True


def project_ledgers():
    """(project name, path to its LEDGER.md) for every project, including this central one."""
    out = [(CENTRAL, os.path.join(HERE, "LEDGER.md"))]
    for r in sorted(api(f"users/{OWNER}/repos?per_page=100"), key=lambda r: r["name"].lower()):
        if r["name"] != CENTRAL:
            out.append((r["name"], os.path.join(repo_dir(r["name"]), "LEDGER.md")))
    return out


def monthly(upload_now=True):
    last = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    for name, path in project_ledgers()[1:]:
        d = local_copy(name)
        n = record_commits(path, name, name) + (record_reviews(path, name) if name == "PNMaster-Graph" else 0)
        ok, rws = verify(path, quiet=True)
        if not ok:
            print(f"{name}: chain broken, nothing uploaded for this project")
            continue
        sent = upload(d, f"{LEDGER_COMMIT} record through {date.today().isoformat()}") if upload_now else False
        print(f"{name}: {n} new rows · {rws} total · {'uploaded' if sent else 'no upload needed'}")
    report(last)
    if upload_now:
        upload(HERE, f"{LEDGER_COMMIT} {last} monthly report")


def report(month):
    title = datetime.strptime(month, "%Y-%m").strftime("%B %Y")
    total, sections, overall = Counter(), [], []
    for name, path in project_ledgers():
        rs = [r for r in rows(path) if r[0].startswith(month)]
        if name == CENTRAL:          # its pre-2026-10-08 combined rows are counted once, in each project's own ledger
            rs = [r for r in rs if r[2] in (None, CENTRAL, "Priority Nexus LLC")]
        ok, n = verify(path, quiet=True)
        overall.append((name, len(rs), ok))
        c = Counter(r[1] for r in rs)
        total.update(c)
        if not rs:
            continue
        lines = [f"### {name}", "", " · ".join(f"{a} {c[a]}" for a in ACTIONS if c[a]) + f" · chain {'intact' if ok else 'BROKEN'}", ""]
        for kind in ("Corrected", "Deleted", "Published"):
            for r in [r for r in rs if r[1] == kind]:
                lines.append(f"- **{kind}** {r[0]}: {r[3]}" + (f" ({r[5]})" if r[5] and r[5] != "commit" else ""))
        sections.append("\n".join(lines))
    if month == date.today().strftime("%Y-%m"):
        title += " (month in progress; the final report is published on the 1st)"
    L = [f"# Monthly report: {title}", "",
         f"All Priority Nexus projects, from each project's own ledger. **{sum(total.values())} entries** across "
         f"**{sum(1 for _, k, _ in overall if k)} projects** · every chain intact: "
         f"**{'yes' if all(ok for _, _, ok in overall) else 'NO'}**", "",
         "| " + " | ".join(ACTIONS) + " |", "|" + "---|" * len(ACTIONS),
         "| " + " | ".join(str(total.get(a, 0)) for a in ACTIONS) + " |", "",
         "Corrections, deletions and publications are listed by name: we own our mistakes. Routine edits are counted only.", "",
         "## By project", ""] + (sections or ["No activity this month."]) + ["",
         "## Ledger check", "", "| Project | Entries this month | Chain |", "|---|---|---|"] + \
        [f"| [{n}](https://github.com/{OWNER}/{n}/blob/main/LEDGER.md) | {k} | {'intact' if ok else 'BROKEN'} |" for n, k, ok in overall]
    os.makedirs(os.path.join(HERE, "STATS"), exist_ok=True)
    p = os.path.join(HERE, "STATS", f"{month}.md")
    open(p, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
    print(f"report: {p}")


def main():
    ap = argparse.ArgumentParser(description="Priority Nexus Transparency Ledger")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("ledgers", nargs="+")
    a = sub.add_parser("add")
    a.add_argument("ledger")
    a.add_argument("action", choices=ACTIONS)
    a.add_argument("what")
    a.add_argument("--file")
    a.add_argument("--note", default="")
    a.add_argument("--date", default=date.today().isoformat())
    m = sub.add_parser("monthly")
    m.add_argument("--no-upload", action="store_true")
    r = sub.add_parser("report")
    r.add_argument("month", nargs="?", default=date.today().strftime("%Y-%m"))
    x = ap.parse_args()
    if x.cmd == "verify":
        return 0 if all(verify(p)[0] for p in x.ledgers) else 1
    if x.cmd == "add":
        fp = fingerprint_file(x.file) if x.file else hashlib.sha256(x.what.encode("utf-8")).hexdigest()[:12]
        project = os.path.basename(os.path.dirname(os.path.abspath(x.ledger)))
        print("added, chain", append(x.ledger, project, x.date, x.action, x.what, fp, x.note))
    elif x.cmd == "monthly":
        monthly(upload_now=not x.no_upload)
    else:
        report(x.month)
    return 0


if __name__ == "__main__":
    sys.exit(main())
