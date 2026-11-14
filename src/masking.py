import re

from src.extractor import PHONE_PATTERN


# 주민번호 모양 6+7자리. 더 긴 숫자 내부는 제외하고 한국어에 바로 붙은 번호는 가린다.
_RESIDENT_PATTERN = re.compile(r"(?<!\d)(\d{6})-?(\d)\d{6}(?!\d)")

# 카드 모양 4자리 4묶음. 숫자 경계로 더 긴 번호의 부분 매칭을 막는다.
_CARD_PATTERN = re.compile(r"(?<!\d)(\d{4})[- ]?\d{4}[- ]?\d{4}[- ]?(\d{4})(?!\d)")

# 전화 구분자만 제거한다. 실제 번호 경계와 길이는 공유 PHONE_PATTERN이 검사한다.
_NON_DIGIT_PATTERN = re.compile(r"\D")


def mask_resident_id(text: str) -> str:
    return _RESIDENT_PATTERN.sub(r"\1-\2******", text)


def mask_card_number(text: str) -> str:
    return _CARD_PATTERN.sub(r"\1-****-****-\2", text)


def mask_phone_number(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        digits = _NON_DIGIT_PATTERN.sub("", match.group(0))
        prefix = 2 if digits.startswith("02") else 3
        middle = "*" * (len(digits) - prefix - 4)
        return f"{digits[:prefix]}-{middle}-{digits[-4:]}"

    return PHONE_PATTERN.sub(repl, text)


def mask_personal_info(text: str) -> str:
    return mask_phone_number(mask_card_number(mask_resident_id(text)))
