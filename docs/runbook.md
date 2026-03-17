# TEAM-BOT Runbook

## 1. 문서 범위

이 문서는 `실제 운영 환경` 기준입니다.

중요:

- 로컬에서 한 번 동작했다고 해서 운영 환경에서도 그대로 되지 않습니다.
- 운영 환경에서는 Open WebUI URL, 인증 방식, 모델 id, terminal id, network topology를 다시 확인해야 합니다.
- 특히 Open Terminal URL은 `사용자 브라우저`가 아니라 `Open WebUI 서버`에서 접근 가능한 주소여야 합니다.

## 2. 배포 전 준비

운영 환경에서 아래를 먼저 준비합니다.

1. Open WebUI에 봇 전용 사용자 계정을 만든다.
2. 그 계정의 API 토큰을 발급한다.
3. websocket 인증용으로 아래 둘 중 하나를 준비한다.
   - `OPENWEBUI_BOT_SESSION_TOKEN`
   - 또는 `OPENWEBUI_BOT_EMAIL` / `OPENWEBUI_BOT_PASSWORD`
4. 봇이 읽고 써야 하는 채널에 권한을 부여한다.
5. 사용할 모델 preset, builtin tools, MCP/OpenAPI 연결, Open Terminal 연결을 Open WebUI에서 먼저 구성한다.
6. `OPENWEBUI_BOT_USER_ID`는 표시 이름이 아니라 실제 내부 user id로 확인한다.

## 2-1. 시스템 아키텍처

이 저장소는 Open WebUI를 대체하지 않고, Open WebUI 바깥에서 동작하는 채널 오케스트레이션 워커입니다.

구성 요소:

- `사용자`
  - Open WebUI 채널 / 스레드에서 대화
- `Open WebUI`
  - 인증, 채널 UI, 모델 preset, native tools, terminal connection 관리
- `owbot Worker`
  - 멘션 감지, 채널 문맥 수집, completion 요청, 최종 응답 게시
- `OpenTerminal`
  - 별도 API 서버
  - 명령 실행, 파일 조작, skill이 참조하는 로컬 스크립트 실행 기반 제공

실제 요청 흐름:

1. 사용자가 채널 또는 스레드에서 `@TEAM-BOT` 멘션
2. 워커가 Open WebUI websocket `events:channel`을 통해 메시지 수신
3. 워커가 Open WebUI REST API로 최근 채널 / 스레드 문맥 조회
4. 워커가 Open WebUI `/api/chat/completions` 호출
5. tool / terminal / skill이 필요하면 Open WebUI가 자체 tool lifecycle 수행
6. terminal이 필요한 경우 Open WebUI가 등록된 terminal connection `url`로 OpenTerminal API 호출
7. 워커가 websocket completion event에서 최종 답변 회수
8. 워커가 Open WebUI 채널 메시지 API로 답변 게시

즉 워커는 OpenTerminal에 직접 붙지 않습니다. `terminal_id`만 Open WebUI에 넘기고, 실제 OpenTerminal API 호출은 Open WebUI가 담당합니다.

## 3. 환경 변수

필수:

- `OPENWEBUI_BASE_URL`
- `OPENWEBUI_BOT_TOKEN`
- `OPENWEBUI_BOT_USER_ID`

선택:

- `OPENWEBUI_BOT_SESSION_TOKEN`
- `OPENWEBUI_BOT_EMAIL`
- `OPENWEBUI_BOT_PASSWORD`
- `OPENWEBUI_BOT_DISPLAY_NAME`
- `OPENWEBUI_MODEL_ID`
- `OPENWEBUI_TERMINAL_ID`
- `OPENWEBUI_SKILL_IDS`
- `OPENWEBUI_TOOL_IDS`
- `OPENWEBUI_TOOL_SERVER_IDS`
- `OPENWEBUI_FEATURES_JSON`
- `OPENWEBUI_FORCE_NATIVE_FUNCTION_CALLING`
- `CHANNEL_CONTEXT_LIMIT`
- `THREAD_CONTEXT_LIMIT`
- `COMPLETION_TIMEOUT_SECONDS`
- `OPENWEBUI_TOOL_TIMEOUT_SECONDS`
- `OPENWEBUI_STARTUP_RETRY_SECONDS`
- `STATE_RETENTION_SECONDS`
- `STATE_CLEANUP_INTERVAL_SECONDS`
- `STATE_DB_PATH`
- `LOG_LEVEL`
- `SOCKETIO_DEBUG`
- `LOG_RAW_CHANNEL_EVENTS`
- `LOG_MESSAGE_CONTENT`

