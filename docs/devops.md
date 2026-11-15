# 실행 환경과 자동 검증

## 환경 계약

- 프로젝트 실행·검증은 Python 3.11이며 `.python-version`에 `3.11`을 기록한다. 환경·의존성 관리는 uv를 사용한다. 미션의 최소 조건은 Python 3.10 이상이다.
- 평가 환경은 iMac의 macOS이며, CI도 macOS·Python 3.11 단일 환경을 검증한다.
- 미션 원본은 `docs/A4_2_mission.pdf`다. 제출용 환경 파일은 `requirements.txt`다.
- 현재 런타임과 테스트 의존성은 Python 표준 라이브러리다. 테스트 러너는 `unittest`다.
- 로컬 확인 환경은 Windows, Python 3.11.4, uv 0.13.7이다. CI도 uv 0.13.7로 고정한다.
- 가상환경은 저장소의 `.venv`를 명시한다. Python 자동 다운로드는 끈다.

uv의 [가상환경 문서](https://docs.astral.sh/uv/pip/environments/)와 [GitHub Actions 문서](https://docs.astral.sh/uv/guides/integration/github/)를 기준으로 구성한다.

## 로컬 명령

Python 3.11이 설치된 환경에서 저장소 루트의 `.python-version`을 읽어 가상환경을 만든다. 아래 명령은 macOS 터미널과 로컬 개발 셸에서 가상환경 활성화 없이 사용한다.

```shell
uv venv --no-python-downloads .venv
uv pip sync --python .venv --allow-empty-requirements requirements.txt
uv run --python .venv python -B -X utf8 -m unittest discover -s tests -v
uv run --python .venv python -B -X utf8 main.py --evaluate-all
```

`.python-version`은 uv의 환경 생성과 CI의 Python 준비 단계에서 같은 버전을 선택하게 한다. `--allow-empty-requirements`는 현재 빈 의존성 목록에 맞춰 프로젝트 가상환경을 동기화한다. `--python .venv`는 사용할 환경을 고정한다. `-B`는 바이트코드 생성을 막고 `-X utf8`은 CLI 인코딩을 맞춘다.

제한된 실행 환경에서는 각 uv 명령에 `--no-cache`를 추가해 기본 사용자 캐시 대신 임시 캐시를 사용한다. 예: `uv --no-cache run --python .venv python -B -X utf8 main.py --help`.

## 검증 범위

`tests/test_pipeline_smoke.py`의 8개 테스트가 다음 계약을 확인한다.

| 범위 | 검증 내용 |
|---|---|
| CLI | 도움말 옵션, 저장소 밖 작업 디렉터리에서 데이터 경로 해결, 이메일 JSON과 감성 출력 |
| 마스킹 | 휴대전화 원문이 출력에서 가려지고 마스킹 문자열이 표시됨 |
| 평가 CLI | IE와 감성 전후 평가 보고서 출력 |
| IE 지표 | 정답·오탐·미탐 fixture의 Precision = 1 / 3, Recall = 1 / 2 |
| 감성 지표 | 3문장 fixture의 규칙 전 Accuracy = 2 / 3, Macro F1 = 5 / 9, 규칙 후 둘 다 1 |
| 빈 데이터 | 모든 평가 지표 0, 분모 0 예외 방어 |
| 감성 근거 | 부정어·강조어 가중치와 근거, 이중부정의 판정·로그 |

감성 fixture는 `좋다`(긍정), `안 좋다`(부정), `일정 확인`(중립)이다. 테스트용 JSON은 임시 디렉터리에 작성한다. 원자료는 `data/`에 보존한다. 성능 평가 CLI의 정상 종료와 별도로 unittest assertion이 검증 실패를 비정상 종료로 전달한다.

## CI

`.github/workflows/ci.yml`은 `main`/`develop` 대상 PR, 두 브랜치의 push, 수동 실행을 지원한다.

- OS: `macos-latest`. GitHub가 제공하는 macOS runner에서 실행한다.
- Python: `.python-version`의 3.11. CI 실행당 job은 1개다.
- PR과 머지 후 `develop` push에서 각각 단일 job이 실행된다.
- 단계: 체크아웃 → Python/uv 준비 → `.venv` 생성 → requirements 동기화 → unittest.
- `contents: read` 권한, 체크아웃 자격 증명 저장 해제, 액션 커밋 SHA 고정.
- uv 캐시와 Python 자동 다운로드를 끄고, 각 job 제한 시간은 10분이다.
- 동일 PR/브랜치의 새 실행이 이전 실행을 대체한다.

runner의 현재 OS·CPU 사양은 [GitHub 공식 문서](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)에서 확인한다. `macos-latest`는 현재 Apple Silicon(arm64) runner다.

원격 Actions 실행 결과는 push/PR 이후 확인한다. CI 검사 이름이 확정되면 `main`/`develop` 보호와 필수 상태 검사를 별도 승인 범위에서 설정한다.

## 브랜치와 커밋

합의한 흐름은 `main` → `develop` → 이슈별 feature → `develop` 통합 → 최종 `main` 반영이다. [#2](https://github.com/ntt65/A4_2/issues/2)의 브랜치는 `feature/2-devops-baseline`이며, 사용자 미션 PDF 커밋 `2f34b49`를 기준으로 한다.

평가 환경에 맞춘 CI 축소는 [#7](https://github.com/ntt65/A4_2/issues/7)의 `feature/7-macos-python311-ci`에서 진행하며, 기준은 `develop`의 `30f5591`이다.

승인된 작업 단위마다 검증하고 관련 문서를 동기화한다. 담당 파일을 명시해 스테이징한 후 `git diff --cached`와 `git diff --cached --check`를 확인한다. 이슈 번호를 연결한 Conventional Commit으로 로컬 커밋하고 SHA·포함 파일·검증 결과·남은 작업을 보고한다.

## 기능 기준선과 후속 작업

기능 기준 `2f34b49`, 2026-11-15 평가에서 이메일·전화·날짜 Precision/Recall은 각각 1.000/1.000, 금액은 0.184/0.700, URL은 0.900/0.900이다. 감성 Accuracy/Macro F1은 규칙 전 0.966/0.963, 후 1.000/1.000이다.

| 이슈 | 남은 작업 |
|---|---|
| [#3](https://github.com/ntt65/A4_2/issues/3) | 금액·URL 경계, 서울 전화 마스킹, 추출 후 마스킹 순서의 회귀 검증과 수정 |
| [#4](https://github.com/ntt65/A4_2/issues/4) | 일반 사전 임시 항목 12개, 감성 116행/고유 31문장의 다양성, 사전 출처·라이선스 검토 |
| [#5](https://github.com/ntt65/A4_2/issues/5) | IE 실패 5건 이상·감성 오분류 10건 이상의 실제 원인 분석과 최종 리포트 |

미션에 지표 최저 합격 임계값은 명시되어 있지 않다. 후속 기능 변경마다 해당 회귀 테스트와 전체 평가를 실행하고 README 및 관련 문서의 수치를 갱신한다.
