"""Pagina SQL interattiva riutilizzabile per ogni dashboard Streamlit.

Replica l'UX di lab-dashboard/pages/09_Query_SQL.py, ma usando
lab_connectors.registry invece di lab-dashboard.sources.load_catalog().
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd


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
                use_container_width=True,
                hide_index=True,
            )

    # ── Anni disponibili ──────────────────────────────────────────────────────
    # Usa il period dal registry per il dataset selezionato
    period = ds_info.get("period", {})
    start = period.get("start")
    end = period.get("end")
    if start and end:
        ds_years = list(range(start, end + 1))
    elif years:
        ds_years = years
    else:
        ds_years = list(range(2017, 2026))

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
            use_container_width=True,
        )
    with col_hist:
        show_hist = st.button(
            "📜 Storico",
            use_container_width=True,
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
                # Risolvi slug → URL GCS
                urls, cte_expr, _ = _resolve_slug(
                    selected_slug, prefix, ds_years, multi_file=ds_info.get("multi_file", True)
                )
                wrapped_sql = _build_query(sql, cte_expr, max_rows)

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
                        use_container_width=True,
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
                "columns": cols,
            }
        )
    return datasets


def _resolve_slug(
    slug: str, prefix: str, years: list[int], multi_file: bool = True
) -> tuple[list[str], str, dict]:
    """Resolve slug → (urls, cte_expr, info).

    multi_file=True  → un Parquet per anno: {prefix}{slug}/{year}/{slug}_{year}_clean.parquet
    multi_file=False → singolo file flat:   {prefix}{slug}/{slug}_clean.parquet
    """
    from lab_connectors.gcs.paths import https_url

    if multi_file:
        urls = [
            https_url("clean", "clean_parquet", slug=slug, year=y, prefix=prefix) for y in years
        ]
    else:
        # File singolo: usa l'ultimo anno disponibile
        urls = [https_url("clean", "clean_parquet", slug=slug, year=years[-1], prefix=prefix)]

    if len(urls) == 1:
        cte_expr = f"SELECT * FROM read_parquet('{urls[0]}')"
    else:
        paths = "', '".join(urls)
        cte_expr = f"SELECT * FROM read_parquet(['{paths}'])"

    return urls, cte_expr, {"slug": slug, "years": years}


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
