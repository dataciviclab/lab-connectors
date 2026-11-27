"""Download una-tantum di oggetti pubblici GCS, con cache su disco.

Perché serve: DuckDB legge i parquet remoti a blocchi da ~128 KB e da alcune
reti ogni richiesta costa 150–250 ms. Una query che "legge 30 MB" fa ~200
viaggi e impiega minuti; lo stesso file da disco è istantaneo.

Chiave della cache: ``(bucket, path, generation)``. La ``generation`` di GCS
è immutabile per contenuto: un oggetto riscritto ha una generation nuova,
quindi la cache non può servire dati stantii per costruzione.

Il trasporto è ``HttpClient``/``object_generation`` di questo stesso package:
stessa catena di fallback TLS/proxy/curl del resto del Lab, nessun client
HTTP parallelo.

Kill switch: ``DCL_EXTERNAL_CACHE=off`` (o ``0``/``false``) disabilita la
cache lato chiamante (vedi ``cache_dir_from_env``). Errori di rete non sono
gestiti qui: il chiamante decide il fallback (leggere l'URL remoto).
"""

from __future__ import annotations

import hashlib
import os
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from lab_connectors.gcs.client import object_generation as _generation
from lab_connectors.http import HttpClient

CACHE_DIR_ENV = "DCL_EXTERNAL_CACHE"
GCS_HTTPS_PREFIX = "https://storage.googleapis.com/"
_DISABLED = {"off", "0", "false", "no"}
_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class FetchResult:
    """Esito di ``fetch_once``."""

    path: Path
    cached: bool
    bytes: int
    generation: str


def gcs_target(url: str) -> tuple[str, str] | None:
    """Restituisce ``(bucket, key)`` se l'URL è un oggetto GCS pubblico.

    Accetta ``gs://bucket/key`` e ``https://storage.googleapis.com/bucket/key``.
    Altri host (GitHub raw, CDN) non sono cacheabili qui: il chiamante li
    lascia come sono.
    """
    if url.startswith("gs://"):
        rest = url[5:]
    elif url.startswith(GCS_HTTPS_PREFIX):
        rest = url[len(GCS_HTTPS_PREFIX) :]
    else:
        return None
    bucket, _, key = rest.partition("/")
    if not bucket or not key:
        return None
    return bucket, urllib.parse.unquote(key)


def _https_url(bucket: str, key: str) -> str:
    return f"{GCS_HTTPS_PREFIX}{bucket}/{urllib.parse.quote(key, safe='/-_.')}"


def object_generation(url: str) -> str | None:
    """Restituisce la generation dell'oggetto per un URL ``gs://``/https GCS."""
    target = gcs_target(url)
    if target is None:
        return None
    return _generation(*target)


def _entry_path(cache_dir: Path, bucket: str, key: str, generation: str) -> Path:
    digest = hashlib.sha1(f"{bucket}/{key}".encode()).hexdigest()[:16]
    suffix = Path(key).suffix or ".bin"
    return cache_dir / bucket / f"{digest}-{generation}{suffix}"


def fetch_once(
    url: str,
    cache_dir: str | Path,
    *,
    timeout: int = 600,
    refresh: bool = False,
) -> FetchResult:
    """Rende locale un oggetto GCS, scaricandolo una volta sola.

    Args:
        url: ``gs://`` o ``https://storage.googleapis.com/…``.
        cache_dir: directory radice della cache.
        timeout: timeout del download (secondi).
        refresh: forza il download anche se la generation è già in cache.

    Raises:
        ValueError: URL non GCS.
        FileNotFoundError: oggetto assente.
        OSError: generation non ottenibile, errore di rete o di scrittura.

    """
    target = gcs_target(url)
    if target is None:
        raise ValueError(f"non è un oggetto GCS pubblico: {url}")
    bucket, key = target
    generation = _generation(bucket, key)
    if not generation:
        raise OSError(f"generation non ottenibile per {url}")

    root = Path(cache_dir)
    dest = _entry_path(root, bucket, key, generation)
    if not refresh and dest.is_file() and dest.stat().st_size > 0:
        # Rinfresca mtime/atime: su mount `noatime` l'atime resta quello della
        # creazione e `gc` cancellerebbe file usati ogni giorno.
        now = time.time()
        try:
            os.utime(dest, (now, now))
        except OSError:
            pass
        return FetchResult(path=dest, cached=True, bytes=0, generation=generation)

    dest.parent.mkdir(parents=True, exist_ok=True)
    # Nome temporaneo per processo: due run concorrenti non si pestano sul
    # file in scrittura (l'ultimo ``replace`` vince, contenuto identico).
    tmp = dest.with_name(f"{dest.name}.{os.getpid()}.part")
    client = HttpClient(timeout=timeout, max_retries=2)
    written = 0
    try:
        result = client.get(_https_url(bucket, key), stream=True)
        response = result.response
        if response is None:
            raise OSError(f"rete non disponibile per {url}: {result.err}")
        if response.status_code == 404:
            raise FileNotFoundError(url)
        if response.status_code >= 400:
            raise OSError(f"HTTP {response.status_code} su GET {url}")
        with tmp.open("wb") as out:
            for chunk in response.iter_content(chunk_size=_CHUNK):
                if isinstance(chunk, str):
                    chunk = chunk.encode()
                out.write(chunk)
                written += len(chunk)
        if written == 0:
            raise OSError(f"download vuoto per {url}")
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return FetchResult(path=dest, cached=False, bytes=written, generation=generation)


def default_cache_dir() -> Path:
    """Directory della cache per difetto: ``$XDG_CACHE_HOME/dcl-external``.

    Fuori dal repo di proposito: la cache è condivisa tra repo (più hit) e non
    sporca i worktree né i `.gitignore` dei consumer. In CI si cachea questa
    directory (o si imposta ``DCL_EXTERNAL_CACHE`` su un path del workspace).
    """
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base).expanduser() / "dcl-external"


def cache_dir_from_env(default: str | Path | None = None) -> Path | None:
    """Restituisce la directory della cache: env, ``default`` o quella utente.

    **In CI la cache è spenta per difetto** (``CI`` presente e
    ``DCL_EXTERNAL_CACHE`` non impostata). Su un runner effimero la cache non
    riusa nulla tra run: scaricare il file intero invece delle sole colonne
    usate peggiora l'egress. Chi vuole la cache in CI la abilita
    esplicitamente (``DCL_EXTERNAL_CACHE`` + ``actions/cache`` sulla stessa
    directory).

    ``DCL_EXTERNAL_CACHE=off`` (o 0/false/no) disabilita la cache e restituisce
    ``None``: il chiamante deve continuare a leggere l'URL remoto.
    """
    raw = os.environ.get(CACHE_DIR_ENV)
    if raw is not None:
        value = raw.strip()
        if not value or value.lower() in _DISABLED:
            return None
        return Path(value).expanduser()
    if os.environ.get("CI"):
        return None
    return Path(default).expanduser() if default is not None else default_cache_dir()


def gc(cache_dir: str | Path, keep_days: int = 90) -> int:
    """Rimuove le entry non usate da ``keep_days`` giorni; ritorna i file rimossi.

    Usa mtime, non atime: su mount ``noatime`` l'atime non viene aggiornato e
    file usati ogni giorno sembrerebbero vecchi. Ogni cache hit rinfresca il
    mtime (vedi ``fetch_once``).
    """
    root = Path(cache_dir)
    if not root.is_dir():
        return 0
    cutoff = time.time() - keep_days * 86400
    removed = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.name.endswith(".part"):
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed
