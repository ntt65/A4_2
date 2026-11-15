import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.contextual_sentiment import analyze_contextual_sentiment, format_contextual_analysis
from src.evaluator import evaluate_contextual_sentiment
from src.sentiment import analyze_sentiment


ROOT = Path(__file__).resolve().parents[1]


class ContextualSentimentTests(unittest.TestCase):
    def test_irony_requires_an_asserted_event_and_positive_praise(self) -> None:
        for text in ("택배가 늦었는데 참 빠르네요.", "고장이라니 품질이 훌륭하네요."):
            with self.subTest(text=text):
                result = analyze_contextual_sentiment(text)
                self.assertEqual(result["label"], "negative")
                self.assertIn("adverse_event_irony", result["rule_logs"])
                self.assertTrue(all(item["weight"] < 0 for item in result["detected_sentiments"]))
        for text in ("정말 훌륭하네요.", "고장 났는데 수리가 정말 훌륭하네요.",
                     "고장이 없으니 정말 훌륭하네요.", "고장 났다. 정말 훌륭하네요.",
                     "고장 났다니 정말 좋지 않네요."):
            with self.subTest(text=text):
                result = analyze_contextual_sentiment(text)
                self.assertNotIn("adverse_event_irony", result["rule_logs"])
                self.assertEqual(result["final_score"], result["baseline"]["final_score"])

    def test_literal_quotes_support_pairs_and_keep_author_sentiment(self) -> None:
        for quoted in ("'좋다'", '"좋다"', "‘좋다’", "“좋다”"):
            with self.subTest(quoted=quoted):
                result = analyze_contextual_sentiment(f"예문 {quoted}를 확인했다. 상품은 나쁘다.")
                self.assertEqual(result["label"], "negative")
                self.assertEqual(result["excluded_quotes"][0]["text"], quoted)
        result = analyze_contextual_sentiment("예문 '나쁘다'를 고쳤고 나는 '좋다'고 느꼈다.")
        self.assertEqual([quote["text"] for quote in result["excluded_quotes"]], ["'나쁘다'"])
        self.assertEqual(result["label"], "positive")

    def test_testimony_self_expression_and_unclosed_quotes_are_preserved(self) -> None:
        for text in ("친구가 '좋다'고 말했다.", "내 기분을 '행복하다'라는 표현으로 나타냈다.",
                     "예문은 '좋다", "'좋다'. 예문을 확인했다."):
            with self.subTest(text=text):
                result = analyze_contextual_sentiment(text)
                self.assertEqual(result["excluded_quotes"], [])
                self.assertEqual(result["final_score"], result["baseline"]["final_score"])
        self.assertEqual(analyze_contextual_sentiment("'최고다'라는 표현이 몇 번 나오는지 세었다.")["label"], "neutral")

    def test_final_intent_and_recovery_replace_only_their_sentence(self) -> None:
        for text, label, rule in (
            ("아름답지만 다시 주문하지 않겠다.", "negative", "final_refusal"),
            ("친절하지만 환불을 거절당했다.", "negative", "final_rejection"),
            ("실망했지만 지금은 계속 잘 쓴다.", "positive", "current_recovery"),
            ("비싸지만 앞으로도 이 가게만 이용하겠다.", "positive", "reuse_intent"),
            ("어려울 줄 알았는데 누구 도움도 없이 끝냈다.", "positive", "completed_without_help"),
        ):
            with self.subTest(text=text):
                result = analyze_contextual_sentiment(text)
                self.assertEqual(result["label"], label)
                self.assertIn(rule, result["rule_logs"])
        self.assertEqual(analyze_contextual_sentiment("좋다. 다시 주문하지 않겠다.")["final_score"], 0.0)

    def test_conditional_negated_and_quoted_intent_does_not_override(self) -> None:
        for text in ("앞으로도 문제가 해결된다면 이용하겠다.", "다시 주문하지 않겠다는 뜻은 아니다.",
                     "다시 주문하지 않겠다고 말한 적은 없다.", "예문 '다시 주문하지 않겠다'를 읽었다."):
            with self.subTest(text=text):
                result = analyze_contextual_sentiment(text)
                self.assertTrue(all(segment["rule"] is None for segment in result["segments"]))

    def test_source_spans_and_score_accounting(self) -> None:
        text = "예문 '좋다'를 썼다. 배송이 늦었는데 참 빠르네요! 지금은 잘 쓴다."
        result = analyze_contextual_sentiment(text)
        for item in result["excluded_quotes"] + result["segments"]:
            self.assertEqual(text[slice(*item["span"])], item["text"])
        for segment in result["segments"]:
            trigger = segment["trigger"]
            if trigger:
                self.assertEqual(text[slice(*trigger["span"])], trigger["text"])
        self.assertEqual(result["final_score"], sum(item["weighted_score"] for item in result["detected_sentiments"]))
        output = format_contextual_analysis(result)
        self.assertIn("[문맥 감성 분석 결과]", output)
        self.assertIn("weight=", output)

    def test_empty_input_and_custom_empty_lexicon(self) -> None:
        with patch("src.contextual_sentiment.load_lexicon", side_effect=AssertionError("must not load")):
            self.assertEqual(analyze_contextual_sentiment("좋다", lexicon={})["label"], "neutral")
        for text in ("", "?!\n", "일정 확인"):
            self.assertEqual(analyze_contextual_sentiment(text)["label"], "neutral")

    def test_existing_corpus_is_unchanged_without_applicable_context_rule(self) -> None:
        cases = json.loads((ROOT / "data/sentiment_test_cases.json").read_text(encoding="utf-8"))
        for case in cases:
            result = analyze_contextual_sentiment(case["text"])
            if not result["rule_logs"]:
                with self.subTest(text=case["text"]):
                    self.assertEqual(result["final_score"], analyze_sentiment(case["text"])["final_score"])

    def test_evaluation_compares_fixed_labels_and_counts_regressions(self) -> None:
        cases = [{"text": "일정 확인", "label": "neutral"},
                 {"text": "자료 확인", "label": "positive"},
                 {"text": "다시 주문하지 않겠다.", "label": "neutral"}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.json"
            path.write_text(json.dumps(cases), encoding="utf-8")
            result, report = evaluate_contextual_sentiment((path,))
        dataset = result["datasets"][0]
        self.assertEqual(dataset["case_count"], 3)
        self.assertEqual(dataset["metrics"]["baseline"]["accuracy"], 2 / 3)
        self.assertEqual(dataset["metrics"]["contextual"]["accuracy"], 1 / 3)
        self.assertAlmostEqual(dataset["metrics"]["contextual"]["macro_f1"], 1 / 6)
        self.assertEqual(dataset["regression_rows"], [3])
        self.assertIn("[문맥 감성 평가]", report)

    def test_evaluation_empty_data_has_zero_denominators(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.json"
            path.write_text("[]", encoding="utf-8")
            result, _ = evaluate_contextual_sentiment((path,))
        metrics = result["datasets"][0]["metrics"]
        self.assertTrue(all(value == 0 for phase in metrics.values() for value in phase.values()))

    def test_cli_context_and_masking_and_required_text(self) -> None:
        command = [sys.executable, "-B", "-X", "utf8", str(ROOT / "main.py")]
        result = subprocess.run(command + ["--text", "배송이 늦었는데 참 빠르네요 010-1234-5678", "--contextual", "--mask"],
                                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[문맥 감성 분석 결과]", result.stdout)
        self.assertNotIn("010-1234-5678", result.stdout)
        error = subprocess.run(command + ["--contextual"], cwd=ROOT, capture_output=True,
                               text=True, encoding="utf-8", timeout=20)
        self.assertEqual(error.returncode, 2)
        self.assertIn("--contextual requires --text", error.stderr)

    def test_cli_evaluation_resolves_paths_outside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(ROOT / "main.py"), "--evaluate-contextual"],
                                    cwd=directory, capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("contextual_sentiment_test_cases.json | contextual", result.stdout)

    def test_development_data_has_controls_and_explicit_known_failures(self) -> None:
        cases = json.loads((ROOT / "data/contextual_sentiment_test_cases.json").read_text(encoding="utf-8"))
        self.assertEqual(len(cases), len({case["text"] for case in cases}))
        self.assertEqual({case["label"] for case in cases}, {"positive", "negative", "neutral"})
        self.assertTrue(any(case["category"].startswith("control") for case in cases))
        self.assertTrue(any(case["category"].startswith("challenge_") for case in cases))


if __name__ == "__main__":
    unittest.main()
