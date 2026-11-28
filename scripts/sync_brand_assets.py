"""Sincronizza gli asset di brand dal repo canonico al pacchetto.

Gli asset canonici vivono in `infra/lab-ops/standards/assets/logo/`. Il pacchetto
`lab-connectors` ne spedisce una copia verificata, perché le dashboard lo hanno già
installato e non devono scaricare il marchio dalla rete all'avvio.

Uso::

    python scripts/sync_brand_assets.py --source ../infra/lab-ops/standards/assets/logo
    python scripts/sync_brand_assets.py --check    # verifica senza scrivere

`--check` esce con codice 1 se una copia diverge dal canonico: serve a impedire che
la copia diventi una seconda fonte di verità.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

FILES = ("symbol.svg", "symbol-on-dark.svg", "favicon.svg")
CANONICAL = "infra/lab-ops/standards/assets/logo"
TARGET = Path(__file__).parents[1] / "lab_connectors" / "assets" / "brand"
MANIFEST = TARGET / "MANIFEST.json"


def sha256(path: Path) -> str:
    """Digest SHA-256 di un file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    """Copia o verifica gli asset."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="cartella canonica (logo/)")
    parser.add_argument("--check", action="store_true", help="verifica senza scrivere")
    args = parser.parse_args()

    if args.check:
        if not MANIFEST.exists():
            print(f"manifest mancante: {MANIFEST}")
            return 1
        manifest = json.loads(MANIFEST.read_text())
        bad = []
        for name in FILES:
            target = TARGET / name
            if not target.exists():
                bad.append(f"{name}: assente")
                continue
            actual = sha256(target)
            expected = manifest["files"].get(name, {}).get("sha256")
            if actual != expected:
                bad.append(f"{name}: hash diverso dal manifest")
        if bad:
            print("asset non allineati:\n  " + "\n  ".join(bad))
            return 1
        print(f"asset allineati al manifest ({len(FILES)} file)")
        return 0

    if not args.source:
        parser.error("--source è obbligatorio senza --check")

    TARGET.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict[str, str]] = {}
    for name in FILES:
        src = args.source / name
        if not src.exists():
            print(f"mancante nel canonico: {src}")
            return 1
        shutil.copyfile(src, TARGET / name)
        files[name] = {"sha256": sha256(TARGET / name), "source": f"{CANONICAL}/{name}"}

    MANIFEST.write_text(
        json.dumps(
            {
                "note": "copia verificata degli asset canonici di lab-ops; non modificare qui",
                "canonical": CANONICAL,
                "files": files,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"copiati {len(FILES)} asset e riscritto {MANIFEST.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
