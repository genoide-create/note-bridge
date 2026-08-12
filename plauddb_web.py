#!/usr/bin/env python3
"""Local browser UI for Note Bridge.

Runs only on 127.0.0.1 and uses the existing sync engine.
"""

import json
import os
import plistlib
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.error
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingTCPServer
from typing import Any, Dict, List, Tuple

import sync_plaud_to_notion as sync


ROOT = Path(__file__).resolve().parent
RUNTIME = Path.home() / ".plauddb"
PLIST_PATH = ROOT / "com.note-bridge.sync.plist"
RUNTIME_PLIST = Path.home() / "Library/LaunchAgents/com.note-bridge.sync.plist"
PORT = int(os.environ.get("PLAUDDB_PORT", "8765"))
PERSONAL_MODE = os.environ.get("NOTE_BRIDGE_PERSONAL_MODE") == "1"


HTML = r"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Note Bridge</title>
  <style>
    :root {
      color-scheme: light;
      --deep: #2D4A3E;
      --mustard: #B8923A;
      --cream: #FBFAF7;
      --cream-soft: #F4F0E8;
      --green-soft: #E8EDE9;
      --mustard-soft: #F4ECD9;
      --line: #E5E2DA;
      --ink: #1A1A1A;
      --gray: #6B6B6B;
      --panel: #FFFFFF;
      --ok: #2D4A3E;
      --warn: #B8923A;
      --bad: #b42318;
      --shadow: 0 18px 45px rgba(45, 74, 62, .08);
      --radius: 8px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Noto Sans KR", "Segoe UI", sans-serif;
      background: var(--cream);
      color: var(--ink);
      min-width: 960px;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 28px;
      padding: 30px 36px 24px;
      background: var(--deep);
      color: var(--cream);
    }
    .brand {
      display: flex;
      flex-direction: column;
      gap: 8px;
      min-width: 0;
    }
    .eyebrow {
      display: inline-flex;
      align-items: center;
      gap: 9px;
      color: rgba(251, 250, 247, .74);
      font-size: 12px;
      line-height: 1;
      text-transform: uppercase;
    }
    .eyebrow::before {
      content: "";
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--cream);
      opacity: .9;
    }
    h1 {
      margin: 0;
      font-size: 34px;
      line-height: 1.05;
      font-weight: 760;
      letter-spacing: 0;
    }
    .header-status {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 92px;
      min-height: 34px;
      padding: 8px 14px;
      border: 1px solid rgba(251, 250, 247, .24);
      border-radius: 999px;
      background: rgba(251, 250, 247, .1);
      color: var(--cream);
      font-size: 13px;
      font-weight: 650;
      white-space: nowrap;
    }
    main {
      padding: 22px 36px 34px;
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 14px;
      margin-bottom: 14px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 16px;
      box-shadow: var(--shadow);
    }
    .metric {
      min-height: 98px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .label {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--gray);
      font-size: 11px;
      font-weight: 700;
      margin-bottom: 10px;
      text-transform: uppercase;
    }
    .label::before {
      content: "";
      width: 22px;
      height: 2px;
      background: var(--mustard);
    }
    .value {
      color: var(--deep);
      font-size: 18px;
      font-weight: 760;
      line-height: 1.35;
      word-break: break-word;
    }
    .toolbar {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      padding: 14px 0;
      border-bottom: 1px solid var(--line);
    }
    .toolbar:first-child { padding-top: 0; }
    .toolbar:last-child {
      padding-bottom: 0;
      border-bottom: 0;
    }
    .toolbar label {
      color: var(--gray);
      font-size: 13px;
      font-weight: 650;
    }
    .spacer { flex: 1; min-width: 24px; }
    .section-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      margin: 22px 0 12px;
    }
    h2 {
      margin: 0;
      color: var(--ink);
      font-size: 22px;
      line-height: 1.2;
      font-weight: 760;
      letter-spacing: 0;
    }
    .caption {
      color: var(--gray);
      font-size: 12px;
      line-height: 1.5;
    }
    .settings-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 14px;
    }
    .settings-head h2 {
      font-size: 22px;
    }
    .settings-body {
      display: none;
      border-top: 1px solid var(--line);
      padding-top: 4px;
    }
    .settings-panel.open .settings-body {
      display: block;
    }
    body.personal-mode .settings-panel {
      display: none;
    }
    .settings-toggle {
      min-width: 104px;
    }
    .settings-group {
      padding: 14px 0;
      border-bottom: 1px solid var(--line);
    }
    .settings-group:last-child {
      border-bottom: 0;
      padding-bottom: 0;
    }
    .group-title {
      margin: 0 0 10px;
      color: var(--deep);
      font-size: 14px;
      font-weight: 760;
    }
    .step-title {
      display: flex;
      align-items: center;
      gap: 9px;
      margin: 0 0 10px;
      color: var(--deep);
      font-size: 14px;
      font-weight: 760;
    }
    .step-number {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 26px;
      height: 26px;
      border-radius: 999px;
      background: var(--deep);
      color: var(--cream);
      font-size: 12px;
      font-weight: 760;
      flex: 0 0 auto;
    }
    .hint {
      color: var(--gray);
      font-size: 12px;
      line-height: 1.55;
      margin: 6px 0 0;
    }
    button {
      appearance: none;
      border: 1px solid var(--line);
      border-radius: 7px;
      min-height: 38px;
      padding: 9px 14px;
      background: var(--panel);
      color: var(--ink);
      font-size: 14px;
      font-weight: 650;
      cursor: pointer;
      transition: background .15s ease, border-color .15s ease, color .15s ease, transform .15s ease;
    }
    button.primary {
      background: var(--deep);
      border-color: var(--deep);
      color: var(--cream);
      font-weight: 650;
    }
    button.secondary {
      background: var(--mustard);
      border-color: var(--mustard);
      color: #fff;
    }
    button.ghost {
      background: transparent;
      border-color: var(--ink);
    }
    button:hover:not(:disabled) {
      transform: translateY(-1px);
      border-color: var(--deep);
    }
    button.primary:hover:not(:disabled) { background: #243D34; }
    button.secondary:hover:not(:disabled) { background: #A8822C; }
    button:disabled { opacity: .55; cursor: wait; }
    input, select, textarea {
      border: 1px solid var(--line);
      border-radius: 7px;
      min-height: 38px;
      padding: 8px 10px;
      font-size: 14px;
      background: var(--cream);
      color: var(--ink);
      outline: 0;
      font-family: inherit;
    }
    input:focus, select:focus, textarea:focus {
      border-color: var(--deep);
      box-shadow: 0 0 0 3px rgba(45, 74, 62, .1);
    }
    input[type="password"] { width: 260px; }
    input[type="checkbox"] {
      width: 16px;
      height: 16px;
      min-height: 16px;
      accent-color: var(--deep);
      vertical-align: -3px;
    }
    .tiny-input { width: 72px; text-align: center; }
    .db-input { min-width: 380px; flex: 1; }
    .switch-control {
      display: inline-flex;
      align-items: center;
      gap: 9px;
      color: var(--gray);
      font-size: 13px;
      font-weight: 650;
      white-space: nowrap;
    }
    .switch {
      position: relative;
      display: inline-flex;
      width: 52px;
      height: 30px;
      flex: 0 0 auto;
      cursor: pointer;
    }
    .switch input {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      min-height: 0;
      margin: 0;
      opacity: 0;
      cursor: pointer;
    }
    .switch-track {
      width: 100%;
      height: 100%;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--green-soft);
      transition: background .16s ease, border-color .16s ease;
    }
    .switch-track::after {
      content: "";
      position: absolute;
      top: 4px;
      left: 4px;
      width: 22px;
      height: 22px;
      border-radius: 50%;
      background: var(--panel);
      box-shadow: 0 3px 9px rgba(26, 26, 26, .16);
      transition: transform .16s ease;
    }
    .switch input:checked + .switch-track {
      border-color: var(--deep);
      background: var(--deep);
    }
    .switch input:checked + .switch-track::after {
      transform: translateX(22px);
    }
    .select-all {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: var(--gray);
      font-size: 12px;
      font-weight: 760;
      white-space: nowrap;
      cursor: pointer;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      overflow: hidden;
      box-shadow: var(--shadow);
    }
    th, td {
      padding: 13px 14px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      text-align: left;
      font-size: 14px;
    }
    th {
      color: var(--gray);
      font-size: 12px;
      font-weight: 760;
      background: var(--cream-soft);
      text-transform: uppercase;
    }
    tr:last-child td { border-bottom: 0; }
    tbody tr:hover { background: #FEFDF9; }
    .note-title {
      color: var(--ink);
      font-weight: 650;
      line-height: 1.45;
    }
    .file-id {
      color: var(--gray);
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      word-break: break-all;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 96px;
      min-height: 28px;
      padding: 5px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 760;
      white-space: nowrap;
    }
    .status-pill.ok {
      background: var(--green-soft);
      color: var(--deep);
    }
    .status-pill.warn {
      background: var(--mustard-soft);
      color: #7F631F;
    }
    .status-ok { color: var(--ok); font-weight: 650; }
    .status-warn { color: var(--warn); font-weight: 650; }
    .status-bad { color: var(--bad); font-weight: 650; }
    pre {
      margin: 16px 0 0;
      white-space: pre-wrap;
      background: var(--deep);
      color: var(--cream);
      padding: 14px;
      border-radius: var(--radius);
      max-height: 230px;
      overflow: auto;
      font-size: 12px;
      line-height: 1.45;
      box-shadow: var(--shadow);
    }
    .empty-row {
      color: var(--gray);
      text-align: center;
      padding: 28px 14px;
    }
    .load-more-row {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      margin: 14px 0 0;
    }
    .load-more-row button {
      min-width: 160px;
    }
    #loadMoreBtn { display: none; }
    .note-count {
      color: var(--gray);
      font-size: 12px;
    }
    .connection-row {
      display: grid;
      grid-template-columns: minmax(120px, 160px) 1fr auto;
      gap: 10px;
      align-items: center;
    }
    .connection-state {
      min-height: 38px;
      display: inline-flex;
      align-items: center;
      color: var(--deep);
      font-size: 13px;
      font-weight: 650;
      line-height: 1.4;
    }
    .readiness-list {
      display: grid;
      gap: 8px;
      margin-top: 10px;
    }
    .readiness-item {
      display: grid;
      grid-template-columns: 120px 1fr;
      gap: 10px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: var(--cream);
      font-size: 13px;
      line-height: 1.45;
    }
    .readiness-item strong {
      color: var(--deep);
    }
    .readiness-item.ready strong { color: var(--ok); }
    .readiness-item.warn strong { color: #7F631F; }
    .readiness-item.bad strong { color: var(--bad); }
    .category-editor {
      display: grid;
      gap: 10px;
      margin-top: 4px;
    }
    .category-row {
      display: grid;
      grid-template-columns: minmax(120px, 180px) 1fr auto;
      gap: 10px;
      align-items: start;
    }
    .category-row textarea {
      min-height: 64px;
      resize: vertical;
      line-height: 1.45;
    }
    .category-row button {
      min-width: 72px;
    }
    @media (max-width: 900px) {
      body { min-width: 0; }
      header { padding: 24px 20px 20px; }
      main { padding: 18px 20px 28px; }
      .grid { grid-template-columns: 1fr; }
      .db-input { min-width: 100%; }
      .connection-row { grid-template-columns: 1fr; }
      .category-row { grid-template-columns: 1fr; }
      table { min-width: 860px; }
      .table-wrap { overflow-x: auto; }
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="eyebrow">NOTE BRIDGE · LOCAL APP</div>
      <h1>Note Bridge</h1>
    </div>
    <div class="header-status" id="busy">준비됨</div>
  </header>
  <main>
    <section class="grid">
      <div class="panel metric"><div class="label">Notion</div><div class="value" id="notion">확인 중...</div></div>
      <div class="panel metric"><div class="label">API 모델</div><div class="value" id="openai">확인 중...</div></div>
      <div class="panel metric"><div class="label">자동 실행</div><div class="value" id="schedule">확인 중...</div></div>
    </section>

    <section class="panel">
      <div class="toolbar">
        <button class="primary" id="syncBtn" onclick="syncNow()">미전송 전사본 전부 전송</button>
        <button class="secondary" id="selectedBtn" onclick="syncSelected()">선택한 전사본 전송</button>
        <button class="ghost" id="refreshBtn" onclick="loadNotes()">목록 새로고침</button>
      </div>
    </section>

    <section class="panel settings-panel" id="settingsPanel">
      <div class="settings-head">
        <div>
          <h2>세팅</h2>
          <div class="caption">Plaud, AI API, Notion, 분류 기준, 자동 실행을 설정합니다.</div>
        </div>
        <button class="settings-toggle ghost" id="settingsToggle" onclick="toggleSettings()">펼치기</button>
      </div>
      <div class="settings-body">
        <div class="settings-group">
          <p class="step-title"><span class="step-number">1</span><span>Plaud 연결</span></p>
          <div class="connection-row">
            <span class="connection-state" id="plaudStatus">플라우드 연결 전</span>
            <div class="hint">Plaud 연결하기를 누르면 로그인 창이 열립니다. 연결이 성공하면 최근 노트 10개를 확인할 수 있습니다.</div>
            <button id="plaudConnectBtn" onclick="checkPlaud()">Plaud 연결하기</button>
          </div>
        </div>

        <div class="settings-group">
          <p class="step-title"><span class="step-number">2</span><span>Notion API 연결</span></p>
          <div class="toolbar">
            <label>Notion API 토큰</label>
            <input id="notionToken" type="password" placeholder="secret_... 또는 ntn_..." />
            <button onclick="saveNotionToken()">토큰 저장</button>
            <button id="notionTokenStatus" disabled>Notion 토큰 미등록</button>
          </div>
          <p class="hint">Notion의 `설정` → `연결` 또는 `내 통합`에서 새 Internal Integration을 만들고, 발급된 Internal Integration Secret을 붙여넣습니다. 이 토큰은 이 Mac 안에만 저장됩니다.</p>
        </div>

        <div class="settings-group">
          <p class="step-title"><span class="step-number">3</span><span>AI API 연결 (선택)</span></p>
          <div class="toolbar">
            <label id="apiKeyLabel">AI API 키</label>
            <input id="apiKey" type="password" placeholder="OpenAI sk-... 또는 Claude sk-ant-..." />
            <button onclick="saveKey()">키 저장</button>
            <button id="apiStatus" disabled>API 미등록</button>
          </div>
          <p class="hint">API 키를 넣으면 OpenAI 또는 Claude 키인지 자동으로 확인하고 기본 모델을 설정합니다. API 키가 없어도 규칙 기반 분류로 기본 동작은 가능합니다.</p>
          <div class="toolbar">
            <label>전사문 나누기</label>
            <select id="segmentGranularity">
              <option value="compact">적게</option>
              <option value="balanced">보통</option>
              <option value="detailed">자세히</option>
            </select>
            <button onclick="saveAnalysisSettings()">저장</button>
          </div>
          <p class="hint">2~8시간 녹음 기준 `적게`는 큰 흐름 중심, `보통`은 기본 추천, `자세히`는 주제 전환을 더 민감하게 나눕니다.</p>
        </div>

        <div class="settings-group">
          <p class="step-title"><span class="step-number">4</span><span>Notion DB 주소 등록</span></p>
          <div class="toolbar">
            <label>Notion DB 전체 주소</label>
            <input class="db-input" id="notionDb" type="text" placeholder="전체 주소를 붙여넣어주세요" />
            <button onclick="pasteNotionDb()">붙여넣기</button>
            <button onclick="saveNotionDb()">DB 저장</button>
          </div>
          <p class="hint">데이터베이스 화면에서 복사한 전체 주소를 그대로 붙여넣으면 됩니다. 그 다음 Notion DB 우측 상단 `...` 또는 `공유`에서 `연결 추가`를 눌러 2번에서 만든 통합을 이 DB에 허용해 주세요.</p>
        </div>

        <div class="settings-group">
          <p class="step-title"><span class="step-number">5</span><span>카테고리 세팅</span></p>
          <div class="toolbar">
            <button class="primary" onclick="saveCategories()">분류 기준 저장</button>
            <button class="ghost" onclick="addCategoryRow()">행 추가</button>
            <button onclick="resetCategories()">기본값 불러오기</button>
          </div>
          <p class="hint">카테고리명과 설명을 적어두면 AI 분석과 규칙 기반 분류가 이 기준을 우선 참고합니다. 기타는 자동으로 유지됩니다.</p>
          <div class="category-editor" id="categoryRows"></div>
        </div>

        <div class="settings-group">
          <p class="step-title"><span class="step-number">6</span><span>DB 속성 세팅</span></p>
          <div class="toolbar">
            <button class="primary" onclick="setupNotionDb()">DB 속성 세팅</button>
            <div class="hint">5번에서 저장한 카테고리를 Notion의 분류 select 옵션으로 반영합니다.</div>
          </div>
        </div>

        <div class="settings-group">
          <p class="step-title"><span class="step-number">7</span><span>준비 상태 점검</span></p>
          <div class="toolbar">
            <button class="primary" onclick="checkReadiness()">준비 상태 점검</button>
            <div class="hint">Plaud, Notion, DB 주소, 카테고리, DB 속성이 실제 작업 가능한 상태인지 확인합니다.</div>
          </div>
          <div class="readiness-list" id="readinessList"></div>
        </div>

        <div class="settings-group">
          <p class="group-title">자동 실행</p>
          <div class="toolbar">
            <span class="switch-control">
              <label class="switch" title="자동 실행 사용">
                <input id="autorun" type="checkbox" onchange="updateAutorunLabel()" />
                <span class="switch-track"></span>
              </label>
              <span id="autorunLabel">자동 실행 꺼짐</span>
            </span>
            <label>자동 실행</label>
            <input class="tiny-input" id="hour" type="number" min="0" max="23" value="22" />
            <span>:</span>
            <input class="tiny-input" id="minute" type="number" min="0" max="59" value="0" />
            <button onclick="saveSchedule()">시간 저장</button>
          </div>
        </div>
      </div>
    </section>

    <div class="section-title">
      <h2>연결/작업 기록</h2>
      <div class="caption">Notion, AI API, 등록 작업 상태를 기록합니다.</div>
    </div>
    <pre id="log"></pre>

    <div class="section-title">
      <h2>최근 Plaud 노트</h2>
      <div class="caption">Notion DB 기준으로 등록 상태를 확인합니다.</div>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th style="width:136px;">상태</th>
            <th style="width:82px;"><label class="select-all"><input id="selectAll" type="checkbox" onchange="toggleAllNotes(this.checked)" /> 전체</label></th>
            <th>제목</th>
            <th style="width:170px;">녹음일시</th>
            <th style="width:96px;">길이</th>
            <th style="width:250px;">파일 ID</th>
          </tr>
        </thead>
        <tbody id="notes"><tr><td class="empty-row" colspan="6">불러오기 전</td></tr></tbody>
      </table>
    </div>
    <div class="load-more-row">
      <button id="loadMoreBtn" class="ghost" onclick="loadMoreNotes()">더 불러오기</button>
      <span class="note-count" id="noteCount"></span>
    </div>
  </main>
  <script>
    const logBox = document.getElementById('log');
    const NOTE_PAGE_SIZE = 20;
    let nextNotesPage = 1;
    let noteHasMore = false;
    let isBusy = false;
    let didLogInitialStatus = false;
    let didAutoLoadNotes = false;
    let categoryDefaults = [];
    let logLines = [];
    const loadedNoteIds = new Set();
    function log(text) {
      const time = new Date().toLocaleTimeString();
      logLines.push(`[${time}] ${text}`);
      logLines = logLines.slice(-5);
      logBox.textContent = logLines.join('\n') + (logLines.length ? '\n' : '');
      logBox.scrollTop = logBox.scrollHeight;
    }
    function busy(on, text='작업 중...') {
      isBusy = on;
      document.getElementById('busy').textContent = on ? text : '준비됨';
      for (const id of ['syncBtn', 'selectedBtn', 'refreshBtn', 'loadMoreBtn']) {
        const el = document.getElementById(id);
        if (el) el.disabled = on;
      }
      updateLoadMoreButton();
    }
    async function api(path, opts={}) {
      const res = await fetch(path, opts);
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || res.statusText);
      return data;
    }
    function toggleSettings(force) {
      const panel = document.getElementById('settingsPanel');
      const open = typeof force === 'boolean' ? force : !panel.classList.contains('open');
      panel.classList.toggle('open', open);
      document.getElementById('settingsToggle').textContent = open ? '접기' : '펼치기';
    }
    async function checkPlaud() {
      const target = document.getElementById('plaudStatus');
      const button = document.getElementById('plaudConnectBtn');
      target.textContent = '연결 중...';
      if (button) {
        button.disabled = true;
        button.textContent = '연결 중...';
      }
      log('Plaud 연결을 시작합니다. 로그인 창이 열리면 Plaud 계정으로 인증해 주세요.');
      try {
        const data = await api('/api/plaud-status');
        target.textContent = '연결완료';
        log(`Plaud 연결완료${data.note_count !== undefined ? `: 최근 노트 ${data.note_count}개 확인` : ''}`);
        await loadNotes();
      } catch (e) {
        target.textContent = '플라우드 연결 전';
        log('Plaud 연결 오류: ' + e.message);
        alert(e.message);
      } finally {
        if (button) {
          button.disabled = false;
          button.textContent = 'Plaud 연결하기';
        }
      }
    }
    function addCategoryRow(item={}) {
      const wrap = document.getElementById('categoryRows');
      const row = document.createElement('div');
      row.className = 'category-row';
      const name = document.createElement('input');
      name.type = 'text';
      name.className = 'categoryName';
      name.placeholder = '카테고리명';
      name.value = item.name || '';
      const desc = document.createElement('textarea');
      desc.className = 'categoryDescription';
      desc.placeholder = '설명';
      desc.value = item.description || '';
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = '삭제';
      remove.onclick = () => row.remove();
      row.append(name, desc, remove);
      wrap.appendChild(row);
    }
    function renderCategories(categories) {
      const wrap = document.getElementById('categoryRows');
      wrap.innerHTML = '';
      for (const item of categories) addCategoryRow(item);
    }
    function readCategories() {
      return [...document.querySelectorAll('.category-row')].map(row => ({
        name: row.querySelector('.categoryName').value.trim(),
        description: row.querySelector('.categoryDescription').value.trim(),
      })).filter(item => item.name);
    }
    async function loadCategories() {
      try {
        const data = await api('/api/categories');
        categoryDefaults = data.defaults || [];
        renderCategories(data.categories || categoryDefaults);
        log(`분류 기준 ${readCategories().length}개 불러오기 완료`);
      } catch (e) { log('분류 기준 불러오기 오류: ' + e.message); }
    }
    async function saveCategories() {
      const categories = readCategories();
      if (!categories.length) { alert('카테고리를 1개 이상 입력해 주세요.'); return; }
      log('분류 기준 저장 중...');
      try {
        const data = await api('/api/categories', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({categories}) });
        renderCategories(data.categories || categories);
        log(`분류 기준 저장 완료: ${(data.categories || categories).length}개`);
      } catch (e) { log('분류 기준 저장 오류: ' + e.message); alert(e.message); }
    }
    function resetCategories() {
      renderCategories(categoryDefaults);
      log('기본 분류 기준을 화면에 불러왔습니다. 저장을 누르면 적용됩니다.');
    }
    async function loadStatus() {
      try {
        const data = await api('/api/status');
        document.body.classList.toggle('personal-mode', !!data.personal_mode);
        document.getElementById('notion').textContent = data.notion;
        document.getElementById('openai').textContent = data.ai_display || data.openai_model || 'AI API 미등록';
        document.getElementById('schedule').textContent = data.schedule;
        document.getElementById('autorun').checked = !!data.autorun_enabled;
        updateAutorunLabel();
        document.getElementById('plaudStatus').textContent = data.plaud_connected ? '연결완료' : '플라우드 연결 전';
        if (data.plaud_connected && !didAutoLoadNotes) {
          didAutoLoadNotes = true;
          await loadNotes();
        }
        document.getElementById('segmentGranularity').value = data.segment_granularity || 'balanced';
        document.getElementById('apiStatus').textContent = data.api_key_registered ? 'AI 등록완료' : 'AI API 미등록';
        document.getElementById('notionTokenStatus').textContent = data.notion_token_registered ? 'Notion 연결완료' : 'Notion 토큰 미등록';
        document.getElementById('notionDb').placeholder = '전체 주소를 붙여넣어주세요';
        if (!didLogInitialStatus) {
          didLogInitialStatus = true;
          if (data.personal_mode) {
            log(`개인용 설정으로 실행 중: ${data.notion} / ${data.ai_display || data.openai_model}`);
          } else {
            log(data.notion_token_registered ? `Notion 연결 확인: ${data.notion}` : 'Notion 연결 상태: 토큰 미등록');
            log(data.api_key_registered ? `AI API 연결 확인: ${data.ai_display || data.openai_model}` : 'AI API 상태: 키 미등록');
          }
          if (!data.personal_mode && (!data.notion_token_registered || !data.api_key_registered || String(data.notion || '').includes('미등록') || String(data.notion || '').includes('확인 실패'))) {
            toggleSettings(true);
          }
        }
        if (data.first_time) {
          document.getElementById('hour').value = data.first_time.hour;
          document.getElementById('minute').value = data.first_time.minute;
        }
      } catch (e) { log('상태 확인 실패: ' + e.message); }
    }
    function updateAutorunLabel() {
      const checked = document.getElementById('autorun').checked;
      document.getElementById('autorunLabel').textContent = checked ? '자동 실행 켜짐' : '자동 실행 꺼짐';
    }
    function updateLoadMoreButton() {
      const btn = document.getElementById('loadMoreBtn');
      if (!btn) return;
      btn.disabled = isBusy || !noteHasMore;
      btn.style.display = noteHasMore ? 'inline-flex' : 'none';
    }
    function updateNoteCount() {
      const count = document.querySelectorAll('.noteCheck').length;
      document.getElementById('noteCount').textContent = count ? `${count}개 표시 중` : '';
    }
    function updateSelectAllState() {
      const master = document.getElementById('selectAll');
      const checks = [...document.querySelectorAll('.noteCheck')];
      if (!master) return;
      const selected = checks.filter(x => x.checked).length;
      master.checked = checks.length > 0 && selected === checks.length;
      master.indeterminate = selected > 0 && selected < checks.length;
    }
    function toggleAllNotes(checked) {
      for (const box of document.querySelectorAll('.noteCheck')) box.checked = checked;
      updateSelectAllState();
    }
    function appendNoteRow(n) {
      const cls = n.status.startsWith('등록완료') ? 'ok' : 'warn';
      const tr = document.createElement('tr');
      tr.innerHTML = `<td><span class="status-pill ${cls}">${escapeHtml(n.status)}</span></td><td><input type="checkbox" class="noteCheck" value="${escapeHtml(n.file_id)}" onchange="updateSelectAllState()"></td><td><div class="note-title">${escapeHtml(n.title)}</div></td><td>${escapeHtml(n.started)}</td><td>${escapeHtml(n.duration)}</td><td><div class="file-id">${escapeHtml(n.file_id)}</div></td>`;
      document.getElementById('notes').appendChild(tr);
    }
    async function loadNotes(options={}) {
      const append = !!options.append;
      if (!append) {
        nextNotesPage = 1;
        noteHasMore = false;
        loadedNoteIds.clear();
        document.getElementById('selectAll').checked = false;
        document.getElementById('selectAll').indeterminate = false;
      }
      busy(true, append ? '더 불러오는 중...' : '목록 불러오는 중...');
      try {
        const page = nextNotesPage;
        const data = await api(`/api/notes?page=${page}&page_size=${NOTE_PAGE_SIZE}`);
        const body = document.getElementById('notes');
        if (!append) body.innerHTML = '';
        let added = 0;
        if (!append && !data.notes.length) {
          body.innerHTML = '<tr><td class="empty-row" colspan="6">최근 Plaud 노트가 없습니다.</td></tr>';
        }
        for (const n of data.notes) {
          if (loadedNoteIds.has(n.file_id)) continue;
          loadedNoteIds.add(n.file_id);
          appendNoteRow(n);
          added += 1;
        }
        noteHasMore = !!data.has_more;
        nextNotesPage = data.next_page || page + 1;
        updateSelectAllState();
        updateNoteCount();
        updateLoadMoreButton();
        log(append ? `추가 ${added}개 불러오기 완료` : '목록 새로고침 완료');
      } catch (e) { log('목록 오류: ' + e.message); }
      busy(false);
    }
    async function loadMoreNotes() {
      if (!noteHasMore) return;
      await loadNotes({ append: true });
    }
    async function syncNow() {
      busy(true, '전송 중...');
      log('미전송 전사본 전체 등록을 시작합니다.');
      try {
        const data = await api('/api/sync', { method: 'POST' });
        log(data.output || '전송 완료');
        await loadStatus();
        await loadNotes();
      } catch (e) { log('전송 오류: ' + e.message); }
      busy(false);
    }
    async function syncSelected() {
      const ids = [...document.querySelectorAll('.noteCheck:checked')].map(x => x.value).filter(Boolean);
      if (!ids.length) { alert('전송할 Plaud 노트를 선택해 주세요.'); return; }
      busy(true, '선택 전송 중...');
      log(`선택한 전사본 ${ids.length}개 등록을 시작합니다.`);
      try {
        const data = await api('/api/sync-selected', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({file_ids: ids}) });
        log(data.output || '선택 전송 완료');
        await loadStatus();
        await loadNotes();
      } catch (e) { log('선택 전송 오류: ' + e.message); }
      busy(false);
    }
    async function saveKey() {
      const key = document.getElementById('apiKey').value.trim();
      if (!key) { alert('API 키를 입력해 주세요.'); return; }
      log('AI API 키 연결 확인 중...');
      try {
        await api('/api/ai-key', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({key}) });
        document.getElementById('apiKey').value = '';
        await loadStatus();
        log('AI API 키 연결 성공');
        alert('AI API 키를 저장했습니다.');
      } catch (e) { log('AI API 키 연결 오류: ' + e.message); alert(e.message); }
    }
    async function saveAnalysisSettings() {
      const segment_granularity = document.getElementById('segmentGranularity').value;
      log('분석 설정 저장 중...');
      try {
        await api('/api/analysis-settings', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({segment_granularity})
        });
        log('분석 설정 저장 완료');
      } catch (e) { log('분석 설정 저장 오류: ' + e.message); alert(e.message); }
    }
    async function saveNotionToken() {
      const token = document.getElementById('notionToken').value.trim();
      if (!token) { alert('Notion API 토큰을 입력해 주세요.'); return; }
      log('Notion API 토큰 연결 확인 중...');
      try {
        await api('/api/notion-token', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({token}) });
        document.getElementById('notionToken').value = '';
        await loadStatus();
        log('Notion API 토큰 연결 성공');
        alert('Notion API 토큰을 저장했습니다.');
      } catch (e) { log('Notion API 토큰 연결 오류: ' + e.message); alert(e.message); }
    }
    async function saveNotionDb() {
      const database = document.getElementById('notionDb').value.trim();
      if (!database) { alert('Notion 데이터베이스 전체 주소를 붙여넣어 주세요.'); return; }
      log('Notion DB 주소 저장 및 연결 확인 중...');
      try {
        const data = await api('/api/notion-db', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({database}) });
        document.getElementById('notionDb').value = '';
        await loadStatus();
        log(`Notion DB 연결 성공: ${data.title || data.database_id}`);
        alert(`Notion DB를 저장했습니다: ${data.title || data.database_id}`);
      } catch (e) { log('Notion DB 연결 오류: ' + e.message); alert(e.message); }
    }
    async function pasteNotionDb() {
      const input = document.getElementById('notionDb');
      input.focus();
      try {
        const data = await api('/api/clipboard');
        const text = String(data.text || '').trim();
        if (!text) { alert('클립보드에 붙여넣을 텍스트가 없습니다.'); return; }
        input.value = text;
        log('Notion DB 주소/ID를 붙여넣었습니다.');
      } catch (e) {
        try {
          if (!navigator.clipboard || !navigator.clipboard.readText) throw new Error('clipboard unavailable');
          const text = (await navigator.clipboard.readText()).trim();
          if (!text) { alert('클립보드에 붙여넣을 텍스트가 없습니다.'); return; }
          input.value = text;
          log('Notion DB 주소/ID를 붙여넣었습니다.');
        } catch (fallback) {
          alert('클립보드를 읽지 못했습니다. Notion DB 입력칸을 클릭한 뒤 ⌘V로 붙여넣어 주세요.');
        }
      }
    }
    async function setupNotionDb() {
      if (!confirm('현재 저장된 Notion DB에 Note Bridge 속성을 세팅할까요?')) return;
      log('Notion DB 속성 세팅을 시작합니다.');
      try {
        const data = await api('/api/notion-schema', { method: 'POST' });
        await loadStatus();
        log('Notion DB 속성 세팅 완료: ' + (data.message || '완료'));
        await checkReadiness();
        alert((data.message || 'Notion DB 속성 세팅 완료') + '\n\nNotion 화면에 바로 안 보이면 Notion 페이지를 새로고침해 주세요.');
      } catch (e) { log('Notion DB 속성 세팅 오류: ' + e.message); alert(e.message); }
    }
    function renderReadiness(checks, readyMessage) {
      const wrap = document.getElementById('readinessList');
      wrap.innerHTML = '';
      for (const check of checks) {
        const item = document.createElement('div');
        const level = check.level || (check.ok ? 'ready' : (check.optional ? 'warn' : 'bad'));
        item.className = `readiness-item ${level}`;
        const label = check.ok ? '완료' : (check.optional ? '선택' : '확인필요');
        item.innerHTML = `<strong>${escapeHtml(label)}</strong><span><b>${escapeHtml(check.name)}</b><br>${escapeHtml(check.message)}</span>`;
        wrap.appendChild(item);
      }
      if (readyMessage) log(readyMessage);
    }
    async function checkReadiness() {
      log('전체 준비 상태 점검 중...');
      try {
        const data = await api('/api/readiness');
        renderReadiness(data.checks || [], data.ready_message || '');
        if (!data.ok) toggleSettings(true);
      } catch (e) {
        log('준비 상태 점검 오류: ' + e.message);
        alert(e.message);
      }
    }
    async function saveSchedule() {
      const hour = Number(document.getElementById('hour').value);
      const minute = Number(document.getElementById('minute').value);
      const enabled = document.getElementById('autorun').checked;
      try {
        const data = await api('/api/schedule', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({hour, minute, enabled}) });
        document.getElementById('schedule').textContent = data.schedule;
        log('자동 실행 시간 저장 완료: ' + data.schedule);
      } catch (e) { alert(e.message); }
    }
    function escapeHtml(s) {
      return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }
    loadStatus();
    loadCategories();
  </script>
