"""Tests for lab_connectors.textmatch — shared query-matching primitives."""

from __future__ import annotations

from lab_connectors.textmatch import (
    query_matches,
    query_tokens,
    query_words,
    token_in_text,
    word_forms,
)


class TestQueryWords:
    def test_snake_case_split(self):
        assert query_words("anac_bandi_gara") == ["anac", "bandi", "gara"]

    def test_deaccent_and_punctuation(self):
        assert query_words("spesa più recente!") == ["spesa", "piu", "recente"]

    def test_none_and_empty(self):
        assert query_words(None) == []
        assert query_words("") == []


class TestQueryTokens:
    def test_drops_stopwords(self):
        assert query_tokens("bandi di gara") == ["bandi", "gara"]
        assert query_tokens("appalti pubblici ANAC") == ["appalti", "pubblici", "anac"]

    def test_drops_accents_and_short(self):
        assert query_tokens("spesa più recente") == ["spesa", "recente"]
        assert query_tokens("e") == []
        assert query_tokens("di dei delle") == []

    def test_dedupes(self):
        assert query_tokens("gara gara bandi") == ["gara", "bandi"]


class TestWordForms:
    def test_plural_gender(self):
        assert word_forms("gara") & word_forms("gare")
        assert word_forms("pubblico") & word_forms("pubblici")
        assert word_forms("appalto") & word_forms("appalti")

    def test_short_words_not_stripped(self):
        assert word_forms("akn") == {"akn"}


class TestTokenInText:
    def test_whole_word_and_morphology(self):
        assert token_in_text("gara", "bandi di gara pubblici")
        assert token_in_text("gare", "bandi di gara pubblici")

    def test_prefix(self):
        assert token_in_text("pension", "pensioni inps")
        assert token_in_text("pen", "pensioni inps")  # 3 chars: allowed prefix
        assert not token_in_text("pe", "pensioni inps")  # < 3 chars

    def test_no_substring_false_positive(self):
        assert not token_in_text("appalti", "n_subappalti")
        assert token_in_text("appalti", "appalti pubblici")

    def test_snake_case_field(self):
        assert token_in_text("bandi", "anac_bandi_gara")


class TestQueryMatches:
    def test_cross_text_tokens(self):
        assert query_matches("appalti anac", "appalti", "anac")
        assert not query_matches("appalti anac banane", "appalti", "anac")

    def test_stopword_only_never_matches(self):
        assert not query_matches("di dei")
        assert not query_matches("")
