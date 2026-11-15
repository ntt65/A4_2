import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CliExtractionTests(unittest.TestCase):
    def _analyze(self, text: str, mask: bool = False, aspect: bool = False) -> tuple[dict, str]:
        command = [sys.executable, "-B", "-X", "utf8", str(ROOT / "main.py"), "--text", text]
        if mask:
            command.append("--mask")
        if aspect:
            command.append("--aspect")
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = result.stdout.split("[정보 추출 결과]", 1)[1].lstrip()
        extracted, _ = json.JSONDecoder().raw_decode(output)
        return extracted, result.stdout

    def test_extracts_original_then_masks_display(self) -> None:
        extracted, output = self._analyze("연락처 02-123-4567, 비용 10000원", mask=True)
        self.assertEqual(extracted["phones"], ["02-***-4567"])
        self.assertEqual(extracted["amounts"], [10000])
        self.assertNotIn("02-123-4567", output)

    def test_normal_output_is_preserved(self) -> None:
        extracted, output = self._analyze("연락처 02-123-4567, 계약 1억 2천만원")
        self.assertEqual(extracted["phones"], ["02-123-4567"])
        self.assertEqual(extracted["amounts"], [120000000])
        self.assertNotIn("[Aspect 감성 분석 결과]", output)

    def test_masking_preserves_sentiment_and_normalizes_duplicates(self) -> None:
        extracted, output = self._analyze("01012345678, 010.1234.5678 정말 좋다", mask=True)
        self.assertEqual(extracted["phones"], ["010-****-5678"])
        self.assertNotIn("01012345678", output)
        self.assertNotIn("010.1234.5678", output)
        self.assertIn("판정: positive", output)

    def test_aspect_option_and_masking_use_the_displayed_text(self) -> None:
        _, output = self._analyze("음식은 맛있는데 가격이 비싸요. 연락처 010-1234-5678", mask=True, aspect=True)
        self.assertIn("측면: 음식 | 점수: +1 | 판정: positive", output)
        self.assertIn("측면: 가격 | 점수: -1 | 판정: negative", output)
        self.assertNotIn("010-1234-5678", output)

    def test_aspect_requires_text(self) -> None:
        result = subprocess.run(
            [sys.executable, "-B", "-X", "utf8", str(ROOT / "main.py"), "--aspect"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--aspect requires --text", result.stderr)

    def test_aspect_evaluation_resolves_data_outside_repository(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-B", "-X", "utf8", str(ROOT / "main.py"), "--evaluate-aspect"],
                cwd=directory, capture_output=True, text=True, encoding="utf-8", timeout=20,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[Aspect 감성 평가]", result.stdout)
        self.assertIn("측면·극성 Precision/Recall/F1:", result.stdout)

    def test_address_extraction_and_masked_display(self) -> None:
        address = "경기도 성남시 분당구 판교역로 166 101동 1203호"
        text = f"배송지는 {address}입니다. 서비스는 정말 좋다. 연락처 02-123-4567"
        extracted, _ = self._analyze(text)
        self.assertEqual(extracted["addresses"], [address])
        masked, output = self._analyze(text, mask=True)
        self.assertEqual(masked["addresses"], ["경기도 성남시 분당구 ***"])
        self.assertEqual(masked["phones"], ["02-***-4567"])
        for detail in ("판교역로", "166", "101동", "1203호", "02-123-4567"):
            with self.subTest(detail=detail):
                self.assertNotIn(detail, output)
        self.assertIn("판정: positive", output)


if __name__ == "__main__":
    unittest.main()
