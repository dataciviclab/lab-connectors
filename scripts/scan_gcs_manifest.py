#!/usr/bin/env python3
"""Scansiona i bucket GCS pubblici del Lab e pubblica gcs_manifest.json.

Produces: gs://dataciviclab-clean/registry/gcs_manifest.json

Uso:
    python scripts/scan_gcs_manifest.py              # solo stdout (dry-run)
    python scripts/scan_gcs_manifest.py --upload     # carica su GCS
    python scripts/scan_gcs_manifest.py --pretty      # output formattato
"""

from __future__ import annotations

import argparse
import json
import sys

from lab_connectors.gcs.manifest import build_manifest, upload_manifest


def main() -> None:
    """Entry point: scansiona bucket GCS e opzionalmente carica su GCS."""
    parser = argparse.ArgumentParser(description="Scansiona bucket GCS e produce manifest")
    parser.add_argument("--upload", action="store_true", help="Carica il manifest su GCS")
    parser.add_argument("--pretty", action="store_true", help="Output JSON formattato")
    args = parser.parse_args()

    print("🔍 Scansione bucket GCS...", file=sys.stderr)
    manifest = build_manifest()

    print(
        f"   Trovati {manifest['file_count']} file, "
        f"{manifest['total_size_bytes'] / 1024 / 1024:.1f} MB",
        file=sys.stderr,
    )
    print(f"   Bucket: {', '.join(manifest['buckets'])}", file=sys.stderr)

    if args.upload:
        print("   Caricamento su GCS...", file=sys.stderr)
        upload_manifest(manifest)
        print(
            "   ✅ Pubblicato su gs://dataciviclab-clean/registry/gcs_manifest.json",
            file=sys.stderr,
        )
    else:
        indent = 2 if args.pretty else None
        print(json.dumps(manifest, indent=indent, ensure_ascii=False))


if __name__ == "__main__":
    main()
