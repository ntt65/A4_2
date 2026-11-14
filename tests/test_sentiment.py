import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from src.sentiment import analyze_sentiment, format_analysis, load_lexicon, tokenize


ROOT = Path(__file__).resolve().parents[1]


class SentimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lexicon = load_lexicon()

    def test_korean_surface_forms_and_postposed_negation(self) -> None:
        for text in ("좋지 않다", "좋지 않았어요", "맛있지 않았어요", "친절하지 않아요"):
            with self.subTest(text=text):
                result = analyze_sentiment(text, self.lexicon)
                self.assertEqual(result["label"], "negative")
                self.assertEqual(result["final_score"], -1.0)
                self.assertTrue(any(rule.startswith("negation:") for rule in result["detected_sentiments"][0]["rules"]))

    def test_intensifier_changes_score_and_matches_evidence(self) -> None:
        for text in ("정말 안 좋다", "안 정말 좋다", "정말 맛있지 않았어요"):
            with self.subTest(text=text):
                result = analyze_sentiment(text, self.lexicon)
                evidence = result["detected_sentiments"][0]
                self.assertEqual(result["final_score"], -1.5)
                self.assertEqual(evidence["base_score"], 1.0)
                self.assertEqual(evidence["weight"], -1.5)
                self.assertEqual(evidence["weighted_score"], -1.5)

    def test_ascii_case_normalization_matches_as_domain_entries(self) -> None:
        for text, expected in (("AS만족", 1.5), ("as만족", 1.5), ("As불만", -1.6)):
            with self.subTest(text=text):
                self.assertEqual(analyze_sentiment(text, self.lexicon)["final_score"], expected)

    def test_partial_words_do_not_override_negative_lexemes(self) -> None:
        self.assertEqual(analyze_sentiment("불친절하다", self.lexicon)["final_score"], -1.0)
        self.assertEqual(analyze_sentiment("좋다ness", self.lexicon)["label"], "neutral")
        self.assertEqual(analyze_sentiment("안좋다기록", self.lexicon)["label"], "neutral")

    def test_negation_does_not_cross_sentence_punctuation_or_another_noun(self) -> None:
        for text in ("좋다. 않다", "좋다, 않다", "좋다! 않다", "좋다\n않다", "좋다 문제는 없다"):
            with self.subTest(text=text):
                self.assertEqual(analyze_sentiment(text, self.lexicon)["final_score"], 1.0)

    def test_clause_negation_does_not_leak_to_next_sentiment(self) -> None:
        result = analyze_sentiment("안 좋지만 친절하다", self.lexicon)
        self.assertEqual(result["final_score"], 0.0)
        self.assertEqual([item["weight"] for item in result["detected_sentiments"]], [-1.0, 1.0])

    def test_double_negation_has_evidence_and_is_not_counted_twice(self) -> None:
        for text in ("나쁘지 않다", "나쁘지 않았어요", "불편하지 않아요"):
            with self.subTest(text=text):
                result = analyze_sentiment(text, self.lexicon)
                self.assertEqual(result["label"], "positive")
                self.assertEqual(len(result["detected_sentiments"]), 1)
                self.assertTrue(result["rule_logs"][0].startswith("double_negative:"))
                self.assertEqual(result["final_score"], result["detected_sentiments"][0]["weighted_score"])
        result = analyze_sentiment("나쁘지 않다. 나쁘지 않다", self.lexicon)
        self.assertEqual(result["final_score"], 3.0)

    def test_rules_disabled_keeps_surface_matching_but_does_not_flip_score(self) -> None:
        result = analyze_sentiment("정말 맛있지 않았어요", self.lexicon, use_rules=False)
        self.assertEqual(result["final_score"], 1.0)
        self.assertEqual(result["detected_sentiments"][0]["rules"], [])
        self.assertEqual(result["rule_logs"], [])

    def test_explicit_empty_custom_lexicon_does_not_load_default(self) -> None:
        with patch("src.sentiment.load_lexicon", side_effect=AssertionError("must not load")):
            self.assertEqual(analyze_sentiment("좋다", lexicon={})["label"], "neutral")

    def test_lexicon_counts_real_entries_and_alias_targets(self) -> None:
        general = self.lexicon["general_sentiment"]
        domain = self.lexicon["domain_sentiment"]
        self.assertGreaterEqual(len(general), 200)
        self.assertGreaterEqual(len(domain), 30)
        self.assertFalse(any(key.startswith(("긍정확장", "부정확장")) for key in general))
        self.assertEqual(self.lexicon["metadata"]["general_count"], len(general))
        normalized = {word.casefold() for word in {**general, **domain}}
        self.assertTrue(all(word.casefold() in normalized for word in self.lexicon["surface_forms"].values()))

    def test_dataset_is_unique_labeled_and_includes_challenge_categories(self) -> None:
        cases = json.loads((ROOT / "data/sentiment_test_cases.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(cases), 100)
        self.assertEqual(len(cases), len({case["text"] for case in cases}))
        self.assertEqual({case["label"] for case in cases}, {"positive", "negative", "neutral"})
        self.assertTrue({"negation", "intensifier", "domain", "challenge_sarcasm", "challenge_quote", "challenge_mixed"}
                        <= {case["category"] for case in cases})

    def test_archives_preserve_original_bytes(self) -> None:
        expected = {
            "sentiment_lexicon.json": "76ebcd0528283684aad787efc0f7fe9ccd1c8213ffc5c51cc4bb1176094b7184",
            "sentiment_test_cases.json": "fb2da83c6f55b6d04ad4355a05d854df10d26bc69b461ca521449802ff48a2ef",
        }
        for name, digest in expected.items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((ROOT / "data/archive" / name).read_bytes()).hexdigest(), digest)

    def test_result_contract_and_rendered_matching_details(self) -> None:
        result = analyze_sentiment("정말 좋다. 안 친절하다", self.lexicon)
        self.assertEqual(set(result), {"text", "tokens", "detected_sentiments", "rule_logs", "final_score", "label"})
        self.assertAlmostEqual(result["final_score"], sum(item["weighted_score"] for item in result["detected_sentiments"]))
        output = format_analysis(result)
        self.assertIn("weighted=1.5", output)
        self.assertIn("negation:안", output)
        self.assertEqual(tokenize("AS만족!"), ["as만족"])
        self.assertEqual(analyze_sentiment("", self.lexicon)["final_score"], 0.0)


if __name__ == "__main__":
    unittest.main()
