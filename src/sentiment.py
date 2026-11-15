import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LEXICON_PATH = BASE_DIR / "data" / "sentiment_lexicon.json"

# 한글·영문·숫자의 최대 연속 구간을 매칭한다. 단어 전체를 사용하므로
# '불친절하다' 안의 '친절하다'가 부분 매칭되어 긍정이 되는 일을 막는다.
TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9]+")
# 토큰 사이 문장부호·줄바꿈을 경계로 삼아 부정어가 다른 절로 전파되지 않게 한다.
# 단어 내부 일부를 경계로 자르지 않는다.
CLAUSE_BOUNDARY_PATTERN = re.compile(r"[,.;:!?…\n]")
ENDINGS = (
    "다", "요", "아요", "어요", "네요", "네", "고", "지만", "서", "어서", "아서",
    "면", "으면", "지", "지는", "지도", "은", "는", "을", "게", "다고", "다니",
    "았다", "었다", "았어요", "었어요", "았고", "었고", "았지만", "었지만",
    "았습니다", "었습니다", "습니다", "은데", "는데", "에요",
)
PARTICLES = ("이", "가", "은", "는", "을", "를", "도", "만", "에", "에서", "으로", "로", "과", "와")
SCOPE_ADVERBS = {"전혀", "결코", "조금도"}
CONJUNCTIONS = {"하지만", "그러나", "그런데", "다만", "반면"}


def load_lexicon(path: Path = LEXICON_PATH) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.casefold())


def _surface_forms(word: str) -> set[str]:
    word = word.casefold()
    forms = {word}
    if word.endswith("다"):
        stem = word[:-1]
        forms.update(stem + ending for ending in ENDINGS)
        if stem.endswith("하"):
            forms.update(stem[:-1] + ending for ending in (
                "해", "해요", "해서", "했고", "했어요", "했다", "했지만", "했습니다", "한", "하게", "합니다",
            ))
    else:
        forms.update(word + particle for particle in PARTICLES)
    return forms


def _surface_index(lexicon: dict) -> dict[str, tuple[str, float]]:
    words = {str(key).casefold(): float(value) for key, value in {
        **lexicon.get("general_sentiment", {}), **lexicon.get("domain_sentiment", {}),
    }.items()}
    index = {word: (word, score) for word, score in words.items()}
    for word, score in words.items():
        for form in _surface_forms(word):
            index.setdefault(form, (word, score))
    for form, word in lexicon.get("surface_forms", {}).items():
        normalized = word.casefold()
        if normalized in words:
            index[form.casefold()] = (normalized, words[normalized])
    return index


def _clause_ids(text: str) -> list[int]:
    matches = list(TOKEN_PATTERN.finditer(text.casefold()))
    clauses = []
    clause = 0
    for index, match in enumerate(matches):
        if index:
            previous = matches[index - 1]
            if (CLAUSE_BOUNDARY_PATTERN.search(text[previous.end():match.start()])
                    or previous.group().endswith(("지만", "는데"))
                    or match.group() in CONJUNCTIONS):
                clause += 1
        clauses.append(clause)
    return clauses


def _modifiers(
    tokens: list[str], start: int, end: int, clauses: list[int],
    negations: set[str], intensifiers: set[str],
) -> tuple[float, list[str]]:
    weight = 1.0
    rules = []
    intensified = False
    # 연속된 앞쪽 수식어 최대 세 개만 적용한다. 명사나 다른 감성어를 넘지 않는다.
    for index in range(start - 1, max(-1, start - 4), -1):
        if clauses[index] != clauses[start]:
            break
        token = tokens[index]
        if token in intensifiers:
            if not intensified:
                weight *= 1.5
                intensified = True
                rules.append(f"intensifier:{token}")
        elif token in negations:
            weight *= -1
            rules.append(f"negation:{token}")
        elif token not in SCOPE_ADVERBS:
            break
    # 뒤쪽은 부정 보조 용언/허용 부사만 본다. '안/못'은 다음 감성어의 접두 부정어다.
    # '좋고 안 나쁘다'의 좋고까지 반전시키거나 '좋다. 문제는 없다'를 뒤집지 않는다.
    postposed_negations = negations & {"않다", "없다", "아니다"}
    negative_forms = set().union(*(_surface_forms(word) for word in postposed_negations)) if postposed_negations else set()
    for index in range(end + 1, min(len(tokens), end + 4)):
        if clauses[index] != clauses[end]:
            break
        token = tokens[index]
        if token in negative_forms:
            weight *= -1
            rules.append(f"negation:{token}")
            break
        if token not in SCOPE_ADVERBS:
            break
    return weight, rules


