import json
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
LEXICON_PATH = BASE_DIR / "data" / "sentiment_lexicon.json"


def load_lexicon(path: Path = LEXICON_PATH) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def tokenize(text: str) -> list[str]:
    return re.findall(r"[가-힣A-Za-z0-9]+", text.lower())


def _label_from_score(score: float) -> str:
    if score > 0.5:
        return "positive"
    if score < -0.5:
        return "negative"
    return "neutral"


def analyze_sentiment(text: str, lexicon: dict | None = None, use_rules: bool = True) -> dict:
    lexicon = lexicon or load_lexicon()
    sentiment_dict = {}
    sentiment_dict.update(lexicon.get("general_sentiment", {}))
    sentiment_dict.update(lexicon.get("domain_sentiment", {}))

    negations = set(lexicon.get("negations", []))
    intensifiers = set(lexicon.get("intensifiers", []))
    double_negatives = lexicon.get("double_negatives", {})

    tokens = tokenize(text)
    score = 0.0
    detected = []
    rule_logs = []
    consumed_positions: set[int] = set()

    if use_rules:
        joined = " ".join(tokens)
        for phrase, phrase_score in double_negatives.items():
            phrase_tokens = phrase.split()
            for i in range(0, len(tokens) - len(phrase_tokens) + 1):
                if tokens[i : i + len(phrase_tokens)] == phrase_tokens:
                    score += phrase_score
                    consumed_positions.update(range(i, i + len(phrase_tokens)))
                    rule_logs.append(f"double_negative:{phrase} => +{phrase_score}")

    for i, token in enumerate(tokens):
        if i in consumed_positions:
            continue
        if token not in sentiment_dict:
            continue

        base = float(sentiment_dict[token])
        weight = 1.0
        applied_rules = []

        prev_token = tokens[i - 1] if i - 1 >= 0 else ""
        next_token = tokens[i + 1] if i + 1 < len(tokens) else ""

        if use_rules and prev_token in intensifiers:
            weight *= 1.5
            applied_rules.append(f"intensifier:{prev_token}")

        if use_rules and (prev_token in negations or next_token in negations):
            weight *= -1
            if prev_token in negations:
                applied_rules.append(f"negation:{prev_token}")
            if next_token in negations:
                applied_rules.append(f"negation:{next_token}")

        weighted = base * weight
        score += weighted
        detected.append(
            {
                "token": token,
                "base_score": base,
                "weight": weight,
                "weighted_score": weighted,
                "rules": applied_rules,
            }
        )

    label = _label_from_score(score)
    return {
        "text": text,
        "tokens": tokens,
        "detected_sentiments": detected,
        "rule_logs": rule_logs,
        "final_score": round(score, 3),
        "label": label,
    }


def format_analysis(result: dict) -> str:
    lines = [
        f"입력 문장: {result['text']}",
        f"토큰화: {result['tokens']}",
        "탐지된 감성 단어:",
    ]
    if result["detected_sentiments"]:
        for item in result["detected_sentiments"]:
            lines.append(
                f"- {item['token']} | base={item['base_score']} weight={item['weight']} weighted={item['weighted_score']} rules={item['rules']}"
            )
    else:
        lines.append("- 없음")

    lines.append("규칙 적용 로그:")
    if result["rule_logs"]:
        for log in result["rule_logs"]:
            lines.append(f"- {log}")
    else:
        lines.append("- 없음")

    lines.append(f"최종 점수: {result['final_score']}")
    lines.append(f"판정: {result['label']}")
    return "\n".join(lines)
