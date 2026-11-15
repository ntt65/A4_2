"""Fixed-evaluation learning curves with a separate synthetic training corpus."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import random
from statistics import mean, pstdev
import subprocess
import sys
import tempfile
from time import perf_counter
import unicodedata

from src.evaluator import SENTIMENT_DATA_PATH, _macro_f1, _safe_div
from src.sentiment import analyze_sentiment, load_lexicon, tokenize
from src.tfidf import LABELS, TfidfCentroidClassifier


BASE_DIR = Path(__file__).resolve().parents[1]
TRAINING_PATH = BASE_DIR / "data" / "sentiment_train_cases.json"
RESULT_PATH = BASE_DIR / "docs" / "results" / "tfidf_comparison.json"
TRAIN_SIZES = (10, 100, 1000)
SEEDS = (11, 23, 37, 53, 71)


def normalized_text(text: str) -> str:
    return "".join(character for character in unicodedata.normalize("NFKC", text).casefold()
                   if character.isalnum())


def load_cases(path: Path) -> tuple[list[dict], dict]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"{path}: expected a nonempty case list.")
    seen = set()
    for index, case in enumerate(cases):
        if (not isinstance(case, dict) or not isinstance(case.get("text"), str)
                or not tokenize(case["text"]) or case.get("label") not in LABELS):
            raise ValueError(f"{path}: invalid text or label at row {index}.")
        key = normalized_text(case["text"])
        if key in seen:
            raise ValueError(f"{path}: duplicate normalized text at row {index}.")
        seen.add(key)
    return cases, metadata


def stratified_order(cases: list[dict], seed: int) -> list[int]:
    groups = {label: [index for index, case in enumerate(cases) if case["label"] == label]
              for label in LABELS}
    if any(not group for group in groups.values()):
        raise ValueError("Training must contain all three classes.")
    generator = random.Random(seed)
    for group in groups.values():
        generator.shuffle(group)
    # Prefixes of one shuffled, interleaved order produce nested subsets.
    return [group[index] for index in range(max(map(len, groups.values())))
            for group in groups.values() if index < len(group)]


def classification_metrics(expected: list[str], predicted: list[str]) -> dict:
    if len(expected) != len(predicted):
        raise ValueError("Expected and predicted labels must have the same length.")
    return {
        "accuracy": _safe_div(sum(gold == guess for gold, guess in zip(expected, predicted)), len(expected)),
        "macro_f1": _macro_f1(expected, predicted, list(LABELS)),
        "correct": sum(gold == guess for gold, guess in zip(expected, predicted)),
        "confusion": {
            gold: {guess: sum(actual == gold and prediction == guess
                              for actual, prediction in zip(expected, predicted)) for guess in LABELS}
            for gold in LABELS
        },
    }


def lf_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _describe_data(path: Path, cases: list[dict]) -> dict:
    return {"path": str(path.resolve()), "sha256_lf": lf_sha256(path), "rows": len(cases),
            "label_counts": dict(Counter(case["label"] for case in cases))}


def run_experiment(
    training_path: Path = TRAINING_PATH, evaluation_path: Path = SENTIMENT_DATA_PATH,
    train_sizes: tuple[int, ...] = TRAIN_SIZES, seeds: tuple[int, ...] = SEEDS,
) -> dict:
    training, training_metadata = load_cases(training_path)
    evaluation, _ = load_cases(evaluation_path)
    overlap = {normalized_text(case["text"]) for case in training} & {
        normalized_text(case["text"]) for case in evaluation
    }
    if overlap:
        raise ValueError("Training/evaluation normalized text overlap detected.")
    if (not train_sizes or len(set(train_sizes)) != len(train_sizes)
            or any(size < len(LABELS) or size > len(training) for size in train_sizes)):
        raise ValueError("Training sizes must be distinct and between 3 and the training corpus size.")
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("Provide at least one distinct seed.")

    expected = [case["label"] for case in evaluation]
    texts = [case["text"] for case in evaluation]
    lexicon = load_lexicon()
    started = perf_counter()
    rule_predictions = [analyze_sentiment(text, lexicon=lexicon, use_rules=True)["label"] for text in texts]
    rule_seconds = perf_counter() - started
    runs = []
    for seed in seeds:
        order = stratified_order(training, seed)
        for size in train_sizes:
            indices = order[:size]
            subset = [training[index] for index in indices]
            model = TfidfCentroidClassifier()
            started = perf_counter()
            model.fit([case["text"] for case in subset], [case["label"] for case in subset])
            fit_seconds = perf_counter() - started
            started = perf_counter()
            predictions = model.predict(texts)
            predict_seconds = perf_counter() - started
            runs.append({
                "seed": seed, "train_size": size, "training_indices": indices,
                "label_counts": dict(Counter(case["label"] for case in subset)),
                "vocabulary_size": len(model.idf), "metrics": classification_metrics(expected, predictions),
                "fit_seconds": fit_seconds, "predict_seconds": predict_seconds, "predictions": predictions,
            })

    summaries = []
    for size in train_sizes:
        selected = [run for run in runs if run["train_size"] == size]
        summaries.append({
            "train_size": size,
            **{f"{metric}_{statistic}": function([run["metrics"][metric] for run in selected])
               for metric in ("accuracy", "macro_f1")
               for statistic, function in (("mean", mean), ("std", pstdev))},
            "fit_seconds_mean": mean(run["fit_seconds"] for run in selected),
            "predict_seconds_mean": mean(run["predict_seconds"] for run in selected),
        })

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=BASE_DIR, capture_output=True,
                            text=True, check=False)
    sources = ("main.py", "src/tfidf.py", "src/sentiment_experiment.py", "src/sentiment.py", "src/evaluator.py")
    return {
        "schema_version": 1,
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {"python": sys.version, "platform": platform.platform()},
        "command": sys.argv,
        "base_commit": commit.stdout.strip() if commit.returncode == 0 else None,
        "source_sha256_lf": {source: lf_sha256(BASE_DIR / source) for source in sources},
        "data": {"training": _describe_data(training_path, training),
                 "evaluation": _describe_data(evaluation_path, evaluation),
                 "lexicon_sha256_lf": lf_sha256(BASE_DIR / "data" / "sentiment_lexicon.json"),
                 "normalized_overlap": 0, "training_metadata": training_metadata},
        "protocol": {
            "train_sizes": list(train_sizes), "seeds": list(seeds), "labels": list(LABELS),
            "features": "src.sentiment.tokenize word unigrams + adjacent word bigrams",
            "tf": "raw count", "idf": "ln((1 + n_train) / (1 + train_document_frequency)) + 1",
            "classifier": "L2 document vectors, L2 class centroids, maximum cosine similarity",
            "ties": "neutral, positive, negative", "sampling": "seeded class shuffles, interleaved nested prefixes",
            "std": "population standard deviation across the configured training sample seeds",
            "timing": "one fit and one evaluation-batch prediction per run, excluding I/O and metrics",
            "interpretation": "synthetic training and an existing development evaluation set, sample-selection variation only",
        },
        "evaluation_cases": evaluation,
        "rule_based": {"metrics": classification_metrics(expected, rule_predictions),
                       "predict_seconds": rule_seconds, "predictions": rule_predictions},
        "runs": runs, "summary": summaries,
    }


def save_experiment(result: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent,
                                         suffix=".tmp", delete=False) as output:
            temporary_path = Path(output.name)
            json.dump(result, output, ensure_ascii=False, indent=2)
            output.write("\n")
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def format_experiment(result: dict) -> str:
    rule = result["rule_based"]["metrics"]
    lines = ["[규칙 기반·TF-IDF 감성 비교]", f"고정 평가 {result['data']['evaluation']['rows']}문장",
             f"규칙 기반 Accuracy {rule['accuracy']:.6f}, Macro F1 {rule['macro_f1']:.6f}",
             "train | accuracy mean ± std | macro F1 mean ± std"]
    for row in result["summary"]:
        lines.append(f"{row['train_size']:>5} | {row['accuracy_mean']:.6f} ± {row['accuracy_std']:.6f}"
                     f" | {row['macro_f1_mean']:.6f} ± {row['macro_f1_std']:.6f}")
    return "\n".join(lines)
