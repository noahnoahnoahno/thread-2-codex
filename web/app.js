const report = window.UPLOADER_REPORT || {
  generatedAt: "",
  summary: { total: 0, ready: 0, review: 0, videoFail: 0, errors: 0, duplicates: {} },
  candidates: [],
  auth: {},
};

let activeFilter = "all";
let activeSource = "drive";
let searchText = "";

const generatedAt = document.getElementById("generatedAt");
const authStatus = document.getElementById("authStatus");
const metrics = document.getElementById("metrics");
const grid = document.getElementById("candidateGrid");
const search = document.getElementById("search");
const triggerDate = document.getElementById("triggerDate");
const allowReview = document.getElementById("allowReview");
const setupFolders = document.getElementById("setupFolders");
const writeTemplates = document.getElementById("writeTemplates");
const refreshScan = document.getElementById("refreshScan");
const previewTrigger = document.getElementById("previewTrigger");
const executeTrigger = document.getElementById("executeTrigger");
const triggerResult = document.getElementById("triggerResult");

generatedAt.textContent = report.generatedAt ? `생성 시각 ${report.generatedAt}` : "리포트 없음";
authStatus.innerHTML = `
  <div>credentials ${report.auth.credentialsExists ? "연결됨" : "없음"}</div>
  <div>token ${report.auth.tokenExists ? "연결됨" : "없음"}</div>
  <div>drive token ${report.auth.driveTokenExists ? "연결됨" : "필요"}</div>
  <div>drive date ${escapeHtml(report.drive?.target_date || "-")} · ${report.drive?.date_folder_found ? "폴더 있음" : "폴더 없음"}</div>
  <div>default channel ${escapeHtml(report.channels?.default || "-")}</div>
  <div>${escapeHtml(report.auth.mode || "beta")}</div>
`;

if (triggerDate) {
  triggerDate.value = report.drive?.target_date || todayKey();
}

renderMetrics();
renderTriggerResult(loadStoredTriggerResult() || {
  type: "idle",
  message: "날짜 폴더 안의 채널 폴더를 기준으로 업로드 대상을 확인합니다.",
});
renderCards();

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((tab) => tab.classList.remove("active"));
    button.classList.add("active");
    activeFilter = button.dataset.filter;
    renderCards();
  });
});

document.querySelectorAll(".source-tab").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".source-tab").forEach((tab) => tab.classList.remove("active"));
    button.classList.add("active");
    activeSource = button.dataset.source;
    renderMetrics();
    renderCards();
  });
});

search.addEventListener("input", () => {
  searchText = search.value.trim().toLowerCase();
  renderCards();
});

setupFolders?.addEventListener("click", async () => {
  await runDashboardAction("drive", "/api/drive-setup");
});

writeTemplates?.addEventListener("click", async () => {
  await runDashboardAction("templates", "/api/drive-templates");
});

refreshScan?.addEventListener("click", async () => {
  await runDashboardAction("scan", "/api/scan", { reloadAfter: true });
});

previewTrigger?.addEventListener("click", async () => {
  await runDashboardAction("trigger", "/api/trigger-preview");
});

executeTrigger?.addEventListener("click", async () => {
  const confirmed = window.confirm("현재 날짜 폴더의 신규 영상을 각 채널에 private로 업로드합니다. 계속할까요?");
  if (!confirmed) return;
  await runDashboardAction("trigger", "/api/trigger-execute");
});

function renderMetrics() {
  const candidates = candidatesForSource(report.candidates || []);
  const summary = summarizeCandidates(candidates);
  const items = [
    [activeSource === "drive" ? "오늘 Drive 후보" : "전체 스캔 후보", summary.total],
    ["업로드 가능", summary.ready],
    ["검토 필요", summary.review],
    ["중복 차단", summary.duplicates],
    ["영상 오류", summary.videoFail],
  ];
  metrics.innerHTML = items
    .map(([label, value]) => `<article class="metric"><strong>${value}</strong><span>${label}</span></article>`)
    .join("");
}

function renderCards() {
  const candidates = candidatesForSource(report.candidates || []).filter(matchesFilter).filter(matchesSearch);
  if (!candidates.length) {
    grid.innerHTML = `<p class="empty">${emptyMessage()}</p>`;
    return;
  }
  grid.innerHTML = candidates.map(renderCard).join("");
}

