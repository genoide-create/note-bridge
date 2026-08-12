#!/usr/bin/env python3
"""Sync new Plaud transcripts into a Notion database.

This prototype intentionally uses only local configuration and stdlib Python:
- Plaud data is fetched through the local Plaud MCP CLI.
- Notion writes go directly through the Notion REST API.
- Semantic splitting can use the configured AI provider when an API key is set.
"""

import argparse
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ROOT = Path(
    os.environ.get("NOTE_BRIDGE_HOME")
    or Path(__file__).resolve().parent
).expanduser()
ENV_PATH = ROOT / ".env"
STATE_PATH = ROOT / ".plaud_sync_state.json"
CATEGORY_RULES_PATH = ROOT / "category_rules.json"
LOG_DIR = ROOT / "logs"
KST = timezone(timedelta(hours=9))


NOTION_PROPS = {
    "title": "제목",
    "category": "분류",
    "summary": "요약",
    "plaud_file_id": "플라우드 파일 ID",
    "original_title": "원본 녹음 제목",
    "segment_index": "구간 번호",
    "start_time": "시작 시간",
    "end_time": "종료 시간",
    "time_range": "시간 범위",
    "duration": "길이(분)",
    "recorded_at": "녹음일시",
    "source": "출처",
    "status": "상태",
    "processed_at": "처리일시",
    "confidence": "분류 확신도",
    "transcript_preview": "전사문 미리보기",
    "key_points": "핵심 내용",
    "action_items": "할 일",
    "people": "관련 인물",
}


DEFAULT_CATEGORY_RULES = [
    {"name": "개인통화", "description": "가족, 연인, 친구와의 사적인 통화. 반말 대화나 일상 안부, 집안 이야기 대부분."},
    {"name": "업무통화", "description": "고객, 거래처, 업체, 계약, 견적, 일정 조율 등 업무 목적의 전화 통화."},
    {"name": "강의", "description": "한 사람이 지식, 개념, 방법론을 설명하는 수업, 세미나, 강연, 교육 내용."},
    {"name": "코칭", "description": "개인 피드백, 강점 진단, 상담, 멘토링, 질문과 답을 통해 성찰을 돕는 대화."},
    {"name": "회의", "description": "여러 사람이 목표, 역할, 의사결정, 진행 상황, 일정, 협업 방식을 논의하는 내용."},
    {"name": "아이디어", "description": "새로운 사업, 콘텐츠, 제품, 글감, 자동화, 기획을 떠올리고 발전시키는 내용."},
    {"name": "업무메모", "description": "할 일, 체크리스트, 업무 기록, 빠른 메모, 나중에 처리할 액션 아이템."},
    {"name": "잡담", "description": "특정 업무나 학습 목적이 약한 가벼운 대화, 이동 중 대화, 식사, 취미, 일상 잡담."},
    {"name": "기타", "description": "무음, 소음, 알아듣기 어려운 내용, 분류하기 애매한 내용."},
]
CATEGORIES = {item["name"] for item in DEFAULT_CATEGORY_RULES}


def default_category_rules() -> List[Dict[str, str]]:
    return [dict(item) for item in DEFAULT_CATEGORY_RULES]


def normalize_category_rules(raw: Any) -> List[Dict[str, str]]:
    rules: List[Dict[str, str]] = []
    seen = set()
    if isinstance(raw, dict):
        raw = raw.get("categories", [])
    if not isinstance(raw, list):
        raw = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = clean_spaces(str(item.get("name", "")))
        description = clean_spaces(str(item.get("description", "")))
        if not name or name in seen:
            continue
        seen.add(name)
        rules.append({"name": name[:40], "description": description[:700]})
    if not any(item["name"] == "기타" for item in rules):
        rules.append({"name": "기타", "description": "무음, 소음, 알아듣기 어려운 내용, 분류하기 애매한 내용."})
    return rules or default_category_rules()


def load_category_rules() -> List[Dict[str, str]]:
    if not CATEGORY_RULES_PATH.exists():
        return default_category_rules()
    try:
        return normalize_category_rules(json.loads(CATEGORY_RULES_PATH.read_text()))
    except Exception:
        return default_category_rules()


def save_category_rules(rules: List[Dict[str, str]], path: Path = CATEGORY_RULES_PATH) -> List[Dict[str, str]]:
    normalized = normalize_category_rules(rules)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"categories": normalized}, ensure_ascii=False, indent=2) + "\n")
    return normalized


def category_names() -> List[str]:
    return [item["name"] for item in load_category_rules()]


def category_descriptions_text() -> str:
    return "\n".join(f"- {item['name']}: {item.get('description', '')}" for item in load_category_rules())


def segmentation_mode(env: Dict[str, str]) -> str:
    mode = clean_spaces(env.get("SEGMENT_GRANULARITY", "balanced")).lower()
    return mode if mode in {"compact", "balanced", "detailed"} else "balanced"


def segmentation_rules(mode: str) -> List[str]:
    if mode == "compact":
        return [
            "사용자 설정은 '적게 나누기'다. 큰 세션 중심으로 묶고 불필요한 세부 분할을 피한다.",
            "7시간 녹음 기준 특별한 이유가 없으면 전체 segment 수는 8~12개 정도를 목표로 한다.",
            "각 segment는 가능하면 최소 20분 이상이 되도록 한다. 짧은 통화/무음/잡담은 예외로 별도 segment가 가능하다.",
        ]
    if mode == "detailed":
        return [
            "사용자 설정은 '자세히 나누기'다. 나중에 찾기 좋도록 주제 전환을 비교적 민감하게 분리한다.",
            "7시간 녹음 기준 특별한 이유가 없으면 전체 segment 수는 25~40개 정도를 목표로 한다.",
            "각 segment는 가능하면 최소 5분 이상이 되도록 하되, 짧은 통화/무음/잡담은 독립 segment로 둘 수 있다.",
        ]
    return [
        "사용자 설정은 '보통'이다. 너무 잘게 쪼개지 말고 큰 논리 단위로 묶는다.",
        "7시간 녹음 기준 특별한 이유가 없으면 전체 segment 수는 12~20개 정도를 목표로 한다.",
        "각 segment는 가능하면 최소 10분 이상이 되도록 하되, 짧은 통화/무음/잡담은 독립 segment로 둘 수 있다.",
    ]


