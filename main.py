import argparse
import json
from pathlib import Path

from src.aspect_sentiment import analyze_aspects, format_aspect_analysis
from src.evaluator import evaluate_aspect_sentiment, evaluate_information_extraction, evaluate_sentiment, run_all_evaluations
from src.extractor import extract_information
from src.masking import mask_personal_info
from src.sentiment import analyze_sentiment, format_analysis


def main() -> None:
    parser = argparse.ArgumentParser(description="규칙 기반 정보 추출 및 감성 분석 파이프라인")
    parser.add_argument("--text", type=str, help="단일 문장 분석")
    parser.add_argument("--aspect", action="store_true", help="명시적 측면별 감성 분석 추가 (--text 필요)")
    parser.add_argument("--mask", action="store_true", help="전화·주민번호·카드·주소 마스킹")
    parser.add_argument("--evaluate-ie", action="store_true", help="정보 추출 평가 실행")
    parser.add_argument("--evaluate-sentiment", action="store_true", help="감성 분석 평가 실행")
    parser.add_argument("--evaluate-aspect", action="store_true", help="별도 Aspect 라벨 자료 평가")
    parser.add_argument("--evaluate-all", action="store_true", help="전체 평가 실행")
    parser.add_argument("--compare-sentiment", action="store_true", help="고정 평가셋에서 규칙·TF-IDF와 학습 규모 비교")
    parser.add_argument("--experiment-output", type=Path, help="TF-IDF 실험 원자료 JSON 저장 경로")
    args = parser.parse_args()
    if args.experiment_output and not args.compare_sentiment:
        parser.error("--experiment-output requires --compare-sentiment")
    if args.aspect and not args.text:
        parser.error("--aspect requires --text")

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
        if args.aspect:
            print()
            print(format_aspect_analysis(analyze_aspects(text)))

    if args.evaluate_ie:
        _, report = evaluate_information_extraction()
        print(report)

    if args.evaluate_sentiment:
        _, report = evaluate_sentiment()
        print(report)

    if args.evaluate_all:
        print(run_all_evaluations())

    if args.evaluate_aspect:
        _, report = evaluate_aspect_sentiment()
        print(report)

    if args.compare_sentiment:
        from src.sentiment_experiment import RESULT_PATH, format_experiment, run_experiment, save_experiment

        try:
            result = run_experiment()
            output_path = args.experiment_output or RESULT_PATH
            save_experiment(result, output_path)
        except (ValueError, OSError) as error:
            parser.error(str(error))
        print(format_experiment(result))
        print(f"원자료 JSON: {output_path}")

    if not any([args.text, args.evaluate_ie, args.evaluate_sentiment, args.evaluate_all, args.evaluate_aspect, args.compare_sentiment]):
        parser.print_help()


if __name__ == "__main__":
    main()
