#!/usr/bin/env bash
set -u

APP_NAME="Note Bridge"
APP_PORT="8765"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_PATH="$SCRIPT_DIR/$APP_NAME.app"
CONFIG_DIR="$HOME/Library/Application Support/$APP_NAME"
CONFIG_FILE="$CONFIG_DIR/.env"
APP_LOG="$CONFIG_DIR/app.log"
SERVER_LOG="$CONFIG_DIR/server.log"
PLAUD_TOKEN="$HOME/.plaud/tokens-mcp.json"
AUTORUN_ENV="$HOME/.plauddb/.env"
LAUNCH_AGENT="$HOME/Library/LaunchAgents/com.note-bridge.sync.plist"

mask_logs() {
  sed -E \
    -e 's/sk-ant-[A-Za-z0-9_-]+/sk-ant-.../g' \
    -e 's/sk-[A-Za-z0-9_-]+/sk-.../g' \
    -e 's/secret_[A-Za-z0-9_-]+/secret_.../g' \
    -e 's/ntn_[A-Za-z0-9_-]+/ntn_.../g'
}

has_command() {
  command -v "$1" >/dev/null 2>&1
}

find_tool() {
  local name="$1"
  local found=""
  found="$(command -v "$name" 2>/dev/null || true)"
  if [ -n "$found" ]; then
    echo "$found"
    return 0
  fi
  for path in "/opt/homebrew/bin/$name" "/usr/local/bin/$name"; do
    if [ -x "$path" ]; then
      echo "$path"
      return 0
    fi
  done
  local nvm_root="$HOME/.nvm/versions/node"
  if [ -d "$nvm_root" ]; then
    found="$(find "$nvm_root" -path "*/bin/$name" -type f -perm -111 2>/dev/null | sort -Vr | head -1 || true)"
    if [ -n "$found" ]; then
      echo "$found"
      return 0
    fi
  fi
  return 1
}

has_env_key() {
  local key="$1"
  if [ -f "$CONFIG_FILE" ] && grep -q "^${key}=" "$CONFIG_FILE"; then
    echo "있음"
  else
    echo "없음"
  fi
}

section() {
  echo
  echo "== $1 =="
}

echo "Note Bridge 진단"
echo "실행 시각: $(date '+%Y-%m-%d %H:%M:%S')"
echo "주의: 이 스크립트는 API 키와 토큰 값을 출력하지 않습니다."

section "앱 파일"
if [ -d "$APP_PATH" ]; then
  echo "앱 위치: $APP_PATH"
else
  echo "앱 위치: 찾지 못함"
  echo "현재 폴더: $SCRIPT_DIR"
fi

section "Mac / 기본 도구"
echo "macOS: $(sw_vers -productVersion 2>/dev/null || echo '확인 실패')"
if has_command python3; then
  echo "python3: $(python3 --version 2>&1)"
else
  echo "python3: 없음"
fi
NODE_PATH="$(find_tool node || true)"
NPX_PATH="$(find_tool npx || true)"
if [ -n "$NODE_PATH" ]; then
  echo "node: $("$NODE_PATH" --version 2>&1)"
  echo "node 경로: $NODE_PATH"
else
  echo "node: 없음"
fi
if [ -n "$NPX_PATH" ]; then
  echo "npx: $("$NPX_PATH" --version 2>&1)"
  echo "npx 경로: $NPX_PATH"
else
  echo "npx: 없음"
fi
if has_command codex; then
  echo "codex: $(codex --version 2>&1 | head -1)"
else
  echo "codex: 없음"
fi
if has_command claude; then
  echo "claude: $(claude --version 2>&1 | head -1)"
else
  echo "claude: 없음"
fi

section "저장된 연결 정보"
echo "앱 설정 파일: $([ -f "$CONFIG_FILE" ] && echo '있음' || echo '없음')"
echo "Notion 토큰: $(has_env_key NOTION_TOKEN)"
echo "Notion DB 주소/ID: $(has_env_key NOTION_DATABASE_ID)"
echo "AI 제공자: $(has_env_key AI_PROVIDER)"
echo "OpenAI API 키: $(has_env_key OPENAI_API_KEY)"
echo "Claude API 키: $(has_env_key ANTHROPIC_API_KEY)"
echo "전사문 나누기 설정: $(has_env_key SEGMENT_GRANULARITY)"
echo "Plaud MCP 토큰: $([ -s "$PLAUD_TOKEN" ] && echo '있음' || echo '없음')"
echo "자동 실행 설정 복사본: $([ -f "$AUTORUN_ENV" ] && echo '있음' || echo '없음')"
echo "LaunchAgent: $([ -f "$LAUNCH_AGENT" ] && echo '있음' || echo '없음')"

section "앱 실행 상태"
if pgrep -f "NoteBridge" >/dev/null 2>&1; then
  echo "앱 프로세스: 실행 중"
else
  echo "앱 프로세스: 실행 전"
fi
if pgrep -f "plauddb_web.py" >/dev/null 2>&1; then
  echo "로컬 서버 프로세스: 실행 중"
else
  echo "로컬 서버 프로세스: 실행 전"
fi
if has_command curl; then
  echo "로컬 서버 응답:"
  curl -sS --max-time 5 "http://127.0.0.1:${APP_PORT}/api/status" 2>&1 | mask_logs || true
else
  echo "curl이 없어 로컬 서버 응답을 확인하지 못했습니다."
fi

section "최근 로그"
if [ -f "$APP_LOG" ]; then
  echo "-- app.log 마지막 30줄 --"
  tail -n 30 "$APP_LOG" | mask_logs
else
  echo "app.log 없음"
fi
if [ -f "$SERVER_LOG" ]; then
  echo "-- server.log 마지막 30줄 --"
  tail -n 30 "$SERVER_LOG" | mask_logs
else
  echo "server.log 없음"
fi

section "다음 조치"
echo "1. Plaud 연결이 안 되면 node/npx 설치와 Plaud MCP 토큰 여부를 확인하세요."
echo "2. Notion이 안 되면 DB에 Integration을 연결했는지 확인하세요."
echo "3. 계속 안 되면 이 결과를 복사하지 말고, 이 폴더 전체를 Codex 또는 Claude Code로 열어 진단을 맡기세요."

if [ -t 0 ]; then
  echo
  read -r -p "Enter 키를 누르면 닫습니다. " _
fi
