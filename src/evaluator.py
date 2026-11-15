import json
from pathlib import Path

from src.aspect_sentiment import analyze_aspects
from src.contextual_sentiment import analyze_contextual_sentiment
from src.extractor import extract_information
from src.sentiment import analyze_sentiment, load_lexicon


BASE_DIR = Path(__file__).resolve().parent.parent
IE_DATA_PATH = BASE_DIR / "data" / "ie_test_cases.json"
SENTIMENT_DATA_PATH = BASE_DIR / "data" / "sentiment_test_cases.json"
ASPECT_DATA_PATH = BASE_DIR / "data" / "aspect_sentiment_test_cases.json"
CONTEXTUAL_DATA_PATH = BASE_DIR / "data" / "contextual_sentiment_test_cases.json"


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


def evaluate_contextual_sentiment(
    paths: tuple[Path, ...] = (SENTIMENT_DATA_PATH, CONTEXTUAL_DATA_PATH),
) -> tuple[dict, str]:
    """라벨을 유지한 각 자료에서 기존 규칙과 선택 문맥 규칙을 비교한다."""
    lexicon = load_lexicon()
    datasets = []
    lines = ["[문맥 감성 평가]", "dataset | phase | count | accuracy | macro F1"]
    labels = ["positive", "negative", "neutral"]
    for path in paths:
        cases = json.loads(path.read_text(encoding="utf-8"))
        predictions = []
        for index, case in enumerate(cases, 1):
            if case["label"] not in labels:
                raise ValueError(f"{path.name}:{index}: unsupported sentiment label")
            analysis = analyze_contextual_sentiment(case["text"], lexicon=lexicon)
            predictions.append({"row": index, "text": case["text"], "expected": case["label"],
                                "category": case.get("category", "unspecified"),
                                "baseline_label": analysis["baseline"]["label"], "analysis": analysis})
        metrics = {}
        expected = [case["label"] for case in cases]
        for phase in ("baseline", "contextual"):
            predicted = [row["baseline_label"] if phase == "baseline" else row["analysis"]["label"]
                         for row in predictions]
            correct = sum(truth == prediction for truth, prediction in zip(expected, predicted))
            metrics[phase] = {"correct": correct, "accuracy": _safe_div(correct, len(cases)),
                              "macro_f1": _macro_f1(expected, predicted, labels)}
            lines.append(f"{path.name} | {phase} | {len(cases)} | {metrics[phase]['accuracy']:.6f}"
                         f" | {metrics[phase]['macro_f1']:.6f}")
        regressions = [row["row"] for row in predictions if row["baseline_label"] == row["expected"]
                       and row["analysis"]["label"] != row["expected"]]
        datasets.append({"name": path.name, "case_count": len(cases), "metrics": metrics,
                         "regression_rows": regressions, "predictions": predictions})
    return {"datasets": datasets}, "\n".join(lines)


def evaluate_aspect_sentiment(path: Path = ASPECT_DATA_PATH) -> tuple[dict, str]:
    """Evaluate detection and (aspect, polarity) pairs, retaining every prediction.

    Macro F1 counts missing/extra aspects as false negatives/positives for the
    three sentiment labels. Accuracy on matched aspects is conditional on detection.
    """
    cases = json.loads(path.read_text(encoding="utf-8"))
    lexicon = load_lexicon()
    counts = {"aspect_tp": 0, "pair_tp": 0, "gold": 0, "predicted": 0, "exact": 0}
    y_true: list[str] = []
    y_pred: list[str] = []
    predictions: list[dict] = []
    for case in cases:
        analysis = analyze_aspects(case["text"], lexicon)
        expected = case["aspects"]
        predicted = {item["aspect"]: item["label"] for item in analysis["aspects"]}
        expected_pairs = set(expected.items())
        predicted_pairs = set(predicted.items())
        counts["aspect_tp"] += len(set(expected) & set(predicted))
        counts["pair_tp"] += len(expected_pairs & predicted_pairs)
        counts["gold"] += len(expected)
        counts["predicted"] += len(predicted)
        counts["exact"] += expected == predicted
        for aspect in sorted(set(expected) | set(predicted)):
            y_true.append(expected.get(aspect, "missing"))
            y_pred.append(predicted.get(aspect, "missing"))
        predictions.append({
            "text": case["text"], "category": case.get("category", "unspecified"),
            "expected": expected, "predicted": predicted, "exact_match": expected == predicted,
            "analysis": analysis,
        })

    def metrics(tp: int) -> dict[str, float]:
        precision = _safe_div(tp, counts["predicted"])
        recall = _safe_div(tp, counts["gold"])
        return {"precision": precision, "recall": recall, "f1": _safe_div(2 * precision * recall, precision + recall)}

    result = {
        "case_count": len(cases), "counts": counts,
        "aspect_detection": metrics(counts["aspect_tp"]),
        "aspect_sentiment": metrics(counts["pair_tp"]),
        "exact_match_accuracy": _safe_div(counts["exact"], len(cases)),
        "sentiment_accuracy_on_detected": _safe_div(counts["pair_tp"], counts["aspect_tp"]),
        "sentiment_macro_f1": _macro_f1(y_true, y_pred, ["positive", "negative", "neutral"]),
        "predictions": predictions,
    }
    detection = result["aspect_detection"]
    pairs = result["aspect_sentiment"]
    report = "\n".join([
        "\n[Aspect 감성 평가]",
        f"문장 {len(cases)}개 | 정답 측면 {counts['gold']}개 | 예측 측면 {counts['predicted']}개",
        f"측면 탐지 Precision/Recall/F1: {detection['precision']:.6f}/{detection['recall']:.6f}/{detection['f1']:.6f}",
        f"측면·극성 Precision/Recall/F1: {pairs['precision']:.6f}/{pairs['recall']:.6f}/{pairs['f1']:.6f}",
        f"문장 완전 일치율: {result['exact_match_accuracy']:.6f}",
        f"탐지된 정답 측면의 감성 Accuracy: {result['sentiment_accuracy_on_detected']:.6f}",
        f"누락·오탐 포함 감성 Macro F1: {result['sentiment_macro_f1']:.6f}",
    ])
    return result, report
