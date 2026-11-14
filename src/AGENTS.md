# Source Code Local Agent Guidelines (`src/`)

## 1. 기술 스택 및 필수 제약사항
- **Python 버전**: Python 3.10 이상 표준 문법을 준수하며 모든 함수의 매개변수와 반환값에 타입 힌트(Type Hinting)를 명시한다.
- **내장 모듈 제한**: 모든 패턴 매칭과 텍스트 추출·마스킹 로직은 반드시 파이썬 표준 내장 `re` 모듈만 사용한다 (외부 정규식 패키지 사용 금지).

## 2. 정규표현식(Regex) 작성 표준 (`extractor.py`, `masking.py`)
- 모든 정규표현식 변수 또는 `re.compile()` 상단에는 반드시 다음 2가지를 주석으로 기술한다:
  1. 추출/마스킹 대상과 패턴 구조 설명
  2. 오탐(False Positive) 및 미탐(False Negative) 방지를 위해 고려한 경계 조건
- 날짜, 금액, 연락처, 이메일, URL 등 패턴별 경계 조건(`^`, `$`, `\b`, Lookahead/Lookbehind)을 명확히 분리하여 가독성을 유지한다.

## 3. 감성 분석 및 평가 모듈 규격 (`sentiment.py`, `evaluator.py`)
- 감성 점수 산출 시 긍·부정 단어 매칭 근거(매칭된 토큰 목록 및 가중치)를 함께 반환하여 오분류 원인 분석이 가능하도록 구현한다.
- 평가 지표(`Precision`, `Recall`, `Accuracy`, `F1-Score`) 산출 시 분모가 0이 되는 예외(`ZeroDivisionError`)를 방어 처리한다.

## 4. 모듈 수정 시 동기화 의무
- `src/` 내 함수 시그니처, 정규식 패턴, 감성 점수 계산 로직이 변경될 때마다 `tests/` 검증 스크립트를 실행하고, 변경된 규칙과 지표 수치를 `README.md` 및 `docs/` 문서에 즉시 반영한다.
