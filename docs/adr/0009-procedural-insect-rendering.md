# ADR-0009: Procedural insect rendering instead of photo cutouts

Status: Accepted
Date: 2026-10-06
Deciders: Adrien Cubilla, Diego Alejandro Vasquez
Refines: [ADR-0002](0002-synthetic-first-training-data.md) (how the synthetic images are made; the synthetic-first decision itself stands)

## Context

ADR-0002 planned to build training images by cutting insects out of openly licensed photos and pasting them onto real backgrounds. Building it showed three problems:

- Most public image sources (Zenodo, Hugging Face, Kaggle, Roboflow, Wikimedia) are blocked by the network policy of the environment where the generators run. The iNaturalist Open Dataset on AWS is reachable, but it is our only real yardstick, and using the same photos for cutouts and for testing would contaminate the test.
- Every photo cutout carries its own license and attribution, which follows the dataset everywhere it goes.
- Segmenting thousands of insects needs a segmentation model and a person to check each mask.

## Decision

Draw every insect with code. A generic segmented-insect renderer (head, thorax, waist, abdomen with bands, shading, gloss, hair, wings, legs, antennae), driven by per-species parameter samplers, produces bees (including darker Africanized bees, pollen loads and 0 to 3 Varroa mites), hornets, small hive beetles and distractors at their physical size. Boards, stains and debris are procedural too.

The iNaturalist photos stay out of training and serve as the tier P check. Real backgrounds from our own camera (tier C) replace procedural boards as soon as the camera is mounted, and real-photo cutouts from the iNaturalist calibration split (never the test split) remain an option if the appearance gap stays large.

## Alternatives considered

| Option | Why not, now |
|---|---|
| Photo cutouts (ADR-0002 plan) | Sources blocked here; license bookkeeping; contaminates the only real test set |
| 3D models in Blender/BlenderProc | Needs licensed 3D insect models or modeling time; slow CPU rendering. Kept as an option |
| Diffusion-generated insects | Large GPU models, license limits on most checkpoints, labels can drift. Kept as an option for backgrounds only |

## Consequences

- Generated datasets have no third-party license and can be published under whatever license the team picks.
- Exact physical scale and exact labels, including mite positions and occlusion.
- The appearance gap between drawn and real insects is the main risk. It is measured on every iteration with the iNaturalist test (see [results](../03-vision/07-results.md)), and the renderer is the first thing to improve when it is large.
