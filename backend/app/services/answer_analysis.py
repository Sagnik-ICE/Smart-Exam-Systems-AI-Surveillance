from __future__ import annotations

import json
import math
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..settings import settings


def _combine_answers(answers: dict[str, str]) -> str:
    return " ".join([value.strip() for value in answers.values() if value and value.strip()])


def _entropy(values: list[float]) -> float:
    total = sum(values)
    if total <= 0:
        return 0.0
    entropy = 0.0
    for value in values:
        if value <= 0:
            continue
        p = value / total
        entropy -= p * math.log(p, 2)
    return entropy


def calculate_similarity_risk(current_answers: dict[str, str], historical_answers: list[dict[str, str]]) -> float:
    current_text = _combine_answers(current_answers)
    if not current_text:
        return 0.0

    history_texts = [_combine_answers(item) for item in historical_answers]
    history_texts = [text for text in history_texts if text]
    if not history_texts:
        return 0.0

    corpus = [current_text, *history_texts]
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
    tfidf_matrix = vectorizer.fit_transform(corpus)
    similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]
    max_similarity = float(max(similarities)) if len(similarities) > 0 else 0.0

    if max_similarity >= 0.9:
        return 1.0
    if max_similarity >= 0.8:
        return 0.7
    if max_similarity >= 0.7:
        return 0.4
    return 0.1


def fetch_external_ai_classifier_risk(text: str) -> float | None:
    if not settings.ai_classifier_url or not text.strip():
        return None

    payload = json.dumps({"text": text}).encode("utf-8")
    request = Request(
        settings.ai_classifier_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.ai_classifier_timeout_seconds) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw)
            risk = parsed.get("risk")
            if isinstance(risk, (int, float)):
                return max(0.0, min(1.0, float(risk)))
            return None
    except (URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def calculate_ai_style_risk(
    current_answers: dict[str, str],
    time_taken_seconds: int,
    events: list[dict] | None = None,
    external_ai_risk: float | None = None,
) -> float:
    text = _combine_answers(current_answers)
    if not text:
        return 0.0

    flags = 0
    word_count = len(text.split())
    sentence_parts = re.split(r"[.!?]+", text)
    sentence_lengths = [len(sentence.split()) for sentence in sentence_parts if sentence.strip()]

    markdown_pattern = r"\*\*|^\s*[-*]\s|^\s*\d+\.\s|`"
    if re.search(markdown_pattern, text, flags=re.MULTILINE):
        flags += 1

    if len(sentence_lengths) >= 4:
        max_len = max(sentence_lengths)
        min_len = min(sentence_lengths)
        # Very uniform sentence sizes can indicate AI-generated structure.
        if (max_len - min_len) <= 4:
            flags += 1

    if word_count >= 120 and time_taken_seconds <= 120:
        flags += 1

    if re.search(r"\b(in conclusion|moreover|furthermore|thus|therefore)\b", text.lower()):
        flags += 1

    words = re.findall(r"[A-Za-z']+", text.lower())
    unique_ratio = len(set(words)) / max(1, len(words))
    if len(words) > 120 and unique_ratio < 0.32:
        flags += 1

    sentence_count = max(1, len([item for item in sentence_parts if item.strip()]))
    if len(words) >= 80:
        words_per_sentence = len(words) / sentence_count
        if words_per_sentence >= 24:
            flags += 1

    # Low edit entropy can indicate pasted or machine-generated responses.
    if events:
        change_deltas = []
        for event in events:
            if event.get("event_type") != "answer_change":
                continue
            metadata = event.get("metadata") or {}
            delta = abs(float(metadata.get("delta_chars", 0)))
            if delta > 0:
                change_deltas.append(delta)
        if len(change_deltas) >= 6:
            entropy = _entropy(change_deltas)
            if entropy < 1.2:
                flags += 1

    local_risk = min(1.0, flags / 7.0)
    if external_ai_risk is None:
        return local_risk

    return max(0.0, min(1.0, (0.6 * local_risk) + (0.4 * external_ai_risk)))
