# Rule-based NLP Pipeline (Python 3.11)

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
.python-version
requirements.txt
tests/test_pipeline_smoke.py
.github/workflows/ci.yml
docs/A4_2_mission.pdf
docs/devops.md
README.md
```

## 설치 (uv)

Python 3.11과 [uv](https://docs.astral.sh/uv/)가 필요합니다. 프로젝트의 `.python-version`에 `3.11`을 지정하고 uv와 CI가 같은 파일을 읽습니다. 평가 기준은 iMac의 macOS·Python 3.11입니다. 저장소 루트에서 다음 명령을 실행하며 가상환경 활성화는 필요하지 않습니다.

```shell
uv venv --no-python-downloads .venv
uv pip sync --python .venv --allow-empty-requirements requirements.txt
```

`requirements.txt`는 미션 제출물이며 현재 실행 코드와 테스트는 Python 표준 라이브러리만 사용합니다. `--allow-empty-requirements`는 이 빈 의존성 목록에 맞춰 프로젝트 `.venv`를 동기화합니다. Python 3.11이 설치되어 있어야 합니다. 미션의 최소 조건인 Python 3.10 이상에 맞춰, 프로젝트 실행·검증 버전은 3.11로 통일합니다.

## 실행

### 1) 단일 문장 분석
```bash
uv run --python .venv python -B -X utf8 main.py --text "문의는 USER@EXAMPLE.COM, 연락처는 010 1234 5678, 서비스는 정말 좋다"
```

### 2) 정보 추출 후 출력 마스킹
```bash
uv run --python .venv python -B -X utf8 main.py --text "주민번호 900101-1234567, 카드 1234-5678-9012-3456" --mask
```

### 3) 평가 실행
```bash
uv run --python .venv python -B -X utf8 main.py --evaluate-ie
uv run --python .venv python -B -X utf8 main.py --evaluate-sentiment
uv run --python .venv python -B -X utf8 main.py --evaluate-all
```

## 자동 검증

```shell
uv run --python .venv python -B -X utf8 -m unittest discover -s tests -v
```

8개 테스트가 CLI, 개인정보 마스킹, 감성 규칙의 근거, 평가 지표와 빈 데이터 처리를 검증합니다. CI는 `main`/`develop` 대상 PR과 해당 브랜치의 push에서 macOS·Python 3.11 단일 job을 실행합니다. 환경 구성과 검증 범위는 [DevOps 문서](docs/devops.md)에 기록합니다.

## 데이터 구성

- `data/sentiment_lexicon.json`
  - 일반 감성 항목: 200개 (임시 확장 항목 12개 포함, [#4](https://github.com/ntt65/A4_2/issues/4)에서 개선)
  - 도메인 특화 단어: 36개 (고객 문의/리뷰 문맥)
  - 부정어/강조어/이중부정 패턴 별도 관리
  - 메타데이터에 출처/구축 기준 포함
- `data/ie_test_cases.json`
  - 이메일/전화번호/날짜/금액/URL 각 10문장, 총 50문장
- `data/sentiment_test_cases.json`
  - positive/negative/neutral 라벨 포함 116행, 고유 문장 31개

## 규칙 설계

### 정보 추출 (`src/extractor.py`)
- 이메일: 소문자 정규화
- 전화번호: 다양한 구분자를 `-` 형식으로 통일
- 날짜: `YYYY-MM-DD`(ISO 8601)로 변환
- 금액: 명시적인 통화·금액 단위를 정수로 정규화 (`1억 2천만원`, `$100` 포함), 일반 숫자와 URL 내부 숫자 제외
- URL: scheme/host 소문자 정규화, 경로·쿼리·fragment 보존
- 마스킹: 원문에서 추출한 뒤 표시할 값과 분석 문장을 가림 (서울 9자리 전화 포함)

### 감성 분석 (`src/sentiment.py`)
- 기본: 토큰화 후 감성 사전 점수 합산
- 부정어: 극성 반전 (`× -1`)
- 강조어: 강도 가중 (`× 1.5`)
- 이중부정 단일 패턴: `나쁘지 않다`, `싫지 않다`, `불편하지 않다` 긍정 보정
- 출력: 토큰, 감성 단어, 규칙 로그, 최종 점수/판정 상세 제공

## 현재 평가 결과

정보 추출은 #3 변경 후 기존 정답 50문장으로 측정한 값입니다. 감성은 기준 커밋 `2f34b49`의 기존 116행 결과이며 #4 통합 후 갱신합니다. 환경은 Python 3.11.4, 2026-11-15입니다. 감성 F1은 긍정·부정·중립 3개 클래스의 Macro F1입니다.

```text
[정보 추출 평가]
pattern     | precision | recall
------------|-----------|-------
emails      | 1.000     | 1.000
phones      | 1.000     | 1.000
dates       | 1.000     | 1.000
amounts     | 1.000     | 1.000
urls        | 1.000     | 1.000

[감성 분석 평가]
phase  | accuracy | f1
-------|----------|---
before | 0.966    | 0.963
after  | 1.000    | 1.000
```

평가 CLI는 지표를 출력합니다. 지표와 동작의 회귀 검증은 위 unittest 명령으로 수행합니다. 현재 감성 데이터의 반복과 임시 사전 항목은 [#4](https://github.com/ntt65/A4_2/issues/4), 전체 실패 분석은 [#5](https://github.com/ntt65/A4_2/issues/5)에서 다룹니다.

## 실패 사례 분석

[정보 추출 분석](docs/extraction.md)에 수정 전 실제 실패 5건의 입력·기대값·실제값·원인과 수정 후 결과를 기록했습니다. 기존 50문장의 불일치는 22건에서 0건으로 줄었습니다.

감성 오분류 10건 이상의 분석과 최종 요구사항 점검은 [#4](https://github.com/ntt65/A4_2/issues/4)·[#5](https://github.com/ntt65/A4_2/issues/5)에서 통합합니다.

## 한계점 분석

1. 형태소 분석기 없이 규칙/표면형 기반이라 문맥 해석 한계가 있음
2. 금액/날짜의 예외 표현(속어, 축약, 복합 단위) 대응이 제한적임
3. 감성 사전 미등재 신조어/복합 표현에 취약함
4. 부정어 범위(scope)와 문장 구조(절 단위) 처리 정밀도 개선 필요
