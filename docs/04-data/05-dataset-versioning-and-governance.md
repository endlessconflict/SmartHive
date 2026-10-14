# Dataset versioning and governance

Status: Partly implemented. Dataset IDs, cards, seeds and the frozen real split are in use; DVC is initialized with a placeholder remote and training runs log dataset ID, generator commit and seed; MLflow is not set up yet (Jira EN-06)

Owners: Adrien Cubilla (images), Diego Alejandro Vasquez (telemetry), Maria de los Angeles Agudelo (storage and CI)

Synthetic data is cheap to produce, which makes it easy to lose track of. Six people generating datasets with slightly different configs, training on whichever was on their laptop, and reporting numbers nobody can reproduce: this page exists to prevent that.

## Tools

| Need | Tool | License | Why |
|---|---|---|---|
| Version large files next to git | DVC | Apache-2.0 | Files stay out of git; git holds small pointer files; any commit can restore its exact data |
| Remote storage for DVC | A shared folder on the gateway PC (SSH remote), or any free storage the team already has | | No budget. DVC supports SSH, local folders, Google Drive and S3-compatible storage |
| Experiment tracking | MLflow (self-hosted, file backend) | Apache-2.0 | Links each trained model to its dataset version, config and metrics |
| Browsing image datasets | FiftyOne | Apache-2.0 | Look at samples, filter by label, compare synthetic and real side by side |
| Labeling and review of real images (tiers C and F) | Label Studio or CVAT | Apache-2.0 / MIT | For the few real images we annotate by hand |

## Dataset identity

A dataset is identified by:

```text
<tier>-<domain>-<name>-v<major>.<minor>-s<seed>
```

Examples: `S-telemetry-panama_baseline-v1.0-s42`, `S-images-entrance_composite-v0.3-s7`, `P-images-varroadataset-v1.0`.

- Major version changes when the format changes (a column is renamed, a class is added).
- Minor version changes when the generator changes behavior with the same format.
- Seed identifies one draw from a generator version.

## Dataset card

Every dataset folder contains a `DATASET_CARD.md`:

```markdown
# S-images-entrance_composite-v0.3-s7

Tier: S (synthetic)
Generator: simulation/images/compositor @ git 3f2a1c9, config configs/entrance_v03.yaml, seed 7
Size: 20,000 images, 1640x1232, YOLO and COCO labels
Classes and counts: bee 312,450 | bee_varroa 9,870 | hornet 2,104 | shb 1,950 | other_insect 4,402
Intended use: training stage 1 detector and stage 2 classifier
Not intended for: reporting real-world performance
Assets used: see assets.lock (152 cutouts, 40 backgrounds, licenses CC0/CC BY 4.0)
Known gaps: no night images; no rain on the lens; varroa only on dorsal thorax and abdomen
```

## Asset manifest

The image generator v0.1 uses no external files at all (everything is procedural), so its datasets need no asset manifest. The tier P real photos are listed with license, source URL and observer in [`vision/splits/P-inat-v1.tsv`](../../vision/splits/P-inat-v1.tsv). The rules below apply as soon as any external file (a team photo, a texture, a cutout) enters a generator.

Every external file used by a generator (insect photo, cutout, texture, 3D model, background) is listed in `simulation/images/assets/manifest.csv`:

| Column | Example |
|---|---|
| `asset_id` | `cut-shb-0012` |
| `kind` | `cutout`, `background`, `texture`, `model3d`, `dataset` |
| `class` | `shb` |
| `source_url` | Link to the original page (not the file) |
| `author` | As credited by the source |
| `license` | SPDX identifier: `CC0-1.0`, `CC-BY-4.0`, `CC-BY-SA-4.0`... |
| `derived_from` | Parent asset if this is a cutout or edit |
| `added_by`, `added_on` | |
| `notes` | Anything that limits use |

Rules:

- No license, no use.
- `CC-BY-NC-*` and `CC-BY-ND-*` assets are excluded from generators. They can be used for evaluation only.
- `CC-BY-SA-*` assets make derived datasets share-alike. Keep them in a separate pool so a dataset's license stays clear.
- The generator writes an `assets.lock` with the exact assets each dataset used, and an `ATTRIBUTION.md` built from the manifest.

## Storage layout

```text
data/                         (git-ignored, DVC-tracked)
├── raw/                      Downloaded public datasets, untouched
├── assets/                   Cutouts, backgrounds, textures
├── sim/                      Generated datasets, one folder per dataset ID
├── captures/                 Tier C and F recordings from the team and the prototype
└── splits/                   Frozen split definitions with checksums
```

## Real test splits are frozen

Public (tier P) and field (tier F) test splits are defined once, as lists of file hashes, committed to git. CI checks that no training config references a file in a test split. The splits are opened for evaluation only after a model is frozen for a milestone, and each opening is logged in the experiment tracker.

## Reproducibility check

A dataset is "released" (allowed in a report or a demo) when:

1. Its card and `assets.lock` exist.
2. Regenerating it from the recorded commit, config and seed gives identical checksums.
3. It passes the generator's stylized-fact tests.