function candidatesForSource(candidates) {
  if (activeSource === "all") return candidates;
  return candidates.filter((candidate) => candidate.item?.adapter === "google_drive_date");
}

function summarizeCandidates(candidates) {
  return candidates.reduce(
    (summary, candidate) => {
      summary.total += 1;
      if (candidate.upload_ready) summary.ready += 1;
      if (candidate.item?.policy?.requires_review) summary.review += 1;
      if (!candidate.video_probe?.ok) summary.videoFail += 1;
      if (!["new", "seen"].includes(candidate.duplicate_status)) summary.duplicates += 1;
      return summary;
    },
    { total: 0, ready: 0, review: 0, videoFail: 0, duplicates: 0 },
  );
}

function emptyMessage() {
  if (activeSource === "drive") {
    return "오늘 Drive 날짜 폴더에서 표시할 업로드 후보가 없습니다. 20260531/채널명 폴더 안에 영상과 JSON 또는 같은 이름 캡처 이미지를 넣은 뒤 스캔 갱신을 누르세요.";
  }
  return "표시할 후보가 없습니다.";
}

function matchesFilter(candidate) {
  if (activeFilter === "all") return true;
  if (activeFilter === "ready") return candidate.upload_ready;
  if (activeFilter === "review") return candidate.item.policy.requires_review;
  if (activeFilter === "fail") return !candidate.video_probe.ok;
  if (activeFilter === "duplicate") return !["new", "seen"].includes(candidate.duplicate_status);
  return true;
}

