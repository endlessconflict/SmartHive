# Way of working

Status: Accepted

## Scrum setup

We run Scrum with two-week sprints.

| Ceremony | When | Length | Purpose |
|---|---|---|---|
| Sprint planning | First day of the sprint | 1 h | Pick stories from the backlog, split them into tasks, agree the sprint goal |
| Weekly sync | Once a week | 15 to 20 min | Progress and blockers. Not a status report to the Scrum Master |
| Sprint review | Last day of the sprint | 45 min | Demo what was finished. On hardware or on the simulator, and say which |
| Retrospective | After the review | 30 min | One thing to keep, one thing to change |

Tasks live on a shared board. GitHub Projects is a good fit because issues and pull requests link to cards automatically, and it is free for public repositories.

## The sprint goal is end to end

From the project plan risk register: integration failures discovered late are a high-impact risk. The mitigation is to freeze contracts early and run an end-to-end path from the second sprint of development onwards. In practice:

- Every sprint goal should be phrased as something that crosses the system, for example "a simulated node publishes temperature and it appears on the dashboard", not "finish the API".
- The simulator exists so this is possible before the hardware works.

## Backlog conventions

- User stories use the IDs from the [epics document](../01-requirements/epics-and-user-stories.md) (`US01` to `US22`). The earlier spreadsheet used a different numbering (`US1` to `US4`); the [backlog page](../01-requirements/backlog.md) maps them.
- Priority 1 is must-have for the demo, 2 is should-have, 3 is could-have.
- Technical work that is not user-visible (setting up CI, a benchmark) is an issue with the `spike` or `chore` label, linked to the story it unblocks.
- Research spikes are time-boxed and must end in a number or a decision. Use the issue template.

## Time tracking

The project plan reports hours per member per sprint. Keep doing it in the sprint review slide; it is useful for the course and it shows when one area is overloaded.

## Definition of done

See [CONTRIBUTING.md](../../CONTRIBUTING.md#definition-of-done). The short version: merged, tested, documented, demoed, and every metric labeled with where its data came from.