def _phrase_matches(actual: list[str], expected: list[str]) -> bool:
    return all(
        token == target
        or (target.endswith("다") and token in _surface_forms(target))
        or (target.endswith("지") and token in {target + "는", target + "도"})
        for token, target in zip(actual, expected)
    )


def _label_from_score(score: float) -> str:
    if score > 0.5:
        return "positive"
    if score < -0.5:
        return "negative"
    return "neutral"


def analyze_sentiment(text: str, lexicon: dict | None = None, use_rules: bool = True) -> dict:
    lexicon = load_lexicon() if lexicon is None else lexicon
    index = _surface_index(lexicon)
    negations = {word.casefold() for word in lexicon.get("negations", [])}
    intensifiers = {word.casefold() for word in lexicon.get("intensifiers", [])}
    tokens = tokenize(text)
    clauses = _clause_ids(text)
    score = 0.0
    detected = []
    rule_logs = []
    consumed: set[int] = set()

    if use_rules:
        phrases = sorted(lexicon.get("double_negatives", {}).items(), key=lambda item: len(tokenize(item[0])), reverse=True)
        for phrase, phrase_score in phrases:
            expected = tokenize(phrase)
            if not expected:
                continue
            for start in range(len(tokens) - len(expected) + 1):
                end = start + len(expected) - 1
                if (any(position in consumed for position in range(start, end + 1))
                        or clauses[start] != clauses[end]
                        or not _phrase_matches(tokens[start:end + 1], expected)):
                    continue
                weight, rules = _modifiers(tokens, start, end, clauses, negations, intensifiers)
                rules.insert(0, f"double_negative:{phrase}")
                weighted = float(phrase_score) * weight
                score += weighted
                consumed.update(range(start, end + 1))
                detected.append({"token": " ".join(tokens[start:end + 1]), "base_score": float(phrase_score),
                                 "weight": weight, "weighted_score": weighted, "rules": rules})
                rule_logs.append(f"double_negative:{phrase} => {weighted:+g}")

    for position, token in enumerate(tokens):
        if position in consumed or token not in index:
            continue
        _, base = index[token]
        weight, rules = _modifiers(tokens, position, position, clauses, negations, intensifiers) if use_rules else (1.0, [])
        weighted = base * weight
        score += weighted
        detected.append({"token": token, "base_score": base, "weight": weight, "weighted_score": weighted, "rules": rules})

    return {"text": text, "tokens": tokens, "detected_sentiments": detected, "rule_logs": rule_logs,
            "final_score": round(score, 3), "label": _label_from_score(score)}


def format_analysis(result: dict) -> str:
    lines = [f"입력 문장: {result['text']}", f"토큰화: {result['tokens']}", "탐지된 감성 단어:"]
    if result["detected_sentiments"]:
        for item in result["detected_sentiments"]:
            lines.append(f"- {item['token']} | base={item['base_score']} weight={item['weight']} weighted={item['weighted_score']} rules={item['rules']}")
    else:
        lines.append("- 없음")
    lines.append("규칙 적용 로그:")
    lines.extend(f"- {log}" for log in result["rule_logs"])
    if not result["rule_logs"]:
        lines.append("- 없음")
    lines.extend([f"최종 점수: {result['final_score']}", f"판정: {result['label']}"])
    return "\n".join(lines)
