import argparse
import json

from src.evaluator import evaluate_information_extraction, evaluate_sentiment, run_all_evaluations
from src.extractor import extract_information
from src.masking import mask_personal_info
from src.sentiment import analyze_sentiment, format_analysis


def main() -> None:
    parser = argparse.ArgumentParser(description="규칙 기반 정보 추출 및 감성 분석 파이프라인")
    parser.add_argument("--text", type=str, help="단일 문장 분석")
    parser.add_argument("--mask", action="store_true", help="전화·주민번호·카드·주소 마스킹")
    parser.add_argument("--evaluate-ie", action="store_true", help="정보 추출 평가 실행")
    parser.add_argument("--evaluate-sentiment", action="store_true", help="감성 분석 평가 실행")
    parser.add_argument("--evaluate-all", action="store_true", help="전체 평가 실행")
    args = parser.parse_args()

    if args.text:
        extracted = extract_information(args.text, include_addresses=True)
        text = mask_personal_info(args.text) if args.mask else args.text
        if args.mask:
            extracted = {
                key: [mask_personal_info(value) if isinstance(value, str) else value for value in values]
                for key, values in extracted.items()
            }
        sentiment_result = analyze_sentiment(text, use_rules=True)

        print("[정보 추출 결과]")
        print(json.dumps(extracted, ensure_ascii=False, indent=2))
        print()
        print("[감성 분석 결과]")
        print(format_analysis(sentiment_result))

    if args.evaluate_ie:
        _, report = evaluate_information_extraction()
        print(report)

    if args.evaluate_sentiment:
        _, report = evaluate_sentiment()
        print(report)

    if args.evaluate_all:
        print(run_all_evaluations())

    if not any([args.text, args.evaluate_ie, args.evaluate_sentiment, args.evaluate_all]):
        parser.print_help()


if __name__ == "__main__":
    main()
