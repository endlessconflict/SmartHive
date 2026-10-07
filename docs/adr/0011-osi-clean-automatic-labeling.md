# ADR-0011: Automatic labeling with OSI-licensed weights only

Status: Accepted
Date: 2026-10-07
Deciders: Adrien Cubilla, Diego Alejandro Vasquez
Refines: [ADR-0010](0010-real-photos-with-automatic-labels.md) (how the automatic boxes are made)

## Context

From v0.2 to v0.4, real-photo cutouts and automatic boxes came from YOLOE with **text prompts** ("insect", "bee", "hornet", ...). A text prompt is turned into an embedding by a text encoder that YOLOE downloads on first use: Apple's MobileCLIP (`mobileclip_blt.ts`; newer Ultralytics releases use MobileCLIP2). Apple's code is MIT, but the model weights are under the "Apple Machine Learning Research Model License" (`LICENSE_MODELS` in `apple/ml-mobileclip`): use limited to non-commercial research, no product development. That is not an OSI license, so running it broke the project's FOSS rule, even though our use (a university research project) was within its terms.

The released v0.2 and v0.4 models are AGPL weights trained on boxes that tool produced. We keep them for comparison, but from v0.5 on no step of the pipeline runs a non-OSI model.

Alternatives checked (October 2026):

| Option | License of weights | Reachable here | Notes |
|---|---|---|---|
| YOLOE text prompts | AGPL + Apple research-only encoder | Yes | Breaks the rule |
| YOLOE prompt-free (`-pf`) checkpoints | AGPL, own vocabulary, no text encoder | Yes (GitHub) | Finds 82 % of Open Images' human-boxed bees at IoU 0.5, but names them "squid", "wood duck", "pitcher plant": boxes good, names useless |
| SAM 3 | SAM License, not OSI | No (Hugging Face) | |
| Grounding DINO, OWLv2, Florence-2 | Apache/MIT | No (weights or text model on Hugging Face) | |
| BioCLIP 2 (as species check) | MIT | No (Hugging Face) | |

## Decision

Boxes come from **prompt-free YOLOE-26l proposals** (class-agnostic), filtered by our own **insectness classifier**, a YOLO26n-cls trained on:

- insect: Open Images V7 human bee boxes (CC BY 4.0 annotations on CC BY 2.0 Flickr images) and procedural hornets, wasps, flies, ants and beetles pasted on real background patches;
- background: prompt-free boxes in the same photos that overlap no bee.

The species still comes from the iNaturalist identification. Masks for cutouts still come from SAM 2.1 (Apache-2.0). The labeler is scored against Open Images human boxes on images kept out of its training ([`vision/labeler.py`](../../vision/labeler.py)).

## Consequences

- Every weight file used to make v0.5 data is AGPL-3.0 or Apache-2.0, and the labeler's quality is measured instead of eyeballed.
- One more model to train (minutes on the CPU) and one more stage in the labeling pipeline.
- `mobileclip_blt.ts` is deleted from the build machine and must not be downloaded again; code no longer calls YOLOE text prompts.
- v0.2 and v0.4 stay in the repository as historical releases with this note in their model cards.
