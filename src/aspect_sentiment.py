"""Explicit, preceding aspect nouns and their local sentiment clauses."""

from src.sentiment import (
    CLAUSE_BOUNDARY_PATTERN, CONJUNCTIONS, PARTICLES, TOKEN_PATTERN,
    analyze_sentiment, load_lexicon,
)


ASPECT_TERMS: dict[str, tuple[str, ...]] = {
    "음식": ("음식", "맛", "요리", "메뉴"),
    "가격": ("가격", "비용", "요금", "가성비"),
    "서비스": ("서비스", "응대", "상담", "직원"),
    "배송": ("배송", "배달", "택배"),
    "품질": ("품질", "성능", "내구성"),
}
COORDINATING_PARTICLES = {"과", "와", "랑", "이랑", "하고"}
COORDINATING_WORDS = {"및", "그리고"}
ASPECT_SUFFIXES = {"", *PARTICLES, "에게", "에는", "에도", *COORDINATING_PARTICLES}


def _mention(token: str) -> tuple[str, str] | None:
    for aspect, terms in ASPECT_TERMS.items():
        for term in terms:
            if token.startswith(term) and token[len(term):] in ASPECT_SUFFIXES:
                return aspect, token[len(term):]
    return None


def _label(score: float) -> str:
    return "positive" if score > 0.5 else "negative" if score < -0.5 else "neutral"


def analyze_aspects(text: str, lexicon: dict | None = None, use_rules: bool = True) -> dict:
    """Return five supported aspects, grouping explicit coordinated subjects only.

    Spans are half-open character offsets in the original text. An omitted or
    unknown aspect is not inferred, and evidence never crosses clause boundaries.
    Repeated mentions of an aspect are summed using the sentence score thresholds.
    """
    lexicon = load_lexicon() if lexicon is None else lexicon
    matches = list(TOKEN_PATTERN.finditer(text))
    clauses: list[list[int]] = []
    for position, match in enumerate(matches):
        boundary = position == 0
        if position:
            previous = matches[position - 1]
            boundary = bool(
                CLAUSE_BOUNDARY_PATTERN.search(text[previous.end():match.start()])
                or previous.group().endswith(("지만", "는데"))
                or match.group() in CONJUNCTIONS
            )
        if boundary:
            clauses.append([])
        clauses[-1].append(position)

    aspects: dict[str, dict] = {}
    for clause in clauses:
        groups: list[list[tuple[int, str, str]]] = []
        for position in clause:
            mention = _mention(matches[position].group())
            if mention is None:
                continue
            aspect, suffix = mention
            if groups:
                previous_position, _, previous_suffix = groups[-1][-1]
                gap = [item.group() for item in matches[previous_position + 1:position]]
                coordinated = (
                    (previous_suffix in COORDINATING_PARTICLES and not gap)
                    or (bool(gap) and all(word in COORDINATING_WORDS for word in gap)
                        and previous_suffix in {"", *COORDINATING_PARTICLES})
                )
            else:
                coordinated = False
            if not coordinated:
                groups.append([])
            groups[-1].append((position, aspect, suffix))

        for group_index, group in enumerate(groups):
            start = matches[group[0][0]].start()
            end = (matches[groups[group_index + 1][0][0]].start()
                   if group_index + 1 < len(groups) else matches[clause[-1]].end())
            segment_text = text[start:end].rstrip()
            span = [start, start + len(segment_text)]
            analysis = analyze_sentiment(segment_text, lexicon, use_rules)
            segment = {
                "text": segment_text, "span": span,
                "detected_sentiments": analysis["detected_sentiments"],
                "rule_logs": analysis["rule_logs"],
                "final_score": analysis["final_score"], "label": analysis["label"],
            }
            group_aspects: set[str] = set()
            for position, aspect, _ in group:
                item = aspects.setdefault(aspect, {
                    "aspect": aspect, "mentions": [], "segments": [],
                    "detected_sentiments": [], "final_score": 0.0, "label": "neutral",
                })
                match = matches[position]
                item["mentions"].append({"text": match.group(), "span": [match.start(), match.end()]})
                if aspect in group_aspects:
                    continue
                group_aspects.add(aspect)
                item["segments"].append(segment)
                item["detected_sentiments"].extend(
                    {**evidence, "segment_span": span} for evidence in analysis["detected_sentiments"]
                )
                item["final_score"] = round(item["final_score"] + analysis["final_score"], 3)
                item["label"] = _label(item["final_score"])
    return {"text": text, "aspects": list(aspects.values())}


def format_aspect_analysis(result: dict) -> str:
    lines = ["[Aspect 감성 분석 결과]"]
    for aspect in result["aspects"]:
        lines.append(f"측면: {aspect['aspect']} | 점수: {aspect['final_score']:+g} | 판정: {aspect['label']}")
        for evidence in aspect["detected_sentiments"]:
            lines.append(
                f"- {evidence['token']} | base={evidence['base_score']} weight={evidence['weight']} "
                f"weighted={evidence['weighted_score']} rules={evidence['rules']}"
            )
        if not aspect["detected_sentiments"]:
            lines.append("- 감성 근거 없음")
    if not result["aspects"]:
        lines.append("- 지원하는 명시적 측면 없음")
    return "\n".join(lines)
