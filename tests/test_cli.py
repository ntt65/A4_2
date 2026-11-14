import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CliExtractionTests(unittest.TestCase):
    def _analyze(self, text: str, mask: bool = False) -> tuple[dict, str]:
        command = [sys.executable, "-B", "-X", "utf8", str(ROOT / "main.py"), "--text", text]
        if mask:
            command.append("--mask")
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
        extracted, _ = self._analyze("연락처 02-123-4567, 계약 1억 2천만원")
        self.assertEqual(extracted["phones"], ["02-123-4567"])
        self.assertEqual(extracted["amounts"], [120000000])

    def test_masking_preserves_sentiment_and_normalizes_duplicates(self) -> None:
        extracted, output = self._analyze("01012345678, 010.1234.5678 정말 좋다", mask=True)
        self.assertEqual(extracted["phones"], ["010-****-5678"])
        self.assertNotIn("01012345678", output)
        self.assertNotIn("010.1234.5678", output)
        self.assertIn("판정: positive", output)


if __name__ == "__main__":
    unittest.main()
