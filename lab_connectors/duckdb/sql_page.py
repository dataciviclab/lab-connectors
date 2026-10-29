"""Pagina SQL interattiva riutilizzabile per ogni dashboard Streamlit.

Replica l'UX di lab-dashboard/pages/09_Query_SQL.py, ma usando
lab_connectors.registry invece di lab-dashboard.sources.load_catalog().
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def render_sql_query(
    *,
    registry: Any,
    years: list[int] | None = None,
    prefix: str = "",
    default_slug: str | None = None,
    title: str = "🧪 Query SQL",
    description: str = (
        "Scrivi query SQL sui dataset pubblici. "
        "Usa ``clean_input`` come nome della tabella virtuale — "
        "viene risolta automaticamente sui Parquet GCS."
    ),
    max_rows: int = 1000,
) -> None:
    """Render a complete SQL query page.

    Args:
        registry: Registry object (da load_registry()).
        years: Anni disponibili (se None, presi dal registry).
        prefix: Prefisso GCS per il path contract.
        default_slug: Slug preselezionato (se None, primo del registry).
        title: Titolo della pagina.
        description: Descrizione sotto il titolo.
        max_rows: Numero massimo di righe da restituire.

    """
    import duckdb
    import streamlit as st

    st.title(title)
    st.markdown(description)

    # ── Dataset disponibili ────────────────────────────────────────────────────
    datasets = _get_datasets_with_columns(registry)
    slug_list = [ds["slug"] for ds in datasets]
    slug_to_ds = {ds["slug"]: ds for ds in datasets}

    if not slug_list:
        st.error("Nessun dataset trovato nel registry.")
        return

    # ── Selectbox dataset ──────────────────────────────────────────────────────
    idx = 0
    if default_slug and default_slug in slug_list:
        idx = slug_list.index(default_slug)

    selected_slug = st.selectbox(
        "📋 Dataset",
        slug_list,
        index=idx,
        format_func=lambda s: f"{s} ({len(slug_to_ds[s]['columns'])} colonne)",
    )

    ds_info = slug_to_ds[selected_slug]

    # ── Schema colonne ─────────────────────────────────────────────────────────
    if ds_info["columns"]:
        with st.expander(f"Schema: {selected_slug}", expanded=False):
            st.dataframe(
                pd.DataFrame(ds_info["columns"]),
                width="stretch",
                hide_index=True,
            )

    # ── Anni disponibili ──────────────────────────────────────────────────────
    # Usa il period dal registry per il dataset selezionato
    period = ds_info.get("period", {})
    start = period.get("start")
    end = period.get("end")

    if years:
        ds_years = years
    elif start and end:
        ds_years = list(range(start, end + 1))
    else:
        ds_years = [2026]

    if ds_info.get("location_path"):
        # il layout reale viene da location.path: `period` resta solo un'etichetta
        st.caption(
            f"Periodo nel registry: {ds_years[0]}–{ds_years[-1]} ({len(ds_years)} anni) · "
            "file clean risolti dal layout (``location.path``)"
        )
    else:
        st.caption(
            f"Anni: {ds_years[0]}–{ds_years[-1]} ({len(ds_years)} anni) · "
            f"CTE ``clean_input`` risolta su {len(ds_years)} file Parquet"
        )

    # ── Editor SQL ─────────────────────────────────────────────────────────────
    default_sql = st.session_state.get("sql_query_sql", _default_query(selected_slug))
    sql = st.text_area(
        "SQL",
        value=default_sql,
        height=150,
        key="sql_query_sql",
        label_visibility="collapsed",
        help="Usa 'clean_input' come tabella. La CTE viene risolta automaticamente.",
    )

    # ── Pulsanti ───────────────────────────────────────────────────────────────
    col_exec, col_hist = st.columns([3, 1])
    with col_exec:
        execute = st.button(
            "▶️ Esegui",
            type="primary",
            width="stretch",
        )
    with col_hist:
        show_hist = st.button(
            "📜 Storico",
            width="stretch",
        )

    # ── Storico ────────────────────────────────────────────────────────────────
    history = st.session_state.setdefault("sql_history", [])

    if show_hist and history:
        st.subheader("📜 Storico")
        for i, entry in enumerate(reversed(history[-8:])):
            label = entry["sql"][:60].replace("\n", " ")
            if len(entry["sql"]) > 60:
                label += "…"
            col_a, col_b = st.columns([6, 1])
            with col_a:
                if st.button(
                    f"`{entry['slug']}` {label}",
                    key=f"hist_{i}",
                    help=f"{entry['rows']} righe · {entry['time']}",
                ):
                    st.session_state.sql_query_sql = entry["sql"]
                    st.rerun()
            with col_b:
                st.caption(f"{entry['rows']} rows")
        if st.button("Svuota storico", key="clear_hist"):
            st.session_state.sql_history = []
            st.rerun()

    # ── Esecuzione query ───────────────────────────────────────────────────────
    if execute:
        with st.spinner(f"Esecuzione su `{selected_slug}` via DuckDB…"):
            try:
                # layout del dataset → URL GCS. `location.path` è il contratto del
                # toolkit; se il registry non lo espone (dataset mart-only) non c'è
                # nessun layer clean da interrogare.
                location_path = ds_info.get("location_path", "")
                if not location_path:
                    st.info(
                        "Questo dataset non espone un layer **clean** "
                        "(`location.path` assente nel registry, tipicamente un dataset "
                        "mart-only): non è interrogabile qui."
                    )
                    return
                urls = _urls_from_location(location_path)
                if not urls:
                    # location.path c'è ma il layout non risolve (glob senza match,
                    # registry disallineato). Ricadiamo sulla convenzione per anno:
                    # per i dataset con offset 1 è il comportamento che dava 404,
                    # quindi va reso visibile invece di restare silenzioso.
                    logger.warning(
                        "layout non risolto da location.path (%s): fallback sugli anni %s-%s",
                        location_path,
                        ds_years[0],
                        ds_years[-1],
                    )
                    st.caption(
                        "⚠️ Layout non risolto dal registry: file clean dedotti dagli anni "
                        f"{ds_years[0]}–{ds_years[-1]}."
                    )
                    urls = _urls_from_years(
                        selected_slug, prefix, ds_years, ds_info.get("multi_file", True)
                    )
                wrapped_sql = _build_query(sql, _cte_from_urls(urls), max_rows)

                # Esegui
                t0 = time.perf_counter()
                with duckdb.connect() as con:
                    df = con.sql(wrapped_sql).df()
                elapsed = time.perf_counter() - t0

                n_rows = len(df)
                is_truncated = n_rows >= max_rows

                # Metriche
                m1, m2, m3 = st.columns(3)
                m1.metric("Righe restituite", f"{n_rows:,}")
                m2.metric("Tempo esecuzione", f"{elapsed:.2f}s")
                file_label = "1 file" if len(urls) == 1 else f"{len(urls)} file"
                m3.metric("Parquet letti", file_label)

                if is_truncated:
                    st.info(
                        f"Risultato troncato a {max_rows} righe. "
                        "Aumenta il limite o aggiungi ``LIMIT`` nella query."
                    )

                if n_rows == 0 and not is_truncated:
                    st.success("Query eseguita correttamente — **0 righe** restituite.")
                elif n_rows > 0:
                    st.dataframe(
                        df,
                        width="stretch",
                        column_config={
                            col: st.column_config.Column(col, width="medium")
                            for col in df.columns[:8]
                        },
                    )

                    # Download CSV
                    csv_data = df.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        ":material/download: Scarica CSV",
                        data=csv_data,
                        file_name=f"{selected_slug}_query_{int(time.time())}.csv",
                        mime="text/csv",
                    )

                # Storico
                st.session_state.sql_history.append(
                    {
                        "slug": selected_slug,
                        "sql": sql,
                        "rows": n_rows,
                        "time": f"{elapsed:.2f}s",
                    }
                )

                # SQL eseguita in expander (debug)
                with st.expander("SQL effettivamente eseguita", expanded=False):
                    st.code(wrapped_sql, language="sql")

            except Exception as e:
                st.error(f"Errore durante l'esecuzione: {e}")
                if "404" in str(e):
                    st.info(
                        "Il file Parquet non è stato trovato su GCS. "
                        "Prova con un anno diverso — potrebbe non essere stato pubblicato."
                    )
                if "wrapped_sql" in locals():
                    with st.expander("SQL che ha causato l'errore", expanded=True):
                        st.code(wrapped_sql, language="sql")


# ── Helper interni ─────────────────────────────────────────────────────────────


def _get_datasets_with_columns(registry: Any) -> list[dict[str, Any]]:
    """Extract datasets with columns from registry."""
    datasets = []
    for ds in registry.datasets:
        cols = [
            {
                "colonna": c.name,
                "tipo": c.type,
                "ruolo": c.role,
                "descrizione": c.description or "",
            }
            for c in (ds.columns or [])
        ]
        datasets.append(
            {
                "slug": ds.slug,
                "name": ds.name,
                "description": ds.description or "",
                "period": ds.period or {},
                "multi_file": ds.location.multi_file if ds.location else True,
                "location_path": ds.location.path if ds.location else "",
                "columns": cols,
            }
        )
    return datasets


def _urls_from_location(location_path: str) -> list[str]:
    """URL HTTPS dei parquet clean descritti da ``location.path``.

    ``location.path`` è il contratto del layout scritto dal toolkit: può essere un
    singolo file (``multi_file: false``) o un glob, come
    ``gs://bucket/prefix/<slug>/*/<slug>_*_clean.parquet``.

    Il glob va espanso **listando il bucket** (GCS JSON API, accesso anonimo ai
    bucket pubblici): DuckDB non espande i glob su HTTPS
    (``Globs (`*`) for generic HTTP file are not supported``).

    Ritorna ``[]`` se il path non è ``gs://``, se il glob non produce match o se il
    listing fallisce: il chiamante ricade sulla ricostruzione per anno.
    """
    from lab_connectors.gcs.client import list_objects
    from lab_connectors.gcs.paths import glob_to_regex, parse_gs_url, public_url

    try:
        bucket, key = parse_gs_url(location_path)
    except ValueError:
        return []

    # singolo file: nessun glob da espandere
    if "*" not in key:
        return [public_url(location_path)]

    # il listing si ferma al prefisso che precede il primo '*'
    prefix = key[: key.index("*")]
    prefix = prefix[: prefix.rfind("/") + 1]
    try:
        items = list_objects(bucket, prefix=prefix, auth=False)
    except Exception:  # rete/permessi: meglio il fallback che un errore in pagina
        return []

    pattern = re.compile(glob_to_regex(key))
    return sorted(
        public_url(f"gs://{bucket}/{item['name']}")
        for item in items
        if pattern.match(item.get("name", ""))
    )


def _cte_from_urls(urls: list[str]) -> str:
    """CTE ``clean_input`` da una lista di URL parquet."""
    if len(urls) == 1:
        return f"SELECT * FROM read_parquet('{urls[0]}')"
    paths = "', '".join(urls)
    return f"SELECT * FROM read_parquet(['{paths}'])"


def _build_query(sql: str, cte_expr: str, max_rows: int) -> str:
    """Wrap user SQL with CTE and LIMIT."""
    q = sql.strip().rstrip(";")
    if not q.upper().startswith("WITH"):
        q = f"WITH clean_input AS ({cte_expr}) {q}"
    if "LIMIT" not in q.upper():
        q += f" LIMIT {max_rows}"
    return q


def _default_query(slug: str) -> str:
    """Default query for a slug."""
    return "SELECT * FROM clean_input LIMIT 10"


def _urls_from_years(
    slug: str, prefix: str, years: list[int], multi_file: bool = True
) -> list[str]:
    """URL clean dagli anni (convenzione ``{prefix}{slug}/{year}/...``).

    Usata solo se ``location.path`` non risolve: è la convenzione storica, che
    assume che gli anni passati siano anche i nomi delle cartelle. Tiene
    ``prefix`` e ``multi_file`` significativi per i registry che non espongono
    ``location.path``.
    """
    from lab_connectors.gcs.paths import https_url

    anni = years if multi_file else years[-1:]
    return [https_url("clean", "clean_parquet", slug=slug, year=y, prefix=prefix) for y in anni]
