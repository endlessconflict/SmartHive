# Camera and optics

Status: Proposed. Feeds the camera selection, which is still open.

Owners: Adrien Cubilla, Ricardo Villarreal

The camera in the schematic is "to be defined". Varroa is what defines it: everything else we want to see is bigger.

## How many pixels does a mite need?

A Varroa female is about 1.1 mm long and 1.6 mm wide. To be recognized by a small CNN, an object needs on the order of 10 pixels across its smallest side. Below that it becomes a reddish smudge that the model cannot tell apart from pollen, a shadow or a dark band on the abdomen.

Target: **at least 8 pixels per millimeter on the landing board, 10 or more preferred.** At 8 px/mm the mite covers about 9 × 13 px and a bee about 100 × 35 px.

## What that means for field of view

| Sensor width in pixels | Board width covered at 8 px/mm | At 10 px/mm |
|---|---|---|
| 1280 (720p webcam) | 16 cm | 12.8 cm |
| 1920 (1080p webcam) | 24 cm | 19.2 cm |
| 3280 (Raspberry Pi Camera v2, IMX219, full res) | 41 cm | 32.8 cm |
| 4608 (Raspberry Pi Camera v3, IMX708, full res) | 57.6 cm | 46 cm |

A full Langstroth entrance is about 37 cm wide, but most entrances are reduced to a few centimeters, especially in defensive Africanized colonies. A camera covering 15 to 20 cm of board is enough. A 1080p USB webcam that someone already owns can meet the target if it is mounted close enough and can focus there.

## Why the detector cannot just run at full resolution

Detectors that fit on a Pi 3B run at 320 to 416 px input. If the whole frame (say 1920 px wide) is shrunk to 320 px, the scale drops 6×. The mite goes from about 9 px to 1.5 px. It is gone.

Running the detector on the full image by tiling it (the SAHI approach, Akyon et al. 2022) works for small objects, but on a 1920 × 1080 frame it means about 20 tiles at 416 px, which at roughly a second per tile on a Pi 3B is far too slow.

The way out is two stages: find the bees at low resolution (a bee is still 15 to 20 px long after downscaling, enough to detect), then go back to the full-resolution frame and crop each bee for the Varroa classifier. Details in [model architecture](04-model-architecture.md).

## Motion blur

A bee walking on the board moves a few centimeters per second; a bee landing or taking off moves much faster. At 8 px/mm:

| Bee speed | Exposure 1/250 s | Exposure 1/1000 s |
|---|---|---|
| Walking, 2 cm/s | 0.6 px | 0.16 px |
| Fast walk, 5 cm/s | 1.6 px | 0.4 px |
| Flying, 50 cm/s | 16 px | 4 px |

So: Varroa detection works on walking bees, and only in good light, where the camera picks short exposures by itself. Flying bees are still useful for stage 1 (traffic, hornets) but their crops should be skipped by stage 2. A blur score (variance of the Laplacian on the crop) decides that.

## Camera requirements

| Requirement | Value | Why |
|---|---|---|
| Resolution on the board | ≥ 8 px/mm, ≥ 10 preferred | Varroa |
| Focus | Sharp at the mounting distance (typically 10 to 25 cm) | Many fixed-focus modules are set for far distances. The Pi Camera v2's lens can be refocused by hand; the v3 has autofocus |
| Interface | CSI preferred, USB acceptable | CSI with `picamera2` gives two simultaneous streams (low-res for motion, full-res for stills) and costs less CPU than USB on a Pi 3B |
| Exposure control | Manual or capped exposure time | Keep blur down on bright days |
| IR / night | Not needed | Bees and hornets are not active at the entrance at night |
| Power | As low as possible | See [power budget](../02-hardware/power-budget.md) |

## Mounting

```text
          camera (looking down, 10-25 cm above the board)
             |
             v
   ┌──────────────────────────────┐
   │   shade hood (avoid harsh    │
   │   sun and rain on the lens)  │
   └──────────────────────────────┘
  ═════════════════════════════════  landing board (plain, matte, light color)
         ^ entrance of the hive
```

Recommendations:

- Look straight down, or at a small angle, at the landing board just outside the entrance.
- Make the board surface plain, matte and light-colored if possible. Contrast with a red-brown mite helps; so does a uniform background for the motion check.
- Add a hood to block direct sun (shadows and glare) and rain.
- Keep the field of view tight. Every extra centimeter of board costs pixels per millimeter.

### Option: an entrance passage

A short transparent-roofed tunnel at the entrance forces bees to walk under the camera in single file, at a known distance, slowly. This is the strongest single improvement for Varroa detection, and it simplifies the synthetic images (fixed geometry, fixed distance). It also changes how bees use the entrance, so it must be tested with the colony, and it needs to be cleaned. Worth a prototype once the camera is chosen.

## Team captures (tier C) to make now

Even without bees, the chosen camera mounted at the chosen distance can capture data the generator needs:

1. Empty board backgrounds: 200+ frames across a day (morning, noon, afternoon, cloudy, sunny, wet). These become the backgrounds for synthetic images.
2. Noise and color profile: a few frames of a gray card or plain paper at several light levels, to fit the camera noise model.
3. Scale: one frame of a ruler on the board, to fix px/mm in the generator config.
4. Any real bees: if any member has access to a hive (a neighbor, a university apiary), a few minutes of video of the entrance with the same camera is worth more than thousands of synthetic images for validation.
