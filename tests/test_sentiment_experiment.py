import contextlib
import io
import json
from math import log
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from main import main
from src.evaluator import SENTIMENT_DATA_PATH
from src.sentiment_experiment import (
    SEEDS, TRAINING_PATH, TRAIN_SIZES, classification_metrics, load_cases,
    normalized_text, run_experiment, save_experiment, stratified_order,
)
from src.tfidf import LABELS, TfidfCentroidClassifier


class TfidfExperimentTests(unittest.TestCase):
    def test_idf_uses_training_documents_and_predict_does_not_expand_vocabulary(self) -> None:
        model = TfidfCentroidClassifier()
        model.fit(["좋다 공통 공통", "싫다 공통", "기록"], list(LABELS))
        self.assertAlmostEqual(model.idf["공통"], log(4 / 3) + 1)
        self.assertAlmostEqual(model.idf["좋다"], log(4 / 2) + 1)
        previous = dict(model.idf)
        self.assertEqual(model.predict(["좋다", "싫다", "기록", "미등록어"]), list(LABELS) + ["neutral"])
        self.assertEqual(model.idf, previous)
        self.assertNotIn("미등록어", model.idf)

    def test_refitting_replaces_old_vocabulary_and_centroids(self) -> None:
        model = TfidfCentroidClassifier()
        model.fit(["좋다", "싫다", "기록"], list(LABELS))
        model.fit(["행복", "불행", "문서"], list(LABELS))
        self.assertEqual(set(model.idf), {"행복", "불행", "문서"})
        self.assertEqual(model.predict(["좋다", "행복", "불행", "문서"]), ["neutral", *LABELS])

    def test_unfitted_missing_class_and_empty_training_fail_explicitly(self) -> None:
        model = TfidfCentroidClassifier()
        with self.assertRaises(ValueError):
            model.predict(["좋다"])
        for texts, labels in (([], []), (["좋다"], ["positive"]), (["", "", ""], list(LABELS)),
                              (["좋다", "싫다", "기록"], ["positive", "negative", "unknown"])):
            with self.subTest(texts=texts, labels=labels), self.assertRaises(ValueError):
                model.fit(texts, labels)

    def test_corpus_is_reconstructable_and_sampling_is_nested_balanced_and_seeded(self) -> None:
        training, metadata = load_cases(TRAINING_PATH)
        evaluation, _ = load_cases(SENTIMENT_DATA_PATH)
        regenerated = [
            {"text": context + " " + sentence, "label": label, "context_id": context_id,
             "template_id": f"{label}-{template_id:02d}"}
            for label, sentences in metadata["templates"].items()
            for template_id, sentence in enumerate(sentences)
            for context_id, context in enumerate(metadata["contexts"])
        ]
        self.assertEqual(training, regenerated)
        self.assertEqual(len(training), 1008)
        self.assertFalse({normalized_text(row["text"]) for row in training} &
                         {normalized_text(row["text"]) for row in evaluation})
        orders = []
        for seed in SEEDS:
            order = stratified_order(training, seed)
            self.assertEqual(order, stratified_order(training, seed))
            self.assertEqual(len(set(order)), len(training))
            previous: set[int] = set()
            for size in TRAIN_SIZES:
                selected = order[:size]
                self.assertEqual(len(selected), size)
                self.assertTrue(previous.issubset(selected))
                counts = [sum(training[index]["label"] == label for index in selected) for label in LABELS]
                self.assertLessEqual(max(counts) - min(counts), 1)
                previous = set(selected)
            orders.append(tuple(order))
        self.assertEqual(len(set(orders)), len(SEEDS))

    def test_invalid_labels_and_normalized_duplicate_rows_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            for rows in ([{"text": "내용", "label": "unknown"}],
                         [{"text": "ＡＢ C!", "label": "positive"},
                          {"text": "abc", "label": "negative"}]):
                path.write_text(json.dumps(rows), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_cases(path)

    def test_experiment_rejects_overlap_before_fitting(self) -> None:
        with self.assertRaisesRegex(ValueError, "overlap"):
            run_experiment(SENTIMENT_DATA_PATH, SENTIMENT_DATA_PATH)

    def test_small_experiment_reproduces_subsets_predictions_and_metrics(self) -> None:
        training = [{"text": f"{word} sample {index}", "label": label}
                    for label, word in zip(LABELS, ("bright", "broken", "record")) for index in range(3)]
        evaluation = [{"text": f"{word} evaluation", "label": label}
                      for label, word in zip(LABELS, ("bright", "broken", "record"))]
        with tempfile.TemporaryDirectory() as directory:
            train_path = Path(directory) / "train.json"
            eval_path = Path(directory) / "eval.json"
            train_path.write_text(json.dumps(training), encoding="utf-8")
            eval_path.write_text(json.dumps(evaluation), encoding="utf-8")
            first = run_experiment(train_path, eval_path, (3, 6), (11, 23))
            second = run_experiment(train_path, eval_path, (3, 6), (11, 23))
        self.assertEqual(len(first["runs"]), 4)
        for left, right in zip(first["runs"], second["runs"]):
            for key in ("training_indices", "predictions", "metrics", "vocabulary_size"):
                self.assertEqual(left[key], right[key])
            self.assertEqual(left["metrics"]["accuracy"], 1.0)
            self.assertEqual(left["metrics"]["macro_f1"], 1.0)
        self.assertEqual(classification_metrics([], [])["macro_f1"], 0.0)
        with self.assertRaises(ValueError):
            classification_metrics(["positive"], [])

    def test_cli_writes_requested_result_path(self) -> None:
        fixture = {"data": {"evaluation": {"rows": 3}},
                   "rule_based": {"metrics": {"accuracy": 1.0, "macro_f1": 1.0}}, "summary": []}
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "nested" / "result.json"
            with patch("sys.argv", ["main.py", "--compare-sentiment", "--experiment-output", str(output_path)]), \
                    patch("src.sentiment_experiment.run_experiment", return_value=fixture), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                main()
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), fixture)
            self.assertIn("TF-IDF", output.getvalue())

    def test_failed_save_preserves_previous_measurement_and_removes_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            path.write_text('{"previous": true}\n', encoding="utf-8")
            with patch("src.sentiment_experiment.json.dump", side_effect=OSError("disk write failed")):
                with self.assertRaises(OSError):
                    save_experiment({"replacement": True}, path)
            self.assertEqual(path.read_text(encoding="utf-8"), '{"previous": true}\n')
            self.assertEqual(list(path.parent.iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