def log(message: str) -> None:
    stamp = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def load_env() -> Dict[str, str]:
    if not ENV_PATH.exists():
        raise SystemExit(f"Missing {ENV_PATH}")
    values: Dict[str, str] = {}
    for raw in ENV_PATH.read_text().splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    required = ["NOTION_TOKEN", "NOTION_DATABASE_ID"]
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise SystemExit(f"Missing {', '.join(missing)} in {ENV_PATH}")
    return values


def load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {"processed_file_ids": []}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {"processed_file_ids": []}


def save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def msfmt(ms: int) -> str:
    seconds = int(round(ms / 1000))
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    return max(0, min(a_end, b_end) - max(a_start, b_start))


def clean_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def split_text(text: str, size: int = 1800) -> List[str]:
    text = text.strip()
    chunks: List[str] = []
    while text:
        if len(text) <= size:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, size)
        if cut < size * 0.5:
            cut = text.rfind(" ", 0, size)
        if cut < size * 0.5:
            cut = size
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    return chunks


def rich_text(text: str, limit: int = 1900) -> List[Dict[str, Any]]:
    text = "" if text is None else str(text)
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    if not text:
        return []
    return [{"type": "text", "text": {"content": text}}]


def paragraph(text: str) -> Dict[str, Any]:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": rich_text(text)}}


def heading(level: int, text: str) -> Dict[str, Any]:
    block_type = f"heading_{level}"
    return {"object": "block", "type": block_type, block_type: {"rich_text": rich_text(text)}}


def bullet(text: str) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": rich_text(text)},
    }


class NotionClient:
    def __init__(self, token: str, database_id: str) -> None:
        self.token = token
        self.database_id = database_id

    def request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            "https://api.notion.com/v1" + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"Notion HTTP {exc.code}: {body[:1200]}") from exc

    def database_title(self) -> str:
        data = self.request("GET", f"/databases/{self.database_id}")
        return "".join(t.get("plain_text", "") for t in data.get("title", [])) or "(untitled)"

    def existing_pages_for_file(self, file_id: str) -> List[Dict[str, Any]]:
        payload = {
            "filter": {"property": NOTION_PROPS["plaud_file_id"], "rich_text": {"equals": file_id}},
            "page_size": 100,
        }
        pages: List[Dict[str, Any]] = []
        while True:
            response = self.request("POST", f"/databases/{self.database_id}/query", payload)
            pages.extend(response.get("results", []))
            if not response.get("has_more") or not response.get("next_cursor"):
                break
            payload["start_cursor"] = response["next_cursor"]
        return [page for page in pages if not page.get("archived") and not page.get("in_trash")]

    def create_segment_page(self, row: "SegmentRow", dry_run: bool = False) -> Optional[str]:
        props = NOTION_PROPS
        key_points_text = "\n".join(f"- {topic}" for topic in row.topics[:20])
        transcript_preview = row.transcript[:1800] + ("…" if len(row.transcript) > 1800 else "")
        payload = {
            "parent": {"database_id": self.database_id},
            "properties": {
                props["title"]: {"title": rich_text(row.title)},
                props["category"]: {"select": {"name": row.category}},
                props["summary"]: {"rich_text": rich_text(row.summary)},
                props["plaud_file_id"]: {"rich_text": rich_text(row.file_id)},
                props["original_title"]: {"rich_text": rich_text(row.original_title)},
                props["segment_index"]: {"number": row.index},
                props["start_time"]: {"rich_text": rich_text(msfmt(row.start_ms))},
                props["end_time"]: {"rich_text": rich_text(msfmt(row.end_ms))},
                props["time_range"]: {"rich_text": rich_text(row.time_range_text)},
                props["duration"]: {"number": row.duration_minutes},
                props["recorded_at"]: {"date": {"start": row.recorded_at}},
                props["source"]: {"select": {"name": "Plaud"}},
                props["status"]: {"select": {"name": "분석완료"}},
                props["processed_at"]: {"date": {"start": row.processed_at}},
                props["confidence"]: {"number": row.confidence},
                props["transcript_preview"]: {"rich_text": rich_text(transcript_preview)},
                props["key_points"]: {"rich_text": rich_text(key_points_text)},
                props["action_items"]: {"rich_text": []},
            },
            "children": [
                heading(2, "Plaud 전사본 분석"),
                paragraph(f"원본: {row.original_title}"),
                paragraph(
                    f"구간: {row.time_range_text} / 분류: {row.category} / 길이: {row.duration_minutes}분"
                ),
                paragraph(f"분류 확신도: {row.confidence}"),
                heading(3, "요약"),
                paragraph(row.summary),
                heading(3, "핵심 내용"),
            ],
        }
        for topic in row.topics[:20]:
            payload["children"].append(bullet(topic))
        if not row.topics:
            payload["children"].append(paragraph("추출된 세부 주제가 없습니다."))

        if dry_run:
            log(f"DRY-RUN create: {row.index:02d} {row.category} {row.duration_minutes}분 {row.title}")
            return None

        page = self.request("POST", "/pages", payload)
        page_id = page["id"]
        blocks = [heading(3, "전사문")]
        for chunk in split_text(row.transcript or "(전사문 없음)"):
            blocks.append(paragraph(chunk))
        for i in range(0, len(blocks), 90):
            self.request("PATCH", f"/blocks/{page_id}/children", {"children": blocks[i : i + 90]})
        return page_id


