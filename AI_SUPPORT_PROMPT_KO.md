# AI에게 도움 요청할 때

이 저장소를 Codex 또는 Claude Code에서 연 뒤, 아래 문장을 그대로 붙여넣으세요.

```text
이 프로젝트는 Note Bridge입니다.
Plaud 녹음 전사본을 가져와 사용자의 기준으로 분류하고 Notion DB에 저장하는 macOS 로컬 앱입니다.

먼저 README.md를 읽고 구조를 파악해 주세요.

그 다음 다음 순서로 도와주세요.
1. diagnose.command를 실행해서 필요한 도구가 있는지 확인해 주세요.
2. Note Bridge.app이 정상 실행되는지 확인해 주세요.
3. Plaud 연결이 안 되면 npx, Node.js, Plaud MCP 로그인 상태, ~/.plaud/tokens-mcp.json 존재 여부를 확인해 주세요.
4. Notion 연결이 안 되면 Notion API 토큰, Notion DB 전체 주소, 해당 DB에 Integration이 연결되어 있는지 확인해 주세요.
5. AI API 연결이 안 되면 OpenAI 또는 Claude API 키 형식과 모델 확인 요청이 성공하는지 봐 주세요.
6. 앱 로그는 ~/Library/Application Support/Note Bridge/server.log 와 app.log를 확인해 주세요.
7. 수정이 필요하면 소스를 고치고 ./build_app.sh로 앱을 다시 빌드해 주세요.

주의:
- API 키, Plaud 토큰, Notion 토큰 값을 채팅에 그대로 출력하지 마세요.
- 토큰이 있는지 여부만 확인하고, 값은 마스킹해 주세요.
- 이 앱은 Plaud 공식 앱이 아니며, 개인 로컬 자동화 도구입니다.
```
