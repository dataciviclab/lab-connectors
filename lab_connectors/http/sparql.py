"""SPARQL over HTTP — executor, CSV fetch, named graph discovery, schema inference.

Tutte le funzioni condividono la stessa strategia di trasporto:
1. POST con form-encoded body (standard SPARQL protocol)
2. GET con query URL-encoded fallback (Virtuoso e altri)

Usano HttpClient per retry, SSL fallback, e User-Agent consistenti.

Pattern: funzioni pure (input → HTTP → output), nessuna orchestrazione.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, cast

import requests

from lab_connectors.http.client import HttpClient

log = logging.getLogger(__name__)

# Regex per individuare LIMIT/OFFSET già presenti in una query SPARQL
_RE_HAS_LIMIT = re.compile(r"\bLIMIT\s+\d+", re.IGNORECASE)

# Namespace SPARQL Results XML (W3C Standard)
_SPARQL_NS = "http://www.w3.org/2005/sparql-results#"


def _parse_sparql_xml(xml_text: str) -> list[dict[str, Any]]:
    """Parsa SPARQL Results XML in list[dict] identico al formato JSON.

    Standard: SPARQL 1.1 Query Results XML Format (W3C).
    https://www.w3.org/TR/rdf-sparql-XMLres/

    Args:
        xml_text: XML response body (application/sparql-results+xml).

    Returns:
        Lista di binding, ogni binding e' un dict
        ``{var: {"type": str, "value": str}}``.
        Lista vuota se la query non restituisce risultati.

    """
    ns = {"s": _SPARQL_NS}
    root = ET.fromstring(xml_text)

    results_elem = root.find("s:results", ns)
    if results_elem is None:
        return []

    bindings: list[dict[str, Any]] = []
    for result in results_elem.findall("s:result", ns):
        binding: dict[str, Any] = {}
        for b in result.findall("s:binding", ns):
            name = b.get("name")
            # Il binding ha un solo child: literal, uri, bnode o typed-literal
            child = next(iter(b), None)
            if child is None or name is None:
                continue

            # Estrai il tag locale (dopo il namespace)
            tag = child.tag
            local_tag = tag.split("}", 1)[-1] if "}" in tag else tag
            value = child.text or ""

            entry: dict[str, str] = {"type": local_tag, "value": value}

            if local_tag == "literal":
                lang = child.get("{http://www.w3.org/XML/1998/namespace}lang")
                if lang:
                    entry["xml:lang"] = lang
                datatype = child.get("datatype")
                if datatype and not lang:
                    entry["datatype"] = datatype
            elif local_tag == "typed-literal":
                datatype = child.get("datatype")
                if datatype:
                    entry["datatype"] = datatype

            binding[name] = entry
        bindings.append(binding)

    return bindings


def _sparql_post(
    client: HttpClient,
    endpoint: str,
    query: str,
) -> list[dict[str, Any]] | None:
    """Esegue query SPARQL via POST form-encoded. Restituisce bindings o None."""
    try:
        result = client.post(
            endpoint,
            {"query": query},
            headers={
                "Accept": "application/sparql-results+json,application/json",
            },
        )
        if result.is_error:
            return None
        resp = cast(requests.Response, result.response)
        content_type = (resp.headers.get("Content-Type") or "").lower()

        if "sparql-results+xml" in content_type:
            return _parse_sparql_xml(resp.text)
        payload = resp.json()
        return ((payload.get("results") or {}).get("bindings")) or []
    except Exception:
        return None


def _sparql_get(
    client: HttpClient,
    endpoint: str,
    query: str,
) -> list[dict[str, Any]] | None:
    """Esegue query SPARQL via GET con query URL-encoded. Restituisce bindings o None."""
    url = f"{endpoint}?query={urllib.parse.quote(query)}"
    try:
        result = client.get(
            url,
            headers={"Accept": "application/sparql-results+json,application/json"},
        )
        if result.is_error:
            return None
        resp = cast(requests.Response, result.response)
        content_type = (resp.headers.get("Content-Type") or "").lower()

        if "sparql-results+xml" in content_type:
            return _parse_sparql_xml(resp.text)
        payload = resp.json()
        return ((payload.get("results") or {}).get("bindings")) or []
    except Exception:
        return None


def execute_sparql(
    endpoint: str,
    query: str,
    timeout: int = 60,
) -> list[dict[str, Any]]:
    """Esegue una query SPARQL SELECT e restituisce i bindings.

    Tenta POST form-encoded (standard), poi GET URL-encoded (fallback).

    Args:
        endpoint: URL endpoint SPARQL.
        query: Query SPARQL SELECT.
        timeout: Timeout HTTP in secondi.

    Returns:
        Lista di bindings, ogni binding è un dict {var: {"type": ..., "value": ...}}.
        Lista vuota se la query non restituisce risultati.

    Raises:
        RuntimeError: se POST e GET falliscono entrambi.

    """
    client = HttpClient(timeout=timeout)

    bindings = _sparql_post(client, endpoint, query)
    if bindings is not None:
        return bindings

    bindings = _sparql_get(client, endpoint, query)
    if bindings is not None:
        return bindings

    raise RuntimeError(f"SPARQL query failed on {endpoint} (POST e GET fallback entrambi falliti)")


def fetch_csv(
    endpoint: str,
    query: str,
    timeout: int = 60,
    pages: int = 1,
    step: int = 50000,
) -> bytes:
    """Esegue una query SPARQL e restituisce i risultati come CSV bytes.

    Supporta paginazione automatica via LIMIT/OFFSET:
    - Se la query contiene già LIMIT, non viene modificata.
    - Se pages > 1, inietta OFFSET incrementali e concatena i risultati.

    Args:
        endpoint: URL endpoint SPARQL.
        query: Query SPARQL SELECT.
        timeout: Timeout HTTP per pagina.
        pages: Numero massimo di pagine (1 = nessuna paginazione).
        step: Dimensione della pagina (LIMIT).

    Returns:
        CSV bytes con header.

    """
    has_custom_limit = bool(_RE_HAS_LIMIT.search(query))
    limit_value = step

    if has_custom_limit:
        # Query con LIMIT esplicito — una sola fetch, nessuna paginazione
        return _fetch_csv_page(endpoint, query, timeout)

    # Inietta LIMIT/OFFSET sempre (funziona sia con che senza ORDER BY)
    query = query.rstrip().rstrip(";").rstrip()
    query += "\nLIMIT {limit}\nOFFSET {offset}"

    all_csv_parts: list[bytes] = []
    for page in range(pages):
        offset = page * limit_value
        page_query = query.replace("{limit}", str(limit_value)).replace("{offset}", str(offset))
        csv_bytes = _fetch_csv_page(endpoint, page_query, timeout)

        if page == 0:
            all_csv_parts.append(csv_bytes)
        else:
            # Salta header sulle pagine successive
            lines = csv_bytes.split(b"\n", 1)
            if len(lines) == 2:
                all_csv_parts.append(lines[1])
            else:
                all_csv_parts.append(csv_bytes)

        # Se questa pagina ha meno righe del limite, fermati
        if len(csv_bytes.split(b"\n")) < limit_value + 2:
            break

    # Concatena con newline tra le parti
    return b"\n".join(all_csv_parts)


def _fetch_csv_page(
    endpoint: str,
    query: str,
    timeout: int,
) -> bytes:
    """Esegue una singola pagina SPARQL e restituisce CSV bytes.

    Tenta:
    1. POST chiedendo text/csv
    2. POST chiedendo JSON, poi conversione a CSV
    3. GET chiedendo JSON, poi conversione a CSV
    """
    client = HttpClient(timeout=timeout)

    # Tentativo 1: POST con Accept: text/csv
    try:
        result = client.post(
            endpoint,
            {"query": query},
            headers={
                "Accept": "text/csv,text/plain;q=0.5",
            },
        )
        if result.is_ok:
            resp = cast(requests.Response, result.response)
            content_type = (resp.headers.get("Content-Type") or "").lower()
            body = resp.content
            if "csv" in content_type or _looks_like_csv(body):
                return body
    except Exception:
        pass

    # Tentativo 2: POST con Accept JSON → conversione
    bindings = _sparql_post(client, endpoint, query)
    if bindings is not None:
        return _bindings_to_csv(bindings)

    # Tentativo 3: GET con Accept JSON → conversione
    bindings = _sparql_get(client, endpoint, query)
    if bindings is not None:
        return _bindings_to_csv(bindings)

    raise RuntimeError(f"SPARQL CSV fetch failed on {endpoint} (POST/GET + CSV/JSON tutti falliti)")


def _looks_like_csv(data: bytes) -> bool:
    """Euristica: se la risposta contiene virgole e newline, probabile CSV."""
    try:
        text = data.decode("utf-8", errors="replace")
        first_line = text.split("\n")[0] if text else ""
        return "," in first_line and len(first_line) < 500
    except Exception:
        return False


def _bindings_to_csv(bindings: list[dict[str, Any]]) -> bytes:
    """Convert SPARQL Results JSON bindings to CSV bytes.

    Uses the first binding to determine columns,
    then extracts `.value` from each variable.
    """
    import csv
    import io

    if not bindings:
        return b""

    # Colonna = tutte le chiavi presenti nel primo binding
    columns = list(bindings[0].keys())
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    for binding in bindings:
        row = []
        for col in columns:
            entry = binding.get(col)
            row.append(entry.get("value", "") if entry else "")
        writer.writerow(row)
    return output.getvalue().encode("utf-8")


def discover_graphs(
    endpoint: str,
    timeout: int = 60,
    prefix: str = "",
    blacklist: list[str] | None = None,
) -> list[str]:
    """Enumera tutti i named graphs di un endpoint SPARQL.

    Esclude i grafi interni del database Virtuoso
    (es. localhost, virtrdf, owl).

    Args:
        endpoint: URL endpoint SPARQL.
        timeout: Timeout HTTP in secondi.
        prefix: Se specificato, include solo grafi che iniziano con questo prefisso.
        blacklist: Esclude grafi che contengono queste stringhe (case-sensitive).

    Returns:
        Lista di URI dei named graphs, ordinati alfabeticamente.

    """
    query = """
    SELECT DISTINCT ?g
    WHERE { GRAPH ?g { ?s ?p ?o } }
    ORDER BY ?g
    """.strip()

    bindings = execute_sparql(endpoint, query, timeout=timeout)

    blacklist = _ensure_str_list(
        blacklist
        or [
            "localhost",
            "virtrdf",
            "owl#",
            "8890",
        ]
    )
    graphs: list[str] = []
    for binding in bindings:
        g = _binding_value(binding, "g")
        if not g:
            continue
        if prefix and not g.startswith(prefix):
            continue
        if any(blk in g for blk in blacklist):
            continue
        graphs.append(g)
    return graphs


def infer_schema(
    endpoint: str,
    graph_uri: str,
    timeout: int = 60,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Estrae i predicati (≈ colonne) usati in un named graph.

    Per ogni predicato restituisce il conteggio di soggetti distinti
    che lo usano — equivalente alla copertura di una colonna in un CSV.

    Args:
        endpoint: URL endpoint SPARQL.
        graph_uri: URI del named graph da analizzare.
        timeout: Timeout HTTP in secondi.
        limit: Massimo numero di predicati da restituire.

    Returns:
        Lista di dict: {pred, compact_name, count}
        Ordinati per count decrescente.

    """
    query = f"""
    SELECT ?pred (COUNT(DISTINCT ?s) as ?cnt)
    WHERE {{ GRAPH <{graph_uri}> {{ ?s ?pred ?o }} }}
    GROUP BY ?pred
    ORDER BY DESC(?cnt)
    LIMIT {limit}
    """.strip()

    bindings = execute_sparql(endpoint, query, timeout=timeout)
    return _build_schema_list(bindings)


