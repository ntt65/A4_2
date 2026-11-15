import json
import tempfile
import unittest
from pathlib import Path

from src.evaluator import evaluate_information_extraction
from src.extractor import extract_addresses, extract_information


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
            ("3천5백만원", [35000000]),
            ("1억2천3백만원", [123000000]),
            ("1억2천3백4십5만원", [123450000]),
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

    def test_road_and_lot_addresses_with_details(self) -> None:
        addresses = (
            "서울특별시 강남구 테헤란로 123",
            "경기도 성남시 분당구 판교역로 166 101동 1203호",
            "세종특별자치시 한누리대로 2130 3층",
            "제주특별자치도 제주시 첨단로 242 301호",
            "강원특별자치도 평창군 봉평면 태기로 174 2층",
            "전북특별자치도 전주시 완산구 효자로 225",
            "경북 안동시 풍천면 갈전리 123-4 201호",
            "부산 해운대구 우동 1408",
            "서울 중구 을지로1가 10",
            "경기도 가평군 가평읍 읍내리 산 12-3",
            "대전 유성구 대학로 99 지하 1층 101호",
            "인천 연수구 센트럴로 100 101동202호",
        )
        for address in addresses:
            with self.subTest(address=address):
                self.assertEqual(extract_addresses(f"주소는 {address}입니다."), [address])
                self.assertEqual(extract_information(address, include_addresses=True)["addresses"], [address])

    def test_address_normalization_duplicates_and_particles(self) -> None:
        text = (
            "서울  강남구\t테헤란로 123, 101동 202호와 "
            "부산 해운대구 우동 456-7에서 만나요. "
            "서울 강남구 테헤란로 123 101동 202호"
        )
        self.assertEqual(extract_addresses(text), sorted([
            "서울 강남구 테헤란로 123 101동 202호", "부산 해운대구 우동 456-7",
        ]))
        self.assertEqual(
            extract_addresses("배송지는 서울 강남구 테헤란로 123으로 정했다."),
            ["서울 강남구 테헤란로 123"],
        )
        self.assertEqual(
            extract_addresses("서울 강남구 테헤란로 123, 101동, 12층, 1203호"),
            ["서울 강남구 테헤란로 123 101동 12층 1203호"],
        )

    def test_address_boundaries_reject_incomplete_and_embedded_values(self) -> None:
        for text in (
            "", "서울 강남구 테헤란로에서 만나요", "부산 해운대구입니다",
            "강남구 테헤란로 123", "key_서울 강남구 테헤란로 123",
            "가짜서울 강남구 테헤란로 123", "서울 강남구 테헤란로 123ABC",
            "서울 강남구 테헤란로 12.5", "서울 강남구 테헤란로 123-45-6",
            "서울 강남구 테헤란로 123원", "서울 강남구 테헤란로 123/45",
            "https://example.com/서울 강남구 테헤란로 123",
            "https://example.com/?address=서울 강남구 테헤란로 123",
            "서울 강남구 테헤란로\n123",
        ):
            with self.subTest(text=text):
                self.assertEqual(extract_addresses(text), [])
        self.assertEqual(extract_information("일정 확인", include_addresses=True)["addresses"], [])

    def test_address_evaluation_counts_only_annotated_cases(self) -> None:
        correct = "서울 강남구 테헤란로 123"
        wrong = "부산 해운대구 우동 456-7"
        cases = [
            {"text": correct, "labels": {"addresses": [correct]}},
            {"text": wrong, "labels": {"addresses": [correct]}},
            {"text": wrong, "labels": {"addresses": []}},
            {"text": correct, "labels": {"emails": []}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "addresses.json"
            path.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
            metrics, report = evaluate_information_extraction(path)
        self.assertAlmostEqual(metrics["addresses"]["precision"], 1 / 3)
        self.assertAlmostEqual(metrics["addresses"]["recall"], 1 / 2)
        self.assertIn("addresses", report)


if __name__ == "__main__":
    unittest.main()