class PlaudMCP:
    def __init__(self, npx_path: Optional[str] = None) -> None:
        self.npx_path = self._resolve_npx(npx_path or os.environ.get("PLAUD_NPX"))
        if not self.npx_path:
            raise RuntimeError("Could not find npx. Set PLAUD_NPX=/path/to/npx in .env or shell.")
        self.proc: Optional[subprocess.Popen[str]] = None
        self.out_q: "queue.Queue[str]" = queue.Queue()
        self.err_q: "queue.Queue[str]" = queue.Queue()
        self.next_id = 1

    @staticmethod
    def _resolve_npx(preferred: Optional[str]) -> Optional[str]:
        candidates: List[Path] = []
        if preferred:
            candidates.append(Path(preferred).expanduser())
        found = shutil.which("npx")
        if found:
            candidates.append(Path(found))
        candidates.extend(
            [
                Path("/opt/homebrew/bin/npx"),
                Path("/usr/local/bin/npx"),
            ]
        )
        nvm_candidates = list((Path.home() / ".nvm/versions/node").glob("*/bin/npx"))

        def version_key(path: Path) -> Tuple[int, ...]:
            return tuple(int(part) for part in re.findall(r"\d+", path.parent.parent.name))

        candidates.extend(sorted(nvm_candidates, key=version_key, reverse=True))
        seen = set()
        for candidate in candidates:
            expanded = candidate.expanduser()
            key = str(expanded)
            if key in seen:
                continue
            seen.add(key)
            if expanded.exists():
                return str(expanded)
        return None

    def _process_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        npx = Path(self.npx_path).expanduser()
        path_parts = [str(npx.parent)]
        try:
            resolved_parent = str(npx.resolve().parent)
            if resolved_parent not in path_parts:
                path_parts.append(resolved_parent)
        except OSError:
            pass
        existing_path = env.get("PATH", "")
        if existing_path:
            path_parts.append(existing_path)
        env["PATH"] = os.pathsep.join(path_parts)
        return env

    def __enter__(self) -> "PlaudMCP":
        self.proc = subprocess.Popen(
            [self.npx_path, "-y", "@plaud-ai/mcp@latest"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=self._process_env(),
        )
        assert self.proc.stdout and self.proc.stderr
        threading.Thread(target=self._reader, args=(self.proc.stdout, self.out_q), daemon=True).start()
        threading.Thread(target=self._reader, args=(self.proc.stderr, self.err_q), daemon=True).start()
        init = self.send(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "plaud-notion-local-sync", "version": "0.1.0"},
            },
            timeout=60,
        )
        if "error" in init:
            raise RuntimeError(init["error"])
        self.send("notifications/initialized", {}, expect_response=False)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=2)
            except Exception:
                pass

    @staticmethod
    def _reader(stream: Iterable[str], q: "queue.Queue[str]") -> None:
        for line in stream:
            q.put(line)

    def send(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        expect_response: bool = True,
        timeout: int = 180,
    ) -> Optional[Dict[str, Any]]:
        if not self.proc or not self.proc.stdin:
            raise RuntimeError("Plaud MCP process is not running")
        msg: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        msg_id = None
        if expect_response:
            msg_id = self.next_id
            self.next_id += 1
            msg["id"] = msg_id
        if params is not None:
            msg["params"] = params
        try:
            self.proc.stdin.write(json.dumps(msg, separators=(",", ":")) + "\n")
            self.proc.stdin.flush()
        except BrokenPipeError as exc:
            raise RuntimeError(f"Plaud MCP process closed before {method}") from exc
        if not expect_response:
            return None
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                errors: List[str] = []
                while not self.err_q.empty():
                    errors.append(self.err_q.get_nowait().strip())
                detail = f"; stderr={errors[-5:]}" if errors else ""
                raise RuntimeError(f"Plaud MCP exited before {method}{detail}")
            try:
                line = self.out_q.get(timeout=0.2).strip()
            except queue.Empty:
                continue
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("id") == msg_id:
                return obj
        errors: List[str] = []
        while not self.err_q.empty():
            errors.append(self.err_q.get_nowait().strip())
        raise TimeoutError(f"Timeout waiting for {method}; stderr={errors[-5:]}")

    @staticmethod
    def content_text(resp: Dict[str, Any]) -> str:
        return "\n".join(
            c.get("text", "") for c in resp.get("result", {}).get("content", []) if c.get("type") == "text"
        ).strip()

    def call_tool(self, name: str, arguments: Dict[str, Any], timeout: int = 180) -> str:
        resp = self.send("tools/call", {"name": name, "arguments": arguments}, timeout=timeout)
        assert resp is not None
        if "error" in resp:
            raise RuntimeError(resp["error"])
        text = self.content_text(resp)
        if text.startswith("Failed to"):
            raise RuntimeError(text)
        return text

    def list_files(self, args: Dict[str, Any]) -> List[Dict[str, Any]]:
        text = self.call_tool("list_files", args, timeout=120)
        data = json.loads(text)
        return data.get("data", []) if isinstance(data, dict) else data

    def get_file(self, file_id: str) -> Dict[str, Any]:
        text = self.call_tool("get_file", {"file_id": file_id}, timeout=240)
        if not text.lstrip().startswith("{"):
            raise RuntimeError("Plaud returned a non-JSON file response: " + text[:500])
        return json.loads(text)


