from __future__ import annotations

import sys
from pathlib import Path
import threading
from typing import Any

from mcp.server.fastmcp import FastMCP

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from gcs_client import (
    GcsClientError,
    check_public as check_public_impl,
    list_objects as list_objects_impl,
    warmup as _warmup,
)


threading.Thread(target=_warmup, daemon=True).start()

mcp = FastMCP(
    name="gcs",
    instructions=(
        "Connector MCP read-only per una minima ispezione di Google Cloud Storage. "
        "Usalo per elencare oggetti in bucket noti e verificare URL pubblici GCS."
    ),
)


def _guard(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return fn(*args, **kwargs)
    except GcsClientError as exc:
        return {"error": str(exc)}


@mcp.tool(description="Elenca oggetti in un bucket GCS con prefisso opzionale.", structured_output=True)
def gcs_list_objects(bucket: str, prefix: str = "") -> dict[str, Any]:
    return _guard(list_objects_impl, bucket, prefix or None)


@mcp.tool(description="Verifica se un URL pubblico GCS e' raggiungibile.", structured_output=True)
def gcs_check_public(url: str) -> dict[str, Any]:
    return _guard(check_public_impl, url)


if __name__ == "__main__":
    mcp.run()
