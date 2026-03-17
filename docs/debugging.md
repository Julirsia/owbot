# TEAM-BOT Debugging Guide

## 1. 먼저 확인할 것

- Open WebUI에서 `TEAM-BOT` 계정이 실제로 채널 멤버인지
- `OPENWEBUI_BOT_TOKEN`이 그 계정의 토큰인지
- `OPENWEBUI_BOT_USER_ID`가 실제 사용자 id와 일치하는지
- 봇이 사용할 모델 id가 Open WebUI에 존재하는지

## 2. 환경 변수 검증

```bash
python - <<'PY'
from team_bot.config import BotConfig
print(BotConfig.from_env())
PY
```

실패하면 필수 환경 변수가 비어 있거나 `OPENWEBUI_FEATURES_JSON` 형식이 잘못된 것입니다.

## 3. REST API 연결 확인

```bash
curl -sS "$OPENWEBUI_BASE_URL/api/v1/channels" \
  -H "Authorization: Bearer $OPENWEBUI_BOT_TOKEN"
```

기대 결과:

- 200 응답
- 봇이 접근 가능한 채널 목록 JSON

실패 패턴:

- 401: 토큰 불일치
- 403: Channels 비활성화 또는 권한 부족

## 4. 모델 completion 단독 확인

워커를 띄우기 전에 completion 자체가 되는지 먼저 확인합니다.

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

여기서 실패하면 워커 문제가 아니라 Open WebUI 모델 설정 문제입니다.

## 5. 워커 실행 로그 보기

```bash
LOG_LEVEL=DEBUG python -m team_bot.main
```

정상 시작 시 기대 로그:

- websocket connect
- `user-join` 인증 성공
- heartbeat loop 시작

## 6. 멘션이 안 먹을 때

이 워커는 Open WebUI 저장 포맷 그대로 `<@U:{bot_user_id}|TEAM-BOT>` 멘션을 감지합니다.

확인 순서:

1. 채널에서 실제로 자동완성으로 `@TEAM-BOT`을 선택했는지
2. 단순 텍스트 `@TEAM-BOT`만 쓴 것이 아닌지
3. 봇 계정이 그 채널 멤버인지
4. 워커 로그에 `Skipping duplicate` 외 다른 오류가 없는지

## 7. 응답 위치가 이상할 때

- 메인 채널 호출: `parent_id` 없이 최상위 메시지로 답함
- 스레드 호출: `parent_id=thread_root_id`로 같은 스레드에 답함

확인은 SQLite 상태파일을 지운 뒤 같은 호출을 다시 테스트하면 빠릅니다.

```bash
rm -f "$STATE_DB_PATH"
```

## 8. 중복 응답 디버깅

중복 방지 키는 `channel_id:message_id:updated_at_or_created_at`입니다.

확인 방법:

```bash
sqlite3 "$STATE_DB_PATH" 'select * from processed_events order by processed_at desc limit 20;'
```

## 9. websocket 세션이 끊길 때

Open WebUI는 heartbeat가 없으면 세션을 정리할 수 있습니다. 이 워커는 주기적으로:

- `heartbeat`
- `join-channels`

를 전송합니다.

그래도 끊기면 확인할 것:

- 프록시가 websocket을 허용하는지
- `OPENWEBUI_BASE_URL`이 브라우저 접속 주소와 같은지
- 네트워크 장비가 idle websocket을 자르는지

## 10. 도구 호출이 안 될 때

우선순위:

1. Open WebUI UI에서 같은 모델로 도구 호출이 실제 되는지 확인
2. `OPENWEBUI_TOOL_IDS`에 올바른 tool id가 들어갔는지 확인
3. 필요한 경우 `OPENWEBUI_FEATURES_JSON`에서 웹검색/코드실행 같은 feature toggle이 켜져 있는지 확인
4. 작은 모델은 native tool calling 품질이 낮을 수 있으므로 `gpt-5-mini` 같은 상위 모델로 먼저 검증

## 11. 최소 재현 순서

1. `.env` 작성
2. `curl /api/v1/channels` 확인
3. `curl /api/chat/completions` 확인
4. `python -m team_bot.main` 실행
5. 채널에서 자동완성으로 `@TEAM-BOT` 멘션 후 테스트