</body>
</html>
"""


def env_values(path: Path = sync.ENV_PATH) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text().splitlines():
        raw = raw.strip()
        if raw and not raw.startswith("#") and "=" in raw:
            key, value = raw.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def write_env_value(key: str, value: str) -> None:
    for path in [sync.ENV_PATH, RUNTIME / ".env"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = path.read_text().splitlines() if path.exists() else []
        output: List[str] = []
        found = False
        for line in lines:
            if line.startswith(f"{key}="):
                output.append(f"{key}={value}")
                found = True
            else:
                output.append(line)
        if not found:
            output.append(f"{key}={value}")
        path.write_text("\n".join(output).rstrip() + "\n")
        if path.name == ".env":
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass


def delete_env_keys(keys: List[str]) -> None:
    wanted = set(keys)
    for path in [sync.ENV_PATH, RUNTIME / ".env"]:
        if not path.exists():
            continue
        lines = []
        for line in path.read_text().splitlines():
            name = line.split("=", 1)[0].strip() if "=" in line else ""
            if name not in wanted:
                lines.append(line)
        path.write_text("\n".join(lines).rstrip() + ("\n" if lines else ""))
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def save_category_rules_for_app(rules: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized = sync.save_category_rules(rules)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    sync.save_category_rules(normalized, RUNTIME / "category_rules.json")
    return normalized


NOTION_ID_RE = re.compile(
    r"[0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
CATEGORY_COLORS = ["blue", "green", "purple", "pink", "orange", "yellow", "red", "brown", "gray", "default"]


def normalize_notion_id(value: str) -> str:
    return value.replace("-", "").lower()


def parse_notion_database_id(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError("Notion 데이터베이스 전체 주소를 붙여넣어 주세요.")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme and parsed.netloc:
        path_candidates = NOTION_ID_RE.findall(urllib.parse.unquote(parsed.path or ""))
        if path_candidates:
            return normalize_notion_id(path_candidates[-1])
        raise ValueError("Notion 데이터베이스 전체 주소에서 DB ID를 찾지 못했습니다. 데이터베이스 화면의 공유/링크 복사 주소 전체를 붙여넣어 주세요.")
    candidates = NOTION_ID_RE.findall(value)
    if not candidates:
        raise ValueError("Notion 데이터베이스 전체 주소에서 DB ID를 찾지 못했습니다. 주소 전체를 다시 복사해 붙여넣어 주세요.")
    return normalize_notion_id(candidates[-1])


def notion_error_message(code: int, body: str) -> str:
    try:
        data = json.loads(body)
        message = data.get("message") or data.get("error", {}).get("message") or body
    except Exception:
        message = body
    if code == 401:
        return "Notion API 토큰이 올바르지 않습니다. 토큰을 다시 저장해 주세요."
    if code == 403:
        return "Notion 권한이 없습니다. 해당 데이터베이스를 Notion 통합(Integration)에 공유했는지 확인해 주세요."
    if code == 404:
        return "Notion 데이터베이스를 찾지 못했습니다. 전체 DB 주소를 붙여넣었는지, 그리고 그 DB가 Notion 통합(Integration)에 공유되어 있는지 확인해 주세요."
    return f"Notion HTTP {code}: {message[:700]}"


def notion_request(token: str, method: str, path: str, payload: Dict[str, Any] = None) -> Dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "https://api.notion.com/v1" + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
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
        raise RuntimeError(notion_error_message(exc.code, body)) from exc


def notion_title(database: Dict[str, Any]) -> str:
    return "".join(t.get("plain_text", "") for t in database.get("title", []))


def ensure_notion_database_title(token: str, database_id: str) -> Tuple[Dict[str, Any], str, bool]:
    database = notion_request(token, "GET", f"/databases/{database_id}")
    title = notion_title(database).strip()
    if title:
        return database, title, False
    database = notion_request(
        token,
        "PATCH",
        f"/databases/{database_id}",
        {"title": [{"type": "text", "text": {"content": "Note Bridge"}}]},
    )
    return database, "Note Bridge", True


def notion_database_has_rows(token: str, database_id: str) -> bool:
    response = notion_request(token, "POST", f"/databases/{database_id}/query", {"page_size": 1})
    return bool(response.get("results"))


def category_color(name: str, index: int) -> str:
    preferred = {
        "개인통화": "blue",
        "업무통화": "green",
        "강의": "purple",
        "코칭": "pink",
        "회의": "orange",
        "아이디어": "yellow",
        "업무메모": "red",
        "잡담": "brown",
        "기타": "gray",
    }
    return preferred.get(name, CATEGORY_COLORS[index % len(CATEGORY_COLORS)])


def colored_category_options(names: List[str]) -> List[Dict[str, str]]:
    return [{"name": name, "color": category_color(name, index)} for index, name in enumerate(names)]


def merge_category_options(existing_options: List[Dict[str, Any]], category_names: List[str]) -> List[Dict[str, str]]:
    existing_by_name = {option.get("name", ""): option for option in existing_options if option.get("name")}
    payload: List[Dict[str, str]] = []
    for option in existing_options:
        if option.get("id"):
            payload.append({"id": option["id"]})
        elif option.get("name"):
            payload.append({"name": option["name"]})
    for index, name in enumerate(category_names):
        if name not in existing_by_name:
            payload.append({"name": name, "color": category_color(name, index)})
    return payload


def category_colors_need_recreate(prop: Dict[str, Any], desired_names: List[str]) -> bool:
    options = prop.get("select", {}).get("options", []) if prop.get("type") == "select" else []
    by_name = {option.get("name", ""): option for option in options}
    for index, name in enumerate(desired_names):
        option = by_name.get(name)
        if option and option.get("color") != category_color(name, index):
            return True
    return False


def existing_category_page_values(token: str, database_id: str) -> List[Tuple[str, str]]:
    payload: Dict[str, Any] = {"page_size": 100}
    values: List[Tuple[str, str]] = []
    while True:
        response = notion_request(token, "POST", f"/databases/{database_id}/query", payload)
        for page in response.get("results", []):
            prop = page.get("properties", {}).get(sync.NOTION_PROPS["category"], {})
            selected = prop.get("select") if isinstance(prop, dict) else None
            if selected and selected.get("name"):
                values.append((page["id"], selected["name"]))
        if not response.get("has_more") or not response.get("next_cursor"):
            break
        payload["start_cursor"] = response["next_cursor"]
    return values


def recreate_category_property_preserving_values(token: str, database_id: str, desired_names: List[str]) -> int:
    existing_values = existing_category_page_values(token, database_id)
    extra_names = [name for _page_id, name in existing_values if name and name not in desired_names]
    option_names = desired_names + [name for name in extra_names if name not in desired_names]
    notion_request(token, "PATCH", f"/databases/{database_id}", {"properties": {sync.NOTION_PROPS["category"]: None}})
    notion_request(
        token,
        "PATCH",
        f"/databases/{database_id}",
        {"properties": {sync.NOTION_PROPS["category"]: {"select": {"options": colored_category_options(option_names)}}}},
    )
    for page_id, category in existing_values:
        notion_request(
            token,
            "PATCH",
            f"/pages/{page_id}",
            {"properties": {sync.NOTION_PROPS["category"]: {"select": {"name": category}}}},
        )
    return len(existing_values)


def sanitize_notion_token(value: str) -> str:
    value = (value or "").strip().strip('"').strip("'")
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    return value


def validate_notion_token(token: str) -> Tuple[bool, str]:
    try:
        notion_request(token, "GET", "/users/me")
        return True, "Notion API 토큰 확인 완료"
    except Exception as exc:
        return False, str(exc)


def plaud_auth_present() -> bool:
    token_path = Path.home() / ".plaud/tokens-mcp.json"
    try:
        return token_path.exists() and token_path.stat().st_size > 0
    except OSError:
        return False


def check_plaud_recent(env: Dict[str, str], limit: int = 10) -> str:
    with sync.PlaudMCP(env.get("PLAUD_NPX")) as plaud:
        files = plaud.list_files({"page": 1, "page_size": limit})
    return f"Plaud 연결완료 / 최근 노트 {len(files)}개 확인"


def is_plaud_auth_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "not authenticated" in text or "please login" in text or "401" in text or "unauthorized" in text


def connect_plaud_and_check(env: Dict[str, str], limit: int = 10) -> str:
    try:
        return check_plaud_recent(env, limit)
    except Exception as exc:
        if not is_plaud_auth_error(exc):
            raise
    with sync.PlaudMCP(env.get("PLAUD_NPX")) as plaud:
        login_text = plaud.call_tool("login", {}, timeout=180)
        files = plaud.list_files({"page": 1, "page_size": limit})
    prefix = "Plaud 연결완료"
    if login_text:
        lower = login_text.lower()
        if "already" in lower:
            prefix = "Plaud 이미 연결됨"
    return f"{prefix} / 최근 노트 {len(files)}개 확인"


def connect_plaud_and_count(env: Dict[str, str], limit: int = 10) -> Tuple[str, int]:
    try:
        with sync.PlaudMCP(env.get("PLAUD_NPX")) as plaud:
            files = plaud.list_files({"page": 1, "page_size": limit})
        return "연결완료", len(files)
    except Exception as exc:
        if not is_plaud_auth_error(exc):
            raise
    with sync.PlaudMCP(env.get("PLAUD_NPX")) as plaud:
        plaud.call_tool("login", {}, timeout=180)
        files = plaud.list_files({"page": 1, "page_size": limit})
    return "연결완료", len(files)


def ensure_notion_schema(token: str, database_id: str) -> str:
    database, _title, title_changed = ensure_notion_database_title(token, database_id)
    props = database.get("properties", {})
    changes: List[str] = []
    if title_changed:
        changes.append("데이터베이스 제목 Note Bridge 설정")

    managed_names = set(sync.NOTION_PROPS.values()) - {sync.NOTION_PROPS["title"]}
    has_rows = notion_database_has_rows(token, database_id)
    resettable_props = {name: None for name in props if name in managed_names}
    if resettable_props and not has_rows:
        notion_request(token, "PATCH", f"/databases/{database_id}", {"properties": resettable_props})
        changes.append("빈 DB의 앱 관리 속성 순서/색상 재정렬")
        database = notion_request(token, "GET", f"/databases/{database_id}")
        props = database.get("properties", {})

    patch: Dict[str, Any] = {"properties": {}}

    def add(name: str, body: Dict[str, Any]) -> None:
        if name not in props:
            patch["properties"][name] = body

    # Rename an existing title property to 제목 if needed. Notion databases always have one title property.
    if sync.NOTION_PROPS["title"] not in props:
        for old_name, prop in props.items():
            if prop.get("type") == "title":
                patch["properties"][old_name] = {"name": sync.NOTION_PROPS["title"]}
                break

    category_options = sync.category_names()
    add(sync.NOTION_PROPS["category"], {"select": {"options": colored_category_options(category_options)}})
    category_prop = props.get(sync.NOTION_PROPS["category"])
    if category_prop and category_prop.get("type") == "select" and category_colors_need_recreate(category_prop, category_options):
        restored = recreate_category_property_preserving_values(token, database_id, category_options)
        changes.append(f"분류 색상 재생성 및 기존 값 {restored}개 복원")
        database = notion_request(token, "GET", f"/databases/{database_id}")
        props = database.get("properties", {})
        category_prop = props.get(sync.NOTION_PROPS["category"])
    if category_prop and category_prop.get("type") == "select":
        existing_options = category_prop.get("select", {}).get("options", [])
        existing_names = [x.get("name", "") for x in existing_options]
        if any(x not in existing_names for x in category_options):
            patch["properties"][sync.NOTION_PROPS["category"]] = {
                "select": {"options": merge_category_options(existing_options, category_options)}
            }
    add(sync.NOTION_PROPS["recorded_at"], {"date": {}})
    add(sync.NOTION_PROPS["duration"], {"number": {"format": "number"}})
    add(sync.NOTION_PROPS["summary"], {"rich_text": {}})
    add(sync.NOTION_PROPS["plaud_file_id"], {"rich_text": {}})
    add(sync.NOTION_PROPS["original_title"], {"rich_text": {}})
    add(sync.NOTION_PROPS["segment_index"], {"number": {"format": "number"}})
    add(sync.NOTION_PROPS["start_time"], {"rich_text": {}})
    add(sync.NOTION_PROPS["end_time"], {"rich_text": {}})
    add(sync.NOTION_PROPS["time_range"], {"rich_text": {}})
    add(sync.NOTION_PROPS["source"], {"select": {"options": [{"name": "Plaud"}]}})
    add(sync.NOTION_PROPS["status"], {"select": {"options": [{"name": x} for x in ["신규", "분석완료", "확인필요", "보관"]]}})
    add(sync.NOTION_PROPS["processed_at"], {"date": {}})
    add(sync.NOTION_PROPS["confidence"], {"number": {"format": "number"}})
    add(sync.NOTION_PROPS["transcript_preview"], {"rich_text": {}})
    add(sync.NOTION_PROPS["key_points"], {"rich_text": {}})
    add(sync.NOTION_PROPS["action_items"], {"rich_text": {}})
    add(sync.NOTION_PROPS["people"], {"multi_select": {}})

    if patch["properties"]:
        notion_request(token, "PATCH", f"/databases/{database_id}", patch)
        changes.append(f"속성 {len(patch['properties'])}개 추가/변경")
    return " / ".join(changes) if changes else "이미 필요한 속성이 모두 있습니다."


def notion_schema_status(token: str, database_id: str) -> Tuple[bool, str]:
    database = notion_request(token, "GET", f"/databases/{database_id}")
    props = database.get("properties", {})
    expected_types = {
        "title": "title",
        "category": "select",
        "summary": "rich_text",
        "plaud_file_id": "rich_text",
        "original_title": "rich_text",
        "segment_index": "number",
        "start_time": "rich_text",
        "end_time": "rich_text",
        "time_range": "rich_text",
        "duration": "number",
        "recorded_at": "date",
        "source": "select",
        "status": "select",
        "processed_at": "date",
        "confidence": "number",
        "transcript_preview": "rich_text",
        "key_points": "rich_text",
        "action_items": "rich_text",
        "people": "multi_select",
    }
    missing: List[str] = []
    wrong_type: List[str] = []
    for key, expected in expected_types.items():
        name = sync.NOTION_PROPS[key]
        prop = props.get(name)
        if not prop:
            missing.append(name)
        elif prop.get("type") != expected:
            wrong_type.append(f"{name}({prop.get('type') or '알 수 없음'})")

    category_missing: List[str] = []
    category_prop = props.get(sync.NOTION_PROPS["category"])
    if category_prop and category_prop.get("type") == "select":
        existing = {item.get("name", "") for item in category_prop.get("select", {}).get("options", [])}
        category_missing = [name for name in sync.category_names() if name not in existing]

    if not missing and not wrong_type and not category_missing:
        return True, "DB 속성이 현재 카테고리 기준까지 모두 준비되어 있습니다."

    issues: List[str] = []
    if missing:
        issues.append("없는 속성: " + ", ".join(missing[:8]) + ("..." if len(missing) > 8 else ""))
    if wrong_type:
        issues.append("타입 확인 필요: " + ", ".join(wrong_type[:5]) + ("..." if len(wrong_type) > 5 else ""))
    if category_missing:
        issues.append("분류 옵션 누락: " + ", ".join(category_missing[:8]) + ("..." if len(category_missing) > 8 else ""))
    return False, " / ".join(issues) + " / 6번 DB 속성 세팅을 눌러 주세요."


def readiness_checks() -> Dict[str, Any]:
    env = env_values()
    token = env.get("NOTION_TOKEN", "")
    database_id = env.get("NOTION_DATABASE_ID", "")
    provider, ai_key, model = configured_ai(env)
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, message: str, optional: bool = False, level: str = "") -> None:
        checks.append(
            {
                "name": name,
                "ok": ok,
                "optional": optional,
                "level": level or ("ready" if ok else ("warn" if optional else "bad")),
                "message": message,
            }
        )

    try:
        add("Plaud MCP", True, check_plaud_recent(env))
    except Exception as exc:
        add(
            "Plaud MCP",
            False,
            "Plaud 연결이 필요합니다. 1번의 `Plaud 연결하기`를 누르고 로그인 창에서 인증해 주세요. "
            "창이 열리지 않으면 터미널에서 `npx -y @plaud-ai/mcp@latest`를 한 번 실행해 인증할 수 있습니다. "
            f"원인: {exc}",
        )

    if not token:
        add("Notion API", False, "Notion API 토큰이 아직 저장되지 않았습니다.")
    else:
        ok, message = validate_notion_token(token)
        add("Notion API", ok, message)

    if not ai_key:
        add("AI API", False, "선택 사항입니다. 미등록 상태에서는 규칙 기반 분류로 동작합니다.", optional=True, level="warn")
    else:
        ok, message = validate_ai_key(provider, ai_key)
        add(f"AI API ({provider_label(provider)} · {model})", ok, message if ok else f"{message} / 규칙 기반 분류는 계속 사용할 수 있습니다.", optional=True)

    if not database_id:
        add("Notion DB 주소", False, "Notion DB 전체 주소가 아직 저장되지 않았습니다.")
    elif not token:
        add("Notion DB 주소", False, "DB 주소 확인 전에 Notion API 토큰을 먼저 저장해 주세요.")
    else:
        try:
            database = notion_request(token, "GET", f"/databases/{database_id}")
            title = notion_title(database).strip() or "(제목 없음)"
            add("Notion DB 주소", True, f"DB 연결 확인 완료: {title}")
        except Exception as exc:
            add("Notion DB 주소", False, str(exc))

    categories = sync.load_category_rules()
    if categories:
        category_names = ", ".join(item["name"] for item in categories[:8])
        suffix = "..." if len(categories) > 8 else ""
        add("카테고리", True, f"{len(categories)}개 설정됨: {category_names}{suffix}")
    else:
        add("카테고리", False, "카테고리를 1개 이상 저장해 주세요.")

    if not token or not database_id:
        add("DB 속성", False, "Notion API 토큰과 DB 주소 저장 후 6번 DB 속성 세팅을 진행해 주세요.")
    else:
        try:
            ok, message = notion_schema_status(token, database_id)
            add("DB 속성", ok, message)
        except Exception as exc:
            add("DB 속성", False, str(exc))

    blocking = [item for item in checks if not item["optional"] and not item["ok"]]
    return {
        "ok": not blocking,
        "checks": checks,
        "ready_message": "모든 필수 설정이 준비되었습니다." if not blocking else f"필수 설정 {len(blocking)}개를 더 확인해 주세요.",
    }


def duration_text(ms: Any) -> str:
    try:
        total = int(ms or 0) // 1000
    except Exception:
        total = 0
    hours, rem = divmod(total, 3600)
    minutes, _ = divmod(rem, 60)
    if hours:
        return f"{hours}시간 {minutes}분"
    return f"{minutes}분"


def recorded_at_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 10_000_000_000:
            seconds = seconds / 1000
        return datetime.fromtimestamp(seconds, tz=timezone.utc).astimezone(sync.KST).strftime("%Y-%m-%d %H:%M:%S")
    raw = str(value).strip()
    if not raw:
        return ""
    if raw.isdigit():
        return recorded_at_text(int(raw))
    normalized = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return raw.split(".")[0].replace("T", " ")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(sync.KST).strftime("%Y-%m-%d %H:%M:%S")


def sanitize_openai_key(value: str) -> str:
    value = (value or "").strip().strip('"').strip("'")
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    return value


def provider_label(provider: str) -> str:
    return "Claude" if provider == "anthropic" else "OpenAI"


def normalize_ai_provider(value: str) -> str:
    value = (value or "").strip().lower()
    if value in {"claude", "anthropic"}:
        return "anthropic"
    return "openai"


def default_ai_model(provider: str) -> str:
    return "claude-opus-4-5" if provider == "anthropic" else "gpt-5.4-mini"


def configured_ai(env: Dict[str, str]) -> Tuple[str, str, str]:
    provider = (env.get("AI_PROVIDER", "") or "").strip().lower()
    if provider in {"claude", "anthropic"}:
        return "anthropic", env.get("ANTHROPIC_API_KEY", ""), env.get("ANTHROPIC_MODEL", default_ai_model("anthropic"))
    if provider == "openai":
        return "openai", env.get("OPENAI_API_KEY", ""), env.get("OPENAI_MODEL", default_ai_model("openai"))
    if env.get("ANTHROPIC_API_KEY"):
        return "anthropic", env.get("ANTHROPIC_API_KEY", ""), env.get("ANTHROPIC_MODEL", default_ai_model("anthropic"))
    if env.get("OPENAI_API_KEY"):
        return "openai", env.get("OPENAI_API_KEY", ""), env.get("OPENAI_MODEL", default_ai_model("openai"))
    return "openai", "", ""


def ai_status(env: Dict[str, str]) -> Dict[str, Any]:
    provider, key, model = configured_ai(env)
    registered = bool(key)
    return {
        "ai_provider": provider,
        "ai_model": model if registered else "",
        "ai_display": f"{provider_label(provider)} · {model}" if registered else "AI API 미등록",
        "api_key_registered": registered,
    }


def validate_openai_key(key: str) -> Tuple[bool, str]:
    req = urllib.request.Request(
        "https://api.openai.com/v1/models",
        method="GET",
        headers={"Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.status == 200:
                return True, "OpenAI API 키 확인 완료"
            return False, f"OpenAI 응답 상태가 예상과 다릅니다: {resp.status}"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            data = json.loads(body)
            message = data.get("error", {}).get("message") or body
        except Exception:
            message = body
        if exc.code == 401:
            return False, "OpenAI API 키가 올바르지 않습니다. 복사한 키 전체를 다시 붙여넣어 주세요."
        return False, f"OpenAI 키 확인 실패: HTTP {exc.code} {message[:400]}"
    except Exception as exc:
        return False, f"OpenAI 키 확인 실패: {exc}"


def validate_anthropic_key(key: str) -> Tuple[bool, str]:
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/models",
        method="GET",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.status == 200:
                return True, "Claude API 키 확인 완료"
            return False, f"Claude 응답 상태가 예상과 다릅니다: {resp.status}"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            data = json.loads(body)
            message = data.get("error", {}).get("message") or body
        except Exception:
            message = body
        if exc.code == 401:
            return False, "Claude API 키가 올바르지 않습니다. 복사한 키 전체를 다시 붙여넣어 주세요."
        return False, f"Claude 키 확인 실패: HTTP {exc.code} {message[:400]}"
    except Exception as exc:
        return False, f"Claude 키 확인 실패: {exc}"


def validate_ai_key(provider: str, key: str) -> Tuple[bool, str]:
    if provider == "anthropic":
        return validate_anthropic_key(key)
    return validate_openai_key(key)


def detect_ai_key(key: str) -> Tuple[str, str, str]:
    lowered = key.lower()
    if lowered.startswith("sk-ant-"):
        provider = "anthropic"
        ok, message = validate_anthropic_key(key)
        if not ok:
            raise ValueError(message)
        return provider, default_ai_model(provider), message
    if lowered.startswith("sk-"):
        provider = "openai"
        ok, message = validate_openai_key(key)
        if not ok:
            raise ValueError(message)
        return provider, default_ai_model(provider), message

    attempts: List[str] = []
    for provider in ["openai", "anthropic"]:
        ok, message = validate_ai_key(provider, key)
        if ok:
            return provider, default_ai_model(provider), message
        attempts.append(message)
    raise ValueError("API 키 제공자를 자동으로 확인하지 못했습니다. " + " / ".join(attempts[:2]))


def update_plist_schedule(path: Path, hour: int, minute: int) -> None:
    with path.open("rb") as f:
        data = plistlib.load(f)
    data["StartCalendarInterval"] = {"Hour": hour, "Minute": minute}
    with path.open("wb") as f:
        plistlib.dump(data, f)


def autorun_enabled() -> bool:
    return env_values().get("PLAUDDB_AUTORUN_ENABLED", "false").lower() == "true"


def current_schedule() -> Tuple[str, Dict[str, int], bool]:
    path = RUNTIME_PLIST if RUNTIME_PLIST.exists() else PLIST_PATH
    enabled = autorun_enabled()
    try:
        with path.open("rb") as f:
            data = plistlib.load(f)
        intervals = data.get("StartCalendarInterval", [])
        if isinstance(intervals, dict):
            intervals = [intervals]
        text = ", ".join(f"{int(x.get('Hour', 0)):02d}:{int(x.get('Minute', 0)):02d}" for x in intervals[:1])
        first = intervals[0] if intervals else {"Hour": 22, "Minute": 0}
        prefix = "사용" if enabled else "꺼짐"
        return f"{prefix} / {text or '설정 없음'}", {"hour": int(first.get("Hour", 22)), "minute": int(first.get("Minute", 0))}, enabled
    except Exception:
        return "확인 실패", {"hour": 22, "minute": 0}, enabled


def json_response(handler: BaseHTTPRequestHandler, data: Dict[str, Any], status: int = 200) -> None:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    raw = handler.rfile.read(length).decode("utf-8") if length else "{}"
    return json.loads(raw or "{}")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[Note Bridge] {self.address_string()} {fmt % args}")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/":
                body = HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif parsed.path == "/api/status":
                env = env_values()
                token = env.get("NOTION_TOKEN", "")
                database_id = env.get("NOTION_DATABASE_ID", "")
                ai = ai_status(env)
                plaud_connected = plaud_auth_present()
                plaud_note_count = 0
                notion_text = "Notion 토큰 미등록"
                try:
                    if token and database_id:
                        notion = sync.NotionClient(token, database_id)
                        notion_text = notion.database_title()
                    elif token:
                        notion_text = "DB 주소 미등록"
                except Exception as exc:
                    notion_text = f"확인 실패: {exc}"
                schedule, first, enabled = current_schedule()
                json_response(
                    self,
                    {
                        "notion": notion_text,
                        "openai_model": ai["ai_display"],
                        "ai_display": ai["ai_display"],
                        "ai_provider": ai["ai_provider"],
                        "ai_model": ai["ai_model"],
                        "api_key_registered": ai["api_key_registered"],
                        "notion_token_registered": bool(token),
                        "schedule": schedule,
                        "first_time": first,
                        "autorun_enabled": enabled,
                        "notion_database_id": env.get("NOTION_DATABASE_ID", ""),
                        "plaud_connected": plaud_connected,
                        "plaud_note_count": plaud_note_count,
                        "segment_granularity": env.get("SEGMENT_GRANULARITY", "balanced"),
                        "personal_mode": PERSONAL_MODE,
                    },
                )
            elif parsed.path == "/api/categories":
                json_response(
                    self,
                    {
                        "categories": sync.load_category_rules(),
                        "defaults": sync.default_category_rules(),
                    },
                )
            elif parsed.path == "/api/plaud-status":
                env = env_values()
                try:
                    message, note_count = connect_plaud_and_count(env)
                    json_response(self, {"ok": True, "message": message, "note_count": note_count})
                except Exception as exc:
                    raise RuntimeError(
                        "Plaud 연결에 실패했습니다. 로그인 창이 열렸다면 Plaud 계정 인증을 완료한 뒤 다시 눌러 주세요. "
                        "창이 열리지 않으면 터미널에서 `npx -y @plaud-ai/mcp@latest`를 한 번 실행해 인증할 수 있습니다. "
                        f"원인: {exc}"
                    )
            elif parsed.path == "/api/readiness":
                json_response(self, readiness_checks())
            elif parsed.path == "/api/clipboard":
                proc = subprocess.run(["/usr/bin/pbpaste"], text=True, capture_output=True, timeout=5)
                if proc.returncode != 0:
                    raise RuntimeError(proc.stderr.strip() or "클립보드를 읽지 못했습니다.")
                json_response(self, {"text": proc.stdout})
            elif parsed.path == "/api/notes":
                query = urllib.parse.parse_qs(parsed.query)
                page = max(1, int(query.get("page", ["1"])[0] or "1"))
                page_size = max(10, min(50, int(query.get("page_size", ["20"])[0] or "20")))
                env = env_values()
                token = env.get("NOTION_TOKEN", "")
                database_id = env.get("NOTION_DATABASE_ID", "")
                notion = sync.NotionClient(token, database_id) if token and database_id else None
                notes = []
                with sync.PlaudMCP(env.get("PLAUD_NPX")) as plaud:
                    files = plaud.list_files({"page": page, "page_size": page_size})
                    page_files = files[:page_size]
                    for item in page_files:
                        file_id = item.get("id", "")
                        existing = notion.existing_pages_for_file(file_id) if notion and file_id else []
                        if notion:
                            status = f"등록완료 ({len(existing)})" if existing else "노션 등록전"
                        else:
                            status = "노션 연결전"
                        notes.append(
                            {
                                "status": status,
                                "title": item.get("name") or "(untitled)",
                                "started": recorded_at_text(item.get("start_at") or item.get("created_at") or ""),
                                "duration": duration_text(item.get("duration")),
                                "file_id": file_id,
                            }
                        )
                json_response(
                    self,
                    {
                        "notes": notes,
                        "page": page,
                        "page_size": page_size,
                        "has_more": len(files) >= page_size,
                        "next_page": page + 1,
                    },
                )
            else:
                json_response(self, {"error": "not found"}, 404)
        except Exception as exc:
            json_response(self, {"error": str(exc)}, 500)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path in {"/api/ai-key", "/api/openai-key"}:
                data = read_json(self)
                key = sanitize_openai_key(str(data.get("key", "")))
                if not key:
                    raise ValueError("API 키가 비어 있습니다.")
                provider, model, message = detect_ai_key(key)
                write_env_value("AI_PROVIDER", provider)
                if provider == "anthropic":
                    write_env_value("ANTHROPIC_API_KEY", key)
                    write_env_value("ANTHROPIC_MODEL", model)
                    delete_env_keys(["OPENAI_API_KEY", "OPENAI_MODEL"])
                else:
                    write_env_value("OPENAI_API_KEY", key)
                    write_env_value("OPENAI_MODEL", model)
                    delete_env_keys(["ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"])
                json_response(self, {"ok": True, "message": message, "provider": provider, "model": model})
            elif parsed.path == "/api/categories":
                data = read_json(self)
                categories = data.get("categories", [])
                if not isinstance(categories, list):
                    raise ValueError("분류 기준 형식이 올바르지 않습니다.")
                normalized = save_category_rules_for_app(categories)
                json_response(self, {"ok": True, "categories": normalized})
            elif parsed.path == "/api/notion-token":
                data = read_json(self)
                token = sanitize_notion_token(str(data.get("token", "")))
                if not token:
                    raise ValueError("Notion API 토큰이 비어 있습니다.")
                ok, message = validate_notion_token(token)
                if not ok:
                    raise ValueError(message)
                write_env_value("NOTION_TOKEN", token)
                json_response(self, {"ok": True, "message": message})
            elif parsed.path == "/api/analysis-settings":
                data = read_json(self)
                granularity = str(data.get("segment_granularity", "balanced")).strip().lower()
                if granularity not in {"compact", "balanced", "detailed"}:
                    raise ValueError("전사문 나누기 설정이 올바르지 않습니다.")
                write_env_value("SEGMENT_GRANULARITY", granularity)
                json_response(self, {"ok": True, "segment_granularity": granularity})
            elif parsed.path == "/api/schedule":
                data = read_json(self)
                hour = int(data.get("hour"))
                minute = int(data.get("minute"))
                enabled = bool(data.get("enabled"))
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError("시간은 00:00-23:59 범위여야 합니다.")
                update_plist_schedule(PLIST_PATH, hour, minute)
                write_env_value("PLAUDDB_AUTORUN_ENABLED", "true" if enabled else "false")
                proc = subprocess.run(["./install_launchd.sh"], cwd=ROOT, text=True, capture_output=True, timeout=60)
                if proc.returncode != 0:
                    raise RuntimeError((proc.stdout or "") + (proc.stderr or ""))
                schedule = f"{'사용' if enabled else '꺼짐'} / {hour:02d}:{minute:02d}"
                json_response(self, {"ok": True, "schedule": schedule})
            elif parsed.path == "/api/notion-db":
                data = read_json(self)
                database_id = parse_notion_database_id(str(data.get("database", "")))
                env = env_values()
                token = env.get("NOTION_TOKEN", "")
                if not token:
                    raise ValueError("NOTION_TOKEN이 없습니다.")
                _database, title, title_changed = ensure_notion_database_title(token, database_id)
                write_env_value("NOTION_DATABASE_ID", database_id)
                json_response(self, {"ok": True, "database_id": database_id, "title": title, "title_changed": title_changed})
            elif parsed.path == "/api/notion-schema":
                env = env_values()
                token = env.get("NOTION_TOKEN", "")
                database_id = env.get("NOTION_DATABASE_ID", "")
                if not token or not database_id:
                    raise ValueError("NOTION_TOKEN 또는 NOTION_DATABASE_ID가 없습니다.")
                message = ensure_notion_schema(token, database_id)
                json_response(self, {"ok": True, "message": message})
            elif parsed.path == "/api/sync":
                cmd = [
                    "/usr/bin/python3",
                    str(ROOT / "sync_plaud_to_notion.py"),
                    "--recent",
                    "100",
                    "--analysis",
                    "auto",
                    "--limit",
                    "100",
                ]
                proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=3600)
                output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
                if proc.returncode != 0:
                    raise RuntimeError(output.strip() or f"exit {proc.returncode}")
                json_response(self, {"ok": True, "output": output.strip()})
            elif parsed.path == "/api/sync-selected":
                data = read_json(self)
                file_ids = [str(x).strip() for x in data.get("file_ids", []) if str(x).strip()]
                if not file_ids:
                    raise ValueError("선택된 Plaud 노트가 없습니다.")
                cmd = [
                    "/usr/bin/python3",
                    str(ROOT / "sync_plaud_to_notion.py"),
                    "--analysis",
                    "auto",
                    "--limit",
                    str(len(file_ids)),
                ]
                for file_id in file_ids:
                    cmd.extend(["--file-id", file_id])
                proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=3600)
                output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
                if proc.returncode != 0:
                    raise RuntimeError(output.strip() or f"exit {proc.returncode}")
                json_response(self, {"ok": True, "output": output.strip()})
            else:
                json_response(self, {"error": "not found"}, 404)
        except Exception as exc:
            json_response(self, {"error": str(exc)}, 500)


class ReusableThreadingTCPServer(ThreadingTCPServer):
    allow_reuse_address = True


def main() -> int:
    url = f"http://127.0.0.1:{PORT}"
    server = ReusableThreadingTCPServer(("127.0.0.1", PORT), Handler)
    print(f"Note Bridge running at {url}")
    if os.environ.get("PLAUDDB_NO_BROWSER") != "1":
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping Note Bridge")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
