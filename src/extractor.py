import re
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse


# 이메일: 점으로 구분한 로컬 파트와 DNS 형태의 도메인.
# ASCII 주소 내부에서는 시작하지 않으며, 한국어 조사와 문장 끝 마침표는 허용한다.
EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9_%+-]+(?:\.[A-Za-z0-9_%+-]+)*"
    r"@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,}"
    r"(?![A-Za-z0-9_-]|\.[A-Za-z0-9.-])"
)

# 전화: 서울 02 및 3자리 국내 번호, 하이픈/점/공백/무구분 표기.
# 더 긴 숫자나 ASCII 식별자 내부의 부분 번호를 추출하지 않는다.
PHONE_PATTERN = re.compile(
    r"(?<![0-9A-Za-z_])(?:02[-. ]?\d{3,4}|0[1-9]\d[-. ]?\d{3,4})"
    r"[-. ]?\d{4}(?![0-9A-Za-z_])"
)

# 한글 날짜: 2자리/4자리 연도와 월일. 숫자 내부 매칭은 막고 한국어 조사는 허용한다.
KOR_DATE_PATTERN = re.compile(
    r"(?<!\d)(?P<year>\d{4}|\d{2})\s*년\s*(?P<month>\d{1,2})"
    r"\s*월\s*(?P<day>\d{1,2})\s*일(?!\d)"
)

# 구분자 날짜: 연월일에 같은 /, -, .을 사용한다. 혼합 구분자와 긴 숫자의 부분 매칭 방지.
SEP_DATE_PATTERN = re.compile(
    r"(?<!\d)(?P<year>\d{4}|\d{2})(?P<sep>[./-])(?P<month>\d{1,2})"
    r"(?P=sep)(?P<day>\d{1,2})(?!\d)"
)

# 금액 숫자 구성: 올바른 천 단위 쉼표 또는 무구분 숫자와 소수.
# 실제 시작/끝 경계와 통화 단위는 아래 완성 패턴에서 검사한다.
_AMOUNT_NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"

# 금액 시작 경계: 긴 숫자, 잘못된 쉼표/소수 및 ASCII 식별자 중간에서 시작하지 않는다.
_AMOUNT_START = r"(?<![0-9A-Za-z_.,])"

# 금액 끝 경계: 단위/숫자 중간에서 끝내지 않고 명·개 등 명시적인 수량 표기를 제외한다.
_AMOUNT_END = (
    r"(?![0-9A-Za-z_]|[.,]\d|억|천|백|십|만|원)"
    r"(?![ \t]*(?:명|개|건|번|회|년|월|일|배|장|대|%))"
)

# 숫자 금액: 달러 접두사 또는 원 접미사를 반드시 요구한다.
# 전화·날짜·일반 숫자는 통화 표시가 없으므로 금액으로 잡히지 않는다.
NUM_AMOUNT_PATTERN = re.compile(
    rf"{_AMOUNT_START}(?:\$[ \t]*{_AMOUNT_NUMBER}|{_AMOUNT_NUMBER}[ \t]*원){_AMOUNT_END}"
)

# 한글 복합 금액: 숫자+단위가 최소 한 번 존재해야 하며, 여러 금액을 모두 찾는다.
# 개행을 넘어 합산하지 않고, 빈 문자열이나 단위 중간의 부분 매칭을 막는다.
KOR_AMOUNT_PATTERN = re.compile(
    rf"{_AMOUNT_START}(?:{_AMOUNT_NUMBER}[ \t]*"
    rf"(?:억|천만|백만|십만|만|천|백|십)[ \t]*)+"
    rf"(?:{_AMOUNT_NUMBER}[ \t]*원|원)?{_AMOUNT_END}"
)

# 복합 금액의 구성 요소: 천·백·십을 모아 만·억 앞에서 묶는다.
# '2천만'의 만처럼 숫자 없는 큰 단위도 소비하며, 빈 매칭은 허용하지 않는다.
_KOR_COMPONENT_PATTERN = re.compile(
    rf"(?P<value>{_AMOUNT_NUMBER})?(?P<unit>억|만|천|백|십)"
)

_KOR_UNITS = {
    "억": 100_000_000, "만": 10_000, "천": 1_000, "백": 100, "십": 10,
}

# URL: http(s), 호스트, 포트와 선택적 경로/쿼리/fragment. 슬래시 없는 ?query도 허용한다.
# ASCII 식별자 내부의 가짜 스킴 및 도메인 중간 매칭을 막고 공백·각괄호·한글 문장을 넘지 않는다.
URL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])https?://"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*"
    r"(?::\d+)?(?:[/?#][A-Za-z0-9\-._~:/?#[\]@!$&'()*+,;=%]*)?"
    r"(?![A-Za-z0-9_-]|\.[A-Za-z0-9.-])",
    re.IGNORECASE,
)

