"""
Download the public reference datasets used by the sleep and step benchmarks.

    python -m benchmarks.external.fetch walch     [--dest data/external]
    python -m benchmarks.external.fetch clemson
    python -m benchmarks.external.fetch karas

Nothing here is committed to the repository: files go to `data/external/`
(git-ignored). Each dataset entry records its upstream source, licence and
citation (benchmarks/external/MANIFEST.md). Where the canonical host
(PhysioNet, Clemson) is not reachable from a build environment, GitHub
mirrors are used; for the Walch dataset every mirrored file is checked
against the upstream SHA256SUMS.txt and rejected on mismatch.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAW = "https://raw.githubusercontent.com/{repo}/{ref}/{path}"

# --- Walch 2019, PhysioNet sleep-accel 1.0.0 (ODC-By 1.0) -----------------------------
WALCH_SUMS = ("josedv82/public_sport_science_datasets", "main", "Sleep Dataset/SHA256SUMS.txt")
WALCH_LABEL_HR_REPO = ("josedv82/public_sport_science_datasets", "main", "Sleep Dataset")
# Acceleration files are not in that mirror (size); these mirrors carry unmodified copies.
WALCH_ACCEL = {
    **{s: ("SebastianSigur/LokaverkefniSmartAlarm", "main", f"SleepPrediction/data/hr_data/motion/{s}_acceleration.txt")
       for s in ["1066528", "1360686", "3509524", "4018081", "4314139", "46343", "5132496", "5383425", "5498603",
                 "759667", "7749105", "781756", "8173033", "8258170", "844359", "8686948"]},
    "1455390": ("tachyonFlux/sleep-tracker-service", "main", "realdata/1455390_acceleration.txt"),
    "8000685": ("tachyonFlux/sleep-tracker-service", "main", "realdata/8000685_acceleration.txt"),
}

# --- Karas 2021, PhysioNet accelerometry-walk-climb-drive 1.0.0 (ODbL 1.0) ------------
KARAS_REPO = ("kevin-chao-com/walking-detection", "main", "data")

# --- Clemson Pedometer Evaluation (Mattfeld, Jesch, Hoover 2017), prepared copy -------
CLEMSON_REPO = ("ChaddBrenner/mattfeld_research_data", "main", "Data")


def _url(repo, ref, path):
    return RAW.format(repo=repo, ref=ref, path=urllib.parse.quote(path))


def _get(url, dest: Path, expect_sha=None):
    if dest.exists() and (expect_sha is None or _sha(dest) == expect_sha):
        return "cached"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    if expect_sha is not None and _sha(tmp) != expect_sha:
        tmp.unlink()
        raise ValueError(f"SHA256 mismatch for {dest.name} from {url}")
    tmp.replace(dest)
    return "ok"


def _sha(p: Path):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def fetch_walch(dest: Path):
    d = dest / "walch"
    _get(_url(*WALCH_SUMS), d / "SHA256SUMS.txt")
    sums = dict(reversed(line.split(maxsplit=1)) for line in (d / "SHA256SUMS.txt").read_text().splitlines() if line)
    repo, ref, base = WALCH_LABEL_HR_REPO
    _get(_url(repo, ref, f"{base}/LICENSE.txt"), d / "LICENSE.txt", sums["LICENSE.txt"])
    for sid, src in sorted(WALCH_ACCEL.items()):
        for rel, url in ((f"labels/{sid}_labeled_sleep.txt", _url(repo, ref, f"{base}/labels/{sid}_labeled_sleep.txt")),
                         (f"heart_rate/{sid}_heartrate.txt", _url(repo, ref, f"{base}/heart_rate/{sid}_heartrate.txt")),
                         (f"motion/{sid}_acceleration.txt", _url(*src))):
            print(f"walch {rel}: {_get(url, d / rel, sums[rel])}", flush=True)


def fetch_karas(dest: Path):
    d = dest / "karas"
    repo, ref, base = KARAS_REPO
    for name in ("LICENSE.txt", "SHA256SUMS.txt", "participant_demog.csv"):
        _get(_url(repo, ref, f"{base}/{name}"), d / name)
    sums = dict(reversed(line.split(maxsplit=1)) for line in (d / "SHA256SUMS.txt").read_text().splitlines() if line)
    missing = []
    for rel, sha in sorted(sums.items()):
        if rel.startswith("raw_accelerometry_data/") and rel.endswith(".csv"):
            try:
                print(f"karas {rel}: {_get(_url(repo, ref, f'{base}/{rel}'), d / rel, sha)}", flush=True)
            except urllib.error.HTTPError as e:   # the mirror lacks 5 of 32 subjects (altered copies)
                missing.append(rel)
                print(f"karas {rel}: not in mirror ({e.code})", flush=True)
    print(f"karas: {len(missing)} subject file(s) unavailable from the mirror", flush=True)


def fetch_clemson(dest: Path):
    d = dest / "clemson"
    repo, ref, base = CLEMSON_REPO
    for p in range(1, 31):
        for kind in ("Regular", "SemiRegular", "Irregular"):
            name = f"P{p:03d}_{kind}.csv"
            print(f"clemson {name}: {_get(_url(repo, ref, f'{base}/{name}'), d / name)}", flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dataset", choices=["walch", "karas", "clemson", "all"])
    ap.add_argument("--dest", default="data/external")
    a = ap.parse_args(argv)
    dest = Path(a.dest)
    for name in (["walch", "karas", "clemson"] if a.dataset == "all" else [a.dataset]):
        try:
            globals()[f"fetch_{name}"](dest)
        except Exception as e:  # report and continue with the next dataset
            print(f"{name}: FAILED: {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