예시:

```bash
export OPENWEBUI_BASE_URL="https://openwebui.company.internal"
export OPENWEBUI_BOT_TOKEN="sk_xxx"
export OPENWEBUI_BOT_EMAIL="team-bot@company.internal"
export OPENWEBUI_BOT_PASSWORD="super-secret-password"
export OPENWEBUI_BOT_USER_ID="actual-user-id"
export OPENWEBUI_BOT_DISPLAY_NAME="TEAM-BOT"
export OPENWEBUI_MODEL_ID="team-bot-model"
export OPENWEBUI_TERMINAL_ID="terminal-prod"
export OPENWEBUI_SKILL_IDS=""
export OPENWEBUI_TOOL_IDS=""
export OPENWEBUI_TOOL_SERVER_IDS=""
export OPENWEBUI_FEATURES_JSON=''
export OPENWEBUI_FORCE_NATIVE_FUNCTION_CALLING="false"
export CHANNEL_CONTEXT_LIMIT="20"
export THREAD_CONTEXT_LIMIT="50"
export COMPLETION_TIMEOUT_SECONDS="60"
export OPENWEBUI_TOOL_TIMEOUT_SECONDS="300"
export OPENWEBUI_STARTUP_RETRY_SECONDS="5"
export STATE_RETENTION_SECONDS="604800"
export STATE_CLEANUP_INTERVAL_SECONDS="3600"
export STATE_DB_PATH="/var/lib/team-bot/state.db"
export LOG_LEVEL="INFO"
```

설정 원칙:

- `OPENWEBUI_BOT_USER_ID`에는 `bot`, `TEAM-BOT`, 이메일을 넣지 않습니다.
- `OPENWEBUI_TOOL_IDS`를 직접 지정하면 그 요청은 `tool_ids`만 보내는 단순 모드가 되고, `terminal_id`, `skill_ids`, `tool_servers`, `features`는 같은 요청에 섞지 않습니다.
- `OPENWEBUI_TOOL_IDS`, `OPENWEBUI_TOOL_SERVER_IDS`, `OPENWEBUI_FEATURES_JSON`가 비어 있으면 모델 UI에 저장된 기본 도구 설정을 그대로 사용합니다.
- `/api/models`가 model preset 메타를 충분히 주지 않는 환경이면 `OPENWEBUI_FORCE_NATIVE_FUNCTION_CALLING=true`로 강제하는 편이 안전합니다.
- 중복 이벤트 dedupe는 `STATE_RETENTION_SECONDS` 동안만 유지하고, `STATE_CLEANUP_INTERVAL_SECONDS`마다 만료 레코드를 자동 삭제합니다.

## 4. Open Terminal URL 규칙

가장 자주 깨지는 부분입니다.

`OPENWEBUI_TERMINAL_ID`는 단지 Open WebUI에 등록된 terminal connection id일 뿐이고, 실제 접속 가능 여부는 Open WebUI 쪽 terminal connection 설정의 `url`에 달려 있습니다.

이 URL은 `Open WebUI 서버 프로세스가 보는 주소`여야 합니다.

구분:

- `OPENWEBUI_TERMINAL_ID`
  - 워커가 사용하는 값
  - Open WebUI 내부 terminal connection 레코드 id
- terminal connection `url`
  - Open WebUI 관리자 UI에서 설정하는 값
  - 실제 OpenTerminal API base URL

대표 프록시 경로:

- `/api/v1/terminals/{terminal_id}/api/config`
- `/api/v1/terminals/{terminal_id}/files/cwd`
- `/api/v1/terminals/{terminal_id}/ports`

대표 OpenTerminal API:

- `/openapi.json`
- `/execute`
- `/execute/{process_id}/status`
- `/files/list`
- `/files/read`
- `/files/grep`
- `/files/write`
- `/files/replace`

예:

- Open WebUI와 Open Terminal이 같은 Docker host에 있고 Open WebUI가 컨테이너로 뜬 경우
  - `http://localhost:8000`은 대개 잘못된 값입니다
  - `http://host.docker.internal:8000` 또는 컨테이너 간 통신 가능한 주소를 사용해야 합니다
