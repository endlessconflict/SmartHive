"""Generate jira-import.csv and backlog.md from backlog.yaml.

    python docs/jira/build.py
"""
import csv
from collections import defaultdict
from pathlib import Path

import yaml

HERE = Path(__file__).parent
B = yaml.safe_load((HERE / "backlog.yaml").read_text())
REPO, PEOPLE = B["repo"], B["people"]
EPIC = {e["id"]: e for e in B["epics"]}
STORY = {s["id"]: s for s in B["stories"]}


VISION = "https://github.com/endlessconflict/SmartHive-Vision/blob/main"  # files that moved with the vision split


def url(path):
    """`vision:docs/x.md` lives in the SmartHive-Vision repository, anything else in this one."""
    return f"{VISION}/{path[7:]}" if path.startswith("vision:") else f"{REPO}/{path}"


def md_link(path):
    return f"[{path}]({url(path)})" if path.startswith("vision:") else f"[{path}](../../{path})"


def link(path):
    return f"[{path}|{url(path)}]"


def wiki(s):
    out = [f"h3. User story\n{s['story']}", "h3. Acceptance criteria\n" + "\n".join(f"# {a}" for a in s["ac"])]
    if s.get("docs"):
        out.append("h3. Design documents\n" + "\n".join(f"* {link(d)}" for d in s["docs"]))
    if s.get("evidence"):
        out.append("h3. Evidence (done)\n" + "\n".join(f"* {link(d)}" for d in s["evidence"]))
    if s.get("blocked_by"):
        out.append("h3. Blocked by\n" + ", ".join(s["blocked_by"]))
    out.append(f"h3. Definition of done\nSee {link('CONTRIBUTING.md')} (merged, tested, documented, demoed, data tier named).")
    return "\n\n".join(out)


def rows():
    ids, n = {}, 1
    for key in [e["id"] for e in B["epics"]] + list(STORY):
        ids[key], n = n, n + 1
    blocks = defaultdict(list)
    for s in B["stories"]:
        for b in s.get("blocked_by", []):
            blocks[b].append(s["id"])
    out = []
    for e in B["epics"]:
        out.append({"Issue ID": ids[e["id"]], "Issue Type": "Epic", "Summary": e["name"], "Epic Name": e["name"],
                    "Description": e["description"] + "\n\nh3. Design documents\n" + "\n".join(f"* {link(d)}" for d in e["docs"]),
                    "Priority": "High", "Status": "In Progress", "Assignee": PEOPLE[e["owner"]], "Component": [e["component"]],
                    "Labels": ["smarthive"]})
    for s in B["stories"]:
        hours = sum(t["hours"] for t in s.get("subtasks", []))
        out.append({"Issue ID": ids[s["id"]], "Parent ID": ids[s["epic"]], "Issue Type": s.get("type", "Story"),
                    "Summary": f"[{s['id']}] {s['summary']}", "Description": wiki(s), "Priority": s["priority"],
                    "Status": s["status"], "Assignee": PEOPLE[s["assignee"]], "Component": s["components"][:2],
                    "Labels": s["labels"][:3], "Story Points": s["points"], "Sprint": s["sprint"],
                    "Epic Link": EPIC[s["epic"]]["name"], "Original Estimate": hours * 3600,
                    "Blocks": [ids[x] for x in blocks.get(s["id"], [])]})
        for k, t in enumerate(s.get("subtasks", []), 1):
            n += 1
            out.append({"Issue ID": n, "Parent ID": ids[s["id"]], "Issue Type": "Sub-task",
                        "Summary": f"[{s['id']}.{k}] {t['summary']}",
                        "Description": f"Sub-task of {s['id']}: {s['summary']}.", "Priority": s["priority"],
                        "Status": t["status"], "Assignee": PEOPLE[t["assignee"]], "Component": s["components"][:1],
                        "Labels": s["labels"][:1], "Sprint": s["sprint"], "Original Estimate": t["hours"] * 3600})
    return out


