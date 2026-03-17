# TEAM-BOT Runbook

## 1. Open WebUI 준비

1. Open WebUI에서 봇 전용 사용자 계정 `TEAM-BOT`을 생성합니다.
2. 해당 사용자의 API 토큰을 발급합니다.
3. 봇이 반응해야 하는 채널에 읽기/쓰기 권한을 부여합니다.
4. 사용할 모델과 Tools/MCP/OpenAPI 연결을 Open WebUI에 미리 구성합니다.

## 2. 환경 변수

필수:

- `OPENWEBUI_BASE_URL`
- `OPENWEBUI_BOT_TOKEN`
- `OPENWEBUI_BOT_USER_ID`

선택:

- `OPENWEBUI_BOT_DISPLAY_NAME`
- `OPENWEBUI_MODEL_ID`
- `OPENWEBUI_TOOL_IDS`
- `OPENWEBUI_TOOL_SERVER_IDS`
- `OPENWEBUI_FEATURES_JSON`
- `CHANNEL_CONTEXT_LIMIT`
- `THREAD_CONTEXT_LIMIT`
- `COMPLETION_TIMEOUT_SECONDS`
- `STATE_DB_PATH`
- `LOG_LEVEL`

예시:

```bash
export OPENWEBUI_BASE_URL="https://openwebui.example.com"
export OPENWEBUI_BOT_TOKEN="owui_xxx"
export OPENWEBUI_BOT_USER_ID="user-123"
export OPENWEBUI_BOT_DISPLAY_NAME="TEAM-BOT"
export OPENWEBUI_MODEL_ID="gpt-5-mini"
export OPENWEBUI_TOOL_IDS="tool_1,tool_2"
export OPENWEBUI_TOOL_SERVER_IDS="server_1"
export OPENWEBUI_FEATURES_JSON='{"web_search": true, "image_generation": false, "code_interpreter": false}'
export CHANNEL_CONTEXT_LIMIT="20"
export THREAD_CONTEXT_LIMIT="50"
export COMPLETION_TIMEOUT_SECONDS="60"
export STATE_DB_PATH="/tmp/team-bot-state.db"
```

## 3. 실행

```bash
python -m team_bot.main
```

디버깅 절차는 [debugging.md](/Users/julirsia/development/company/openwebui-bot/docs/debugging.md)를 참고합니다.

## 4. 호출 규칙

- 사용자가 채널에서 `@TEAM-BOT`을 멘션해야만 반응합니다.
- 메인 채널에서 호출하면 메인 채널에 답합니다.
- 스레드에서 호출하면 같은 스레드에 답합니다.

## 5. 장애 대응

- 봇이 무응답이면 먼저 Open WebUI 토큰과 `OPENWEBUI_BOT_USER_ID`가 일치하는지 확인합니다.
- 이벤트는 SQLite 상태 저장소로 중복 제거합니다. 테스트 중 같은 메시지를 다시 처리하려면 `STATE_DB_PATH` 파일을 지웁니다.
- 도구 호출 실패는 Open WebUI 쪽 모델/도구 설정 문제일 수 있으므로, 동일 토큰으로 `/api/chat/completions`를 직접 호출해 재현해 봅니다.
