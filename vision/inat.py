"""Build the real-image check set (tier P) from the iNaturalist Open Dataset on AWS.

Streams the metadata archive once (no full download kept on disk), keeps research-grade
observations of our classes, keeps only the first photo of each observation and only
CC0 / CC-BY licenses, then downloads a capped number of photos per class.

    python -m vision.inat filter  --out data/raw/inat       # ~30 min, streams ~4.8 GB
    python -m vision.inat download --out data/raw/inat --per-class 300
    # asset pool for cutouts, disjoint from the frozen tier P split:
    python -m vision.inat download --src data/raw/inat --out data/raw/inat_pool --per-class 600 --seed 1 --exclude vision/splits/P-inat-v1.tsv
"""
import argparse
import csv
import hashlib
import random
import re
from concurrent.futures import ThreadPoolExecutor
import sys
import tarfile
import urllib.request
from pathlib import Path

BUCKET = "https://inaturalist-open-data.s3.amazonaws.com"
ARCHIVE = f"{BUCKET}/metadata/inaturalist-open-data-20260927.tar.gz"  # P-inat-v1 came from the 20210407 snapshot
# (taxon_id, class, group). A taxon takes its most specific listed ancestor, so Apis mellifera stays "bee"
# although Anthophila (all bees) is "other_insect". Groups are the hard negatives we want to report on.
ROOTS = [
    (47219, "bee", "apis_mellifera"),
    (47220, None, "apis_other"),            # Apis cerana etc. look like A. mellifera: never label them "other"
    (54328, "hornet", "vespa"),
    (457066, "shb", "aethina_tumida"),
    (194696, "varroa", "varroa"),
    (52747, "other_insect", "vespidae_other"),  # potter wasps etc.
    (61356, "other_insect", "vespula"),
    (52912, "other_insect", "dolichovespula"),
    (52756, "other_insect", "polistes"),
    (51967, "other_insect", "scoliidae"),
    (48742, "other_insect", "sphecidae"),
    (53256, "other_insect", "siricidae"),
    (354819, "other_insect", "hornet_moth"),
    (630955, "other_insect", "bees_other"),
    (52775, "other_insect", "bombus"),
    (51111, "other_insect", "xylocopa"),
    (200106, "other_insect", "meliponini"),
    (49995, "other_insect", "syrphidae"),
    (52491, "other_insect", "eristalis"),
    (143339, "other_insect", "milesia"),
    (52481, "other_insect", "volucella"),
    (70144, "other_insect", "muscidae"),
    (61860, "other_insect", "calliphoridae"),
    (52910, "other_insect", "sarcophagidae"),
    (47982, "other_insect", "asilidae"),
    (47336, "other_insect", "formicidae"),
    (126791, "other_insect", "nitidulidae"),
    (122940, "other_insect", "wax_moth"),
    (362715, "other_insect", "wax_moth"),
]
LICENSES = {"CC0", "CC-BY"}
csv.field_size_limit(sys.maxsize)


def rows(member_file):
    # Plain TSV without quoting; TextIOWrapper needs a seekable stream, which tar's stream mode is not
    return (line.decode("utf-8", "replace").rstrip("\r\n").split("\t") for line in member_file)


def taxon_map(taxa_csv: Path):
    """taxon_id -> (class, group) through the most specific ancestor listed in ROOTS."""
    roots = {t: (c, g) for t, c, g in ROOTS}
    out = {}
    for r in csv.reader(open(taxa_csv, encoding="utf-8"), delimiter="\t"):
        if r[0] == "taxon_id":
            continue
        chain = [int(r[0])] + [int(a) for a in reversed(r[1].split("/")) if a]  # self, parent, ..., root
        hit = next((roots[t] for t in chain if t in roots), None)
        if hit and hit[0]:
            out[int(r[0])] = hit
    return out


