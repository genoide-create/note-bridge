# Note Bridge

Plaud 전사록을 사용자의 기준에 맞게 분류하고, 내용별로 나누어 Notion 데이터베이스에 저장하는 로컬 자동화 앱입니다.

> 녹음은 Plaud가 하고, 정리는 Note Bridge가 하고, 축적은 Notion이 맡습니다.

## 프로젝트 배경

Plaud를 사용하면서 가장 크게 느낀 문제는 녹음 자체보다 녹음 이후의 정리였습니다.

하루 종일 녹음하면 개인통화, 회의, 강의, 아이디어, 업무메모, 잡담이 하나의 긴 전사본 안에 뒤섞입니다. 이 전사본을 직접 읽고, 의미 단위로 나누고, 분류하고, Notion에 옮기는 과정은 반복적이고 시간이 많이 걸렸습니다.

그래서 “그냥 하루 종일 녹음하고, AI가 알아서 분류하게 해보자”는 생각에서 Note Bridge를 만들었습니다.

## 해결하고자 한 문제

긴 녹음 파일 하나를 그대로 저장하는 것이 아니라, 실제로 다시 꺼내 쓸 수 있는 기록으로 바꾸는 것이 목표였습니다.

예를 들어 2시간 녹음 안에 1시간 개인통화, 40분 회의, 20분 무음이 있다면 각각 다른 데이터로 분리되어야 합니다. 각 데이터는 제목, 분류, 녹음일시, 길이, 요약, 원문, 상태를 가진 Notion DB 항목으로 저장됩니다.

## 주요 기능

- Plaud MCP를 통해 최근 녹음 노트와 전사본을 가져옵니다.
- 아직 Notion에 등록되지 않은 전사본만 자동으로 처리합니다.
- 사용자가 선택한 Plaud 노트만 따로 전송할 수 있습니다.
- 전사문을 개인통화, 업무통화, 강의, 코칭, 회의, 아이디어, 업무메모, 잡담, 기타 등으로 분류합니다.
- 긴 전사문을 내용 단위로 분할하고, 같은 주제의 구간은 병합합니다.
- OpenAI 또는 Claude API 키가 있으면 AI 기반 분석을 사용하고, 없으면 규칙 기반 분석으로 동작합니다.
- Notion DB 속성을 자동으로 세팅합니다.
- 분류 카테고리와 설명을 사용자가 직접 수정할 수 있습니다.
- 자동 실행 시간을 설정해 정해진 시간에 동기화할 수 있습니다.
- 지인이 설치하다가 막혔을 때를 대비해 진단 스크립트와 AI 지원 프롬프트를 포함했습니다.

## 작동 흐름

```text
Plaud 녹음
  -> Plaud MCP로 전사본 가져오기
  -> 전사문 분류, 분할, 병합
  -> 요약과 메타데이터 생성
  -> Notion API로 데이터베이스에 저장
```

## 사용 기술

- Python
- Swift / WebKit 기반 macOS 로컬 앱 래퍼
- Plaud MCP
- Notion API
- OpenAI API 또는 Claude API 선택 연동
- macOS launchd 자동 실행
- Codex / Claude Code를 활용한 AI 보조 개발

## 화면 구성

아래 이미지는 포트폴리오/소개용으로 추가할 예정입니다.

1. `docs/images/01-problem.png`  
   Plaud 녹음이 쌓이지만 정리가 어려운 문제 상황

2. `docs/images/02-goal.png`  
   긴 녹음이 내용별 데이터로 나뉘어 Notion DB에 들어가는 목표 구조

3. `docs/images/03-development.png`  
   AI와 함께 기능을 설계하고 테스트한 개발 과정

4. `docs/images/04-settings.png`  
   Plaud, Notion, AI API, 카테고리, DB 속성 세팅 화면

5. `docs/images/05-main.png`  
   미전송 전사본 전체 전송, 선택 전송, 최근 Plaud 노트 목록 화면

6. `docs/images/06-notion-result.png`  
   Notion DB에 분류/요약되어 저장된 결과 화면

## 실행 방법

macOS 기준입니다.

```bash
./build_app.sh
open "Note Bridge.app"
```

개발용 브라우저 UI로 실행하려면:

```bash
./launch_gui.sh
```

브라우저에서 `http://127.0.0.1:8765`가 열립니다.

## 처음 세팅 순서

1. Plaud 연결
2. Notion API 토큰 저장
3. AI API 키 저장 (선택)
4. Notion DB 전체 주소 등록
5. Notion DB에 Integration 허용
6. 카테고리 세팅
7. DB 속성 세팅
8. 준비 상태 점검

## 로컬 저장 위치

API 키와 인증 토큰은 앱 파일 안에 저장하지 않고 사용자 Mac에 저장합니다.

- 앱 설정: `~/Library/Application Support/Note Bridge/.env`
- Plaud MCP 인증 토큰: `~/.plaud/tokens-mcp.json`
- 자동 실행 설정 복사본: `~/.plauddb/.env`
- 앱 로그: `~/Library/Application Support/Note Bridge/server.log`

## 환경 변수 예시

`.env.example`을 참고해 직접 설정할 수 있습니다.

```bash
cp .env.example .env
```

앱에서 세팅하면 직접 `.env`를 만들 필요는 없습니다.

## 포트폴리오 포인트

이 프로젝트는 단순한 API 연결 예제가 아니라, 실제 개인 사용 문제를 발견하고 AI 도구로 제품화한 경험입니다.

- 녹음 습관의 문제를 데이터 정리 문제로 재정의했습니다.
- Plaud, Notion, AI API를 하나의 로컬 워크플로우로 연결했습니다.
- 긴 전사문을 내용 단위로 분류/분할/병합하는 기준을 직접 설계했습니다.
- 지인 배포를 고려해 설치 안내, 진단 스크립트, AI 지원 프롬프트까지 포함했습니다.
- AI와 대화하며 요구사항 정의, 기능 구현, 테스트, 배포 패키징까지 진행했습니다.

## 주의

- 이 프로젝트는 Plaud 공식 앱이 아닙니다.
- 사용자는 본인의 Plaud 계정, Notion API 토큰, 선택 사항인 AI API 키를 직접 연결해야 합니다.
- `.env`, API 키, Plaud 토큰, Notion 토큰, 로그 파일은 GitHub에 올리지 않습니다.
- 현재 앱 래퍼와 자동 실행은 macOS 기준입니다. 핵심 Python 로직은 Windows용으로도 이식할 수 있습니다.

## 소개 페이지

- Notion 소개 페이지: https://ptis.notion.site/Note-Bridge-3b130b2bcddd802db391c938a733676f