function matchesSearch(candidate) {
  if (!searchText) return true;
  const haystack = [
    candidate.item.source_project,
    candidate.item.source_title,
    candidate.seo.title,
    candidate.seo.description,
    ...(candidate.seo.tags || []),
    ...(candidate.seo.hashtags || []),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(searchText);
}

function renderCard(candidate) {
  const status = cardStatus(candidate);
  const probe = candidate.video_probe || {};
  const item = candidate.item || {};
  const seo = candidate.seo || {};
  return `
    <article class="card">
      <div class="card-head">
        <div>
          <h2>${escapeHtml(seo.title || item.video_name)}</h2>
          <div class="project">${escapeHtml(item.source_project)} · ${escapeHtml(item.adapter)} · ${escapeHtml(item.target_channel || report.channels?.default || "default")} · clip ${item.clip_index || "-"}</div>
        </div>
        <span class="status ${status.className}">${status.label}</span>
      </div>
      <div class="card-body">
        <div class="row"><div class="label">설명</div><div class="desc">${escapeHtml(seo.description || "")}</div></div>
        <div class="row"><div class="label">해시태그</div><div class="chips">${chips(seo.hashtags || [])}</div></div>
        <div class="row"><div class="label">태그</div><div class="chips">${chips(seo.tags || [])}</div></div>
        <div class="row"><div class="label">영상</div><div>${probe.width || "-"}x${probe.height || "-"} · ${fmt(probe.duration_sec)}초 · ${escapeHtml(probe.reason || "")}</div></div>
        <div class="row"><div class="label">중복</div><div>${escapeHtml(candidate.duplicate_status)} · ${escapeHtml(candidate.duplicate_reason)}</div></div>
        <div class="row"><div class="label">검토</div><div>${escapeHtml(item.policy.review_reason || "없음")}</div></div>
        <div class="row"><div class="label">파일</div><div class="path">${escapeHtml(item.video_path)}</div></div>
      </div>
    </article>
  `;
}

function cardStatus(candidate) {
  if (!candidate.video_probe.ok) return { className: "fail", label: "영상 실패" };
  if (isUploaded(candidate)) return { className: "complete", label: "업로드 완료" };
  if (!["new", "seen"].includes(candidate.duplicate_status)) return { className: "duplicate", label: "중복 차단" };
  if (candidate.upload_ready) return { className: "ready", label: "업로드 가능" };
  return { className: "review", label: "검토 필요" };
}

async function runDashboardAction(type, endpoint, options = {}) {
  const state = {
    type: "pending",
    message: actionLabel(type, endpoint),
  };
  renderTriggerResult(state);
  setActionBusy(true);
  try {
    const { response, payload } = await dashboardFetch(endpoint, {
      date: cleanDate(triggerDate?.value),
      allow_review: Boolean(allowReview?.checked),
    });
    if (!response.ok || !payload?.ok) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    const nextState = {
      type,
      result: payload.result || payload,
      savedAt: new Date().toLocaleString("ko-KR"),
    };
    saveStoredTriggerResult(nextState);
    renderTriggerResult(nextState);
    if (options.reloadAfter) {
      window.setTimeout(() => window.location.reload(), 900);
    }
  } catch (error) {
    renderTriggerResult({
      type: "error",
      message: error.message || String(error),
    });
  } finally {
    setActionBusy(false);
  }
}

async function dashboardFetch(endpoint, body, retry = true) {
  const headers = { "Content-Type": "application/json" };
  const token = window.localStorage.getItem("uploader:adminToken") || "";
  if (token) headers["X-Uploader-Admin-Token"] = token;
  const response = await fetch(endpoint, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (response.status === 401 && retry) {
    const nextToken = window.prompt("관리자 토큰을 입력하세요.");
    if (nextToken) {
      window.localStorage.setItem("uploader:adminToken", nextToken.trim());
      return dashboardFetch(endpoint, body, false);
    }
  }
  return { response, payload };
}

function renderTriggerResult(state) {
  if (!triggerResult) return;
  if (!state || state.type === "idle") {
    triggerResult.className = "trigger-result";
    triggerResult.innerHTML = `<span>${escapeHtml(state?.message || "")}</span>`;
    return;
  }
  if (state.type === "pending") {
    triggerResult.className = "trigger-result pending";
    triggerResult.innerHTML = `<span>${escapeHtml(state.message || "처리 중입니다.")}</span>`;
    return;
  }
  if (state.type === "error") {
    triggerResult.className = "trigger-result error";
    triggerResult.innerHTML = `<strong>오류</strong><span>${escapeHtml(state.message || "알 수 없는 오류")}</span>`;
    return;
  }
  if (state.type === "drive") {
    renderDriveResult(state);
    return;
  }
  if (state.type === "templates") {
    renderTemplateResult(state);
    return;
  }
  if (state.type === "scan") {
    renderScanResult(state);
    return;
  }
  renderUploadResult(state);
}

function renderTemplateResult(state) {
  const result = state.result || {};
  const channels = result.channels || [];
  triggerResult.className = "trigger-result success";
  triggerResult.innerHTML = `
    <div class="result-head">
      <strong>JSON 양식 배포 완료</strong>
      <span>${escapeHtml(result.date || cleanDate(triggerDate?.value) || "-")}</span>
    </div>
    <div class="result-note">${escapeHtml(result.template_name || "_metadata_template.json")} 파일을 채널 폴더 ${channels.length}개에 배포했습니다.</div>
  `;
}

function renderDriveResult(state) {
  const result = state.result || {};
  const channels = result.channels || [];
  triggerResult.className = "trigger-result success";
  triggerResult.innerHTML = `
    <div class="result-head">
      <strong>폴더 확인 완료</strong>
      <span>${escapeHtml(result.date || cleanDate(triggerDate?.value) || "-")}</span>
    </div>
    <div class="result-note">날짜 폴더와 채널 폴더 ${channels.length}개를 확인했습니다.</div>
  `;
}

function renderScanResult(state) {
  const summary = state.result?.summary || {};
  triggerResult.className = "trigger-result success";
  triggerResult.innerHTML = `
    <div class="result-head">
      <strong>스캔 갱신 완료</strong>
      <span>${escapeHtml(state.savedAt || "")}</span>
    </div>
    <div class="result-counts">
      ${countPill("전체", summary.total || 0)}
      ${countPill("업로드 가능", summary.ready || 0)}
      ${countPill("검토", summary.review || 0)}
      ${countPill("영상 실패", summary.videoFail || 0)}
    </div>
    <div class="result-note">리포트를 다시 불러옵니다.</div>
  `;
}

function renderUploadResult(state) {
  const result = state.result || {};
  const uploaded = result.uploaded || [];
  const failed = result.failed || [];
  const skipped = result.skipped || [];
  const completed = result.execute && uploaded.length > 0 && failed.length === 0;
  const processed = result.execute && uploaded.length === 0 && failed.length === 0;
  const title = completed
    ? "업로드 완료"
    : processed
      ? "처리 완료"
      : result.execute
        ? "업로드 실행 결과"
        : "미리보기 완료";
  triggerResult.className = `trigger-result ${completed || processed ? "complete" : failed.length ? "error" : "success"}`;
  triggerResult.innerHTML = `
    <div class="result-head">
      <strong>${escapeHtml(title)}</strong>
      <span>${escapeHtml(result.date || cleanDate(triggerDate?.value) || "-")}</span>
    </div>
    <div class="result-counts">
      ${countPill("후보", result.candidate_count || 0)}
      ${countPill("업로드", result.uploaded_count || 0)}
      ${countPill("스킵", result.skipped_count || 0)}
      ${countPill("실패", result.failed_count || 0)}
    </div>
    ${uploaded.length ? uploadedList(uploaded) : ""}
    ${failed.length ? issueList("실패", failed, "error") : ""}
    ${skipped.length ? issueList("스킵", skipped.slice(0, 6), "muted") : ""}
    ${!uploaded.length && !failed.length && !skipped.length ? `<div class="result-note">현재 날짜 폴더에 처리할 영상 후보가 없습니다.</div>` : ""}
  `;
}

function uploadedList(items) {
  return `
    <ul class="result-list uploaded">
      ${items
        .map(
          (item) => `
            <li>
              <span>${escapeHtml(item.channel_key || "-")}</span>
              <a href="${escapeHtml(item.url || "#")}" target="_blank" rel="noreferrer">${escapeHtml(item.title || item.url || "YouTube 영상")}</a>
            </li>
          `,
        )
        .join("")}
    </ul>
  `;
}

function issueList(label, items, className) {
  return `
    <div class="issue-list ${className}">
      <strong>${escapeHtml(label)}</strong>
      <ul>
        ${items
          .map(
            (item) => `<li>${escapeHtml(item.channel_key || "-")} · ${escapeHtml(item.title || "")} · ${escapeHtml(item.reason || item.error || "")}</li>`,
          )
          .join("")}
      </ul>
    </div>
  `;
}

function countPill(label, value) {
  return `<span class="count"><strong>${escapeHtml(value)}</strong>${escapeHtml(label)}</span>`;
}

function setActionBusy(isBusy) {
  [setupFolders, writeTemplates, refreshScan, previewTrigger, executeTrigger].forEach((button) => {
    if (button) button.disabled = isBusy;
  });
}

function actionLabel(type, endpoint) {
  if (type === "drive") return "구글 드라이브 날짜/채널 폴더를 확인하는 중입니다.";
  if (type === "templates") return "각 채널 폴더에 JSON 메타데이터 양식을 배포하는 중입니다.";
  if (type === "scan") return "날짜 폴더의 영상과 메타데이터를 다시 스캔하는 중입니다.";
  if (endpoint.includes("execute")) return "채널별 private 업로드를 실행하는 중입니다.";
  return "업로드 전 미리보기를 생성하는 중입니다.";
}

function cleanDate(value) {
  return String(value || "").replace(/\D/g, "").slice(0, 8);
}

function todayKey() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}${month}${day}`;
}

function isUploaded(candidate) {
  const status = String(candidate.duplicate_status || "");
  const reason = String(candidate.duplicate_reason || "");
  return status === "duplicate" && /이미 업로드|youtube|youtu\.be/i.test(reason);
}

function loadStoredTriggerResult() {
  try {
    const raw = window.localStorage.getItem("uploader:lastTriggerResult");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveStoredTriggerResult(value) {
  try {
    window.localStorage.setItem("uploader:lastTriggerResult", JSON.stringify(value));
  } catch {
    // Local storage can be unavailable in hardened browser profiles.
  }
}

function chips(values) {
  return values.map((value) => `<span class="chip">${escapeHtml(value)}</span>`).join("");
}

function fmt(value) {
  if (typeof value !== "number") return "-";
  return value.toFixed(1);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
