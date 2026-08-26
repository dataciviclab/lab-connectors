"""Streamlit SQL query page — renderizza una pagina SQL interattiva.

Usage in una dashboard::

    from lab_connectors.duckdb.sql_page import render_sql_query

    # Nel file pages/05_SQL.py
    render_sql_query(years=[2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025])

    # Con prefix per repo con subdirectory GCS
    render_sql_query(years=[2020, 2021, 2022, 2023, 2024], prefix="conto-annuale/")

Requisiti: streamlit, duckdb, pandas (già in lab-connectors[duckdb]).
"""

from __future__ import annotations

import time


def render_sql_query(
    years: list[int],
    *,
    prefix: str = "",
    slug: str | None = None,
    max_rows: int = 1000,
    title: str = "🧪 Query SQL",
    description: str | None = None,
) -> None:
    """Render a full SQL query page in Streamlit.

    Args:
        years: Anni disponibili per il dataset.
        prefix: Prefisso GCS (es. "open-politica/", "conto-annuale/").
        slug: Slug del dataset per il clean layer. Se None, l'utente sceglie.
        max_rows: Limite massimo righe restituite.
        title: Titolo della pagina.
        description: Descrizione opzionale.

    """
    import streamlit as st

    st.title(title)
    st.markdown(
        description
        or (
            "Scrivi query **SQL** sui dati pubblici. "
            "Usa ``clean_input`` come nome della tabella virtuale — "
            "viene risolta automaticamente sui **Parquet GCS** per tutti gli anni."
        )
    )

    # ── Session state ────────────────────────────────────────────────────────

    if "sql_history" not in st.session_state:
        st.session_state.sql_history = []

    # ── Interfaccia ──────────────────────────────────────────────────────────

    col_sql, col_btn = st.columns([5, 1])
    with col_sql:
        sql = st.text_area(
            "SQL",
            value="SELECT * FROM clean_input LIMIT 10",
            height=100,
            key="sql_page_sql",
        )
    with col_btn:
        st.write("")
        st.write("")
        execute = st.button("▶ Esegui", key="sql_page_exec", use_container_width=True)

    # ── Esecuzione ───────────────────────────────────────────────────────────

    if execute and sql.strip():
        from lab_connectors.duckdb.queries import query_clean

        with st.spinner("Esecuzione su DuckDB..."):
            try:
                t0 = time.perf_counter()
                df = query_clean(
                    slug or _guess_slug(prefix),
                    sql,
                    years,
                    prefix=prefix,
                )
                elapsed = time.perf_counter() - t0

                n_rows = len(df)
                is_truncated = n_rows >= max_rows

                if is_truncated:
                    df = df.head(max_rows)

                # Metriche
                m1, m2 = st.columns(2)
                m1.metric("Righe restituite", f"{n_rows:,}")
                m2.metric("Tempo esecuzione", f"{elapsed:.2f}s")

                if n_rows == 0:
                    st.success("Query eseguita — 0 righe restituite.")
                else:
                    st.dataframe(df, width="stretch")

                    csv_data = df.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        ":material/download: Scarica CSV",
                        data=csv_data,
                        file_name=f"query_{int(time.time())}.csv",
                        mime="text/csv",
                    )

                # Storico
                st.session_state.sql_history.append(
                    {
                        "sql": sql[:80],
                        "rows": n_rows,
                        "time": f"{elapsed:.2f}s",
                    }
                )

            except Exception as e:
                st.error(f"Errore: {e}")

    # ── Storico ──────────────────────────────────────────────────────────────

    if st.session_state.sql_history:
        with st.expander("Storico query", expanded=False):
            for entry in reversed(st.session_state.sql_history[-10:]):
                st.caption(f"`{entry['sql']}` — {entry['rows']} righe · {entry['time']}")


def _guess_slug(prefix: str) -> str:
    """Indovina lo slug dal prefix (rimuove trailing slash)."""
    return prefix.rstrip("/").replace("-", "_") if prefix else "dataset"