def _build_schema_list(bindings: list[dict]) -> list[dict]:
    """Costruisce lista predicati da bindings SPARQL."""
    result: list[dict] = []
    for b in bindings:
        pred_uri = _binding_value(b, "pred") or ""
        cnt_str = _binding_value(b, "cnt") or "0"
        try:
            cnt = int(cnt_str)
        except (ValueError, TypeError):
            cnt = 0
        result.append(
            {
                "pred": pred_uri,
                "compact_name": _compact_uri(pred_uri),
                "count": cnt,
            }
        )
    return result


def _binding_value(binding: dict[str, Any], key: str) -> Any:
    """Estrae il valore da un binding SPARQL Results JSON."""
    entry = binding.get(key)
    if entry is None:
        return None
    return entry.get("value")


def _flatten_binding(binding: dict[str, Any]) -> dict[str, Any]:
    """Riduce un binding ``{var: {"value": ...}}`` a ``{var: value}``."""
    return {key: _binding_value(binding, key) for key in binding}


def execute_sparql_rows(
    endpoint: str,
    query: str,
    timeout: int = 60,
) -> list[dict[str, Any]]:
    """Come :func:`execute_sparql` ma con binding piatti ``{variabile: valore}``.

    Forma comoda per gli script di estrazione, che non hanno bisogno di
    ``type``/``datatype``.
    """
    return [_flatten_binding(b) for b in execute_sparql(endpoint, query, timeout=timeout)]


