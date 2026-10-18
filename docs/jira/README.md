# Jira

Status: Ready to import

Everything needed to set up the SmartHive project in Jira and keep it in sync with the repository.

| File | What it is |
|---|---|
| [`backlog.yaml`](backlog.yaml) | Single source of truth: sprints, components, epics, stories, tasks, sub-tasks, acceptance criteria, estimates, owners, dependencies, status |
| [`build.py`](build.py) | Generates the two files below and checks the YAML (unknown epic, person, sprint or dependency; non-Fibonacci points) |
| [`jira-import.csv`](jira-import.csv) | For Jira's CSV importer. Epics, stories, tasks, sub-tasks and "blocks" links in one file |
| [`backlog.md`](backlog.md) | The same backlog, readable on GitHub: sprint totals, load per person, every story with its criteria and sub-tasks |

```bash
python docs/jira/build.py     # after every edit to backlog.yaml
```

> **Note on the live project.** The real Jira key is `SCRUM`, not `SH`, and the sprints are S1 to S8 (S4 is Oct 19 to Nov 1, S8 is Dec 14 to 20). `backlog.yaml` still uses the names SH Sprint 3 to SH Sprint 10. From US07 on, Jira story numbers run one behind the repository IDs. The backend epic (SCRUM-81) exists only in Jira; its plan is in [`docs/05-backend/09-backend-plan.md`](../05-backend/09-backend-plan.md).

## Project setup (once)

1. Create a **Scrum** project, key `SH`, name SmartHive. A company-managed project gives the most control over fields; a team-managed one also works (see notes below).
2. Components: `edge`, `backend`, `vision`, `simulation`, `ml`, `frontend`, `infra`, `hardware`, `docs` (descriptions in `backlog.yaml`).
3. Make sure these fields are on the Story, Task and Sub-task screens: Story Points (or Story point estimate), Sprint, Components, Labels, Original Estimate.
4. Create the sprints listed in `backlog.yaml` (SH Sprint 3 to SH Sprint 10) on the board, with the same names. The importer can then assign issues to them by name.
5. Invite the six members so the importer can map the Assignee names to accounts.

## Import

Jira settings > System > External system import > CSV (or, in a project, ... > Import issues from CSV).

| CSV column | Map to | Notes |
|---|---|---|
| Issue ID | Issue Id | Internal number used only to link parents and dependencies during the import |
| Parent ID | Parent Id | Links sub-tasks to their story and, in current Jira Cloud, stories to their epic |
| Issue Type | Issue Type | Epic, Story, Task, Sub-task |
| Summary | Summary | Stories start with their repository ID, for example `[US09]`, so commits and PRs can reference them |
| Description | Description | Jira wiki markup: user story, acceptance criteria, design documents, evidence, blockers, definition of done |
| Priority | Priority | Highest, High, Medium, Low |
| Status | Status | To Do, In Progress, Done. Map to your workflow's statuses |
| Assignee | Assignee | Map each name to the member's account in the value-mapping step |
| Component (x2) | Component/s | |
| Labels (x3) | Labels | |
| Story Points | Story Points / Story point estimate | Fibonacci: 1, 2, 3, 5, 8, 13 |
| Sprint | Sprint | Must match an existing sprint name |
| Epic Name | Epic Name | Only on epics. Needed by older company-managed projects |
| Epic Link | Epic Link | Older company-managed projects only. Skip it if Parent ID already links stories to epics |
| Original Estimate | Original Estimate | In seconds, as the importer expects (8 h = 28800). Story estimate = sum of its sub-tasks |
| Outward issue link (Blocks) (x3) | Link "Blocks" | This issue blocks the listed Issue IDs |

Check the preview, run the import, and then check one epic, one story with sub-tasks and one blocked story by hand.

Team-managed projects have no Epic Name or Epic Link. Map only Parent ID, and use "Story point estimate" for points.

## Conventions

| Item | Rule |
|---|---|
| Keys | Jira assigns `SH-n`. The summary keeps the repository ID (`US09`, `EN-03`, `HW-01`, `PM-02`) so both can be searched |
| Story points | Relative effort, Fibonacci. 13 means "split it before the sprint starts" |
| Sub-task estimates | Hours. They are what the time-tracking report uses |
| Labels | Lowercase, hyphenated: `synthetic-data`, `varroa`, `alerts`... |
| Commits and PRs | Mention the Jira key and the repository ID: `feat(vision): stage 2 training (SH-42, US09)` |
| Definition of done | [CONTRIBUTING.md](../../CONTRIBUTING.md#definition-of-done). A story is not done while any acceptance criterion is unmet. Partial progress stays "In Progress" with sub-tasks marked |
| Data tier | Every story that reports a metric names its tier (S, P, C, F) in the sprint review |

## Keeping Jira and the repository in sync

The YAML is reviewed like code. For sprint planning, edit the YAML (sprint, assignee, points), regenerate, and update the same issues in Jira by hand or with a re-import that updates existing issues (map Issue ID to the existing key). During the sprint, Jira is where status changes happen. At the sprint review, copy final statuses back into the YAML so the repository keeps an honest record.

## Epics at a glance

| Epic | Owner | Content |
|---|---|---|
| E1 Sensor node & IoT connectivity | Ricardo | Camera choice, DHT11, load cell, store-and-forward, TLS, offline alerts |
| E2 Pest & threat detection | Adrien | Capture, relevance filter, Varroa, hornet/SHB, edge execution, notifications |
| E3 Colony dashboard | Maria | History, alert log, latest image, anomaly warnings |
| E4 Honey flow & yield (optional) | Diego | 7-day yield range, weather, super and harvest recommendations |
| E5 Synthetic data platform | Diego | Telemetry simulator, procedural renderer, compositor, real check set, MQTT replay, DVC |
| E6 Backend platform & DevOps | James | Message contract, Compose stack, CI |
| E7 Project foundations | Adrien | Docs, ADRs, client interview, consistency fixes |

The full list, with acceptance criteria and sub-tasks, is in [backlog.md](backlog.md).