- docker compose 같은 네트워크에서 서비스명이 서로 resolve되는 경우
  - `http://open-terminal:8000` 같은 내부 서비스명을 사용할 수 있습니다
- bare metal 또는 같은 VM에서 직접 띄운 경우
  - 그때만 `http://localhost:8000`이 맞을 수 있습니다
- reverse proxy 뒤에서 OpenTerminal을 따로 노출한 경우
  - `https://open-terminal.company.internal`처럼 Open WebUI 서버에서 실제로 라우팅 가능한 주소를 사용해야 합니다

운영 전에 반드시 Open WebUI 서버 기준으로 아래 프록시가 200이 나는지 확인합니다.

- `/api/v1/terminals/{terminal_id}/api/config`
- `/api/v1/terminals/{terminal_id}/files/cwd`
- `/api/v1/terminals/{terminal_id}/ports`

## 5. 배포 절차

운영 환경 서버에서:

```bash
git clone https://github.com/Julirsia/owbot.git
cd owbot
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m team_bot.main
```

실행 전에 `.env`를 운영 환경 값으로 채웁니다.

주의:

- 로컬 검증 때 썼던 `BOT_USER_ID`, `terminal_id`, URL을 그대로 복사하지 않습니다.
- `.env`를 바꾼 뒤에는 반드시 프로세스를 재시작합니다.

## 6. 동작 방식 요약

- 사용자가 채널에서 `@TEAM-BOT`을 멘션해야만 반응합니다.
- 메인 채널에서 호출하면 메인 채널에 답합니다.
- 스레드에서 호출하면 같은 스레드에 답합니다.
- 일반 질의는 `/api/chat/completions`의 일반 JSON 응답을 사용합니다.
- native tool / OpenTerminal / MCP 경로는 Open WebUI의 websocket `events` lifecycle을 사용합니다.
- 이 경우 워커는 실제 socket `session_id`와 임시 `local:` `chat_id` / `message_id`를 completion 요청에 넣고, HTTP 본문이 아니라 websocket `events`에서 최종 답변을 회수합니다.

## 7. 운영 전 체크리스트

아래를 모두 만족해야 합니다.

- Open WebUI 로그인 계정과 `OPENWEBUI_BOT_TOKEN` 소유자가 같다
- `OPENWEBUI_BOT_USER_ID`가 실제 user id와 같다
- 봇 계정이 대상 채널에 들어가 있다
- 대상 모델 id가 실제 존재한다
- 모델의 native function calling 설정이 기대대로 켜져 있다
- 필요한 tool / MCP / terminal이 모델 또는 요청 설정으로 노출된다
- terminal connection에 봇 계정 access grant가 있다
- Open WebUI 서버 기준 terminal proxy 엔드포인트가 200이다
- 봇 프로세스가 websocket에 붙고 `join-channels` 후 채널 이벤트를 받는다

## 8. 운영 검증 순서

1. `/api/v1/channels`가 200인지 확인
2. 같은 토큰으로 `/api/chat/completions` 일반 질의가 되는지 확인
3. Open WebUI UI에서 같은 모델로 tool / terminal 호출이 실제 되는지 확인
4. 워커를 `LOG_LEVEL=DEBUG`로 실행
5. 다른 사용자 계정으로 채널에서 자동완성 멘션
6. 채널 응답과 로그를 함께 확인
7. terminal을 쓴다면 Open WebUI 프록시와 OpenTerminal 자체 스펙 경로가 모두 정상인지 확인

반복 검증이 필요하면 [scripts/run_channel_e2e.py](/Users/julirsia/development/company/openwebui-bot/scripts/run_channel_e2e.py)를 사용합니다.

- 전제: 워커가 이미 실행 중이어야 합니다.
- 입력: bot 계정, 테스트 사용자 계정, bot user id
- 동작: 임시 그룹 채널 생성 후 메인 채널 / 스레드의 tool / terminal 시나리오를 확인하고, `OWBOT_TEST_SKILL_NAME`이 주어지면 `$스킬` 시나리오도 함께 확인

## 9. 채널 / 스레드 E2E 검증 매트릭스

운영 투입 전에는 아래 여섯 가지를 실제로 모두 통과시켜야 합니다.

### A. 메인 채널 멘션

1. 일반 응답
   - 예: `@TEAM-BOT 지금 뭐가 보이는지 한 줄로 요약해줘`
   - 기대 결과: 메인 채널에 최상위 메시지로 답변
