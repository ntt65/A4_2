import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.evaluator import evaluate_information_extraction, evaluate_sentiment
from src.sentiment import analyze_sentiment


ROOT = Path(__file__).resolve().parents[1]
PATTERNS = ("emails", "phones", "dates", "amounts", "urls")


class PipelineSmokeTests(unittest.TestCase):
    def _run_cli(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, "-B", "-X", "utf8", str(ROOT / "main.py"), *args],
            cwd=cwd or ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_cli_help_lists_supported_operations(self) -> None:
        output = self._run_cli("--help").stdout
        for option in ("--text", "--mask", "--evaluate-ie", "--evaluate-sentiment", "--evaluate-all"):
            with self.subTest(option=option):
                self.assertIn(option, output)

    def test_cli_analysis_resolves_data_outside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = self._run_cli(
                "--text", "문의는 USER@EXAMPLE.COM, 서비스는 정말 좋다", cwd=Path(directory)
            ).stdout
        json_output = output.split("[정보 추출 결과]", 1)[1].lstrip()
        extracted, _ = json.JSONDecoder().raw_decode(json_output)
        self.assertEqual(
            extracted,
            {"emails": ["user@example.com"], "phones": [], "dates": [], "amounts": [], "urls": []},
        )
        self.assertIn("[감성 분석 결과]", output)
        self.assertIn("판정: positive", output)

    def test_cli_mask_hides_original_phone(self) -> None:
        phone = "010-1234-5678"
        output = self._run_cli("--text", f"연락처 {phone}", "--mask").stdout
        self.assertNotIn(phone, output)
        self.assertIn("010-****-5678", output)

    def test_cli_evaluation_prints_both_reports(self) -> None:
        output = self._run_cli("--evaluate-all").stdout
        for heading in ("[정보 추출 평가]", "[감성 분석 평가]", "before", "after", *PATTERNS):
            with self.subTest(heading=heading):
                self.assertIn(heading, output)

    def test_information_extraction_metrics_count_errors(self) -> None:
        cases = [
            ("USER@EXAMPLE.COM", ["user@example.com"]),
            ("other@example.com", ["missing@example.com"]),
            ("extra@example.com", []),
        ]
        data = [
            {"text": text, "labels": {key: emails if key == "emails" else [] for key in PATTERNS}}
            for text, emails in cases
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ie.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            metrics, _ = evaluate_information_extraction(path)
        self.assertAlmostEqual(metrics["emails"]["precision"], 1 / 3)
        self.assertAlmostEqual(metrics["emails"]["recall"], 1 / 2)
        for pattern in PATTERNS[1:]:
            with self.subTest(pattern=pattern):
                self.assertEqual(metrics[pattern], {"precision": 0.0, "recall": 0.0})

    def test_sentiment_metrics_compare_rules_and_macro_f1(self) -> None:
        data = [
            {"text": "좋다", "label": "positive"},
            {"text": "안 좋다", "label": "negative"},
            {"text": "일정 확인", "label": "neutral"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sentiment.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            metrics, _ = evaluate_sentiment(path)
        self.assertAlmostEqual(metrics["before"]["accuracy"], 2 / 3)
        self.assertAlmostEqual(metrics["before"]["f1"], 5 / 9)
        self.assertEqual(metrics["after"], {"accuracy": 1.0, "f1": 1.0})

    def test_empty_evaluations_return_zero_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.json"
            path.write_text("[]", encoding="utf-8")
            ie_metrics, _ = evaluate_information_extraction(path)
            sentiment_metrics, _ = evaluate_sentiment(path)
        self.assertEqual(set(ie_metrics), set(PATTERNS))
        for pattern, metrics in ie_metrics.items():
            with self.subTest(pattern=pattern):
                self.assertEqual(metrics, {"precision": 0.0, "recall": 0.0})
        self.assertEqual(
            sentiment_metrics,
            {"before": {"accuracy": 0.0, "f1": 0.0}, "after": {"accuracy": 0.0, "f1": 0.0}},
        )

    def test_sentiment_rules_return_matching_evidence(self) -> None:
        lexicon = {
            "general_sentiment": {"좋다": 1.0},
            "domain_sentiment": {},
            "negations": ["안"],
            "intensifiers": ["정말"],
            "double_negatives": {"나쁘지 않다": 1.5},
        }
        for text, label, weight, rule in (
            ("정말 좋다", "positive", 1.5, "intensifier:정말"),
            ("안 좋다", "negative", -1.0, "negation:안"),
        ):
            with self.subTest(text=text):
                result = analyze_sentiment(text, lexicon=lexicon, use_rules=True)
                self.assertEqual(result["label"], label)
                self.assertEqual(result["final_score"], weight)
                self.assertEqual(result["detected_sentiments"][0]["weight"], weight)
                self.assertEqual(result["detected_sentiments"][0]["weighted_score"], weight)
                self.assertIn(rule, result["detected_sentiments"][0]["rules"])
        result = analyze_sentiment("나쁘지 않다", lexicon=lexicon, use_rules=True)
        self.assertEqual(result["label"], "positive")
        self.assertGreater(result["final_score"], 0)
        self.assertTrue(any(log.startswith("double_negative:") for log in result["rule_logs"]))


if __name__ == "__main__":
    unittest.main()
