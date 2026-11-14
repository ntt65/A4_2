import re
from datetime import date
from urllib.parse import urlparse, urlunparse


# 이메일 패턴: 로컬파트(영문/숫자/._%+-) + @ + 도메인(서브도메인 포함) + 최상위 도메인
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# 전화번호 패턴: 지역번호/휴대폰 번호 + 구분자(-, ., 공백) + 국번 + 구분자 + 가입자 번호
PHONE_PATTERN = re.compile(r"\b(?:0\d{1,2})[-.\s]?\d{3,4}[-.\s]?\d{4}\b")

# 날짜 패턴(한글): YYYY년 M월 D일 형식
KOR_DATE_PATTERN = re.compile(r"\b(\d{2,4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\b")

# 날짜 패턴(구분자): YYYY/MM/DD, YYYY-MM-DD, YYYY.MM.DD, YY.MM.DD 형식
SEP_DATE_PATTERN = re.compile(r"\b(\d{2,4})[./-](\d{1,2})[./-](\d{1,2})\b")

# 금액 패턴(숫자): 10,000원 / 50000원 / 3만원 같은 숫자 기반 금액
NUM_AMOUNT_PATTERN = re.compile(r"\b\$\s?\d{1,3}(?:,\d{3})*(?:\.\d+)?\b|\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:원|만원)?\b")

# 금액 패턴(한글 단위): 1억 2천만원, 3천만원 등 한국어 단위 결합 금액
KOR_AMOUNT_PATTERN = re.compile(r"\b(?:(\d+)\s*억)?\s*(?:(\d+)\s*천\s*만\s*원?)?\b")

# URL 패턴: http/https 스킴 + 호스트 + 선택적 경로/쿼리
URL_PATTERN = re.compile(r"\bhttps?://[A-Za-z0-9.-]+(?:\:[0-9]+)?(?:/[A-Za-z0-9\-._~:/?#[\]@!$&'()*+,;=%]*)?\b")


def _normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("02"):
        if len(digits) == 9:
            return f"{digits[:2]}-{digits[2:5]}-{digits[5:]}"
        if len(digits) == 10:
            return f"{digits[:2]}-{digits[2:6]}-{digits[6:]}"
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    if len(digits) == 11:
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    return raw


def _normalize_year(year: int) -> int:
    if year < 100:
        return 2000 + year if year < 50 else 1900 + year
    return year


def _normalize_date(year: int, month: int, day: int) -> str | None:
    year = _normalize_year(year)
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _normalize_amount(raw: str) -> int | None:
    text = raw.strip().replace(",", "")
    if text.startswith("$"):
        value = text.replace("$", "").strip()
        try:
            return int(float(value))
        except ValueError:
            return None

    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(원|만원)?", text)
    if not match:
        return None

    value = float(match.group(1))
    unit = match.group(2)
    if unit == "만원":
        value *= 10000
    return int(value)


def _normalize_korean_amount(text: str) -> int | None:
    match = KOR_AMOUNT_PATTERN.search(text)
    if not match:
        return None

    eok = int(match.group(1)) if match.group(1) else 0
    cheonman = int(match.group(2)) if match.group(2) else 0
    total = eok * 100_000_000 + cheonman * 10_000_000
    return total or None


def _normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", parsed.query, ""))


def extract_information(text: str) -> dict[str, list]:
    emails = sorted({m.group(0).lower() for m in EMAIL_PATTERN.finditer(text)})
    phones = sorted({_normalize_phone(m.group(0)) for m in PHONE_PATTERN.finditer(text)})

    dates = set()
    for m in KOR_DATE_PATTERN.finditer(text):
        normalized = _normalize_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if normalized:
            dates.add(normalized)

    for m in SEP_DATE_PATTERN.finditer(text):
        normalized = _normalize_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if normalized:
            dates.add(normalized)

    amounts = set()
    for m in NUM_AMOUNT_PATTERN.finditer(text):
        normalized = _normalize_amount(m.group(0))
        if normalized is not None:
            amounts.add(normalized)

    korean_amount = _normalize_korean_amount(text)
    if korean_amount is not None:
        amounts.add(korean_amount)

    urls = sorted({_normalize_url(m.group(0)) for m in URL_PATTERN.finditer(text)})

    return {
        "emails": emails,
        "phones": phones,
        "dates": sorted(dates),
        "amounts": sorted(amounts),
        "urls": urls,
    }
