# TEAM-BOT Debugging Guide

## 1. 먼저 구분할 것

문제를 볼 때 아래 세 층을 분리해서 봅니다.

1. Open WebUI 계정 / 권한 문제
2. 워커의 websocket / 채널 이벤트 수신 문제
3. 모델 completion / tool / terminal 실행 문제

한 번에 모두 보지 말고, 아래 순서대로 좁히는 것이 빠릅니다.

## 2. 환경 변수 확인

```bash
python - <<'PY'
from team_bot.config import BotConfig
print(BotConfig.from_env())
PY
```

실패하면:

- 필수 환경 변수가 비어 있거나
- `OPENWEBUI_FEATURES_JSON` 형식이 잘못된 것입니다

특히 반드시 확인할 것:

- `OPENWEBUI_BOT_USER_ID`가 실제 Open WebUI 내부 user id인지
- `OPENWEBUI_MODEL_ID`가 실제 존재하는지
- `OPENWEBUI_TERMINAL_ID`가 실제 등록된 terminal connection id인지

## 3. 강한 진단 모드

`.env` 또는 쉘에서 아래를 켭니다.

```bash
LOG_LEVEL=DEBUG
SOCKETIO_DEBUG=true
LOG_RAW_CHANNEL_EVENTS=true
LOG_MESSAGE_CONTENT=true
```

의미:

- `SOCKETIO_DEBUG=true`: `socketio` / `engineio` 내부 패킷 로그
- `LOG_RAW_CHANNEL_EVENTS=true`: `events:channel` raw payload
- `LOG_MESSAGE_CONTENT=true`: 수신 메시지 본문과 멘션 판정 근거

실행:

```bash
python -m team_bot.main
```

## 4. REST 기본 연결 확인

```bash
curl -sS "$OPENWEBUI_BASE_URL/api/v1/channels" \
  -H "Authorization: Bearer $OPENWEBUI_BOT_TOKEN"
```

기대 결과:

- 200
- 봇이 접근 가능한 채널 목록 JSON

실패 해석:

- 401: 토큰 불일치
- 403: Channels 비활성화 또는 권한 부족

## 5. websocket 계정 일치 확인

정상 시작 시 아래 로그가 보여야 합니다.

- `Connected to Open WebUI websocket ...`
- `Authenticated bot identity actual_user_id=... actual_user_name=...`
- `Bot can access ... channels`

중요:

- `actual_user_id`가 `.env`의 `OPENWEBUI_BOT_USER_ID`와 다르면 설정이 틀린 것입니다
- `actual_user_name`이 기대한 봇 이름과 다르면 plain-text 멘션 fallback이 빗나갈 수 있습니다

## 6. 멘션이 안 먹을 때

이 워커는 두 방식 모두 감지합니다.

- 구조화된 Open WebUI 사용자 멘션: `<@U:{bot_user_id}|봇이름>`
- plain text fallback: `@봇이름`

확인 순서:

1. 채널에서 자동완성으로 봇 계정을 선택했는지
2. 봇이 그 채널 멤버인지
3. 로그에 아래 줄이 찍히는지

- `Received channel event ...`
- `Message received id=...`
- `Mention analysis ...`
- `Accepted bot invocation ...`

해석:

- `Received channel event`가 없으면 websocket room join 또는 권한 문제입니다
- `Message received`까지만 나오면 이벤트는 오지만 멘션 판정이 안 됩니다
- `Mention analysis`에서 둘 다 `False`면 멘션 포맷 또는 봇 식별자 문제입니다

## 7. 일반 completion만 먼저 확인

tool/terminal을 보기 전에 plain completion부터 확인합니다.

```bash
curl -sS "$OPENWEBUI_BASE_URL/api/chat/completions" \
  -H "Authorization: Bearer $OPENWEBUI_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "'"$OPENWEBUI_MODEL_ID"'",
    "messages": [
      {"role": "system", "content": "반드시 한국어로 짧게 답해."},
      {"role": "user", "content": "테스트 응답만 해줘."}
    ],
    "stream": false
  }'
```

여기서 실패하면 워커 문제가 아니라 모델 또는 Open WebUI 설정 문제입니다.

## 8. tool / terminal 경로의 핵심 구조

native tool / OpenTerminal / MCP 경로는 일반 HTTP completion과 다르게 봐야 합니다.

현재 워커는:

- 실제 websocket `session_id`
- 임시 `local:` `chat_id`
- 임시 `message_id`

를 `/api/chat/completions`에 함께 보냅니다.

