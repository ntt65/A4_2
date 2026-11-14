# Rule-based NLP Pipeline (Python 3.10+)

규칙 기반 자연어 처리 파이프라인으로 **정보 추출(IE)** 과 **감성 분석**을 통합 실행합니다.

## 프로젝트 구조

```text
src/
  extractor.py      # 정규표현식 기반 정보 추출/정규화
  sentiment.py      # 감성 사전 기반 점수 계산 + 규칙 처리
  evaluator.py      # IE/감성 평가 (정밀도/재현율/정확도/F1)
  masking.py        # (보너스) 개인정보 마스킹

data/
  sentiment_lexicon.json      # 일반 감성 200+, 도메인 30+, 부정어/강조어
  ie_test_cases.json          # 패턴별 10문장 이상, 총 50개
  sentiment_test_cases.json   # 라벨 포함 100개+

main.py
requirements.txt
README.md
```

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 실행

### 1) 단일 문장 분석
```bash
python main.py --text "문의는 USER@EXAMPLE.COM, 연락처는 010 1234 5678, 서비스는 정말 좋다"
```

### 2) 개인정보 마스킹 후 분석
```bash
python main.py --text "주민번호 900101-1234567, 카드 1234-5678-9012-3456" --mask
```

### 3) 평가 실행
```bash
python main.py --evaluate-ie
python main.py --evaluate-sentiment
python main.py --evaluate-all
```

## 데이터 구성

- `data/sentiment_lexicon.json`
  - 일반 감성 단어: 200개 (긍정/부정 균형)
  - 도메인 특화 단어: 36개 (고객 문의/리뷰 문맥)
  - 부정어/강조어/이중부정 패턴 별도 관리
  - 메타데이터에 출처/구축 기준 포함
- `data/ie_test_cases.json`
  - 이메일/전화번호/날짜/금액/URL 각 10문장, 총 50문장
- `data/sentiment_test_cases.json`
  - positive/negative/neutral 라벨 포함 116문장

## 규칙 설계

### 정보 추출 (`src/extractor.py`)
- 이메일: 소문자 정규화
- 전화번호: 다양한 구분자를 `-` 형식으로 통일
- 날짜: `YYYY-MM-DD`(ISO 8601)로 변환
- 금액: 숫자형 정수 값으로 정규화 (`1억 2천만원`, `$100` 포함)
- URL: scheme/host 소문자 정규화

### 감성 분석 (`src/sentiment.py`)
- 기본: 토큰화 후 감성 사전 점수 합산
- 부정어: 극성 반전 (`× -1`)
- 강조어: 강도 가중 (`× 1.5`)
- 이중부정 단일 패턴: `나쁘지 않다`, `싫지 않다`, `불편하지 않다` 긍정 보정
- 출력: 토큰, 감성 단어, 규칙 로그, 최종 점수/판정 상세 제공

## 평가 결과 리포트 템플릿

```text
[정보 추출 평가]
pattern     | precision | recall
------------|-----------|-------
emails      | 0.000     | 0.000
phones      | 0.000     | 0.000
dates       | 0.000     | 0.000
amounts     | 0.000     | 0.000
urls        | 0.000     | 0.000

[감성 분석 평가]
phase  | accuracy | f1
-------|----------|---
before | 0.000    | 0.000
after  | 0.000    | 0.000
```

## 실패 사례 분석

### 정보 추출 실패 사례 (5건 이상)
1. (예시) ...
2. (예시) ...
3. (예시) ...
4. (예시) ...
5. (예시) ...

### 감성 분석 오분류 사례 (10건 이상)
1. (예시) ...
2. (예시) ...
3. (예시) ...
4. (예시) ...
5. (예시) ...
6. (예시) ...
7. (예시) ...
8. (예시) ...
9. (예시) ...
10. (예시) ...

## 한계점 분석

1. 형태소 분석기 없이 규칙/표면형 기반이라 문맥 해석 한계가 있음
2. 금액/날짜의 예외 표현(속어, 축약, 복합 단위) 대응이 제한적임
3. 감성 사전 미등재 신조어/복합 표현에 취약함
4. 부정어 범위(scope)와 문장 구조(절 단위) 처리 정밀도 개선 필요