# 전화번호 정규화용: 숫자가 아닌 구분자만 제거한다. 추출 경계는 PHONE_PATTERN이 검사한다.
_NON_DIGIT_PATTERN = re.compile(r"\D")


def _normalize_phone(raw: str) -> str:
    digits = _NON_DIGIT_PATTERN.sub("", raw)
    prefix = 2 if digits.startswith("02") else 3
    return f"{digits[:prefix]}-{digits[prefix:-4]}-{digits[-4:]}"


def _normalize_year(year: int) -> int:
    return (2000 + year if year < 50 else 1900 + year) if year < 100 else year


def _normalize_date(year: int, month: int, day: int) -> str | None:
    try:
        return date(_normalize_year(year), month, day).isoformat()
    except ValueError:
        return None


def _normalize_amount(raw: str) -> int | None:
    value = raw.strip().replace(",", "")
    if value.startswith("$"):
        value = value[1:].strip()
    elif value.endswith("원"):
        value = value[:-1].strip()
    else:
        return None
    try:
        return int(Decimal(value))
    except (InvalidOperation, ValueError):
        return None


def _normalize_korean_amount(raw: str) -> int | None:
    # 억·만은 금액 단위로 허용한다. 천·백·십 단독 표기는 원 접미사가 있어야 한다.
    if not raw.rstrip().endswith("원") and "억" not in raw and "만" not in raw:
        return None
    value = raw.replace(" ", "").replace("\t", "").replace(",", "")
    if value.endswith("원"):
        value = value[:-1]
    total = Decimal(0)
    section = Decimal(0)
    position = 0
    try:
        for match in _KOR_COMPONENT_PATTERN.finditer(value):
            if match.start() != position:
                return None
            number = Decimal(match["value"]) if match["value"] is not None else None
            unit = _KOR_UNITS[match["unit"]]
            if unit >= 10_000:
                # 3천5백만은 (3000 + 500) × 10000이다. 명시적 0만은 0을 유지한다.
                coefficient = section + (number if number is not None else Decimal(0))
                if number is None and not section:
                    coefficient = Decimal(1)
                total += coefficient * unit
                section = Decimal(0)
            else:
                section += (number if number is not None else Decimal(1)) * unit
            position = match.end()
        if value[position:]:
            section += Decimal(value[position:])
        return int(total + section) if position else None
    except (InvalidOperation, ValueError):
        return None


def _normalize_url(raw: str) -> str | None:
    value = raw.rstrip(".,;:!'\"")
    for opening, closing in (("(", ")"), ("[", "]"), ("{", "}")):
        while value.endswith(closing) and value.count(closing) > value.count(opening):
            value = value[:-1]
    try:
        parsed = urlparse(value)
        _ = parsed.port
        return parsed._replace(scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower()).geturl()
    except ValueError:
        return None


def _overlaps(span: tuple[int, int], protected: list[tuple[int, int]]) -> bool:
    return any(span[0] < end and start < span[1] for start, end in protected)


def extract_information(text: str) -> dict[str, list]:
    emails = sorted({match.group(0).lower() for match in EMAIL_PATTERN.finditer(text)})
    phones = sorted({_normalize_phone(match.group(0)) for match in PHONE_PATTERN.finditer(text)})
    dates: set[str] = set()
    for pattern in (KOR_DATE_PATTERN, SEP_DATE_PATTERN):
        for match in pattern.finditer(text):
            normalized = _normalize_date(int(match["year"]), int(match["month"]), int(match["day"]))
            if normalized is not None:
                dates.add(normalized)

    url_matches = list(URL_PATTERN.finditer(text))
    urls = {value for match in url_matches if (value := _normalize_url(match.group(0))) is not None}
    protected = [match.span() for match in url_matches]
    amounts: set[int] = set()
    for match in KOR_AMOUNT_PATTERN.finditer(text):
        if _overlaps(match.span(), protected):
            continue
        value = _normalize_korean_amount(match.group(0))
        if value is not None:
            amounts.add(value)
            protected.append(match.span())
    for match in NUM_AMOUNT_PATTERN.finditer(text):
        if not _overlaps(match.span(), protected):
            value = _normalize_amount(match.group(0))
            if value is not None:
                amounts.add(value)
    return {
        "emails": emails, "phones": phones, "dates": sorted(dates),
        "amounts": sorted(amounts), "urls": sorted(urls),
    }
