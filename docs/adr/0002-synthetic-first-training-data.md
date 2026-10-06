# ADR-0002: Synthetic-first training data

Status: Proposed
Date: 2026-10-06
Deciders: Adrien Cubilla (PO), Diego Alejandro Vasquez, James Tack

## Context

The client will not provide historical hive data, labeled audio or images, and none exists in a usable form. The pest detector, the anomaly detector and the yield model all need labeled data. Public datasets exist for some vision classes but differ from our camera setup, have mixed licenses, and do not cover small hive beetles or long weight series with labeled events in a tropical climate. Waiting a season to collect our own data is outside the project's timeframe, and some events (swarms, absconding, Varroa infestations) cannot be produced on demand.

## Decision

1. All models are trained on data produced by our own generators: a mechanistic hive telemetry simulator driven by real historical weather, and a 2D compositor that pastes license-checked real insect photos onto real photos of our entrance board, following our camera's geometry and noise.
2. Public real datasets and team captures are used to validate and test, not to train the headline models. Test splits are frozen before anyone looks at them.
3. Every reported metric names its data tier: synthetic (S), public real (P), team capture (C), field (F).
4. Generators are versioned, seeded and deterministic; datasets carry a card and an asset license manifest.

Details: [data strategy](../04-data/01-data-problem-and-strategy.md), [synthetic image pipeline](../03-vision/03-synthetic-image-pipeline.md).

## Alternatives considered

| Option | Why not |
|---|---|
| Public datasets as the training source | Domain mismatch, license restrictions (NC, GPL, unclear), missing classes. Kept as the yardstick instead |
| Learned generators (GANs, TimeGAN, tabular synthesizers) | They imitate a real dataset; we have none to imitate. SDV is also no longer open source |
| Diffusion-generated images as the main source | Heavy compute, license issues with most checkpoints, labels can drift. Kept as an optional refinement |
| Collect real data only | Too slow, and rare events cannot be scheduled |

## Consequences

- Data generation becomes a component with its own code, tests and owner.
- The backend and dashboard get a simulator for free, which removes the dependency on hardware arriving.
- The main technical risk becomes the sim-to-real gap. We manage it with domain randomization, real backgrounds and cutouts, and a strict evaluation protocol, and we report it openly.
- Claims at the end of the project are limited by the size of the real test sets. We will say so.
