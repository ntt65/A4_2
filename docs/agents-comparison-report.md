# AGENTS.md 네 구성 비교 보고서

2026-11-15 KST. 같은 코드 조회 작업에서 사용자 제공 최초 지침 `ORGINAL`, 분산 지침 3개 A, 기존 통합 지침 1개 B, 최적화한 통합 지침 1개 C의 토큰 사용량과 경과 시간을 비교했다. A·B·C의 기존 완료 기록을 보존하고 `ORGINAL`로 동일 실험 1회를 추가했다. `ORGINAL`은 사용자가 지정한 표기를 그대로 썼다.

토큰 절감을 우선하는 운영안은 최적화한 단일 지침 C를 채택한다. 이번 관측에서 전체 토큰은 C가 가장 작고 경과 시간은 `ORGINAL`이 가장 짧았다. C는 `ORGINAL`보다 전체 토큰을 12.08% 적게 썼으며 시간은 20.79% 더 걸렸다. C는 기존 통합 B보다 전체 토큰 35.68% 감소·시간 8.91% 단축, 분산 A보다 전체 토큰 52.04% 감소·시간 5.70% 단축을 기록했다. 비캐시 입력은 B가 가장 작았다. 비용·크레딧 차감액의 절감률은 미측정이다.

| 구성 | 지침 배치 | 지침 원본 커밋 | 로컬 측정 스냅샷 |
| --- | --- | --- | --- |
| ORGINAL | 사용자 제공 최초 지침을 루트 1개 파일로 적용 | [제공 본문·항목 치환본](results/agents-layout/ORGINAL.md) | `6625b39` |
| A | 루트·src/·docs/의 3개 파일 | `0f03aec` | `0f03aec` |
| B | 규칙을 모은 루트 1개 파일 | `894e9ae` | `26efe80` |
| C | 중복 표현·반복 조회를 줄인 루트 1개 파일 | `11c494e` | `b8ac287` |

| 측정 항목 | ORGINAL | A 분산 | B 기존 통합 | C 최적화 통합 |
| --- | ---: | ---: | ---: | ---: |
| 캐시 입력 | 52,608 | 105,472 | 77,952 | 44,672 |
| 비캐시 입력 | 12,466 | 14,580 | 11,004 | 12,392 |
| 출력·추론 | 753 | 612 | 1,017 | 809 |
| 전체 토큰 | 65,827 | 120,664 | 89,973 | 57,873 |
| 경과 시간 | 22.248초 | 28.498초 | 29.501초 | 26.874초 |
| 사용량 변화로 센 모델 응답 | 3 | 5 | 4 | 3 |
| 도구 호출 | 2 | 5 | 4 | 3 |
| 정답 | 일치 | 일치 | 일치 | 일치 |

아래 변화율의 기준은 각 행의 왼쪽 구성이다. 전체 토큰은 캐시 입력·비캐시 입력·출력의 합계다. 출력에 포함된 추론 토큰을 다시 더하지 않았다. 절감률은 `(기준 - 비교 대상) / 기준 × 100`으로 계산하고 반올림했다.

| 비교 | 전체 토큰 변화 | 비캐시 입력 변화 | 경과 시간 변화 |
| --- | ---: | ---: | ---: |
| ORGINAL → A | 83.30% 증가 | 16.96% 증가 | 28.09% 증가 |
| ORGINAL → B | 36.68% 증가 | 11.73% 감소 | 32.60% 증가 |
| ORGINAL → C | 12.08% 감소 | 0.59% 감소 | 20.79% 증가 |
| A → B | 25.44% 감소 | 24.53% 감소 | 3.52% 증가 |
| A → C | 52.04% 감소 | 15.01% 감소 | 5.70% 감소 |
| B → C | 35.68% 감소 | 12.61% 증가 | 8.91% 감소 |

네 실행은 모두 `gpt-6.1-sol`, 추론 강도 `ultra`, Codex CLI `0.166.0`, Windows·Python `3.11.4` 환경의 독립 새 세션이다. 측정용 작업 경로도 같았다. 코드·테스트·조회 문서는 `0f03aec`으로 고정하고 지침 파일만 교체했다. 전역 지침과 Codex 설정의 해시는 최초 기록과 일치했다. 실제 적용된 모델·추론 강도와 루트 지침의 포함은 각 세션 확인값에 기록돼 있다. IDE 문맥과 보조 에이전트는 사용하지 않았다.

`ORGINAL`은 제공된 코드 블록 본문을 루트 `AGENTS.md`로 적용하고 하위 지침은 두지 않았다. 원문의 문장·체크표를 보존하고 대괄호 네 항목만 채웠다. 프로젝트 경로는 기존 측정 작업 트리, 미션은 `규칙 기반 정보 추출·감성 분석 / docs/A4_2_mission.md`, 저장소는 `https://github.com/ntt65/A4_2`, 환경은 `Python 3.11 + uv 0.13.7`이다. 치환값과 지침 해시는 `manifest.json`에 기록했다. `ORGINAL`은 A·B·C와 규칙 내용도 달라 이 비교는 각 지침 전체를 적용했을 때의 관측값이다.