@dataclass
class OutlinePiece:
    start_ms: int
    end_ms: int
    topic: str
    category: str
    context: str
    confidence: float


@dataclass
class SegmentRow:
    index: int
    file_id: str
    original_title: str
    category: str
    title: str
    summary: str
    start_ms: int
    end_ms: int
    ranges: List[Tuple[int, int]]
    duration_minutes: float
    time_range_text: str
    topics: List[str]
    transcript: str
    recorded_at: str
    processed_at: str
    confidence: float


@dataclass
class AnalysisContext:
    file_id: str
    original_title: str
    recorded_at: str
    processed_at: str
    transaction: List[Dict[str, Any]]
    outline: List[Dict[str, Any]]


def category_from_custom_rules(text: str) -> Optional[Tuple[str, str, float]]:
    lowered = (text or "").lower()
    stopwords = {
        "통화",
        "대화",
        "내용",
        "대부분",
        "속함",
        "분류",
        "업무",
        "일상",
        "목적",
        "사적인",
        "가벼운",
        "어려운",
        "애매한",
    }
    for rule in load_category_rules():
        name = rule["name"]
        hints = [name]
        description = rule.get("description", "")
        for token in re.split(r"[,/·\n\r\t .;:()]+", description):
            token = clean_spaces(token).lower()
            if not token or token in stopwords or len(token) < 2:
                continue
            hints.append(token)
            trimmed = token.rstrip("은는이가을를에와과의도만로")
            if len(trimmed) >= 2 and trimmed not in stopwords:
                hints.append(trimmed)
        for hint in hints:
            if hint and hint.lower() in lowered:
                return name, f"사용자 기준: {name}", 0.84
    return None


def classify_topic(topic: str, sample_text: str = "") -> Tuple[str, str, float]:
    text = f"{topic} {sample_text}".lower()
    custom = category_from_custom_rules(text)
    if custom:
        return custom
    if any(k in text for k in ["아이디어", "구상", "기획안", "브레인스토밍"]):
        return "아이디어", "아이디어", 0.76
    if any(k in text for k in ["할 일", "todo", "업무 메모", "메모", "체크리스트"]):
        return "업무메모", "업무메모", 0.74
    if "통화" in text and any(k in text for k in ["가족", "엄마", "아빠", "아이", "아내", "남편", "집"]):
        return "개인통화", "개인", 0.78
    if "통화" in text and any(k in text for k in ["임대", "부동산", "계약", "상담", "견적", "고객", "거래", "업체"]):
        if "쉐어하우스" in text or "임대" in text or "계약" in text:
            return "업무통화", "쉐어하우스", 0.86
        return "업무통화", "업무", 0.82
    if any(k in text for k in ["야구", "경기", "좌석", "피자", "음식", "유니폼", "상품", "구경", "식사", "교통"]):
        return "잡담", "야구장 일상", 0.80
    if any(k in text for k in ["조별", "공유", "토론", "워크시트", "카드", "자기소개", "프로파일", "업무 스타일", "도움"]):
        return "코칭", "갤럽 강점 워크숍", 0.86
    if any(k in text for k in ["강점", "재능", "검사", "보고서", "테마", "개념", "설명", "q&a", "질의응답", "확률"]):
        return "강의", "갤럽 강점 워크숍", 0.88
    if any(k in text for k in ["회의", "목표", "협업", "갈등", "리더십", "준비", "진행 방식", "점검"]):
        return "회의", "워크숍 준비", 0.80
    if any(k in text for k in ["무음", "소음", "음악", "알 수 없음"]):
        return "기타", "기타", 0.60
    return "기타", "기타", 0.55


def coerce_category(value: str) -> str:
    value = clean_spaces(value)
    return value if value in set(category_names()) else "기타"


def topics_title(category: str, context: str, topics: List[str]) -> str:
    first = topics[0] if topics else context
    if len(topics) == 1:
        return first[:80]
    if context and context not in {"기타", category}:
        return f"{context}: {first} 등"
    return f"{first} 등"


def summarize_segment(category: str, topics: List[str]) -> str:
    if not topics:
        return f"{category}로 분류된 구간입니다."
    topic_text = ", ".join(topics[:6])
    suffix = f" 외 {len(topics) - 6}개 주제" if len(topics) > 6 else ""
    return f"{topic_text}{suffix}를 다룬 {category} 구간입니다."