def curl_sparql(
    endpoint: str,
    query: str,
    accept: str,
    timeout: int = 60,
    method: str = "POST",
) -> tuple[int, bytes, str] | None:
    """Esegue una query SPARQL con il binario curl.

    Serve per gli endpoint che bloccano il TLS fingerprint delle librerie
    Python (es. dati.senato.it). Non solleva: ritorna ``None`` se curl non è
    disponibile o fallisce, così il chiamante propaga l'errore originale.

    Returns:
        ``(status, body, content_type)`` oppure ``None``.

    """
    cmd = [
        "curl",
        "-sS",
        "--max-time",
        str(int(timeout)),
        "-A",
        "Mozilla/5.0 DataCivicLab/1.0",
        "-H",
        f"Accept: {accept}",
    ]
    if method == "GET":
        cmd.append("-G")
    cmd += [
        "--data-urlencode",
        f"query={query}",
        "-w",
        "\n%{http_code}|%{content_type}",
        "--",
        endpoint,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout + 5, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.debug("curl SPARQL non disponibile: %s", exc)
        return None
    if r.returncode != 0:
        log.debug("curl SPARQL exit=%d: %s", r.returncode, r.stderr[:200])
        return None

    raw = r.stdout
    idx = raw.rfind(b"\n")
    if idx < 0:
        return None
    meta = raw[idx + 1 :].decode("utf-8", errors="replace").strip()
    status_s, _, content_type = meta.partition("|")
    if not status_s.isdigit():
        return None
    return int(status_s), raw[:idx], content_type


def execute_sparql_rows_curl(
    endpoint: str,
    query: str,
    timeout: int = 60,
) -> list[dict[str, Any]]:
    """Come :func:`execute_sparql_rows` ma passa da curl (endpoint con WAF TLS).

    Raises:
        RuntimeError: curl non disponibile, HTTP non-200 o risposta non JSON.

    """
    out = curl_sparql(
        endpoint,
        query,
        "application/sparql-results+json",
        timeout=timeout,
        method="GET",
    )
    if out is None:
        raise RuntimeError(f"SPARQL curl failed on {endpoint} (curl non disponibile o errore)")
    status, body, _ = out
    if status != 200:
        raise RuntimeError(f"SPARQL curl HTTP {status} on {endpoint}")
    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        preview = body[:120].decode("utf-8", errors="replace")
        raise RuntimeError(f"SPARQL curl: risposta non JSON su {endpoint}: {preview!r}") from exc
    bindings = ((payload.get("results") or {}).get("bindings")) or []
    return [_flatten_binding(b) for b in bindings]


def _compact_uri(uri: str) -> str:
    """Compatta un URI in nome leggibile (ultimo segmento o frammento)."""
    if not uri:
        return ""
    if "#" in uri:
        return uri.rsplit("#", 1)[-1]
    return uri.rstrip("/").rsplit("/", 1)[-1]


def _ensure_str_list(items: list[Any]) -> list[str]:
    """Assicura che tutti gli elementi siano stringhe (YAML può parsare int)."""
    return [str(i) for i in items]
