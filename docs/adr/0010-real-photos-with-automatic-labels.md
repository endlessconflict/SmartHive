# ADR-0010: Real photos with automatic labels before 3D rendering or diffusion

Status: Accepted
Date: 2026-10-06
Deciders: Adrien Cubilla, Diego Alejandro Vasquez
Refines: [ADR-0009](0009-procedural-insect-rendering.md) (adds a source of training images; procedural scenes stay)

## Context

After v0.2 the detector is above chance on real photos but far from the targets, and the main error is real wasps and bees called "hornet" ([results](../03-vision/07-results.md)). A proposal reached the team to replace the 2D compositor with a fuller pipeline:

1. 3D insect models rendered in Blender, scripted with `bpy`.
2. Domain randomization: HDRI lighting, wood textures, lens blur and dirt.
3. Bounding boxes exported automatically by the renderer.
4. A final pass through Stable Diffusion with ControlNet (depth or Canny) to make the renders look like real camera images.
5. Training a binarized neural network on the result.

We checked each step against what we already have, what the evidence says, and what our machine and rules allow.

| Step | Where we stand | Verdict |
|---|---|---|
| 2. Domain randomization | Already in the compositor: lighting with hood shade and vignetting, wood, painted and random-texture boards, defocus and motion blur, sensor noise, white balance error, JPEG | Done; keep extending it |
| 3. Automatic labels | Already exact, including occlusion and mite positions, because we draw the scene | Done |
| 1. Blender renders | `bpy` installs from PyPI here, so it is possible. But it needs a textured 3D model of each species, which we do not have and would take days per species to build. Our own evidence also argues against it: v0.1, trained on drawn insects only, was at chance on real photos (0.358 against 0.333), and the gain came from real appearance (v0.2). A render with made-up textures is closer to v0.1 than to v0.2 | Not now |
| 4. Diffusion with ControlNet | The usual Stable Diffusion checkpoints and their ControlNets are under OpenRAIL licenses, which are not OSI-approved, so they break the FOSS rule. Model downloads from Hugging Face are blocked here. On our 4-core CPU without a GPU one image would take on the order of a minute or more (estimate), so tens of thousands of images would take weeks. A Varroa mite is about 18 px in a full frame; a re-texturing pass can blur or invent mites, which corrupts the stage 2 labels | Not adopted |
| 5. Binarized network | Not part of our design. YOLO11n in ncnn fp16 already meets the latency budget on the Pi 3B (about 0.24 s estimated for stage 1). Binarized networks lose a lot of accuracy, and the small details (mites, hornet versus wasp) are exactly what we cannot afford to lose. If the on-device benchmark misses the budget, INT8 comes first | Not adopted |

The goal behind steps 1 and 4 is real appearance with labels nobody has to draw. There is a cheaper way to get exactly that.

## Decision

Add real photos with automatic labels to detector training (iteration v0.4):

- Photos: iNaturalist research-grade observations of the target taxa (CC0 and CC BY only), from pools that share no photo and no observation with the frozen tier P split.
- Class: the iNaturalist identification of the observation.
- Box: YOLOE with text prompts ("insect", "bee", "hornet", "wasp", ...), so nobody draws a box ([`vision/pseudolabel.py`](../../vision/pseudolabel.py)).
- Training mixes these photos with the procedural entrance scenes, which keep providing the top-down view, the scale, the board and the mites.

Blender stays an option if the team finds or builds openly licensed, textured insect models. Diffusion stays out while no OSI-licensed model runs on our hardware.

## Consequences

- Real appearance at almost no cost: about 4 photos per second on the CPU for labeling, no manual boxes.
- Labels are noisy. A visual check of 15 random labeled photos found 2 wrong boxes (a wild comb and a flower labeled "bee"), 1 partial box and 2 photos with insects left unboxed. Detectors tolerate this level of noise, but it is a ceiling.
- The photos are side views on flowers and hands, not the entrance from above. They teach what a hornet looks like, not how our camera sees it. Tier C backgrounds remain necessary.
- Photographers overlap between the training pools and tier P: a few prolific observers took most iNaturalist hornet photos. Photos and observations do not overlap, but the tier P numbers for v0.2 (whose cutouts come from the same pools) and v0.4 may be somewhat optimistic for that reason. An observer-disjoint test would leave 8 hornets, too few to measure.
- Every training photo keeps its license and attribution in the dataset manifest, and released models ship the list.
