import json
import unittest
from pathlib import Path

from src.extractor import extract_information


class ExtractorTests(unittest.TestCase):
    def test_existing_fifty_gold_sentences(self) -> None:
        path = Path(__file__).resolve().parents[1] / "data" / "ie_test_cases.json"
        cases = json.loads(path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(cases), 50)
        for case in cases:
            with self.subTest(text=case["text"]):
                actual = extract_information(case["text"])
                self.assertEqual(actual, {key: sorted(values) for key, values in case["labels"].items()})

    def test_at_least_three_variants_per_pattern(self) -> None:
        variants = {
            "emails": [("USER@EXAMPLE.COM", "user@example.com"), ("a.b@sub.example.kr", "a.b@sub.example.kr"), ("a+tag@example.org", "a+tag@example.org")],
            "phones": [("010-1234-5678", "010-1234-5678"), ("010.1234.5678", "010-1234-5678"), ("010 1234 5678", "010-1234-5678"), ("01012345678", "010-1234-5678")],
            "dates": [("2024년 1월 15일", "2024-01-15"), ("2024/01/15", "2024-01-15"), ("24.01.15", "2024-01-15"), ("2024-1-15", "2024-01-15")],
            "amounts": [("10,000원", 10000), ("50000원", 50000), ("1억 2천만원", 120000000), ("$100", 100)],
            "urls": [("https://EXAMPLE.COM", "https://example.com"), ("http://example.kr?a=1&b=2", "http://example.kr?a=1&b=2"), ("https://example.com/path?q=1#section", "https://example.com/path?q=1#section")],
        }
        for category, cases in variants.items():
            for text, expected in cases:
                with self.subTest(category=category, text=text):
                    self.assertEqual(extract_information(text)[category], [expected])

    def test_money_multiple_compound_decimal_and_zero(self) -> None:
        for text, expected in (
            ("1억 2천만원과 3만원, $100", [100, 30000, 120000000]),
            ("1억 5000원", [100005000]),
            ("1.5만원과 $49.9", [49, 15000]),
            ("0원, 0만원", [0]),
            ("3천원", [3000]),
        ):
            with self.subTest(text=text):
                self.assertEqual(extract_information(text)["amounts"], expected)

    def test_plain_numbers_quantities_and_urls_are_not_money(self) -> None:
        text = "010-1234-5678 2024-01-15 123456 10,000 12,34원 3천개 3만 명 1억명"
        self.assertEqual(extract_information(text)["amounts"], [])
        self.assertEqual(extract_information("https://example.com/?price=$100")["amounts"], [])

    def test_numeric_and_calendar_boundaries(self) -> None:
        for text in ("2024-02-30", "2024/01-15", "12024-01-15", "2024-01-150"):
            with self.subTest(text=text):
                self.assertEqual(extract_information(text)["dates"], [])
        self.assertEqual(extract_information("A01012345678 0010123456789")["phones"], [])

    def test_korean_adjacent_text_and_email_boundaries(self) -> None:
        result = extract_information("메일은USER@EXAMPLE.COM입니다. 연락처01012345678입니다.")
        self.assertEqual(result["emails"], ["user@example.com"])
        self.assertEqual(result["phones"], ["010-1234-5678"])
        self.assertEqual(extract_information("bad..name@example.com")["emails"], [])
        self.assertEqual(extract_information("user@example.com.")["emails"], ["user@example.com"])

    def test_url_punctuation_fragment_and_port(self) -> None:
        result = extract_information("참고 (HTTPS://EXAMPLE.COM/a(b)).")
        self.assertEqual(result["urls"], ["https://example.com/a(b)"])
        self.assertEqual(extract_information("http://example.com:999999/test")["urls"], [])


if __name__ == "__main__":
    unittest.main()
