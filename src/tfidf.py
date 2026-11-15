"""Training-only TF-IDF with cosine nearest-centroid classification."""

from collections import Counter
from math import log, sqrt

from src.sentiment import tokenize


LABELS = ("positive", "negative", "neutral")


def _features(text: str) -> Counter[str]:
    tokens = tokenize(text)
    features = Counter(tokens)
    features.update(f"{left} {right}" for left, right in zip(tokens, tokens[1:]))
    return features


def _normalize(vector: dict[str, float]) -> dict[str, float]:
    norm = sqrt(sum(value * value for value in vector.values()))
    return {term: value / norm for term, value in vector.items()} if norm else {}


class TfidfCentroidClassifier:
    def __init__(self) -> None:
        self.idf: dict[str, float] = {}
        self.centroids: dict[str, dict[str, float]] = {}

    def fit(self, texts: list[str], labels: list[str]) -> None:
        if not texts or len(texts) != len(labels):
            raise ValueError("Training texts and labels must have the same nonzero length.")
        if set(labels) != set(LABELS):
            raise ValueError("Training must contain positive, negative and neutral labels only.")
        documents = [_features(text) for text in texts]
        frequencies: Counter[str] = Counter()
        for document in documents:
            frequencies.update(document.keys())
        if not frequencies:
            raise ValueError("Training must contain at least one token.")

        # Replace fitted state on every successful fit. Vocabulary and document
        # frequency depend exclusively on this training subset.
        idf = {term: log((1 + len(texts)) / (1 + count)) + 1 for term, count in frequencies.items()}
        totals: dict[str, Counter[str]] = {label: Counter() for label in LABELS}
        for document, label in zip(documents, labels):
            vector = _normalize({term: count * idf[term] for term, count in document.items()})
            totals[label].update(vector)
        self.idf = idf
        # Dividing a class sum by its size has no effect after L2 normalization.
        self.centroids = {label: _normalize(dict(totals[label])) for label in LABELS}

    def predict(self, texts: list[str]) -> list[str]:
        if not self.centroids:
            raise ValueError("Fit the classifier before prediction.")
        predictions = []
        for text in texts:
            vector = _normalize({
                term: count * self.idf[term]
                for term, count in _features(text).items() if term in self.idf
            })
            scores = {
                label: sum(value * centroid.get(term, 0.0) for term, value in vector.items())
                for label, centroid in self.centroids.items()
            }
            # Exact ties, including an all-OOV document, prefer neutral. The
            # remaining fixed tie order is positive, negative.
            predictions.append(max(LABELS, key=lambda label: (scores[label], label == "neutral")))
        return predictions
