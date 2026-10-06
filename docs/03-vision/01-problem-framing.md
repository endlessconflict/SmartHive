# Problem framing

Status: Proposed

## Goal

Detect pests and threats at the hive entrance from images taken periodically by a camera on the node, so the beekeeper gets an early warning and goes to check. The output supports a decision. It is not a diagnosis of infestation or disease.

## Classes

| Class ID | Name | Real size | Priority | Why it matters |
|---|---|---|---|---|
| 0 | `bee` | Worker about 12 to 15 mm long | Reference | Needed to count traffic, to crop for the Varroa classifier, and as the negative class |
| 1 | `hornet` | *Vespa velutina* worker, roughly 2 to 3 cm | 2 | Predator that hunts at the entrance |
| 2 | `shb` | *Aethina tumida*, 5 to 7 mm | 3 | Larvae destroy comb |
| 3 | `other_insect` | Varies | Distractor | Flies, wasps, ants, native hornets: things that are not bees and not our target pests |
| (stage 2) | `varroa` on a bee | Mite about 1.1 mm long and 1.6 mm wide | 1 | The main threat to honey bees; US09 |

Varroa is not a stage 1 class. At the resolution the detector runs at, a mite covers a handful of pixels. It is handled by a classifier on bee crops; see [model architecture](04-model-architecture.md).

`other_insect` exists because a detector that only knows "bee" and "pest" will call every fly a pest. Native hornets (*Vespa crabro* where present, and local wasps) belong here: the VespAI project (O'Shea-Wheller et al. 2024) highlighted the native hornet as the main false positive when detecting *V. velutina*.

The proposal's priority order (Varroa first, then beetles and hornets as data allows) is kept, with hornets ahead of beetles because hornets are larger and easier, so they make a better second milestone. EL-15 asks the client to confirm.

A note on geography: *Vespa velutina* is invasive in Europe and East Asia and is not known in Panama or Colombia. For a deployment there, the relevant "hornet" class is whatever predatory wasps hunt at local entrances. The class stays in the plan because the user stories ask for it, and because the pipeline is the same for any large wasp. This is worth raising with the client.

## What an entrance camera can and cannot see

### Varroa

Phoretic mites (adult mites riding on adult bees) are the only ones a camera can see. Mites in capped brood cells are invisible from outside.

Many phoretic mites ride on the underside of the bee's abdomen, partly hidden between segments. A camera looking down at the landing board sees only the mites on the back and the sides. So the camera gives an **index** that rises and falls with the infestation, not the infestation rate itself. Some research systems (for example Bjerge et al. 2019) build a tunnel that bees must walk through, with lighting and cameras set up for this purpose. The [camera document](02-camera-and-optics.md) discusses an entrance passage as an option.

Mites on flying bees are lost to motion blur. Detection works on bees walking on the board.

### Hornets and beetles

Hornets hover in front of the entrance and land briefly. They are large, so blur and resolution are less of a problem, but they may be partly out of frame.

Small hive beetles live mostly inside the hive. They appear at the entrance occasionally (when arriving or when chased out). Expect few positives in real use, which makes false positives the bigger risk for this class.

## What the system outputs

Per analyzed frame, internally:

```json
{
  "frame_id": "0190f5a2-...",
  "ts": "2026-10-06T14:03:21.412Z",
  "objects": [
    {"cls": "bee", "conf": 0.91, "box": [412, 230, 498, 301], "varroa_p": 0.07},
    {"cls": "bee", "conf": 0.88, "box": [640, 310, 721, 380], "varroa_p": 0.83},
    {"cls": "hornet", "conf": 0.76, "box": [90, 40, 260, 170]}
  ]
}
```

Per event, sent to the backend (the [messaging contract](../05-backend/04-messaging-contract.md) has the exact schema):

- `threat_detected` when a threat class passes the aggregation rule (for example, hornet in at least 3 of the last 10 analyzed frames, each above its threshold).
- A rolling **Varroa index**: bees classified as carrying a mite divided by bees classified, over a window (default 1 hour and 24 hours), with the number of bees it is based on. An index from 12 bees and one from 3,000 bees are very different things, and the dashboard must show both numbers.
- The best image of the event, uploaded separately.

## What "good" means

From the proposal: recall on threats matters most, because a missed threat means no alert. A false alarm costs the beekeeper a visit; a missed hornet attack can cost the colony. Still, a system that cries wolf every day gets ignored, so false alerts per day is tracked as carefully as recall. Proposed numeric targets are in [training and evaluation](05-training-and-evaluation.md#acceptance-criteria).

## Later: fusion with sensor data

Also from the proposal, and kept as a second stage: combine visual detections with anomalies in temperature, humidity, weight and (one day) sound to raise or lower the confidence of an alert. For example, a hornet detection on a day when afternoon weight gain collapses is more serious than one on a normal day. The telemetry simulator and the image generator share a clock and a colony state, so this fusion can be developed on synthetic data as well. It is in the [roadmap](../roadmap.md), not in Prototype 1.
