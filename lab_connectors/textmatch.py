"""Tokenized text matching per le query naturali italiane dei tool di ricerca.

Primitive condivise tra i motori di find del Lab (agent-context-builder
``find``, toolkit ``toolkit_dataset find``): tokenizzazione, stopword
italiane, morfologia leggera e match per parola.

Usage::

    from lab_connectors.textmatch import query_matches, query_tokens

    query_tokens("bandi di gara")   # ["bandi", "gara"]
    query_matches("appalti anac", "appalti", "anac")  # True (cross-testo)

Design:
- i token della query devono matchare **tutti** (AND), sparsi tra i testi
  forniti — le parole di una query naturale stanno spesso in campi diversi
- le stopword italiane non sono token richiesti
- ``_`` e punteggiatura sono separatori di parola (slug snake_case)
- morfologia leggera via final-vowel strip (gara≈gare, pubblico≈pubblici),
  non uno stemmer
"""

from __future__ import annotations

import re
import unicodedata

#: Function words che inquinano le query naturali ("bandi di gara",
#: "appalti pubblici anac"). Confrontate dopo de-accentazione.
ITALIAN_QUERY_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "ad",
        "agli",
        "ai",
        "al",
        "alle",
        "allo",
        "anche",
        "avere",
        "chi",
        "ci",
        "circa",
        "come",
        "cui",
        "da",
        "dagli",
        "dai",
        "dal",
        "dalle",
        "del",
        "dello",
        "delle",
        "dei",
        "degli",
        "di",
        "dove",
        "ed",
        "e",
        "era",
        "erano",
        "essere",
        "fra",
        "gia",
        "gli",
        "ha",
        "hanno",
        "i",
        "il",
        "in",
        "la",
        "le",
        "lo",
        "ma",
        "nei",
        "negli",
        "nel",
        "nello",
        "non",
        "o",
        "oppure",
        "per",
        "perche",
        "piu",
        "quale",
        "quali",
        "quanti",
        "quante",
        "quando",
        "si",
        "sono",
        "sugli",
        "sulle",
        "sullo",
        "sul",
        "su",
        "sui",
        "tutto",
        "tutti",
        "tra",
        "un",
        "una",
        "uno",
        "verso",
    }
)


def query_words(value: str | None) -> list[str]:
    """Lowercase alphanumeric words; underscores/punctuation are separators.

    "anac_bandi_gara" → ["anac", "bandi", "gara"]; "più" → ["piu"].
    """
    text = unicodedata.normalize("NFKD", (value or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return [w for w in re.split(r"[^a-z0-9]+", text) if w]


def query_tokens(query: str) -> list[str]:
    """Query tokens minus Italian stopwords (order preserved, deduped)."""
    tokens: list[str] = []
    for word in query_words(query):
        if len(word) < 2 or word in ITALIAN_QUERY_STOPWORDS:
            continue
        if word not in tokens:
            tokens.append(word)
    return tokens


def word_forms(word: str) -> set[str]:
    """Word plus a light morphological variant (final-vowel strip).

    gara≈gare, pubblico≈pubblici, appalto≈appalti. Volutamente semplice:
    non è uno stemmer, è mitigato dai min-length nei call site.
    """
    forms = {word}
    if len(word) >= 4 and word[-1] in "aeiou":
        forms.add(word[:-1])
    return forms


def token_in_text(token: str, text: str | None) -> bool:
    """Match a query token against any word in text.

    Whole word (with light morphology) or typed prefix ("pension" →
    "pensioni"). Word-splitting avoids false positives like "appalti"
    inside "n_subappalti".
    """
    token_forms = word_forms(token)
    for word in query_words(text):
        if word_forms(word) & token_forms:
            return True
        if len(token) >= 3 and word.startswith(token):
            return True
    return False


def query_matches(query: str, *texts: str | None) -> bool:
    """Check whether every non-stopword query token matches at least one text.

    Token match is cross-text: words may be spread across the values.
    Empty/stopword-only queries never match.
    """
    tokens = query_tokens(query)
    if not tokens:
        return False
    return all(any(token_in_text(token, text) for text in texts) for token in tokens)
