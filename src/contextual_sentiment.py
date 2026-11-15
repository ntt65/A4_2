"""명시적 단서에 한정한 선택 문맥 분석. 기존 문장/Aspect 계약은 유지한다."""

import re

from src.sentiment import _label_from_score, analyze_sentiment, load_lexicon

# 같은 종류로 닫힌 따옴표 내부만 찾는다. 줄바꿈·중첩·간접 인용은 추론하지 않는다.
QUOTE_PATTERN = re.compile(r"'[^'\n]*'|\"[^\"\n]*\"|‘[^’\n]*’|“[^”\n]*”")
# 문장 경계까지만 검사한다. 단어/예문 등 명시적 언급 단서가 있는 인용만 제외한다.
LITERAL_CUE_PATTERN = re.compile(r"예문|번역|검색(?:창|어)|대상\s*단어|교육\s*자료")
# 단순 '표현'은 자기 감정일 수도 있다. 인용 뒤의 횟수/계수 문맥만 추가로 인정한다.
QUOTE_COUNT_PATTERN = re.compile(r"표현[^.!?;\n]{0,30}(?:몇\s*번|세었|센다|횟수)")
# 조건부 의사는 확정 결과로 치환하지 않는다. 최종 술어까지의 같은 문장 안에서만 검사한다.
CONDITIONAL_PATTERN = re.compile(r"다면|라면|으면|경우|때만")
# 문장부호·줄바꿈에서 범위를 끝내어 사건/최종 의사가 다음 문장에 전파되지 않게 한다.
SENTENCE_PATTERN = re.compile(r"[^.!?;\n]+(?:[.!?;]+|$)")
# 명시적 불만 사건의 제한된 표면형만 찾는다. 일반 '기다림'은 환불 지연에 한정한다.
ADVERSE_PATTERN = re.compile(
    r"늦었|지연됐|지연되|고장(?:이라니|이?\s*났|나)|파손됐|찢어지|"
    r"전화를\s*끊|멋대로\s*취소|(?:다른|엉뚱한)\s*(?:물건|상품)|"
    r"비밀번호가\s*사라|추가\s*요금|광고만|환불을?[^.!?;\n]{0,15}기다"
)
# 앞 사건과 뒤 칭찬 사이의 연결 어미를 요구한다. '지만'만으로 반어를 추정하지 않는다.
IRONY_LINK_PATTERN = re.compile(r"는데|다니|으니|니|해서")
# 칭찬의 명시적 강조 또는 감탄형만 반어 후보로 삼는다. 순수 긍정 점수도 별도로 요구한다.
PRAISE_MARKER_PATTERN = re.compile(r"(?<![가-힣A-Za-z0-9])(?:참|정말|아주)(?![가-힣A-Za-z0-9])|네요")
# 사건 이후 회복/부정 단서가 있으면 보수적으로 반어 처리를 생략한다. 문장 밖은 보지 않는다.
RECOVERY_PATTERN = re.compile(r"수리|해결|교환|복구|정상|지금|이제|덕분|없|아니|않")
# 문장 끝의 직접적인 의사/결과만 인정한다. \Z는 뒤에 부정·인용·조건이 붙은 표현을 배제한다.
# 조사/어미 전체 해석 대신 아래 표면형만 지원하며 접두 lookbehind는 단어 내부 오탐을 막는다.
OUTCOME_PATTERNS = (
    ("final_refusal", -1.0, re.compile(
        r"(?<![가-힣A-Za-z0-9])(?:다시\s*)?(?:주문|구매|이용)하지\s*않(?:겠다|겠어요|겠습니다)\s*[.!?;]*\s*\Z")),
    # 직접 환불 거절/거래 중단의 종결형만 매칭한다. 단어 경계와 \Z로 인용·후속 부정을 배제한다.
    ("final_rejection", -1.0, re.compile(
        r"(?<![가-힣A-Za-z0-9])(?:환불을\s*거절당(?:했다|했어요)|거래를\s*끊(?:었다|었어요))\s*[.!?;]*\s*\Z")),
    # 현재/수리 후 단서부터 같은 문장 30자 안의 회복 종결형까지다. \Z 뒤에 다른 술어를 허용하지 않는다.
    ("current_recovery", 1.0, re.compile(
        r"(?<![가-힣A-Za-z0-9])(?:지금은|이제는?|수리\s*후)[^.!?;\n]{0,30}(?:잘\s*쓴다|잘\s*쓰고\s*있다|만족한다)\s*[.!?;]*\s*\Z")),
    # 미래 재이용 단서부터 20자 안의 확정 의사 종결형까지다. 접두 경계/\Z로 부분 단어·간접 인용을 막는다.
    ("reuse_intent", 1.0, re.compile(
        r"(?<![가-힣A-Za-z0-9])(?:앞으로도|다음에도)[^.!?;\n]{0,20}(?:이용|주문|구매)하(?:겠다|겠어요|겠습니다)\s*[.!?;]*\s*\Z")),
    # 도움 없이 완료한 명시적 종결형만 매칭한다. 접두 경계/\Z로 단어 내부·완료 예측을 배제한다.
    ("completed_without_help", 1.0, re.compile(
        r"(?<![가-힣A-Za-z0-9])(?:누구\s*)?도움(?:도)?\s*없이\s*(?:끝냈다|완료했다)\s*[.!?;]*\s*\Z")),
)


