# Contributing to SmartHive

This file is for the six of us, and for anyone who picks the project up later. It is short on purpose. If a rule here gets in the way, propose a change in a pull request.

## Language

Everything in the repository is written in English: code, comments, commit messages, issues, pull requests and documentation. Meetings can be in Spanish; what gets written down is in English.

## Branches

- `main` is always in a state we could demo. Nobody pushes to it directly.
- Work happens on short-lived branches named `<area>/<short-description>`, for example `backend/mqtt-ingestor`, `vision/synthetic-compositor`, `docs/power-budget`.
- Areas: `edge`, `backend`, `vision`, `simulation`, `ml`, `frontend`, `infra`, `docs`, `hardware`.
- Rebase or merge `main` into your branch before asking for review, whichever you prefer. Do not rewrite history on a branch someone else is also working on.

## Commits

We use [Conventional Commits](https://www.conventionalcommits.org/) so the history is readable and changelogs can be generated later.

```text
feat(backend): store telemetry batches idempotently by msg_id
fix(edge): retry DHT11 read on checksum error
docs(vision): add camera resolution calculation
chore(infra): pin mosquitto to 2.0.x
```

Types we use: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`. The scope is the area name.

## Pull requests

- One topic per pull request. A 2,000-line PR that touches five areas will sit unreviewed.
- Fill in the template. Link the user story (`US07`) or issue it belongs to.
- At least one teammate approves before merge. For changes to a contract (MQTT topics, payload schemas, database schema, public API), the owner of the other side must approve too. Contracts are listed in [docs/05-backend/04-messaging-contract.md](docs/05-backend/04-messaging-contract.md).
- Squash-merge, so `main` gets one commit per PR with a Conventional Commit title.

## Definition of done

A user story is done when:

1. The code is merged into `main` and CI is green.
2. It has tests at the level that makes sense (unit tests for logic, a contract test for anything that crosses a component boundary).
3. The relevant document in `docs/` is updated. If the change contradicts a document, the document is fixed in the same PR.
4. It was shown working at the sprint review, on real hardware or on the simulator. Say which one.
5. Any number it reports says where it came from: real hive, team capture, public dataset or synthetic.

## Documentation

- Docs live in `docs/`, organized by area. Start from [docs/README.md](docs/README.md).
- One topic per file. If a file passes about 400 lines, split it.
- Diagrams are Mermaid inside the Markdown when possible, so they can be diffed. Images go in `docs/assets/<area>/`.
- Decisions that are expensive to reverse get an ADR in `docs/adr/`. Copy the [template](docs/adr/0000-template.md).
- Mark anything uncertain. "Estimated, to be measured in Sprint N" is better than a number that looks precise and is not.

## Code style (once code exists)

| Language | Formatter / linter | Types | Tests |
|---|---|---|---|
| Python 3.11+ | `ruff format`, `ruff check` | `mypy` (strict on `backend/` and `edge/`) | `pytest` |
| TypeScript | `prettier`, `eslint` | `tsc --strict` | `vitest` |
| SQL migrations | Alembic | | Applied in CI against a throwaway database |

## Data and models

- Never commit datasets, images in bulk or model weights to git. They go through DVC (see [docs/04-data/05-dataset-versioning-and-governance.md](docs/04-data/05-dataset-versioning-and-governance.md)).
- Every external asset (a photo, a texture, a 3D model, a dataset) gets an entry in the asset manifest with its source URL and license. If we cannot name the license, we do not use it.
- Generators take a seed. A dataset that cannot be regenerated from a config file and a seed is not finished.

## Secrets

Nothing secret goes into git: no passwords, API keys, private keys or `.env` files. Use `.env.example` with dummy values to document what a service needs.