2. tool 호출
   - 예: `@TEAM-BOT 현재 사용 가능한 knowledge base를 알려줘`
   - 기대 결과: tool이 실행되고 최종 자연어 답변이 메인 채널에 게시됨
3. terminal 호출
   - 예: `@TEAM-BOT 현재 시스템에서 실행 중인 프로세스를 확인해줘. 가능하면 터미널을 사용해.`
   - 기대 결과: terminal tool이 실행되고 최종 요약 답변이 메인 채널에 게시됨
4. skill 호출
   - 예: `@TEAM-BOT $terminal-file-check 스킬을 실행해서 나온 결과를 그대로 알려줘`
   - 기대 결과: skill 지침과 연결된 terminal script 결과가 메인 채널에 게시됨

### B. 스레드 멘션

1. 일반 응답
   - 스레드 안에서 `@TEAM-BOT 이 스레드 문맥만 보고 답해줘`
   - 기대 결과: 같은 스레드에 답글로 응답
2. tool 호출
   - 스레드 안에서 knowledge / notes / MCP tool이 필요한 요청
   - 기대 결과: 같은 스레드에서 tool 실행 후 최종 자연어 답변까지 이어짐
3. terminal 호출
   - 스레드 안에서 terminal이 필요한 요청
   - 기대 결과: 같은 스레드에서 terminal tool 실행 후 최종 자연어 답변까지 이어짐
4. skill 호출
   - 스레드 안에서 `$스킬명`을 포함한 요청
   - 기대 결과: 같은 스레드에서 skill 지침과 연결된 terminal script 결과까지 포함해 응답

검증 기준:

- 단순히 `tool_calls`가 보이는 것만으로 통과로 보지 않습니다.
- 최종 assistant 자연어 답변이 실제 채널 또는 스레드에 게시돼야 통과입니다.
- 메인 채널 호출은 메인 채널 최상위 메시지, 스레드 호출은 같은 스레드 답글 위치가 맞아야 합니다.

로컬 참고 결과:

- 2026-03-17 로컬 Docker 검증에서는 아래 여섯 가지가 실제 통과했습니다.
- 메인 채널 멘션 + knowledge tool 응답
- 메인 채널 멘션 + Open Terminal 응답
- 스레드 멘션 + knowledge tool 응답
- 스레드 멘션 + Open Terminal 응답
- 메인 채널 멘션 + `$terminal-file-check` skill 응답 (`TERMINAL_SKILL_OK`)
- 스레드 멘션 + `$terminal-file-check` skill 응답 (`TERMINAL_SKILL_OK`)
- 이 결과는 로컬 검증 참고용입니다. 실제 운영 환경에서는 같은 항목을 다시 검증해야 합니다.

## 10. 운영 검증 시 로그 포인트

tool / terminal 검증 시 아래 로그가 같이 보여야 정상입니다.

- `Accepted bot invocation ...`
- `Processing invocation ...`
- `Starting background chat completion ...`
- `Completion event ... type=chat:completion ...`
- 마지막에 `chat:completion`의 `done=true` 또는 `chat:active active=false`
- `Posting response channel_id=...`

실패 판정:

- `Accepted bot invocation`까지만 나오고 응답이 없으면 completion lifecycle 문제
- `tool_calls`는 보이는데 최종 메시지가 안 올라오면 websocket `events` 최종 회수 문제
- 메인 채널 호출인데 스레드에 달리거나, 스레드 호출인데 메인 채널에 올라오면 응답 위치 버그

## 11. 장애 대응

- 봇이 무응답이면 먼저 Open WebUI 토큰과 `OPENWEBUI_BOT_USER_ID` 일치 여부를 봅니다.
- `OPENWEBUI_BOT_TOKEN`이 `sk-...` API 키라면 websocket 수신용으로는 부족할 수 있습니다. 이 경우 `OPENWEBUI_BOT_SESSION_TOKEN` 또는 `OPENWEBUI_BOT_EMAIL` / `OPENWEBUI_BOT_PASSWORD`도 함께 설정합니다.
- tool 호출이 안 되면 먼저 UI에서 같은 모델로 같은 요청이 실제 되는지 확인합니다.
- terminal 호출이 안 되면 먼저 terminal proxy 엔드포인트가 200인지 확인합니다.
- 자세한 절차는 [debugging.md](/Users/julirsia/development/company/openwebui-bot/docs/debugging.md)를 봅니다.
