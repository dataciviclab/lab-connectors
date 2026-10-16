"""Pagina Registry interattiva riutilizzabile per ogni dashboard Streamlit.

Mostra il catalogo dataset di un repo (datasets, marts, signals, entities)
letto da registry/registry.json. Mappata sui dati reali del registry:
- Marts = puntatori a location (no schema nel registry)
- Codelists = sempre vuoti (non mostrati)
- Signals = sempre ok/SUCCESS

Usage::

    from lab_connectors.registry.registry_page import render_registry_page

    render_registry_page(registry=registry)
"""

from __future__ import annotations

from typing import Any


def render_registry_page(
    *,
    registry: Any,
    title: str = "📊 Registry",
    description: str = "",
    show_entities: bool = True,
) -> None:
    """Render a complete registry browsing page.

    Args:
        registry: Registry object (da load_registry()).
        title: Titolo della pagina.
        description: Descrizione opzionale sotto il titolo.
        show_entities: Mostra il tab Entities (se presenti).

    """
    import streamlit as st

    st.title(title)

    n_datasets = len(registry.datasets)
    n_marts = len(registry.marts)
    n_entities = len(registry.entities.get("entities", {}))
    n_bridges = len(registry.entities.get("bridges", []))

    if description:
        st.markdown(description)

    stat_cols = st.columns(4)
    stat_cols[0].metric("Datasets", n_datasets)
    stat_cols[1].metric("Marts", n_marts)
    stat_cols[2].metric("Entità", n_entities)
    stat_cols[3].metric("Bridges", n_bridges)

    st.caption(f"Repo **{registry.repo}** · Aggiornato: {registry.updated_at}")

    # ── Tabs ────────────────────────────────────────────────────────────────────
    tab_names = ["datasets", "marts"]
    if show_entities and (n_entities or n_bridges):
        tab_names.append("entities")

    tabs = st.tabs([t.capitalize() for t in tab_names])

    with tabs[0]:
        _render_datasets(registry)

    with tabs[1]:
        _render_marts(registry)

    if "entities" in tab_names:
        with tabs[tab_names.index("entities")]:
            _render_entities(registry)


# ── Datasets ───────────────────────────────────────────────────────────────────


def _render_datasets(registry: Any) -> None:
    import pandas as pd
    import streamlit as st

    datasets = registry.datasets
    if not datasets:
        st.info("Nessun dataset nel registry.")
        return

    # ── Tabella riassuntiva ─────────────────────────────────────────────────────
    rows = []
    for ds in datasets:
        period = ds.period or {}
        n_dims = sum(1 for c in (ds.columns or []) if c.role == "dimension")
        n_mets = sum(1 for c in (ds.columns or []) if c.role == "metric")
        sem_types = sorted({c.semantic_type for c in (ds.columns or []) if c.semantic_type})
        rows.append(
            {
                "slug": ds.slug,
                "nome": ds.name,
                "periodo": _fmt_period(period),
                "category": ds.category,
                "stage": ds.stage,
                "dims": n_dims,
                "metrics": n_mets,
                "semantic_types": ", ".join(sem_types),
            }
        )

    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    # ── Dettaglio dataset selezionato ───────────────────────────────────────────
    slug_list = [ds.slug for ds in datasets]
    selected = st.selectbox(
        "Dettaglio dataset",
        slug_list,
        key="reg_ds_select",
        label_visibility="collapsed",
    )

    if selected:
        ds = _find_dataset(registry, selected)
        if ds:
            _render_dataset_detail(ds)


