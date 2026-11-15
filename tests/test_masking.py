import unittest

from src.masking import mask_address, mask_card_number, mask_personal_info, mask_phone_number, mask_resident_id


class MaskingTests(unittest.TestCase):
    def test_phone_lengths_and_separators(self) -> None:
        for text, expected in (
            ("02-123-4567", "02-***-4567"),
            ("02 1234 5678", "02-****-5678"),
            ("031.123.4567", "031-***-4567"),
            ("01012345678", "010-****-5678"),
        ):
            with self.subTest(text=text):
                self.assertEqual(mask_phone_number(text), expected)

    def test_ids_cards_and_korean_boundaries(self) -> None:
        self.assertEqual(mask_resident_id("주민번호9001011234567입니다"), "주민번호900101-1******입니다")
        for value in ("1234567890123456", "1234-5678-9012-3456", "1234 5678 9012 3456"):
            with self.subTest(value=value):
                self.assertEqual(mask_card_number(value), "1234-****-****-3456")

    def test_longer_numeric_identifiers_are_not_partially_masked(self) -> None:
        self.assertEqual(mask_phone_number("0010123456789"), "0010123456789")
        self.assertEqual(mask_card_number("11234567890123456"), "11234567890123456")

    def test_combined_mask_and_empty_text(self) -> None:
        text = "900101-1234567, 1234-5678-9012-3456, 02-123-4567"
        masked = mask_personal_info(text)
        for raw in ("900101-1234567", "1234-5678-9012-3456", "02-123-4567"):
            self.assertNotIn(raw, masked)
        self.assertIn("02-***-4567", masked)
        self.assertEqual(mask_personal_info(""), "")

    def test_address_mask_retains_only_city_and_district(self) -> None:
        for text, expected in (
            ("서울 강남구 테헤란로 123으로 정했다.", "서울 강남구 ***으로 정했다."),
            ("경기도 성남시 분당구 판교역로 166 101동 1203호입니다.", "경기도 성남시 분당구 ***입니다."),
            ("세종특별자치시 한누리대로 2130 3층", "세종특별자치시 ***"),
            ("제주특별자치도 제주시 첨단로 242 301호", "제주특별자치도 제주시 ***"),
            ("강원특별자치도 평창군 봉평면 태기로 174 2층", "강원특별자치도 평창군 ***"),
            ("경북 안동시 풍천면 갈전리 123-4 201호에서 만나요.", "경북 안동시 ***에서 만나요."),
            ("서울 강남구 역삼동 123-4와 부산 해운대구 우동 456-7", "서울 강남구 ***와 부산 해운대구 ***"),
            ("서울 강남구 테헤란로 123, 101동, 12층, 1203호", "서울 강남구 ***"),
        ):
            with self.subTest(text=text):
                self.assertEqual(mask_address(text), expected)

    def test_combined_mask_removes_address_before_numeric_patterns(self) -> None:
        text = "서울 강남구 테헤란로 123 101동 202호, 연락처 010-1234-5678, 900101-1234567"
        self.assertEqual(
            mask_personal_info(text),
            "서울 강남구 ***, 연락처 010-****-5678, 900101-1******",
        )
        self.assertEqual(mask_address("서울 강남구 테헤란로"), "서울 강남구 테헤란로")
        self.assertEqual(mask_address(""), "")


if __name__ == "__main__":
    unittest.main()
