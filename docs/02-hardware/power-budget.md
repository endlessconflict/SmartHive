# Power budget

Status: Draft. All numbers are estimates until measured on the real node.

Owner: Ricardo Villarreal

FR-11, NFR-01 and NFR-02 ask for a minimum autonomy that was never defined. This page estimates what the Prototype 1 design can actually deliver, so the team and the client can set that number knowingly.

## Energy available

| Item | Assumption | Value |
|---|---|---|
| Cell capacity | 18650 Li-ion cells, 2,500 to 3,500 mAh each (depends on the cells actually bought) | |
| Pack | 3S2P: two cells in parallel per series group | 5.0 to 7.0 Ah at 11.1 V nominal |
| Nominal energy | 11.1 V × capacity | 55 to 78 Wh |
| Usable energy | About 85 % (BMS cut-off, cell aging, cold) | 47 to 66 Wh |

## Consumption

Measured values for the Pi 3B come from published bench tests on a headless Pi 3B with stock Raspbian Lite: 1.4 W idle and 3.7 W with all four cores at 100 % ([Pi Dramble power measurements](https://pidramble.com/node/27)). The rest are assumptions.

| Consumer (5 V side) | Low case | High case | Notes |
|---|---|---|---|
| Pi 3B idle, Ethernet up | 1.4 W | 1.4 W | Measured by third party. Ethernet is included: on the 3B the LAN chip is always powered |
| Camera while capturing | 0.5 W | 1.3 W | Depends on the model. Assumption until the camera is chosen |
| Motion detection on low-res frames | 0.1 W | 0.2 W | One core partly busy |
| Detector (duty cycle × 2.3 W extra at full load) | 0.1 W (5 %) | 0.7 W (30 %) | Duty cycle depends on bee traffic; a busy entrance triggers more often |
| DHT11 | ~0 | ~0 | Milliwatts |
| **Total at 5 V** | **2.1 W** | **3.6 W** | |
| Buck efficiency (MP1584 at this load) | 87 % | 85 % | Typical for this module and current |
| Diode SS34 loss | ~0.1 W | ~0.15 W | 0.45 V × input current |
| **Total from battery** | **about 2.5 W** | **about 4.4 W** | |

At night there are no foragers, so the camera and detector can be switched off. A night load of about 1.5 W at 5 V (1.8 W from the battery) is realistic.

## Autonomy

| Scenario | Average draw from battery | Autonomy with 47 Wh | Autonomy with 66 Wh |
|---|---|---|---|
| Light day load, 24 h | 2.5 W | 19 h | 26 h |
| Heavy day load, 24 h | 4.4 W | 11 h | 15 h |
| 12 h heavy day + 12 h night mode | 3.1 W | 15 h | 21 h |

**With the Raspberry Pi running all the time, Prototype 1 lasts roughly half a day to one day on a full charge.** The Pi 3B has no low-power sleep mode, so software tuning can only shave the margins; it cannot change the order of magnitude.

## Options to reach a useful autonomy

| Option | What it takes | Effect | Comment |
|---|---|---|---|
| A. Accept about one day for the demo | Nothing | Enough for a demo day, swap batteries daily | Simplest. Requirements must say so |
| B. Power over the existing Ethernet cable | Passive PoE injector at the gateway, splitter at the node feeding about 12 V into the buck input | Unlimited runtime; the battery becomes a UPS | The cable is already in the design. The Pi 3B has no PoE header, so the splitter feeds the existing power path |
| C. Solar charging | Panel plus solar charge controller suitable for a 3S pack | Days to indefinite, depending on the sun | Rough sizing: daily need is about 60 to 75 Wh. With about 4 to 5 peak sun hours and system losses, a panel in the 25 to 40 W range. To be checked against local irradiance |
| D. Power gating | External timer or microcontroller that cuts the Pi's power and wakes it every N minutes | Average drops in proportion to the duty cycle | The Pi takes tens of seconds to boot. Hornets and Varroa would only be seen in short windows |
| E. Split node | ESP32 for sensors (deep sleep), Pi only for vision and only during daylight | Sensors run for weeks; vision limited by option C or D | Matches the original ESP32 concept. More work; see [ADR-0003](../adr/0003-raspberry-pi-3b-edge-node.md) |

Recommendation for Prototype 1: option B for the demo installation, keeping the battery as backup, and option A as the documented fallback. Option C or E belongs in the roadmap for a second prototype.

## What the software does about it

- Night mode: camera and detector pause between configurable sunset and sunrise times; sensors continue.
- The detector only runs on frames where motion was detected.
- Health messages report the throttling and under-voltage flags. Once a voltage sensor is added, they report battery voltage too, which is what US06 needs to tell "battery empty" from "network down".
- The backend treats gaps of hours as normal operation, not as an error, until the autonomy requirement is fixed.

## How to measure

1. Put a USB power meter, or better an INA219 breakout, between the buck output and the Pi.
2. Log consumption for 24 h with the full software running: idle, motion, detector, night mode.
3. Replace the assumptions in this table with the measured numbers and remove the "Draft" status.