이 경우 `/api/chat/completions` HTTP 응답은 보통 최종 텍스트가 아니라:

- `{"status": true, "task_id": "..."}`

만 돌려주고, 실제 진행 상태와 최종 답변은 websocket `events`로 옵니다.

즉 tool/terminal 실패를 볼 때는 HTTP 본문만 보면 안 됩니다.

반드시 websocket `events`에서 아래를 같이 봐야 합니다.

- `chat:completion`
- `chat:message:error`
- `chat:tasks:cancel`
- `chat:active`

## 9. tool 호출이 안 될 때

우선순위:

1. Open WebUI UI에서 같은 모델로 같은 요청이 실제 되는지 확인
2. 모델의 native function calling이 켜져 있는지 확인
3. `OPENWEBUI_TOOL_IDS`를 직접 지정했다면 올바른 id인지 확인
4. `OPENWEBUI_TOOL_IDS`를 직접 지정했다면 `terminal_id`, `skill_ids`, `tool_servers`, `features`가 같은 요청에서 빠진다는 점을 확인
5. 작은 모델이라면 상위 모델로 먼저 재현

## 10. terminal 호출이 안 될 때

가장 흔한 원인은 Open Terminal proxy 연결 문제입니다.

먼저 아래를 확인합니다.

```bash
curl -sS "$OPENWEBUI_BASE_URL/api/v1/terminals/" \
  -H "Authorization: Bearer $OPENWEBUI_BOT_TOKEN"
```

그 다음 실제 프록시가 되는지 봅니다.

```bash
curl -sS -D - "$OPENWEBUI_BASE_URL/api/v1/terminals/$OPENWEBUI_TERMINAL_ID/api/config" \
  -H "Authorization: Bearer $OPENWEBUI_BOT_TOKEN"
```

같은 방식으로 확인:

- `/api/v1/terminals/{id}/files/cwd`
- `/api/v1/terminals/{id}/ports`

실패 해석:

- 404: terminal id 불일치
- 403: access grant 부족
- 502: Open WebUI가 terminal backend URL에 붙지 못함

특히 Docker 환경에서는 `localhost`를 가장 먼저 의심합니다.

- Open WebUI가 컨테이너 안에 있으면 `http://localhost:8000`은 대개 잘못된 값입니다
- `http://host.docker.internal:8000` 또는 컨테이너 간 통신 주소를 써야 합니다

## 11. 실제로 final message가 안 올 때

이 경우 아래를 순서대로 봅니다.

1. worker websocket이 연결돼 있는지
2. completion 요청에 실제 `session_id`, `chat_id`, `message_id`가 실리는지
3. `/api/chat/completions`가 `task_id`를 돌려주는지
4. websocket `events`에서 `chat:completion`이 오는지
5. 마지막에 `done=true`가 붙은 `chat:completion`이 오는지
6. `chat:message:error` 또는 `chat:tasks:cancel`이 같이 오는지

현재 저장소는 최종 assistant 텍스트를:

- `chat:completion.data.output`의 마지막 assistant message
- 없으면 `chat:completion.data.content`에서 `<details>` 블록 제거 후 남은 텍스트

순서로 회수합니다.

## 12. 중복 응답 디버깅

중복 방지 키:

- `channel_id:message_id:updated_at_or_created_at`

확인:

```bash
sqlite3 "$STATE_DB_PATH" 'select * from processed_events order by processed_at desc limit 20;'
```

같은 이벤트를 다시 처리하려면:

```bash
rm -f "$STATE_DB_PATH"
```

## 13. 최소 재현 순서

1. `.env` 작성
2. `curl /api/v1/channels` 확인
3. `curl /api/chat/completions` plain completion 확인
4. terminal proxy 엔드포인트 200 확인
5. `LOG_LEVEL=DEBUG SOCKETIO_DEBUG=true LOG_RAW_CHANNEL_EVENTS=true LOG_MESSAGE_CONTENT=true python -m team_bot.main`
6. 다른 사용자 계정으로 채널에서 자동완성 멘션
7. 아래 로그를 확보

- `Connected to Open WebUI websocket ...`
- `Authenticated bot identity ...`
- `Bot can access ... channels`
- `Received channel event ...`
- `Mention analysis ...`
- `Accepted bot invocation ...`

tool/terminal 문제면 여기에 더해 아래도 봅니다.

- `Starting background chat completion ...`
- `Completion event ... type=chat:completion ...`
- `Completion event ... type=chat:active ...`