def parse_source_list(file_data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    source_list = file_data.get("source_list") or []
    transaction_item = next((x for x in source_list if x.get("data_type") == "transaction"), None)
    outline_item = next((x for x in source_list if x.get("data_type") == "outline"), None)
    transaction = json.loads(transaction_item["data_content"]) if transaction_item and transaction_item.get("data_content") else []
    outline = json.loads(outline_item["data_content"]) if outline_item and outline_item.get("data_content") else []
    return transaction, outline


def transcript_for_ranges(transaction: List[Dict[str, Any]], ranges: List[Tuple[int, int]]) -> str:
    lines: List[str] = []
    for item in transaction:
        start = int(item.get("start_time") or 0)
        end = int(item.get("end_time") or 0)
        if any(overlap(a, b, start, end) > 0 for a, b in ranges):
            content = clean_spaces(item.get("content") or "")
            if content:
                lines.append(f"[{msfmt(start)}-{msfmt(end)}] {content}")
    return "\n".join(lines)


def sample_text_for_range(transaction: List[Dict[str, Any]], start: int, end: int, max_chars: int = 800) -> str:
    parts: List[str] = []
    for item in transaction:
        ts = int(item.get("start_time") or 0)
        te = int(item.get("end_time") or 0)
        if overlap(start, end, ts, te) > 0:
            parts.append(clean_spaces(item.get("content") or ""))
        if sum(len(p) for p in parts) >= max_chars:
            break
    return " ".join(parts)[:max_chars]


def build_outline_pieces(transaction: List[Dict[str, Any]], outline: List[Dict[str, Any]], mode: str = "balanced") -> List[OutlinePiece]:
    pieces: List[OutlinePiece] = []
    if outline:
        for item in outline:
            start = int(item.get("start_time") or 0)
            end = int(item.get("end_time") or start)
            topic = clean_spaces(item.get("topic") or "무제 구간")
            sample = sample_text_for_range(transaction, start, end)
            category, context, confidence = classify_topic(topic, sample)
            pieces.append(OutlinePiece(start, end, topic, category, context, confidence))
        return sorted(pieces, key=lambda p: p.start_ms)

    # Fallback when Plaud outline is missing: chunk size follows the user's split preference.
    chunk_minutes = {"compact": 30, "balanced": 20, "detailed": 10}.get(mode, 20)
    chunk_ms = chunk_minutes * 60 * 1000
    if not transaction:
        return []
    start = int(transaction[0].get("start_time") or 0)
    last = int(transaction[-1].get("end_time") or start)
    cursor = start
    while cursor < last:
        end = min(cursor + chunk_ms, last)
        sample = sample_text_for_range(transaction, cursor, end, max_chars=1200)
        category, context, confidence = classify_topic(sample, sample)
        pieces.append(OutlinePiece(cursor, end, context, category, context, confidence))
        cursor = end
    return pieces


def merge_pieces(pieces: List[OutlinePiece], mode: str = "balanced") -> List[List[OutlinePiece]]:
    if not pieces:
        return []
    max_gap_minutes = {"compact": 15, "balanced": 8, "detailed": 4}.get(mode, 8)
    max_gap_ms = max_gap_minutes * 60 * 1000
    groups: List[List[OutlinePiece]] = [[pieces[0]]]
    for piece in pieces[1:]:
        prev = groups[-1][-1]
        same_flow = piece.category == prev.category and piece.context == prev.context
        close = piece.start_ms - prev.end_ms <= max_gap_ms
        if same_flow and close:
            groups[-1].append(piece)
        else:
            groups.append([piece])

    # Bridge merge: lecture A, short interruption B, same lecture C -> A+C plus B.
    i = 0
    bridged: List[List[OutlinePiece]] = []
    while i < len(groups):
        if i + 2 < len(groups):
            a, b, c = groups[i], groups[i + 1], groups[i + 2]
            a_key = (a[0].category, a[0].context)
            c_key = (c[0].category, c[0].context)
            b_duration = sum(x.end_ms - x.start_ms for x in b)
            interrupt = b[0].category in {"개인통화", "업무통화", "잡담", "기타"}
            mergeable_main = a[0].category in {"강의", "코칭", "회의"}
            interrupt_minutes = {"compact": 5, "balanced": 3, "detailed": 2}.get(mode, 3)
            if a_key == c_key and interrupt and mergeable_main and b_duration <= interrupt_minutes * 60 * 1000:
                bridged.append(a + c)
                bridged.append(b)
                i += 3
                continue
        bridged.append(groups[i])
        i += 1
    return bridged


def make_analysis_context(file_data: Dict[str, Any]) -> AnalysisContext:
    file_id = file_data["id"]
    original_title = file_data.get("name") or "Plaud recording"
    recorded_at_raw = file_data.get("start_at") or file_data.get("created_at")
    recorded_at = recorded_at_raw if recorded_at_raw and "+" in recorded_at_raw else f"{recorded_at_raw}+09:00"
    processed_at = datetime.now(KST).isoformat(timespec="seconds")
    transaction, outline = parse_source_list(file_data)
    if not transaction:
        raise RuntimeError("No transcript transaction data found. The Plaud transcript may not be ready yet.")
    return AnalysisContext(
        file_id=file_id,
        original_title=original_title,
        recorded_at=recorded_at,
        processed_at=processed_at,
        transaction=transaction,
        outline=outline,
    )


def rows_from_piece_groups(ctx: AnalysisContext, groups: List[List[OutlinePiece]]) -> List[SegmentRow]:
    rows: List[SegmentRow] = []
    for idx, group in enumerate(sorted(groups, key=lambda g: min(p.start_ms for p in g)), start=1):
        ranges = [(p.start_ms, p.end_ms) for p in sorted(group, key=lambda p: p.start_ms)]
        start_ms = min(a for a, _ in ranges)
        end_ms = max(b for _, b in ranges)
        duration_minutes = round(sum(b - a for a, b in ranges) / 60000, 1)
        time_range_text = ", ".join(f"{msfmt(a)}-{msfmt(b)}" for a, b in ranges)
        topics = [p.topic for p in group]
        category = group[0].category if group else "기타"
        context = group[0].context if group else "기타"
        confidence = round(sum(p.confidence for p in group) / max(1, len(group)), 2)
        transcript = transcript_for_ranges(ctx.transaction, ranges)
        rows.append(
            SegmentRow(
                index=idx,
                file_id=ctx.file_id,
                original_title=ctx.original_title,
                category=coerce_category(category),
                title=topics_title(category, context, topics),
                summary=summarize_segment(category, topics),
                start_ms=start_ms,
                end_ms=end_ms,
                ranges=ranges,
                duration_minutes=duration_minutes,
                time_range_text=time_range_text,
                topics=topics,
                transcript=transcript,
                recorded_at=ctx.recorded_at,
                processed_at=ctx.processed_at,
                confidence=confidence,
            )
        )
    return rows


def build_rows_rules(file_data: Dict[str, Any], env: Optional[Dict[str, str]] = None) -> List[SegmentRow]:
    ctx = make_analysis_context(file_data)
    mode = segmentation_mode(env or {})
    groups = merge_pieces(build_outline_pieces(ctx.transaction, ctx.outline, mode), mode)
    return rows_from_piece_groups(ctx, groups)


def analysis_items_for_llm(ctx: AnalysisContext) -> List[Dict[str, Any]]:
    pieces = build_outline_pieces(ctx.transaction, ctx.outline, getattr(ctx, "segmentation_mode", "balanced"))
    items: List[Dict[str, Any]] = []
    for i, piece in enumerate(pieces, start=1):
        sample = sample_text_for_range(ctx.transaction, piece.start_ms, piece.end_ms, max_chars=700)
        items.append(
            {
                "id": i,
                "start_ms": piece.start_ms,
                "end_ms": piece.end_ms,
                "time": f"{msfmt(piece.start_ms)}-{msfmt(piece.end_ms)}",
                "topic": piece.topic,
                "rule_category": piece.category,
                "rule_context": piece.context,
                "sample": sample,
            }
        )
    return items


def openai_schema() -> Dict[str, Any]:
    segment = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string", "description": "Notion row title in Korean."},
            "category": {"type": "string", "enum": category_names()},
            "summary": {"type": "string", "description": "Concise Korean summary."},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "topic_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Input outline item ids included in this logical segment. May be non-contiguous.",
            },
            "topics": {"type": "array", "items": {"type": "string"}},
            "reason": {"type": "string", "description": "Short Korean reason for split/merge/classification."},
        },
        "required": ["title", "category", "summary", "confidence", "topic_ids", "topics", "reason"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "segments": {"type": "array", "items": segment},
            "notes": {"type": "string"},
        },
        "required": ["segments", "notes"],
    }


