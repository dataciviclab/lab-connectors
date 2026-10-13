"""Tests per discovery.infer — inferenze pure.

pure_unit: infer_years, infer_years_from_columns, suggest_years,
           infer_granularity, infer_granularity_from_name_and_columns, infer_topics
"""

from __future__ import annotations

import pytest

from lab_connectors.discovery.infer import (
    extract_years_from_columns,
    extract_years_from_filename,
    infer_granularity,
    infer_granularity_from_name_and_columns,
    infer_topics,
    infer_years,
    infer_years_from_columns,
    suggest_years,
)


class TestInferYears:
    """pure_unit: estrazione anni minimo/massimo da testo."""

    @pytest.mark.pure_unit
    @pytest.mark.parametrize(
        "text,expected_min,expected_max",
        [
            ("dataset-2015-2023.csv", 2015, 2023),
            ("data_2020", 2020, 2020),
            ("serie_storica_2010_2025", 2010, 2025),
            ("no-years-here", None, None),
            ("report_2022", 2022, 2022),
            ("anni 2018 2019 2020", 2018, 2020),
            ("", None, None),
            # Anni compatti
            ("202122", 2021, 2022),
            ("dati_202122_v1", 2021, 2022),
            # Anni adiacenti
            ("20142025", 2014, 2025),
        ],
    )
    def test_infer_years(
        self, text: str, expected_min: int | None, expected_max: int | None
    ) -> None:
        result = infer_years(text)
        assert result == (expected_min, expected_max), (
            f"infer_years({text!r}) = {result}, expected ({expected_min}, {expected_max})"
        )


class TestInferYearsFromColumns:
    """pure_unit: estrazione anni da nomi colonna."""

    @pytest.mark.pure_unit
    def test_year_in_column_name(self):
        assert infer_years_from_columns(["anno_2020", "valore"]) == (2020, 2020)

    @pytest.mark.pure_unit
    def test_multiple_years_joined(self):
        """Colonne multiple: anni uniti."""
        assert infer_years_from_columns(["pop_2015", "pop_2023"]) == (2015, 2023)

    @pytest.mark.pure_unit
    def test_multi_year_in_single_column(self):
        """Una colonna con range: anni espansi."""
        assert infer_years_from_columns(["pop_2015_2023"]) == (2015, 2023)

    @pytest.mark.pure_unit
    def test_no_years(self):
        assert infer_years_from_columns(["nome", "valore"]) == (None, None)

    @pytest.mark.pure_unit
    def test_empty_columns(self):
        assert infer_years_from_columns([]) == (None, None)

    @pytest.mark.pure_unit
    def test_extract_years_from_columns_alias(self):
        """Alias backward-compat."""
        assert extract_years_from_columns(["anno_2020"]) == (2020, 2020)


class TestExtractYearsFromFilename:
    """pure_unit: estrazione anni da filename."""

    @pytest.mark.pure_unit
    def test_years_in_filename(self):
        assert extract_years_from_filename("beneficiari_2007-2013.zip") == [2007, 2013]

    @pytest.mark.pure_unit
    def test_no_years(self):
        assert extract_years_from_filename("report.csv") == []

    @pytest.mark.pure_unit
    def test_only_20xx(self):
        assert extract_years_from_filename("data_1999.csv") == []


class TestSuggestYears:
    """pure_unit: suggest_years da colonne e profilo."""

    @pytest.mark.pure_unit
    def test_from_columns(self):
        years = suggest_years(column_names=["anno", "valore"])
        assert years == [2024], f"got {years}"

    @pytest.mark.pure_unit
    def test_from_columns_with_numbers(self):
        years = suggest_years(column_names=["2020", "2021", "2022", "valore"])
        assert years == [2020, 2021, 2022], f"got {years}"

    @pytest.mark.pure_unit
    def test_range_expansion(self):
        """Range di anni viene espanso."""
        years = suggest_years(column_names=["val_2020", "val_2022"])
        assert years == [2020, 2021, 2022], f"got {years}"

    @pytest.mark.pure_unit
    def test_year_values_priority(self):
        """year_values ha priorità su colonne."""
        years = suggest_years(column_names=["val_2020"], year_values={2015, 2016, 2017})
        assert years == [2015, 2016, 2017], f"got {years}"

    @pytest.mark.pure_unit
    def test_fallback(self):
        years = suggest_years()
        assert years == [2024], f"got {years}"


