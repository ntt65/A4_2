import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.aspect_sentiment import analyze_aspects, format_aspect_analysis
from src.evaluator import evaluate_aspect_sentiment


class AspectSentimentTests(unittest.TestCase):
    def _aspects(self, text: str, **kwargs: object) -> dict[str, dict]:
        return {item["aspect"]: item for item in analyze_aspects(text, **kwargs)["aspects"]}

    def test_mission_example_separates_opposing_sentiments(self) -> None:
        aspects = self._aspects("음식은 맛있는데 가격이 비싸요")
        self.assertEqual({key: item["label"] for key, item in aspects.items()}, {"음식": "positive", "가격": "negative"})
        self.assertEqual(aspects["음식"]["final_score"], 1.0)
        self.assertEqual(aspects["가격"]["final_score"], -1.0)

    def test_negation_and_intensification_stay_with_their_aspect(self) -> None:
        aspects = self._aspects("음식은 정말 안 맛있지만 가격은 정말 저렴하다")
        self.assertEqual(aspects["음식"]["final_score"], -1.5)
        self.assertEqual(aspects["가격"]["final_score"], 1.5)
        evidence = aspects["음식"]["detected_sentiments"][0]
        self.assertEqual(evidence["base_score"], 1.0)
        self.assertEqual(evidence["weight"], -1.5)
        self.assertEqual(set(evidence["rules"]), {"intensifier:정말", "negation:안"})

    def test_double_negation_is_not_counted_twice(self) -> None:
        aspects = self._aspects("음식은 나쁘지 않다. 서비스는 불편하지 않다")
        for aspect, expected_score in (("음식", 1.5), ("서비스", 1.2)):
            item = aspects[aspect]
            self.assertEqual(item["label"], "positive")
            self.assertEqual(item["final_score"], expected_score)
            self.assertEqual(len(item["detected_sentiments"]), 1)
            self.assertTrue(item["detected_sentiments"][0]["rules"][0].startswith("double_negative:"))

    def test_no_modifier_leaks_across_punctuation_or_aspect_boundary(self) -> None:
        for text in ("음식은 좋다. 서비스는 안 친절하다", "음식은 좋고 서비스는 안 친절하다"):
            with self.subTest(text=text):
                aspects = self._aspects(text)
                self.assertEqual(aspects["음식"]["final_score"], 1.0)
                self.assertEqual(aspects["서비스"]["final_score"], -1.0)

    def test_aliases_map_to_canonical_aspects(self) -> None:
        aspects = self._aspects("요리는 맛있다 비용은 저렴하다 택배는 느리다 성능이 좋다 상담은 친절하다")
        self.assertEqual({key: item["label"] for key, item in aspects.items()}, {
            "음식": "positive", "가격": "positive", "배송": "negative", "품질": "positive", "서비스": "positive",
        })

    def test_noun_boundary_and_missing_aspect_do_not_invent_mentions(self) -> None:
        for text in ("", "맛있다", "음식점은 좋다 가격표는 비싸다 서비스업은 친절하다 배송지는 빠르다", "주차는 좋다"):
            with self.subTest(text=text):
                self.assertEqual(analyze_aspects(text)["aspects"], [])
        neutral = self._aspects("가격은 확인했다")["가격"]
        self.assertEqual(neutral["label"], "neutral")
        self.assertEqual(neutral["detected_sentiments"], [])

    def test_coordinated_aspects_share_the_predicate(self) -> None:
        for text, score in (("음식과 서비스가 좋다", 1.0), ("음식 및 서비스가 안 좋다", -1.0)):
            with self.subTest(text=text):
                aspects = self._aspects(text)
                self.assertEqual(set(aspects), {"음식", "서비스"})
                self.assertEqual([item["final_score"] for item in aspects.values()], [score, score])
        aspects = self._aspects("음식은 서비스가 좋다")
        self.assertEqual(aspects["음식"]["label"], "neutral")
        self.assertEqual(aspects["서비스"]["label"], "positive")

    def test_repeated_aspect_sums_and_duplicate_alias_is_not_double_counted(self) -> None:
        item = self._aspects("음식은 좋다. 메뉴는 나쁘다")["음식"]
        self.assertEqual(item["final_score"], 0.0)
        self.assertEqual(item["label"], "neutral")
        self.assertEqual(len(item["segments"]), 2)
        item = self._aspects("음식과 메뉴가 좋다")["음식"]
        self.assertEqual(len(item["mentions"]), 2)
        self.assertEqual(len(item["segments"]), 1)
        self.assertEqual(item["final_score"], 1.0)

    def test_spans_refer_to_original_text_and_scores_match_evidence(self) -> None:
        text = "문의: 음식은 정말 맛있다; 가격은 비싸다!"
        for item in analyze_aspects(text)["aspects"]:
            self.assertEqual(item["final_score"], sum(e["weighted_score"] for e in item["detected_sentiments"]))
            for span_item in item["mentions"] + item["segments"]:
                start, end = span_item["span"]
                self.assertEqual(text[start:end], span_item["text"])

    def test_omitted_aspect_is_not_carried_to_next_clause(self) -> None:
        item = self._aspects("음식은 좋지만 나쁘다")["음식"]
        self.assertEqual(item["final_score"], 1.0)
        self.assertEqual(len(item["segments"]), 1)

    def test_custom_empty_lexicon_and_disabled_rules(self) -> None:
        with patch("src.aspect_sentiment.load_lexicon", side_effect=AssertionError("must not load")):
            self.assertEqual(self._aspects("음식은 좋다", lexicon={})["음식"]["label"], "neutral")
        item = self._aspects("음식은 안 맛있다", use_rules=False)["음식"]
        self.assertEqual(item["final_score"], 1.0)
        self.assertEqual(item["detected_sentiments"][0]["rules"], [])

    def test_formatter_includes_aspects_weights_and_empty_state(self) -> None:
        output = format_aspect_analysis(analyze_aspects("음식은 안 맛있다 가격은 확인했다"))
        self.assertIn("측면: 음식 | 점수: -1 | 판정: negative", output)
        self.assertIn("weight=-1.0", output)
        self.assertIn("감성 근거 없음", output)
        self.assertIn("지원하는 명시적 측면 없음", format_aspect_analysis(analyze_aspects("좋다")))

    def test_evaluation_counts_wrong_missing_and_extra_aspects(self) -> None:
        cases = [
            {"text": "음식은 좋다", "aspects": {"음식": "positive"}},
            {"text": "가격은 비싸다", "aspects": {"가격": "positive"}},
            {"text": "서비스는 친절하다", "aspects": {}},
            {"text": "비싸다", "aspects": {"가격": "negative"}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
            result, report = evaluate_aspect_sentiment(path)
        self.assertEqual(result["counts"], {"aspect_tp": 2, "pair_tp": 1, "gold": 3, "predicted": 3, "exact": 1})
        for metric in result["aspect_detection"].values():
            self.assertAlmostEqual(metric, 2 / 3)
        for metric in result["aspect_sentiment"].values():
            self.assertAlmostEqual(metric, 1 / 3)
        self.assertEqual(result["exact_match_accuracy"], 1 / 4)
        self.assertEqual(result["sentiment_accuracy_on_detected"], 1 / 2)
        self.assertAlmostEqual(result["sentiment_macro_f1"], 1 / 6)
        self.assertEqual(len(result["predictions"]), 4)
        self.assertIn("[Aspect 감성 평가]", report)

    def test_empty_evaluation_defends_zero_denominators(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text("[]", encoding="utf-8")
            result, _ = evaluate_aspect_sentiment(path)
        self.assertEqual(result["case_count"], 0)
        self.assertEqual(result["exact_match_accuracy"], 0.0)
        self.assertEqual(result["sentiment_accuracy_on_detected"], 0.0)
        self.assertEqual(result["sentiment_macro_f1"], 0.0)
        self.assertTrue(all(value == 0.0 for value in result["aspect_sentiment"].values()))

    def test_development_dataset_preserves_unique_texts_and_challenges(self) -> None:
        path = Path(__file__).resolve().parents[1] / "data/aspect_sentiment_test_cases.json"
        cases = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(cases), len({case["text"] for case in cases}))
        self.assertEqual({label for case in cases for label in case["aspects"].values()}, {"positive", "negative", "neutral"})
        self.assertTrue(any(case["category"].startswith("challenge_") for case in cases))


if __name__ == "__main__":
    unittest.main()