class OpenAIAnalyzer:
    def __init__(self, api_key: str, model: str = "gpt-5.4-mini") -> None:
        self.api_key = api_key
        self.model = model or "gpt-5.4-mini"

    def request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"OpenAI HTTP {exc.code}: {body[:1600]}") from exc

    @staticmethod
    def output_text(response: Dict[str, Any]) -> str:
        if isinstance(response.get("output_text"), str):
            return response["output_text"]
        parts: List[str] = []
        for item in response.get("output", []):
            for content in item.get("content", []):
                if isinstance(content.get("text"), str):
                    parts.append(content["text"])
        return "\n".join(parts).strip()

    def analyze(self, ctx: AnalysisContext) -> List[SegmentRow]:
        items = analysis_items_for_llm(ctx)
        if not items:
            return []
        prompt_payload = {
            "file": {
                "id": ctx.file_id,
                "title": ctx.original_title,
                "recorded_at": ctx.recorded_at,
            },
            "categories": category_names(),
            "category_descriptions": load_category_rules(),
            "outline_items": items,
            "rules": [
                "category_descriptions의 설명은 사용자가 직접 적은 분류 기준이다. 카테고리 선택 시 이 설명을 강하게 우선한다.",
                *segmentation_rules(getattr(ctx, "segmentation_mode", "balanced")),
                "연속된 outline item들이 같은 강의, 같은 회의, 같은 코칭 세션의 세부 주제라면 하나의 segment로 병합한다.",
                "같은 강의/회의/코칭 흐름이 짧은 통화나 잡담으로 끊긴 경우, 메인 흐름은 하나의 segment로 병합하고 끼어든 통화/잡담은 별도 segment로 만든다.",
                "개인통화, 업무통화, 잡담도 버리지 말고 각각 분류해 저장한다.",
                "무음, 알아듣기 어려운 내용, 의미 없는 소음은 기타로 분류한다.",
                "topic_ids는 반드시 제공된 outline item id만 사용한다.",
            ],
        }
        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "너는 Plaud 전사본을 Notion DB에 저장하기 위해 논리적 내용 단위로 분할, 병합, "
                        "분류하는 한국어 분석기다. 세부 목차 단위가 아니라 나중에 찾기 좋은 큰 덩어리로 묶어라. "
                        "출력은 반드시 주어진 JSON schema를 따른다."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(prompt_payload, ensure_ascii=False),
                },
            ],
            "reasoning": {"effort": "low"},
            "max_output_tokens": 12000,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "plaud_segments",
                    "strict": True,
                    "schema": openai_schema(),
                }
            },
        }
        response = self.request(payload)
        text = self.output_text(response)
        if not text:
            raise RuntimeError("OpenAI returned no text output")
        plan = json.loads(text)
        by_id = {item["id"]: item for item in items}
        rows: List[SegmentRow] = []
        for idx, segment in enumerate(plan.get("segments", []), start=1):
            topic_ids = [int(v) for v in segment.get("topic_ids", []) if int(v) in by_id]
            if not topic_ids:
                continue
            ranges = [(by_id[i]["start_ms"], by_id[i]["end_ms"]) for i in topic_ids]
            start_ms = min(a for a, _ in ranges)
            end_ms = max(b for _, b in ranges)
            duration_minutes = round(sum(b - a for a, b in ranges) / 60000, 1)
            time_range_text = ", ".join(f"{msfmt(a)}-{msfmt(b)}" for a, b in ranges)
            transcript = transcript_for_ranges(ctx.transaction, ranges)
            topics = [clean_spaces(t) for t in segment.get("topics", []) if clean_spaces(t)]
            if not topics:
                topics = [by_id[i]["topic"] for i in topic_ids]
            rows.append(
                SegmentRow(
                    index=idx,
                    file_id=ctx.file_id,
                    original_title=ctx.original_title,
                    category=coerce_category(segment.get("category", "기타")),
                    title=clean_spaces(segment.get("title") or topics_title("기타", "기타", topics))[:120],
                    summary=clean_spaces(segment.get("summary") or summarize_segment("기타", topics)),
                    start_ms=start_ms,
                    end_ms=end_ms,
                    ranges=ranges,
                    duration_minutes=duration_minutes,
                    time_range_text=time_range_text,
                    topics=topics,
                    transcript=transcript,
                    recorded_at=ctx.recorded_at,
                    processed_at=ctx.processed_at,
                    confidence=round(float(segment.get("confidence", 0.75)), 2),
                )
            )
        return rows