def write_csv(rs):
    cols = ["Issue ID", "Parent ID", "Issue Type", "Summary", "Description", "Priority", "Status", "Assignee",
            "Component", "Component", "Labels", "Labels", "Labels", "Story Points", "Sprint", "Epic Name", "Epic Link",
            "Original Estimate", "Outward issue link (Blocks)", "Outward issue link (Blocks)", "Outward issue link (Blocks)"]
    with open(HERE / "jira-import.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rs:
            comp, lab, blk = (r.get("Component") or []) + ["", ""], (r.get("Labels") or []) + ["", "", ""], (r.get("Blocks") or []) + ["", "", ""]
            w.writerow([r.get("Issue ID"), r.get("Parent ID", ""), r["Issue Type"], r["Summary"], r["Description"],
                        r["Priority"], r["Status"], r["Assignee"], comp[0], comp[1], lab[0], lab[1], lab[2],
                        r.get("Story Points", ""), r.get("Sprint", ""), r.get("Epic Name", ""), r.get("Epic Link", ""),
                        r.get("Original Estimate", ""), blk[0], blk[1], blk[2]])


def write_md():
    L = ["# SmartHive backlog (generated)", "",
         "Generated from [`backlog.yaml`](backlog.yaml) by `python docs/jira/build.py`. Edit the YAML, not this file.", ""]
    total = sum(s["points"] for s in B["stories"])
    done = sum(s["points"] for s in B["stories"] if s["status"] == "Done")
    L += [f"{len(B['stories'])} stories and tasks, {sum(len(s.get('subtasks', [])) for s in B['stories'])} sub-tasks, "
          f"{total} story points ({done} done).", "", "## Sprints", "",
          "| Sprint | Dates | Goal | Points | Done |", "|---|---|---|---|---|"]
    for sp in B["sprints"]:
        ss = [s for s in B["stories"] if s["sprint"] == sp["name"]]
        L.append(f"| {sp['name']} | {sp['start']} to {sp['end']} | {sp['goal']} | {sum(s['points'] for s in ss)} | "
                 f"{sum(s['points'] for s in ss if s['status'] == 'Done')} |")
    L += ["", "## Load per person and sprint (story points)", "",
          "| Person | " + " | ".join(sp["name"].replace("SH ", "") for sp in B["sprints"]) + " |",
          "|---|" + "---|" * len(B["sprints"])]
    for p, name in PEOPLE.items():
        L.append(f"| {name} | " + " | ".join(str(sum(s["points"] for s in B["stories"] if s["assignee"] == p and s["sprint"] == sp["name"]) or "")
                                           for sp in B["sprints"]) + " |")
    for e in B["epics"]:
        ss = [s for s in B["stories"] if s["epic"] == e["id"]]
        L += ["", f"## {e['id']} {e['name']}", "", e["description"], "",
              f"Owner: {PEOPLE[e['owner']]}. Component: `{e['component']}`.", "",
              "| ID | Type | Summary | Pts | Sprint | Assignee | Status |", "|---|---|---|---|---|---|---|"]
        for s in ss:
            L.append(f"| [{s['id']}](#{s['id'].lower()}) | {s.get('type', 'Story')} | {s['summary']} | {s['points']} | "
                     f"{s['sprint'].replace('SH ', '')} | {PEOPLE[s['assignee']]} | {s['status']} |")
        for s in ss:
            L += ["", f"### {s['id']}", "", f"**{s['summary']}** ({s.get('type', 'Story')}, {s['priority']}, {s['points']} pts, "
                  f"{s['sprint']}, {PEOPLE[s['assignee']]}, {s['status']})", "", f"> {s['story']}", "",
                  "Acceptance criteria:", ""] + [f"{k}. {a}" for k, a in enumerate(s["ac"], 1)]
            if s.get("blocked_by"):
                L += ["", "Blocked by: " + ", ".join(f"[{b}](#{b.lower()})" for b in s["blocked_by"])]
            if s.get("docs"):
                L += ["", "Design: " + ", ".join(md_link(d) for d in s["docs"])]
            if s.get("evidence"):
                L += ["", "Evidence: " + ", ".join(md_link(d) for d in s["evidence"])]
            if s.get("subtasks"):
                L += ["", "| Sub-task | Assignee | Hours | Status |", "|---|---|---|---|"]
                L += [f"| {s['id']}.{k} {t['summary']} | {PEOPLE[t['assignee']]} | {t['hours']} | {t['status']} |"
                      for k, t in enumerate(s["subtasks"], 1)]
    (HERE / "backlog.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    for s in B["stories"]:  # cheap integrity checks before writing anything
        assert s["epic"] in EPIC and s["assignee"] in PEOPLE, s["id"]
        assert all(b in STORY for b in s.get("blocked_by", [])), s["id"]
        assert s["sprint"] in {sp["name"] for sp in B["sprints"]}, s["id"]
        assert s["points"] in (1, 2, 3, 5, 8, 13), s["id"]
    rs = rows()
    write_csv(rs)
    write_md()
    print(f"{len(rs)} issues -> jira-import.csv, backlog.md")