def filter_archive(out: Path, taxa_csv: Path, archive=ARCHIVE):
    """taxa.csv is the last member of the archive, so ancestry comes from an earlier copy (--taxa); taxa
    created after that copy are missed. Columns are read by header name, which changes between snapshots."""
    taxa = taxon_map(taxa_csv)
    obs = {}
    out.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(archive) as resp, tarfile.open(fileobj=resp, mode="r|gz") as tar:
        for m in tar:
            name = m.name.rsplit("/", 1)[-1]
            if name == "observations.csv":
                it = rows(tar.extractfile(m))
                h = {k: i for i, k in enumerate(next(it))}
                u, o, t, q, d, la, lo = (h[k] for k in ("observation_uuid", "observer_id", "taxon_id", "quality_grade",
                                                        "observed_on", "latitude", "longitude"))
                for r in it:
                    if r[q] == "research" and r[t].isdigit() and int(r[t]) in taxa:
                        obs[r[u]] = (int(r[t]), r[d], r[la], r[lo])
                print("observations kept:", len(obs), flush=True)
            elif name == "photos.csv":
                it = rows(tar.extractfile(m))
                h = {k: i for i, k in enumerate(next(it))}
                pid, ou, ob, ext, lic, pos = (h[k] for k in ("photo_id", "observation_uuid", "observer_id", "extension",
                                                            "license", "position"))
                n = 0
                with open(out / "photos.tsv", "w", newline="") as f:
                    w = csv.writer(f, delimiter="\t", lineterminator="\n")
                    w.writerow(["photo_id", "extension", "license", "observer_id", "observation_uuid", "taxon_id", "cls",
                                "group", "observed_on", "latitude", "longitude"])
                    for r in it:
                        if r[ou] in obs and r[lic] in LICENSES and r[pos] == "0":
                            tx, day, lat, lon = obs[r[ou]]
                            c, g = taxa[tx]
                            w.writerow([r[pid], r[ext], r[lic], r[ob], r[ou], tx, c, g, day, lat, lon])
                            n += 1
                print("photos written:", n, flush=True)
                return


def download(out: Path, per_class: int, seed: int = 0, src: Path | None = None, exclude=(), only=None):
    """exclude: split/manifest files whose photos must never be downloaded again (keeps pools disjoint from tier P)."""
    skip = {Path(r["file"]).stem for e in exclude for r in csv.DictReader(open(e), delimiter="\t")}
    by_cls = {}
    for r in csv.DictReader(open((src or out) / "photos.tsv"), delimiter="\t"):
        if r["photo_id"] not in skip and (not only or r["cls"] in only):
            by_cls.setdefault(r["cls"], []).append(r)
    out.mkdir(parents=True, exist_ok=True)
    manifest = open(out / "manifest.tsv", "w", newline="")
    w = csv.writer(manifest, delimiter="\t", lineterminator="\n")
    w.writerow(["file", "cls", "taxon_id", "license", "source_url", "observer_id"])
    rng = random.Random(seed)
    for cls, items in sorted(by_cls.items()):
        rng.shuffle(items)
        (out / cls).mkdir(parents=True, exist_ok=True)
        got = 0
        for r in items:
            if got >= per_class:
                break
            url = f"{BUCKET}/photos/{r['photo_id']}/medium.{r['extension']}"
            dst = out / cls / f"{r['photo_id']}.{r['extension']}"
            try:
                if not dst.exists():
                    urllib.request.urlretrieve(url, dst)
            except OSError as e:
                print("skip", url, e)
                continue
            w.writerow([str(dst.relative_to(out)), cls, r["taxon_id"], r["license"],
                        f"https://www.inaturalist.org/photos/{r['photo_id']}", r["observer_id"]])
            got += 1
        print(cls, got, "of", len(items), flush=True)


# Tier P v2 and training pools from one snapshot: photographers are split, not only photos (v0.5).
# Quotas per (class, group); "other" leans on what gets confused with hornets and bees.
TEST_QUOTA = {("bee", "apis_mellifera"): 500, ("hornet", "vespa"): 500, ("shb", "aethina_tumida"): 30, ("varroa", "varroa"): 20,
              **{("other_insect", g): n for g, n in {
                  "vespula": 70, "polistes": 60, "dolichovespula": 50, "vespidae_other": 40, "scoliidae": 40, "sphecidae": 30,
                  "siricidae": 20, "hornet_moth": 15, "milesia": 20, "volucella": 30, "eristalis": 40, "syrphidae": 30,
                  "bombus": 40, "bees_other": 30, "xylocopa": 20, "meliponini": 20, "asilidae": 20, "muscidae": 10,
                  "calliphoridae": 10, "sarcophagidae": 5, "formicidae": 20, "nitidulidae": 10, "wax_moth": 5}.items()}}
POOL_QUOTA = {("bee", "apis_mellifera"): 3000, ("hornet", "vespa"): 4000,
              **{("other_insect", g): n for g, n in {
                  "vespula": 700, "polistes": 600, "dolichovespula": 500, "vespidae_other": 400, "scoliidae": 350, "sphecidae": 300,
                  "siricidae": 200, "hornet_moth": 60, "milesia": 200, "volucella": 300, "eristalis": 350, "syrphidae": 250,
                  "bombus": 350, "bees_other": 300, "xylocopa": 200, "meliponini": 250, "asilidae": 200, "muscidae": 100,
                  "calliphoridae": 100, "sarcophagidae": 40, "formicidae": 200, "nitidulidae": 80, "wax_moth": 60}.items()}}