def remove_schema_constraints(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: remove_schema_constraints(child)
            for key, child in value.items()
            if key not in {"minimum", "maximum", "minLength", "maxLength", "pattern", "format"}
        }
    if isinstance(value, list):
        return [remove_schema_constraints(item) for item in value]
    return value


def anthropic_schema() -> Dict[str, Any]:
    return remove_schema_constraints(openai_schema())


class AnthropicAnalyzer:
    def __init__(self, api_key: str, model: str = "claude-opus-4-5") -> None:
        self.api_key = api_key
        self.model = model or "claude-opus-4-5"

    def request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"Anthropic HTTP {exc.code}: {body[:1600]}") from exc

    @staticmethod
    def output_text(response: Dict[str, Any]) -> str:
        parts: List[str] = []
        for item in response.get("content", []):
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts).strip()

    def analyze(self, ctx: AnalysisContext) -> List[SegmentRow]:
        items = analysis_items_for_llm(ctx)
        if not items:
            return []
        prompt_payload = {
            "file": {
                "id": ctx.file_id,
                "title": ctx.original_title,
                "recorded_at": ctx.recorded_at,
            },
            "categories": category_names(),
            "category_descriptions": load_category_rules(),
            "outline_items": items,
            "rules": [
                "category_descriptions의 설명은 사용자가 직접 적은 분류 기준이다. 카테고리 선택 시 이 설명을 강하게 우선한다.",
                *segmentation_rules(getattr(ctx, "segmentation_mode", "balanced")),
                "연속된 outline item들이 같은 강의, 같은 회의, 같은 코칭 세션의 세부 주제라면 하나의 segment로 병합한다.",
                "같은 강의/회의/코칭 흐름이 짧은 통화나 잡담으로 끊긴 경우, 메인 흐름은 하나의 segment로 병합하고 끼어든 통화/잡담은 별도 segment로 만든다.",
                "개인통화, 업무통화, 잡담도 버리지 말고 각각 분류해 저장한다.",
                "무음, 알아듣기 어려운 내용, 의미 없는 소음은 기타로 분류한다.",
                "topic_ids는 반드시 제공된 outline item id만 사용한다.",
            ],
        }
        payload = {
            "model": self.model,
            "max_tokens": 12000,
            "system": (
                "너는 Plaud 전사본을 Notion DB에 저장하기 위해 논리적 내용 단위로 분할, 병합, "
                "분류하는 한국어 분석기다. 세부 목차 단위가 아니라 나중에 찾기 좋은 큰 덩어리로 묶어라. "
                "출력은 반드시 주어진 JSON schema를 따른다."
            ),
            "messages": [{"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False)}],
            "output_config": {"format": {"type": "json_schema", "schema": anthropic_schema()}},
        }
        response = self.request(payload)
        text = self.output_text(response)
        if not text:
            raise RuntimeError("Anthropic returned no text output")
        plan = json.loads(text)
        by_id = {item["id"]: item for item in items}
        rows: List[SegmentRow] = []
        for idx, segment in enumerate(plan.get("segments", []), start=1):
            topic_ids = [int(v) for v in segment.get("topic_ids", []) if int(v) in by_id]
            if not topic_ids:
                continue
            ranges = [(by_id[i]["start_ms"], by_id[i]["end_ms"]) for i in topic_ids]
            start_ms = min(a for a, _ in ranges)
            end_ms = max(b for _, b in ranges)
            duration_minutes = round(sum(b - a for a, b in ranges) / 60000, 1)
            time_range_text = ", ".join(f"{msfmt(a)}-{msfmt(b)}" for a, b in ranges)
            transcript = transcript_for_ranges(ctx.transaction, ranges)
            topics = [clean_spaces(t) for t in segment.get("topics", []) if clean_spaces(t)]
            if not topics:
                topics = [by_id[i]["topic"] for i in topic_ids]
            rows.append(
                SegmentRow(
                    index=idx,
                    file_id=ctx.file_id,
                    original_title=ctx.original_title,
                    category=coerce_category(segment.get("category", "기타")),
                    title=clean_spaces(segment.get("title") or topics_title("기타", "기타", topics))[:120],
                    summary=clean_spaces(segment.get("summary") or summarize_segment("기타", topics)),
                    start_ms=start_ms,
                    end_ms=end_ms,
                    ranges=ranges,
                    duration_minutes=duration_minutes,
                    time_range_text=time_range_text,
                    topics=topics,
                    transcript=transcript,
                    recorded_at=ctx.recorded_at,
                    processed_at=ctx.processed_at,
                    confidence=round(float(segment.get("confidence", 0.75)), 2),
                )
            )
        return rows


def configured_ai(env: Dict[str, str]) -> Tuple[str, str, str]:
    provider = clean_spaces(env.get("AI_PROVIDER", "")).lower()
    if provider in {"claude", "anthropic"}:
        return "anthropic", env.get("ANTHROPIC_API_KEY", ""), env.get("ANTHROPIC_MODEL", "claude-opus-4-5")
    if provider == "openai":
        return "openai", env.get("OPENAI_API_KEY", ""), env.get("OPENAI_MODEL", "gpt-5.4-mini")
    if env.get("ANTHROPIC_API_KEY"):
        return "anthropic", env.get("ANTHROPIC_API_KEY", ""), env.get("ANTHROPIC_MODEL", "claude-opus-4-5")
    if env.get("OPENAI_API_KEY"):
        return "openai", env.get("OPENAI_API_KEY", ""), env.get("OPENAI_MODEL", "gpt-5.4-mini")
    return "", "", ""


def build_rows(file_data: Dict[str, Any], env: Dict[str, str], analysis_mode: str = "auto") -> List[SegmentRow]:
    ctx = make_analysis_context(file_data)
    mode = analysis_mode
    split_mode = segmentation_mode(env)
    setattr(ctx, "segmentation_mode", split_mode)
    provider, api_key, model = configured_ai(env)
    if mode == "rules" or not api_key:
        if mode == "llm" and not api_key:
            raise RuntimeError("An AI API key is required for --analysis llm")
        log("ANALYSIS rules")
        return rows_from_piece_groups(ctx, merge_pieces(build_outline_pieces(ctx.transaction, ctx.outline, split_mode), split_mode))
    try:
        log(f"ANALYSIS llm provider={provider} model={model}")
        if provider == "anthropic":
            rows = AnthropicAnalyzer(api_key, model).analyze(ctx)
        else:
            rows = OpenAIAnalyzer(api_key, model).analyze(ctx)
        if rows:
            return rows
        raise RuntimeError("AI analyzer produced zero rows")
    except Exception as exc:
        if mode == "llm":
            raise
        log(f"ANALYSIS llm failed; falling back to rules | {exc}")
        return rows_from_piece_groups(ctx, merge_pieces(build_outline_pieces(ctx.transaction, ctx.outline, split_mode), split_mode))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Plaud transcripts into Notion.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--today", action="store_true", help="Process today's Plaud recordings.")
    source.add_argument("--date-from", help="Start date inclusive, YYYY-MM-DD.")
    parser.add_argument("--date-to", help="End date inclusive, YYYY-MM-DD.")
    source.add_argument("--recent", type=int, help="Process N most recent recordings.")
    source.add_argument("--query", help="Process recordings whose title contains this query.")
    source.add_argument("--file-id", action="append", help="Process one specific Plaud file ID. Can be repeated.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum files to inspect/process.")
    parser.add_argument("--dry-run", action="store_true", help="Analyze without writing to Notion.")
    parser.add_argument(
        "--analysis",
        choices=["auto", "llm", "rules"],
        default="auto",
        help="auto uses the configured AI API key when set, otherwise rules.",
    )
    return parser.parse_args()


def plaud_list_args(args: argparse.Namespace) -> Dict[str, Any]:
    if args.today:
        today = datetime.now(KST).strftime("%Y-%m-%d")
        return {"date_from": today, "date_to": today, "page_size": max(10, args.limit)}
    if args.date_from:
        return {"date_from": args.date_from, "date_to": args.date_to or args.date_from, "page_size": max(10, args.limit)}
    if args.query:
        return {"query": args.query, "page_size": max(10, args.limit)}
    if args.recent:
        return {"page": 1, "page_size": max(10, args.recent)}
    today = datetime.now(KST).strftime("%Y-%m-%d")
    return {"date_from": today, "date_to": today, "page_size": max(10, args.limit)}


def main() -> int:
    LOG_DIR.mkdir(exist_ok=True)
    args = parse_args()
    env = load_env()
    notion = NotionClient(env["NOTION_TOKEN"], env["NOTION_DATABASE_ID"])
    state = load_state()
    processed = set(state.get("processed_file_ids", []))

    log(f"Notion DB: {notion.database_title()}")
    created_files: List[str] = []
    skipped = 0

    with PlaudMCP(env.get("PLAUD_NPX")) as plaud:
        if args.file_id:
            files = [{"id": file_id, "name": file_id} for file_id in args.file_id]
        else:
            files = plaud.list_files(plaud_list_args(args))
            if args.recent:
                files = files[: args.recent]
            files = files[: args.limit]
        log(f"Plaud files to inspect: {len(files)}")
        for item in files:
            file_id = item.get("id")
            name = item.get("name") or "(untitled)"
            if not file_id:
                continue
            if notion.existing_pages_for_file(file_id):
                log(f"SKIP Notion already has rows: {name}")
                processed.add(file_id)
                skipped += 1
                continue
            if file_id in processed and not args.dry_run:
                log(f"REPROCESS state had file, but Notion has no rows: {name}")

            log(f"FETCH {name}")
            try:
                file_data = plaud.get_file(file_id)
                name = file_data.get("name") or name
                rows = build_rows(file_data, env, args.analysis)
            except Exception as exc:
                log(f"SKIP not ready or failed: {name} | {exc}")
                skipped += 1
                continue
            if not rows:
                log(f"SKIP no analyzable rows: {name}")
                skipped += 1
                continue

            log(f"ANALYZED {name}: {len(rows)} rows")
            for row in rows:
                notion.create_segment_page(row, dry_run=args.dry_run)
            if not args.dry_run:
                processed.add(file_id)
                created_files.append(file_id)
                log(f"CREATED {len(rows)} Notion rows for {name}")

    if not args.dry_run:
        state["processed_file_ids"] = sorted(processed)
        state["last_run_at"] = datetime.now(KST).isoformat(timespec="seconds")
        save_state(state)
    log(f"DONE created_files={len(created_files)} skipped={skipped} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
