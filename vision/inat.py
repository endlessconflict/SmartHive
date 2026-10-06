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
import random
import sys
import tarfile
import urllib.request
from pathlib import Path

BUCKET = "https://inaturalist-open-data.s3.amazonaws.com"
ARCHIVE = f"{BUCKET}/metadata/inaturalist-open-data-20210407.tar.gz"
# iNat taxon ids (2021-04 taxonomy). Descendants (subspecies...) are included via ancestry.
CLASSES = {
    "bee": [47219],                      # Apis mellifera
    "hornet": [54328],                   # genus Vespa (V. velutina 119019, V. crabro 54327, ...)
    "shb": [457066],                     # Aethina tumida
    "varroa": [194693],                  # Varroa destructor
    "other_insect": [120156, 52756, 126155, 52775, 47336],  # Musca domestica, Polistes, Vespula germanica, Bombus, Formicidae
}
LICENSES = {"CC0", "CC-BY"}
csv.field_size_limit(sys.maxsize)


def rows(member_file):
    # Plain TSV without quoting; TextIOWrapper needs a seekable stream, which tar's stream mode is not
    return (line.decode("utf-8", "replace").rstrip("\r\n").split("\t") for line in member_file)


def filter_archive(out: Path, taxa_csv: Path):
    """taxa.csv is the last member of the archive, so it comes from a previous pass (--taxa)."""
    roots = {t: c for c, ts in CLASSES.items() for t in ts}
    taxon_class = {}
    for r in csv.reader(open(taxa_csv, encoding="utf-8"), delimiter="\t"):
        if r[0] == "taxon_id":
            continue
        chain = [int(r[0])] + [int(a) for a in r[1].split("/") if a]
        hit = next((roots[t] for t in chain if t in roots), None)
        if hit:
            taxon_class[int(r[0])] = hit
    obs = {}
    out.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(ARCHIVE) as resp, tarfile.open(fileobj=resp, mode="r|gz") as tar:
        for m in tar:
            name = m.name.rsplit("/", 1)[-1]
            if name == "observations.csv":
                for r in rows(tar.extractfile(m)):
                    # observation_uuid, observer_id, latitude, longitude, positional_accuracy, taxon_id, quality_grade, observed_on
                    if r[6] == "research" and r[5].isdigit() and int(r[5]) in taxon_class:
                        obs[r[0]] = (taxon_class[int(r[5])], r[5])
                print("observations kept:", len(obs), flush=True)
            elif name == "photos.csv":
                with open(out / "photos.tsv", "w", newline="") as f:
                    w = csv.writer(f, delimiter="\t", lineterminator="\n")
                    w.writerow(["photo_id", "extension", "license", "observer_id", "observation_uuid", "taxon_id", "cls"])
                    for r in rows(tar.extractfile(m)):
                        # photo_uuid, photo_id, observation_uuid, observer_id, extension, license, width, height, position
                        if r[2] in obs and r[5] in LICENSES and r[8] == "0":
                            w.writerow([r[1], r[4], r[5], r[3], r[2], obs[r[2]][1], obs[r[2]][0]])
                print("photos written", flush=True)
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


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["filter", "download"])
    p.add_argument("--out", type=Path, default=Path("data/raw/inat"))
    p.add_argument("--taxa", type=Path, help="taxa.csv extracted from the same archive")
    p.add_argument("--per-class", type=int, default=300)
    p.add_argument("--src", type=Path, help="folder with photos.tsv, if not --out")
    p.add_argument("--exclude", type=Path, nargs="*", default=[], help="split/manifest files to stay disjoint from, e.g. vision/splits/P-inat-v1.tsv")
    p.add_argument("--only", nargs="*", help="classes to download")
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()
    if a.cmd == "filter":
        filter_archive(a.out, a.taxa)
    else:
        download(a.out, a.per_class, a.seed, a.src, a.exclude, a.only)
