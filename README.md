# openwebui-bot

Open WebUI 채널에서 `@TEAM-BOT`을 멘션하면 최근 채널 문맥과 현재 스레드 문맥을 읽고 응답하는 외부 워커형 봇입니다.

기본적으로 모델 UI에 저장된 도구 설정을 따르며, `OPENWEBUI_TOOL_IDS`를 지정하면 그 요청은 `tool_ids`만 명시적으로 보내는 단순 모드로 동작합니다. 이 경우 `OPENWEBUI_TOOL_SERVER_IDS` / `OPENWEBUI_FEATURES_JSON` / `OPENWEBUI_TERMINAL_ID` / `OPENWEBUI_SKILL_IDS`는 같은 요청에서 섞지 않습니다. tool/terminal 경로도 Open WebUI의 `/api/chat/completions` 단일 응답을 그대로 사용합니다.

## 구조

- `team_bot/config.py`: 환경 변수 로딩과 검증
- `team_bot/openwebui_client.py`: Open WebUI REST / Socket.IO 클라이언트
- `team_bot/context_builder.py`: 채널 컨텍스트 수집, 멘션 처리, 프롬프트 구성
- `team_bot/state.py`: SQLite 기반 중복 처리 방지
- `team_bot/worker.py`: 이벤트 수신, completion 호출, 응답 전송
- `team_bot/main.py`: 실행 진입점
- `tests/`: 기본 단위 테스트
- `docs/runbook.md`: 운영 절차

## 빠른 실행

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m team_bot.main
```

필수 환경 변수와 운영 절차는 [docs/runbook.md](/Users/julirsia/development/company/openwebui-bot/docs/runbook.md), 디버깅 절차는 [docs/debugging.md](/Users/julirsia/development/company/openwebui-bot/docs/debugging.md)에 정리했습니다.
