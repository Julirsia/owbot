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
- `CHANNEL_CONTEXT_LIMIT`
- `THREAD_CONTEXT_LIMIT`
- `COMPLETION_TIMEOUT_SECONDS`
- `OPENWEBUI_TOOL_TIMEOUT_SECONDS`
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
export CHANNEL_CONTEXT_LIMIT="20"
export THREAD_CONTEXT_LIMIT="50"
export COMPLETION_TIMEOUT_SECONDS="60"
export OPENWEBUI_TOOL_TIMEOUT_SECONDS="300"
export STATE_DB_PATH="/var/lib/team-bot/state.db"
export LOG_LEVEL="INFO"
```

설정 원칙:

- `OPENWEBUI_BOT_USER_ID`에는 `bot`, `TEAM-BOT`, 이메일을 넣지 않습니다.
- `OPENWEBUI_TOOL_IDS`를 직접 지정하면 그 요청은 `tool_ids`만 보내는 단순 모드가 되고, `terminal_id`, `skill_ids`, `tool_servers`, `features`는 같은 요청에 섞지 않습니다.
- `OPENWEBUI_TOOL_IDS`, `OPENWEBUI_TOOL_SERVER_IDS`, `OPENWEBUI_FEATURES_JSON`가 비어 있으면 모델 UI에 저장된 기본 도구 설정을 그대로 사용합니다.

## 4. Open Terminal URL 규칙

가장 자주 깨지는 부분입니다.

`OPENWEBUI_TERMINAL_ID`는 단지 Open WebUI에 등록된 terminal connection id일 뿐이고, 실제 접속 가능 여부는 Open WebUI 쪽 terminal connection 설정의 `url`에 달려 있습니다.

이 URL은 `Open WebUI 서버 프로세스가 보는 주소`여야 합니다.

예:

- Open WebUI와 Open Terminal이 같은 Docker host에 있고 Open WebUI가 컨테이너로 뜬 경우
  - `http://localhost:8000`은 대개 잘못된 값입니다
  - `http://host.docker.internal:8000` 또는 컨테이너 간 통신 가능한 주소를 사용해야 합니다
- docker compose 같은 네트워크에서 서비스명이 서로 resolve되는 경우
  - `http://open-terminal:8000` 같은 내부 서비스명을 사용할 수 있습니다
- bare metal 또는 같은 VM에서 직접 띄운 경우
  - 그때만 `http://localhost:8000`이 맞을 수 있습니다

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

## 9. 장애 대응

- 봇이 무응답이면 먼저 Open WebUI 토큰과 `OPENWEBUI_BOT_USER_ID` 일치 여부를 봅니다.
- `OPENWEBUI_BOT_TOKEN`이 `sk-...` API 키라면 websocket 수신용으로는 부족할 수 있습니다. 이 경우 `OPENWEBUI_BOT_SESSION_TOKEN` 또는 `OPENWEBUI_BOT_EMAIL` / `OPENWEBUI_BOT_PASSWORD`도 함께 설정합니다.
- tool 호출이 안 되면 먼저 UI에서 같은 모델로 같은 요청이 실제 되는지 확인합니다.
- terminal 호출이 안 되면 먼저 terminal proxy 엔드포인트가 200인지 확인합니다.
- 자세한 절차는 [debugging.md](/Users/julirsia/development/company/openwebui-bot/docs/debugging.md)를 봅니다.