def _evidence(token: str, score: float, rule: str, span: list[int]) -> dict:
    return {"token": token, "base_score": score, "weight": 1.0, "weighted_score": score,
            "rules": [rule], "span": span}


def analyze_contextual_sentiment(text: str, lexicon: dict | None = None) -> dict:
    """문장별로 인용 제외 → 최종 의사 → 제한적 반어 순서로 적용한다."""
    lexicon = load_lexicon() if lexicon is None else lexicon
    baseline = analyze_sentiment(text, lexicon=lexicon)
    masked = list(text)
    quotes = []
    # 인용 내부 문장부호를 먼저 가려 인용문이 문장 분할 경계를 만들지 않게 한다.
    quoted_spans = list(QUOTE_PATTERN.finditer(text))
    boundary_text = list(text)
    for quote in quoted_spans:
        boundary_text[quote.start():quote.end()] = " " * len(quote.group())
    for sentence in SENTENCE_PATTERN.finditer("".join(boundary_text)):
        start, end = sentence.span()
        local_quotes = [quote for quote in quoted_spans if start <= quote.start() and quote.end() <= end]
        for index, quote in enumerate(local_quotes):
            previous = local_quotes[index - 1].end() if index else start
            following = local_quotes[index + 1].start() if index + 1 < len(local_quotes) else end
            prefix = text[previous:quote.start()]
            suffix = text[quote.end():following]
            if LITERAL_CUE_PATTERN.search(prefix) or QUOTE_COUNT_PATTERN.search(suffix):
                masked[quote.start():quote.end()] = " " * len(quote.group())
                quotes.append({"text": quote.group(), "span": list(quote.span()), "rule": "literal_quote"})

    filtered = "".join(masked)
    segments = []
    detected = []
    logs = ["literal_quote" for _ in quotes]
    # 구간은 인용문 부호가 아닌 원문 문장 경계를 사용한다.
    for sentence in SENTENCE_PATTERN.finditer("".join(boundary_text)):
        start, end = sentence.span()
        content = filtered[start:end]
        analysis = analyze_sentiment(content, lexicon=lexicon)
        evidence = analysis["detected_sentiments"]
        rule = None
        trigger = None
        for name, score, pattern in OUTCOME_PATTERNS:
            outcome = pattern.search(content)
            if outcome and not CONDITIONAL_PATTERN.search(content[:outcome.end()]):
                rule = name
                trigger = {"text": text[start + outcome.start():start + outcome.end()],
                           "span": [start + outcome.start(), start + outcome.end()]}
                evidence = [_evidence(outcome.group().strip(), score, name,
                                      [start + outcome.start(), start + outcome.end()])]
                break
        if rule is None:
            for event in ADVERSE_PATTERN.finditer(content):
                tail = content[event.end():]
                praise = analyze_sentiment(tail, lexicon=lexicon)
                if (IRONY_LINK_PATTERN.search(content[event.start():]) and PRAISE_MARKER_PATTERN.search(tail)
                        and not RECOVERY_PATTERN.search(tail)
                        and praise["final_score"] > 0.5):
                    rule = "adverse_event_irony"
                    trigger = {"text": event.group(), "span": [start + event.start(), start + event.end()]}
                    evidence = [dict(item, weight=-item["weight"], weighted_score=-item["weighted_score"],
                                     rules=item["rules"] + [rule]) for item in praise["detected_sentiments"]]
                    break
        score = round(sum(item["weighted_score"] for item in evidence), 3)
        segments.append({"text": text[start:end], "span": [start, end], "rule": rule, "trigger": trigger,
                         "final_score": score, "label": _label_from_score(score),
                         "detected_sentiments": evidence})
        detected.extend(evidence)
        if rule:
            logs.append(rule)
    score = round(sum(item["weighted_score"] for item in detected), 3)
    return {"text": text, "baseline": baseline, "excluded_quotes": quotes, "segments": segments,
            "detected_sentiments": detected, "rule_logs": logs, "final_score": score,
            "label": _label_from_score(score)}


def format_contextual_analysis(result: dict) -> str:
    lines = ["[문맥 감성 분석 결과]", f"기존 판정: {result['baseline']['label']}"]
    lines.extend(f"제외한 인용: {quote['text']} | span={quote['span']}" for quote in result["excluded_quotes"])
    for segment in result["segments"]:
        lines.append(f"구간: {segment['text']} | span={segment['span']} | rule={segment['rule']}")
        for item in segment["detected_sentiments"]:
            lines.append(f"- {item['token']} | base={item['base_score']} weight={item['weight']} "
                         f"weighted={item['weighted_score']} rules={item['rules']}")
    lines.extend([f"최종 점수: {result['final_score']}", f"판정: {result['label']}"])
    return "\n".join(lines)