class TestInferGranularity:
    """pure_unit: infer_granularity da testo."""

    @pytest.mark.pure_unit
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("popolazione residente nei comuni", "comune"),
            ("dati provinciali istat", "provincia"),
            ("statistiche nazionali italia", "nazionale"),
            ("indicatori a livello europeo", "europeo"),
            ("dati globali mondo", "mondiale"),
            ("rumore bianco", "non_determinato"),
            ("", "non_determinato"),
            # Region names
            ("indicatori piemonte", "regione"),
            ("dati lombardia", "regione"),
            ("statistiche veneto", "regione"),
            # Nazione / national / ue
            ("dati della nazione", "nazionale"),
            ("national statistics", "nazionale"),
            ("report ue", "europeo"),
        ],
    )
    def test_granularity(self, text: str, expected: str) -> None:
        assert infer_granularity(text) == expected


class TestInferGranularityFromNameAndColumns:
    """pure_unit: infer_granularity_from_name_and_columns."""

    @pytest.mark.pure_unit
    def test_comune_from_codice_comune_column(self):
        result = infer_granularity_from_name_and_columns("", ["CODICE_COMUNE"])
        assert result == "comune"

    @pytest.mark.pure_unit
    def test_comune_from_column_name(self):
        result = infer_granularity_from_name_and_columns("", ["Comune", "Anno"])
        assert result == "comune"

    @pytest.mark.pure_unit
    def test_provincia_from_column(self):
        result = infer_granularity_from_name_and_columns("", ["Provincia", "Importo"])
        assert result == "provincia"

    @pytest.mark.pure_unit
    def test_prov_abbreviation(self):
        """Sigla 'prov' riconosciuta."""
        result = infer_granularity_from_name_and_columns("", ["prov", "valore"])
        assert result == "provincia"

    @pytest.mark.pure_unit
    def test_regione_from_column(self):
        result = infer_granularity_from_name_and_columns("", ["REGIONE", "Anno"])
        assert result == "regione"

    @pytest.mark.pure_unit
    def test_codreg_abbreviation(self):
        """Sigla 'codreg' riconosciuta."""
        result = infer_granularity_from_name_and_columns("", ["codreg", "valore"])
        assert result == "regione"

    @pytest.mark.pure_unit
    def test_fallback_on_name_when_no_geo_columns(self):
        result = infer_granularity_from_name_and_columns(
            "Popolazione residente nei comuni", ["Reddito", "Anno"]
        )
        assert result == "comune"

    @pytest.mark.pure_unit
    def test_non_determinato_without_geo_hints(self):
        result = infer_granularity_from_name_and_columns("Dati generici", ["Nome", "Valore"])
        assert result == "non_determinato"

    @pytest.mark.pure_unit
    def test_non_string_columns_ignored(self):
        """Colonne non-stringhe vengono ignorate senza crash."""
        result = infer_granularity_from_name_and_columns("Dati", [2020, "regione"])
        assert result == "regione"


class TestInferTopics:
    """pure_unit: infer_topics da testo."""

    @pytest.mark.pure_unit
    def test_demografia(self):
        topics = infer_topics("popolazione residente per regione")
        assert len(topics) > 0
        assert any(t["topic"] == "demografia" for t in topics)

    @pytest.mark.pure_unit
    def test_multiple_topics(self):
        topics = infer_topics("lavoro e economia in italia")
        topics_found = [t["topic"] for t in topics]
        assert "lavoro" in topics_found
        assert "economia" in topics_found

    @pytest.mark.pure_unit
    def test_accented_keywords(self):
        """Keyword con accenti funzionano."""
        topics = infer_topics("statistiche sulla sanità italiana")
        assert any(t["topic"] == "sanita" for t in topics)

    @pytest.mark.pure_unit
    def test_inps_keyword(self):
        """Keyword 'inps' riconosciuta."""
        topics = infer_topics("pensioni inps")
        assert any(t["topic"] == "previdenza" for t in topics)

    @pytest.mark.pure_unit
    def test_no_match(self):
        topics = infer_topics("xyzabc123")
        assert topics == []

    @pytest.mark.pure_unit
    def test_ordered_by_score(self):
        topics = infer_topics("lavoro economia lavoro economia lavoro")
        scores = [t["score"] for t in topics]
        assert scores == sorted(scores, reverse=True), "topics should be ordered by score desc"
