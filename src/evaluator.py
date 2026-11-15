import json
from pathlib import Path

from src.extractor import extract_information
from src.sentiment import analyze_sentiment, load_lexicon


BASE_DIR = Path(__file__).resolve().parent.parent
IE_DATA_PATH = BASE_DIR / "data" / "ie_test_cases.json"
SENTIMENT_DATA_PATH = BASE_DIR / "data" / "sentiment_test_cases.json"


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def _format_float(value: float) -> str:
    return f"{value:.3f}"


def evaluate_information_extraction(path: Path = IE_DATA_PATH) -> tuple[dict, str]:
    with path.open("r", encoding="utf-8") as f:
        cases = json.load(f)

    patterns = ["emails", "phones", "dates", "amounts", "urls"]
    include_addresses = any("addresses" in case["labels"] for case in cases)
    if include_addresses:
        patterns.append("addresses")
    counts = {p: {"tp": 0, "fp": 0, "fn": 0} for p in patterns}

    for case in cases:
        predicted = extract_information(case["text"], include_addresses=include_addresses)
        expected = case["labels"]

        for p in patterns:
            if p == "addresses" and p not in expected:
                continue
            pred_set = set(predicted.get(p, []))
            exp_set = set(expected.get(p, []))
            counts[p]["tp"] += len(pred_set & exp_set)
            counts[p]["fp"] += len(pred_set - exp_set)
            counts[p]["fn"] += len(exp_set - pred_set)

    report_lines = [
        "\n[정보 추출 평가]",
        "pattern     | precision | recall",
        "------------|-----------|-------",
    ]
    metrics = {}
    for p in patterns:
        tp = counts[p]["tp"]
        fp = counts[p]["fp"]
        fn = counts[p]["fn"]
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        metrics[p] = {"precision": precision, "recall": recall}
        report_lines.append(f"{p:<11} | {_format_float(precision):>9} | {_format_float(recall):>5}")

    return metrics, "\n".join(report_lines)


def _macro_f1(y_true: list[str], y_pred: list[str], labels: list[str]) -> float:
    f1_scores = []
    for label in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        f1_scores.append(f1)
    return sum(f1_scores) / len(labels)


def evaluate_sentiment(path: Path = SENTIMENT_DATA_PATH) -> tuple[dict, str]:
    with path.open("r", encoding="utf-8") as f:
        cases = json.load(f)

    lexicon = load_lexicon()
    y_true = [case["label"] for case in cases]

    pred_before = [analyze_sentiment(case["text"], lexicon=lexicon, use_rules=False)["label"] for case in cases]
    pred_after = [analyze_sentiment(case["text"], lexicon=lexicon, use_rules=True)["label"] for case in cases]

    labels = ["positive", "negative", "neutral"]

    acc_before = _safe_div(sum(1 for t, p in zip(y_true, pred_before) if t == p), len(y_true))
    acc_after = _safe_div(sum(1 for t, p in zip(y_true, pred_after) if t == p), len(y_true))
    f1_before = _macro_f1(y_true, pred_before, labels)
    f1_after = _macro_f1(y_true, pred_after, labels)

    metrics = {
        "before": {"accuracy": acc_before, "f1": f1_before},
        "after": {"accuracy": acc_after, "f1": f1_after},
    }

    report = "\n".join(
        [
            "\n[감성 분석 평가]",
            "phase  | accuracy | f1",
            "-------|----------|---",
            f"before | {_format_float(acc_before):>8} | {_format_float(f1_before)}",
            f"after  | {_format_float(acc_after):>8} | {_format_float(f1_after)}",
        ]
    )
    return metrics, report


def run_all_evaluations() -> str:
    _, ie_report = evaluate_information_extraction()
    _, sentiment_report = evaluate_sentiment()
    return f"{ie_report}\n{sentiment_report}"
