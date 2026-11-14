import unittest

from src.masking import mask_card_number, mask_personal_info, mask_phone_number, mask_resident_id


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


if __name__ == "__main__":
    unittest.main()