def _render_dataset_detail(ds: Any) -> None:
    import pandas as pd
    import streamlit as st

    with st.expander(f"📋 {ds.slug}", expanded=True):
        # ── Info bar ────────────────────────────────────────────────────────────
        c1, c2, c3 = st.columns(3)
        c1.metric("Periodo", _fmt_period(ds.period or {}))
        c2.metric("Colonne", len(ds.columns or []))
        c3.metric("Stage", ds.stage or "—")

        if ds.tags:
            st.markdown(" ".join(f"`{t}`" for t in ds.tags))

        # ── Semantic summary ────────────────────────────────────────────────────
        cols = ds.columns or []
        sem_types = sorted({c.semantic_type for c in cols if c.semantic_type})
        if sem_types:
            sem_counts = {}
            for c in cols:
                if c.semantic_type:
                    sem_counts[c.semantic_type] = sem_counts.get(c.semantic_type, 0) + 1
            sem_text = " · ".join(f"`{k}` ×{v}" for k, v in sem_counts.items())
            st.markdown(f"**Semantic types:** {sem_text}")

        # ── Colonne per ruolo ───────────────────────────────────────────────────
        dims = [c for c in cols if c.role == "dimension"]
        mets = [c for c in cols if c.role == "metric"]

        col_dim, col_met = st.columns(2)

        with col_dim:
            st.markdown(f"**Dimensions** ({len(dims)})")
            if dims:
                dim_data = [
                    {"colonna": c.name, "tipo": c.type, "semantic": c.semantic_type or ""}
                    for c in dims
                ]
                st.dataframe(pd.DataFrame(dim_data), width="stretch", hide_index=True)

        with col_met:
            st.markdown(f"**Metrics** ({len(mets)})")
            if mets:
                met_data = [
                    {"colonna": c.name, "tipo": c.type, "semantic": c.semantic_type or ""}
                    for c in mets
                ]
                st.dataframe(pd.DataFrame(met_data), width="stretch", hide_index=True)
            else:
                st.caption("Nessuna metrica.")

        # ── Mart refs ───────────────────────────────────────────────────────────
        if ds.mart_refs:
            st.markdown("**Mart collegati:**")
            for ref in ds.mart_refs:
                st.code(ref, language="text")


# ── Marts ──────────────────────────────────────────────────────────────────────


def _render_marts(registry: Any) -> None:
    import pandas as pd
    import streamlit as st

    marts = registry.marts
    if not marts:
        st.info("Nessun mart nel registry.")
        return

    # I marts nel registry sono puntatori a location: slug, dataset, table, location.
    # Lo schema delle colonne vive nel parquet, non nel registry.
    rows = []
    for m in marts:
        short_slug = m.table or (m.slug.split("__")[-1] if "__" in m.slug else m.slug)
        rows.append(
            {
                "mart": short_slug,
                "dataset": m.dataset,
            }
        )

    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    # ── Location per ogni mart ──────────────────────────────────────────────────
    for m in marts:
        short_slug = m.table or (m.slug.split("__")[-1] if "__" in m.slug else m.slug)
        loc = m.location.path if m.location else ""
        if loc:
            st.caption(f"**{short_slug}** → `{loc}`")


# ── Entities ───────────────────────────────────────────────────────────────────


def _render_entities(registry: Any) -> None:
    import pandas as pd
    import streamlit as st

    entities_data = registry.entities.get("entities", {})
    bridges = registry.entities.get("bridges", [])

    # ── Bridges in evidenza ─────────────────────────────────────────────────────
    if bridges:
        st.subheader("Bridges (join indiretti)")
        st.caption("Collegano dataset tra loro attraverso entità condivise.")
        for b in bridges:
            frm = b.get("from", {})
            to = b.get("to", {})
            st.markdown(
                f"**{frm.get('entity', '')}** `{frm.get('dataset', '')}.{frm.get('via', '')}` → "
                f"**{to.get('entity', '')}** via `{to.get('bridge', '')}.{to.get('on', '')}`"
            )

    # ── Entities ────────────────────────────────────────────────────────────────
    if entities_data:
        st.subheader("Entità condivise")
        rows = []
        for name, info in entities_data.items():
            ds_list = info.get("datasets", [])
            types = info.get("types", {})
            rows.append(
                {
                    "entità": info.get("label", name),
                    "# dataset": len(ds_list),
                    "tipi": ", ".join(f"{k}({v})" for k, v in types.items()),
                    "dataset": ", ".join(d.get("slug", "") for d in ds_list),
                    "colonne": ", ".join(d.get("column", "") for d in ds_list),
                }
            )
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    if not entities_data and not bridges:
        st.info("Nessuna entità nel registry.")


# ── Helpers ────────────────────────────────────────────────────────────────────


def _fmt_period(period: dict) -> str:
    start = period.get("start")
    end = period.get("end")
    if start and end:
        return f"{start}–{end}"
    if start:
        return str(start)
    if end:
        return str(end)
    return "—"


def _find_dataset(registry: Any, slug: str) -> Any:
    for ds in registry.datasets:
        if ds.slug == slug:
            return ds
    return None