고정 프롬프트는 다음과 같다.

```text
읽기 전용으로 작업하고 관련 AGENTS 지침을 확인하라. 파일 수정과 보조 에이전트 사용 없이 요청한 파일의 근거를 확인하라. 최종 답변은 요청한 키만 가진 JSON 객체로 반환하라.
src/extractor.py에서 한글 단위 금액을 정규화하는 함수의 이름과 정의 행 번호를 찾고, tests/test_extractor.py에서 '1억 2천만원'을 검사하는 test_at_least_three_variants_per_pattern의 기대 금액을 확인하라. 키는 function, line, expected_amount다.
```

네 실행은 모두 아래 정답을 반환했다.

```json
{"function":"_normalize_korean_amount","line":118,"expected_amount":120000000}
```

CLI `turn.completed.usage`를 토큰 집계 근거로 사용했다. 비캐시 입력은 `input_tokens - cached_input_tokens`다. 모델 응답 수는 세션 로그에서 누적 사용량이 달라진 횟수로 센 값이다. 경과 시간은 단조 시계로 CLI 프로세스 시작부터 최종 응답을 포함한 종료까지 측정했다.

| 시도 | 구성 | 시작 시각 KST | 결과 |
| --- | --- | --- | --- |
| 1 | A | 12:09:17.638 | 완료 |
| 2 | B | 12:09:46.463 | 사용자 요청으로 실행 한도를 줄이며 중단 |
| 3 | B | 12:11:25.025 | 완료 |
| 4 | C | 12:57:27.434 | 새 지침 비교 요청에 따라 1회 추가·완료 |
| 5 | ORGINAL | 13:08:21.748 | 사용자 제공 최초 지침 비교 요청에 따라 1회 추가·완료 |

완료된 네 실행의 합계는 334,337토큰이다. 별도로 보존한 중단 시도는 최종 응답·사용량 이벤트가 없어 토큰과 정확한 경과 시간을 확인할 수 없다. 이 중단 시도는 네 구성의 성능 비교에서 제외했다.

각 구성의 표본은 1회다. A와 `ORGINAL`에서는 지침을 읽은 뒤 UTF-8을 명시해 다시 읽는 과정이 있었다. 실행 순서는 A·B·C·`ORGINAL`이며 교대하지 않았다. 조회 선택, 인코딩 재조회, 캐시 상태, 서버 지연의 영향을 분리 측정하지 않았다. 위 수치는 이번 조회 작업의 관측값이며 지침 길이·배치만의 인과 효과와 구현 작업 전체의 절감률은 미확인이다. `ORGINAL`의 계획·코드 수정 승인·커밋 운영 규칙 전체를 이번 조회 과제로 평가할 수 있는지도 미확인이다.

C의 내용 축약과 반복 작업 억제를 토큰 절감 운영에 반영한다. 이번 결과에서 전체 토큰을 우선하면 C, 실행 시간을 우선하면 `ORGINAL`, 비캐시 입력을 우선하면 B가 유리하다. 검증은 GitHub Actions가 수행하고 실행 결과를 확인한다.

실행 조건·고정 파일 해시·지침 버전은 [manifest.json](results/agents-layout/manifest.json), 전체 완료 기록은 [runs.jsonl](results/agents-layout/runs.jsonl), 시도 시작 기록은 [attempts.jsonl](results/agents-layout/attempts.jsonl), 중단 기록은 [interrupted.json](results/agents-layout/interrupted.json), 네 구성의 계산값은 [summary.json](results/agents-layout/summary.json)에 보관했다. [수집 스크립트](results/agents-layout/measure.py)는 기존 완료 기록을 재사용하며 요청마다 추가 호출을 1회로 제한해 실행했다.

원문 CLI 기록은 [A](results/agents-layout/raw/01_code_1_A.jsonl), [B](results/agents-layout/raw/02_code_1_B.jsonl), [C](results/agents-layout/raw/03_code_1_C.jsonl)이며 실제 모델·추론 강도·지침 포함 확인값은 [A 세션](results/agents-layout/raw/01_code_1_A.session.json), [B 세션](results/agents-layout/raw/02_code_1_B.session.json), [C 세션](results/agents-layout/raw/03_code_1_C.session.json)에 있다.

추가한 `ORGINAL`의 원자료는 [CLI 원문](results/agents-layout/raw/04_code_1_ORGINAL.jsonl), [세션 확인값](results/agents-layout/raw/04_code_1_ORGINAL.session.json), [표준 오류](results/agents-layout/raw/04_code_1_ORGINAL.stderr.txt)에 보관했다.