def bucket(observer_id: str) -> int:
    """0 = test, 1 = calib, 2..9 = training, fixed by the photographer."""
    return int(hashlib.sha1(observer_id.encode()).hexdigest(), 16) % 10


def plan(src: Path, old: list[Path], seed=0, test_cap=3, pool_cap=30):
    """Pick tier P v2 (calib/test) and the training pool. old: earlier split/manifest files; their photos and
    observations are never reused, and their photographers are kept out of v2 calib/test."""
    obs_of = {r["photo_id"]: r["observation_uuid"] for r in csv.DictReader(open(src / "photos.tsv"), delimiter="\t")}
    old_rows = [r for f in old for r in csv.DictReader(open(f), delimiter="\t")]
    old_obs = {obs_of.get(re.search(r"photos/(\d+)", r["source_url"]).group(1)) for r in old_rows} - {None}
    old_observers = {r["observer_id"] for r in old_rows}
    by = {}
    for r in csv.DictReader(open(src / "photos.tsv"), delimiter="\t"):
        if r["observation_uuid"] not in old_obs and (r["cls"], r["group"]) in POOL_QUOTA.keys() | TEST_QUOTA.keys():
            by.setdefault((r["cls"], r["group"]), []).append(r)
    rng = random.Random(seed)
    picked = []
    for key, items in sorted(by.items()):
        rng.shuffle(items)
        for split, want, cap, ok in (("test", TEST_QUOTA.get(key, 0), test_cap, lambda b, o: b == 0 and o not in old_observers),
                                     ("calib", TEST_QUOTA.get(key, 0) * 3 // 5, test_cap, lambda b, o: b == 1 and o not in old_observers),
                                     ("train", POOL_QUOTA.get(key, 0), pool_cap, lambda b, o: b >= 2)):
            per_obs, n = {}, 0
            for r in items:
                if n >= want:
                    break
                o = r["observer_id"]
                if ok(bucket(o), o) and per_obs.get(o, 0) < cap:
                    per_obs[o] = per_obs.get(o, 0) + 1
                    picked.append({**r, "split": split})
                    n += 1
    return picked


def fetch(rows, out: Path, workers=8):
    """Download medium-size photos in parallel; returns the rows that arrived, with file and sha256."""
    def one(r):
        dst = out / r["cls"] / f"{r['photo_id']}.{r['extension']}"
        try:
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                data = urllib.request.urlopen(f"{BUCKET}/photos/{r['photo_id']}/medium.{r['extension']}", timeout=60).read()
                dst.write_bytes(data)
            return {**r, "file": str(dst.relative_to(out)), "sha256": hashlib.sha256(dst.read_bytes()).hexdigest()}
        except OSError as e:
            print("skip", r["photo_id"], e, flush=True)
    with ThreadPoolExecutor(workers) as ex:
        return [r for r in ex.map(one, rows) if r]


def build_v2(src: Path, out: Path, old: list[Path], split_file: Path):
    rows = fetch(plan(src, old), out)
    cols = ["file", "cls", "group", "split", "sha256", "license", "source_url", "observer_id", "observation_uuid", "taxon_id", "observed_on"]
    def write(path, rs):
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, cols, delimiter="\t", lineterminator="\n", extrasaction="ignore")
            w.writeheader()
            w.writerows({**r, "source_url": f"https://www.inaturalist.org/photos/{r['photo_id']}"} for r in rs)
    write(split_file, [r for r in rows if r["split"] in ("calib", "test")])
    write(out / "manifest.tsv", [r for r in rows if r["split"] == "train"])
    for s in ("calib", "test", "train"):
        print(s, len([r for r in rows if r["split"] == s]), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["filter", "download", "v2"])
    p.add_argument("--out", type=Path, default=Path("data/raw/inat"))
    p.add_argument("--taxa", type=Path, help="taxa.csv from an earlier pass or snapshot (ancestry)")
    p.add_argument("--archive", default=ARCHIVE, help="metadata snapshot URL")
    p.add_argument("--per-class", type=int, default=300)
    p.add_argument("--src", type=Path, help="folder with photos.tsv, if not --out")
    p.add_argument("--exclude", type=Path, nargs="*", default=[], help="split/manifest files to stay disjoint from, e.g. vision/splits/P-inat-v1.tsv")
    p.add_argument("--only", nargs="*", help="classes to download")
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()
    if a.cmd == "v2":  # python -m vision.inat v2 --src data/raw/inat26 --out data/raw/inat26_photos --exclude <old splits/manifests>
        build_v2(a.src, a.out, a.exclude, Path(__file__).parent / "splits" / "P-inat-v2.tsv")
    elif a.cmd == "filter":
        filter_archive(a.out, a.taxa, a.archive)
    else:
        download(a.out, a.per_class, a.seed, a.src, a.exclude, a.only)
