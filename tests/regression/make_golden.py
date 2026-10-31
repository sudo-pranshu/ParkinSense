import json
from pathlib import Path

from parkinsense.replay import replay as R

FILES = [("data/reference/ble_v1_104hz/parkinsense_20260630_123551.csv", False)] + [
    (str(p), True) for p in sorted(Path("data/reference/legacy_serial_23hz").glob("*.csv"))]

if __name__ == "__main__":
    g = {}
    for path, rs in FILES:
        g[Path(path).stem] = {"path": path, "resample": rs, "outputs": R.replay(path, resample=rs)["summary"]["outputs"]}
    (Path(__file__).parent / "golden.json").write_text(json.dumps(g, indent=2, sort_keys=True))
    print(json.dumps(g, indent=1)[:2000])
