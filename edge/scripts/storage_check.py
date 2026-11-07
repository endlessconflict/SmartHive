"""US08 test run: synthetic analyzed frames through the node's real filter, and what ends up on the SD card.

    python edge/scripts/storage_check.py                  # 1000 frames, the default retention rule
    python edge/scripts/storage_check.py --frames 5000 --sample-rate 0.02 --seed 7

Frames are written to a temporary folder (on the Pi it is RAM), the filter keeps or deletes each one, and the
script compares the bytes analyzed with the bytes kept. It fails if a frame with a threat or a Varroa-positive
bee was not kept. Nothing is sent anywhere.
"""

import argparse
import random
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "raspberry"))

from pi_node.fake_camera import FRAME_KB, RELEVANT, FakeCamera  # noqa: E402
from pi_node.frames import FrameFilter  # noqa: E402
from pi_node.outbox import Outbox  # noqa: E402
from pi_node.retention import Retention, RetentionRule  # noqa: E402


def mb(n: int) -> str:
    return f"{n / 1024 / 1024:8.1f} MB"


def run() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", type=int, default=1000)
    ap.add_argument("--sample-rate", type=float, default=RetentionRule().sample_rate)
    ap.add_argument("--max-samples", type=int, default=RetentionRule().max_samples_per_day)
    ap.add_argument("--frame-kb", type=float, default=FRAME_KB)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    rule = RetentionRule(sample_rate=args.sample_rate, max_samples_per_day=args.max_samples)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        outbox = Outbox(root / "outbox.db")
        camera = FakeCamera(root / "frames", rng, args.frame_kb)
        filt = FrameFilter("sim-0001", root / "frames", root / "images", outbox, Retention(rule, rng))
        scenes: Counter[str] = Counter()
        relevant_ids = set()
        for _ in range(args.frames):
            shot = camera.shoot()
            scenes[shot.scene] += 1
            if shot.scene in RELEVANT:
                relevant_ids.add(shot.frame_id)
            filt.process()
        kept = {row.image_id: row.reason for row in outbox.pending_images(limit=args.frames)}
        on_card = sum(p.stat().st_size for p in (root / "images").iterdir())
        left_in_ram = list((root / "frames").iterdir())
        outbox.close()

    s = filt.stats
    reasons = Counter(kept.values())
    lost = relevant_ids - kept.keys()
    print(f"frames analyzed  {s.seen:6d}  {mb(s.bytes_seen)}")
    for name, n in sorted(scenes.items(), key=lambda kv: -kv[1]):
        print(f"  {name:<14} {n:6d}{'  relevant' if name in RELEVANT else ''}")
    share = 100 * s.bytes_kept / max(1, s.bytes_seen)
    print(f"kept on the card {s.kept:6d}  {mb(on_card)}  ({share:.1f} % of the bytes)")
    for reason in ("threat", "varroa", "sample"):
        print(f"  {reason:<14} {reasons.get(reason, 0):6d}")
    print(f"discarded        {s.seen - s.kept:6d}")
    print(f"reduction        {100 * (1 - s.bytes_kept / max(1, s.bytes_seen)):6.1f} %")
    print(f"relevant lost    {len(lost):6d}")
    if lost or left_in_ram or on_card != s.bytes_kept:
        sys.exit("FAIL: a relevant frame was not kept, or files were left behind")
    print("OK")


if __name__ == "__main__":
    run()
