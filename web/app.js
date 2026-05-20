const steps = [
  { key: "download_youtube", label: "영상 다운로드" },
  { key: "extract_audio", label: "오디오 추출" },
  { key: "fetch_transcript", label: "음성 인식" },
  { key: "analyze", label: "AI 분석" },
  { key: "render", label: "클립 생성" },
];

const state = {
  view: "input",
  url: "",
  job: null,
  pollTimer: null,
  failure: null,
  selectedClips: new Set(),
  activeClipIndex: null,
  clipDrafts: new Map(),
};

const form = document.querySelector("#url-form");
const urlInput = document.querySelector("#youtube-url");
const stepList = document.querySelector("#step-list");
const overallProgress = document.querySelector("#overall-progress");
const videoTitle = document.querySelector("#video-title");
const videoMeta = document.querySelector("#video-meta");
const failureCard = document.querySelector("#failure-card");
const failureTitle = document.querySelector("#failure-title");
const failureMessage = document.querySelector("#failure-message");
const restartButton = document.querySelector("#restart-button");
const retryButton = document.querySelector("#retry-button");
const resultCard = document.querySelector("#result-card");
const resultSummary = document.querySelector("#result-summary");
const saveFeedback = document.querySelector("#save-feedback");
const candidateList = document.querySelector("#candidate-list");
const selectedCount = document.querySelector("#selected-count");
const selectAllButton = document.querySelector("#select-all-button");
const clearAllButton = document.querySelector("#clear-all-button");
const generateSelectedButton = document.querySelector("#generate-selected-button");
const detailPanel = document.querySelector("#detail-panel");
const detailKicker = document.querySelector("#detail-kicker");
const detailTitleHeading = document.querySelector("#detail-title-heading");
const detailTime = document.querySelector("#detail-time");
const detailTitleInput = document.querySelector("#detail-title-input");
const detailTitleSize = document.querySelector("#detail-title-size");
const detailTitleY = document.querySelector("#detail-title-y");
const detailTitleAlign = document.querySelector("#detail-title-align");
const detailTitleColorOptions = document.querySelectorAll("#detail-title-color-options .color-swatch");
const detailTitleStroke = document.querySelector("#detail-title-stroke");
const detailLayoutSelect = document.querySelector("#detail-layout-select");
const detailCropZoom = document.querySelector("#detail-crop-zoom");
const detailCropFocusX = document.querySelector("#detail-crop-focus-x");
const detailCropFocusY = document.querySelector("#detail-crop-focus-y");
const detailSafeZone = document.querySelector("#detail-safe-zone");
const detailSubtitleSize = document.querySelector("#detail-subtitle-size");
const detailSubtitleY = document.querySelector("#detail-subtitle-y");
const detailSubtitleBackground = document.querySelector("#detail-subtitle-background");
const detailChannelEnabled = document.querySelector("#detail-channel-enabled");
const detailChannelInput = document.querySelector("#detail-channel-input");
const detailChannelSize = document.querySelector("#detail-channel-size");
const detailTags = document.querySelector("#detail-tags");
const tagForm = document.querySelector("#tag-form");
const detailTagInput = document.querySelector("#detail-tag-input");
const detailVideo = document.querySelector("#detail-video");
const editPreview = document.querySelector("#edit-preview");
const previewTitleOverlay = document.querySelector("#preview-title-overlay");
const previewSubtitleOverlay = document.querySelector("#preview-subtitle-overlay");
const previewChannelOverlay = document.querySelector("#preview-channel-overlay");
const safeZoneFrame = document.querySelector(".safe-zone-frame");
const resetDetailButton = document.querySelector("#reset-detail-button");

const titleColorPresets = ["#ffd43b", "#ff8a00", "#ffffff"];

function getStepState(stepKey) {
  return state.job?.steps?.find((step) => step.key === stepKey);
}

function renderSteps() {
  stepList.innerHTML = "";
  steps.forEach((step) => {
    const stepState = getStepState(step.key) || {
      status: "pending",
      progress: 0,
    };
    const status = stepState.status;
    const progress = Number(stepState.progress || 0);
    const item = document.createElement("li");
    item.className = `step-item ${status}`;
    item.innerHTML = `
      <span class="status-mark">${status === "done" ? "✓" : status === "failed" ? "!" : ""}</span>
      <span class="step-label">${step.label}</span>
      <span class="bar"><span class="bar-fill" style="--progress:${progress}%"></span></span>
      <span class="step-percent">${Math.round(progress)}%</span>
    `;
    stepList.append(item);
  });
}

function render() {
  document.querySelector(".app-shell").dataset.view = state.view;
  failureCard.hidden = state.view !== "failed";
  resultCard.hidden = state.view !== "done";
  overallProgress.textContent = `${Math.round(state.job?.progress || 0)}%`;
  if (state.view !== "done") {
    saveFeedback.hidden = true;
    saveFeedback.textContent = "";
  }

  if (state.view === "input") {
    videoTitle.textContent = "대기 중";
    videoMeta.textContent = "URL을 입력하면 영상 확인을 시작합니다.";
  }

  if (state.view === "processing") {
    videoTitle.textContent = state.job?.result?.title || "영상 분석 중";
    videoMeta.textContent = "로컬 파이프라인이 작업을 실행하고 있습니다.";
  }

  if (state.view === "done") {
    videoTitle.textContent = state.job?.result?.title || "분석 완료";
    videoMeta.textContent = state.job?.result?.channel
      ? `${state.job.result.channel} | 렌더 완료`
      : "AI 추천 후킹 구간과 첫 렌더가 준비되었습니다.";
  }

  if (state.view === "failed" && state.failure) {
    failureTitle.textContent = state.failure.display.title;
    failureMessage.textContent = state.failure.display.errorMessage;
  }

  renderSteps();
  renderCandidates();
  renderDetailPanel();
}

function renderCandidates() {
  const clips = state.job?.result?.clips || [];
  candidateList.innerHTML = "";
  if (state.view !== "done" || clips.length === 0) {
    selectedCount.textContent = "0개 선택됨";
    return;
  }

  resultSummary.textContent = `${clips.length}개 후보가 준비되었습니다.`;
  selectedCount.textContent = `${state.selectedClips.size}개 선택됨`;
  generateSelectedButton.disabled = state.selectedClips.size === 0;

  clips.forEach((clip) => {
    const selected = state.selectedClips.has(clip.index);
    const draft = getClipDraft(clip.index);
    const active = state.activeClipIndex === clip.index;
    const card = document.createElement("article");
    card.className = `candidate-card ${selected ? "selected" : ""} ${active ? "active" : ""}`;
    card.tabIndex = 0;
    card.innerHTML = `
      <button type="button" class="candidate-check" aria-label="후보 선택">${selected ? "✓" : ""}</button>
      ${clip.mostReplayed ? '<span class="most-replayed-badge">가장 많이 본 구간</span>' : ""}
      <span class="candidate-index">#${clip.index}</span>
      <strong>${escapeHtml(draft.title)}</strong>
      <span class="candidate-meta">${formatTime(clip.startSec)} - ${formatTime(clip.endSec)} · ${Math.round(
        clip.durationSec
      )}초 · ${Math.round(clip.score * 10)}%</span>
      <span class="candidate-reason">${escapeHtml(clip.reason)}</span>
      <span class="candidate-tags">${draft.hashtags.map((tag) => `<em>${escapeHtml(tag)}</em>`).join("")}</span>
    `;
    card.addEventListener("click", () => setActiveCandidate(clip.index));
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        setActiveCandidate(clip.index);
      }
    });
    card.querySelector(".candidate-check").addEventListener("click", (event) => {
      event.stopPropagation();
      toggleCandidate(clip.index);
    });
    candidateList.append(card);
  });
}

function renderDetailPanel() {
  const clip = getActiveClip();
  detailPanel.hidden = state.view !== "done" || !clip;
  if (!clip) {
    return;
  }

  const draft = getClipDraft(clip.index);
  detailKicker.textContent = `#${clip.index} 상세 편집`;
  detailTitleHeading.textContent = draft.title;
  detailTime.textContent = `${formatTime(clip.startSec)} - ${formatTime(clip.endSec)}`;
  if (document.activeElement !== detailTitleInput) {
    detailTitleInput.value = draft.title;
  }
  detailTitleSize.value = draft.titleSize;
  detailTitleY.value = draft.titleY;
  detailTitleAlign.value = draft.titleAlign;
  detailTitleColorOptions.forEach((option) => {
    option.classList.toggle("active", option.dataset.color === draft.titleColor);
  });
  detailTitleStroke.checked = draft.titleStroke;
  detailLayoutSelect.value = draft.layout;
  detailCropZoom.value = draft.cropZoom;
  detailCropFocusX.value = draft.cropFocusX;
  detailCropFocusY.value = draft.cropFocusY;
  detailSafeZone.checked = draft.showSafeZone;
  detailSubtitleSize.value = draft.subtitleSize;
  detailSubtitleY.value = draft.subtitleY;
  detailSubtitleBackground.checked = draft.subtitleBackground;
  detailChannelEnabled.checked = draft.channelEnabled;
  if (document.activeElement !== detailChannelInput) {
    detailChannelInput.value = draft.channelName;
  }
  detailChannelSize.value = draft.channelSize;
  const previewUrl = getClipPreviewUrl(clip);
  if (previewUrl && detailVideo.getAttribute("src") !== previewUrl) {
    detailVideo.src = previewUrl;
  } else if (!previewUrl) {
    detailVideo.removeAttribute("src");
  }
  editPreview.dataset.layout = draft.layout;
  editPreview.dataset.titleAlign = draft.titleAlign;
  previewTitleOverlay.textContent = draft.title;
  previewTitleOverlay.style.fontSize = `${Math.round(Number(draft.titleSize) / 3)}px`;
  previewTitleOverlay.style.color = draft.titleColor;
  previewTitleOverlay.style.textAlign = draft.titleAlign;
  previewTitleOverlay.style.textShadow = draft.titleStroke ? "0 2px 0 #000, 0 0 6px #000" : "none";
  previewTitleOverlay.style.top = `${draft.titleY}%`;
  previewTitleOverlay.style.bottom = "auto";
  previewTitleOverlay.style.transform = "translateY(-50%)";
  previewSubtitleOverlay.style.fontSize = `${Math.round(Number(draft.subtitleSize) / 2.5)}px`;
  previewSubtitleOverlay.style.background = draft.subtitleBackground ? "rgba(0, 0, 0, 0.68)" : "transparent";
  previewSubtitleOverlay.textContent = clip.sourceText.split(" ").slice(0, 8).join(" ");
  previewSubtitleOverlay.style.top = `${draft.subtitleY}%`;
  previewSubtitleOverlay.style.bottom = "auto";
  previewSubtitleOverlay.style.transform = "translateY(-50%)";
  previewChannelOverlay.hidden = !draft.channelEnabled;
  previewChannelOverlay.textContent = draft.channelName;
  previewChannelOverlay.style.fontSize = `${Math.round(Number(draft.channelSize) / 2.2)}px`;
  safeZoneFrame.hidden = !draft.showSafeZone;
  detailVideo.style.objectPosition = `${Number(draft.cropFocusX) * 100}% ${Number(draft.cropFocusY) * 100}%`;
  detailVideo.style.transformOrigin = `${Number(draft.cropFocusX) * 100}% ${Number(draft.cropFocusY) * 100}%`;
  detailVideo.style.transform = draft.layout === "crop" ? `scale(${Number(draft.cropZoom)})` : "none";
  detailTags.innerHTML = "";
  draft.hashtags.forEach((tag) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "editable-tag";
    chip.innerHTML = `${escapeHtml(tag)} <span aria-hidden="true">×</span>`;
    chip.addEventListener("click", () => removeTag(clip.index, tag));
    detailTags.append(chip);
  });
}

function getClipPreviewUrl(clip) {
  const rendered = state.job?.result?.selectedRender?.renders?.find((item) => item.index === clip.index);
  if (rendered?.outputUrl) {
    return rendered.outputUrl;
  }
  if (state.job?.result?.inputUrl) {
    return `${state.job.result.inputUrl}#t=${clip.startSec},${clip.endSec}`;
  }
  return state.job?.result?.renderUrl || "";
}

function getActiveClip() {
  return (state.job?.result?.clips || []).find((clip) => clip.index === state.activeClipIndex) || null;
}

function setActiveCandidate(index) {
  state.activeClipIndex = index;
  renderCandidates();
  renderDetailPanel();
}

function getClipDraft(index) {
  const clip = (state.job?.result?.clips || []).find((item) => item.index === index);
  if (!state.clipDrafts.has(index)) {
    state.clipDrafts.set(index, buildDefaultDraft(clip));
  }
  return state.clipDrafts.get(index);
}

function buildDefaultDraft(clip) {
  return {
      title: clip?.title || "",
      hashtags: [...(clip?.hashtags || [])],
      layout: "letterbox",
      cropFocusX: 0.5,
      cropFocusY: 0.5,
      cropZoom: 1,
      showSafeZone: true,
      titleSize: 72,
      titleY: 12,
      titleAlign: "center",
      titleColor: "#ffffff",
      titleStroke: true,
      subtitleSize: 48,
      subtitleY: 72,
      subtitleBackground: true,
      channelEnabled: true,
      channelName: state.job?.result?.channel || "@MyChannel",
      channelSize: 42,
  };
}

function updateDraft(index, patch) {
  const draft = getClipDraft(index);
  state.clipDrafts.set(index, { ...draft, ...patch });
  renderCandidates();
  renderDetailPanel();
}

function removeTag(index, tag) {
  const draft = getClipDraft(index);
  updateDraft(index, { hashtags: draft.hashtags.filter((item) => item !== tag) });
}

function addTag(index, tag) {
  const normalized = tag.trim().replace(/^#+/, "");
  if (!normalized) {
    return;
  }
  const value = `#${normalized}`;
  const draft = getClipDraft(index);
  if (draft.hashtags.includes(value)) {
    return;
  }
  updateDraft(index, { hashtags: [...draft.hashtags, value] });
}

function toggleCandidate(index) {
  if (state.selectedClips.has(index)) {
    state.selectedClips.delete(index);
  } else {
    state.selectedClips.add(index);
  }
  renderCandidates();
}

function formatTime(seconds) {
  const value = Number(seconds || 0);
  const minute = Math.floor(value / 60);
  const second = Math.floor(value % 60);
  return `${String(minute).padStart(2, "0")}:${String(second).padStart(2, "0")}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function resetToInput() {
  window.clearInterval(state.pollTimer);
  state.view = "input";
  state.job = null;
  state.failure = null;
  state.selectedClips = new Set();
  state.activeClipIndex = null;
  state.clipDrafts = new Map();
  saveFeedback.hidden = true;
  saveFeedback.textContent = "";
  urlInput.focus();
  render();
}

function failFromState(failure) {
  window.clearInterval(state.pollTimer);
  state.view = "failed";
  state.failure = failure;
  render();
}

async function startJob(url) {
  window.clearInterval(state.pollTimer);
  state.url = url.trim();
  state.view = "processing";
  state.failure = null;
  state.selectedClips = new Set();
  state.activeClipIndex = null;
  state.clipDrafts = new Map();
  saveFeedback.hidden = true;
  saveFeedback.textContent = "";
  state.job = {
    progress: 0,
    steps: steps.map((step) => ({
      ...step,
      status: "pending",
      progress: 0,
    })),
  };
  render();

  try {
    const response = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: state.url }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "작업을 시작하지 못했습니다.");
    }
    state.job = payload;
    render();
    pollJob(payload.id);
  } catch (error) {
    failFromState(buildClientFailure(error.message));
  }
}

function pollJob(jobId) {
  window.clearInterval(state.pollTimer);
  state.pollTimer = window.setInterval(async () => {
    try {
      const response = await fetch(`/api/jobs/${jobId}`);
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "작업 상태를 가져오지 못했습니다.");
      }
      state.job = payload;
      if (payload.status === "failed") {
        failFromState(payload.failure);
        return;
      }
      if (payload.status === "done") {
        window.clearInterval(state.pollTimer);
        state.view = "done";
        const clips = payload.result?.clips || [];
        state.selectedClips = new Set(clips.map((clip) => clip.index));
        state.activeClipIndex = clips[0]?.index || null;
      }
      render();
    } catch (error) {
      failFromState(buildClientFailure(error.message));
    }
  }, 1200);
}

function buildClientFailure(message) {
  return {
    status: "failed",
    step: "download_youtube",
    display: {
      title: "작업 실행 실패",
      errorMessage: message,
      actions: [
        { id: "restart", label: "처음으로", type: "navigate", target: "url_input" },
        { id: "retry", label: "다시 실행", type: "command", args: { url: state.url } },
      ],
    },
  };
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const url = urlInput.value.trim();
  if (!url) {
    urlInput.focus();
    return;
  }
  startJob(url);
});

restartButton.addEventListener("click", () => {
  resetToInput();
});

retryButton.addEventListener("click", () => {
  const retryUrl = state.failure?.display.actions.find((action) => action.id === "retry")?.args.url || state.url;
  startJob(retryUrl);
});

selectAllButton.addEventListener("click", () => {
  state.selectedClips = new Set((state.job?.result?.clips || []).map((clip) => clip.index));
  renderCandidates();
});

clearAllButton.addEventListener("click", () => {
  state.selectedClips = new Set();
  renderCandidates();
});

generateSelectedButton.addEventListener("click", () => {
  renderSelectedClips();
});

async function renderSelectedClips() {
  const selected = Array.from(state.selectedClips).sort((a, b) => a - b);
  if (!state.job?.id || selected.length === 0) {
    return;
  }
  const originalLabel = generateSelectedButton.textContent;
  generateSelectedButton.disabled = true;
  generateSelectedButton.textContent = "생성 중";
  resultSummary.textContent = `${selected.length}개 클립을 렌더링하고 있습니다.`;
  saveFeedback.hidden = true;
  saveFeedback.textContent = "";

  const clips = selected.map((index) => ({
    index,
    ...getClipDraft(index),
  }));

  try {
    const response = await fetch(`/api/jobs/${state.job.id}/render-selected`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clips }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "선택된 클립을 생성하지 못했습니다.");
    }
    state.job.result.selectedRender = payload;
    resultSummary.textContent = "저장 되었습니다";
    saveFeedback.hidden = false;
    saveFeedback.textContent = `${payload.count}개 클립이 ${payload.exportDir || "저장 폴더"}에 저장 되었습니다.`;
    renderDetailPanel();
  } catch (error) {
    failFromState(buildClientFailure(error.message));
  } finally {
    generateSelectedButton.textContent = originalLabel.trim() || "선택된 클립 생성";
    generateSelectedButton.disabled = state.selectedClips.size === 0;
  }
}

detailTitleInput.addEventListener("input", () => {
  if (!state.activeClipIndex) {
    return;
  }
  updateDraft(state.activeClipIndex, { title: detailTitleInput.value });
});

detailTitleSize.addEventListener("input", () => {
  if (!state.activeClipIndex) {
    return;
  }
  updateDraft(state.activeClipIndex, { titleSize: Number(detailTitleSize.value) });
});

detailTitleY.addEventListener("input", () => {
  if (!state.activeClipIndex) {
    return;
  }
  updateDraft(state.activeClipIndex, { titleY: Number(detailTitleY.value) });
});

detailTitleAlign.addEventListener("change", () => {
  if (!state.activeClipIndex) {
    return;
  }
  updateDraft(state.activeClipIndex, { titleAlign: detailTitleAlign.value });
});

detailTitleColorOptions.forEach((option) => {
  option.style.setProperty("--swatch-color", option.dataset.color);
  option.addEventListener("click", () => {
    if (!state.activeClipIndex) {
      return;
    }
    const color = titleColorPresets.includes(option.dataset.color) ? option.dataset.color : "#ffffff";
    updateDraft(state.activeClipIndex, { titleColor: color });
  });
});

detailTitleStroke.addEventListener("change", () => {
  if (!state.activeClipIndex) {
    return;
  }
  updateDraft(state.activeClipIndex, { titleStroke: detailTitleStroke.checked });
});

detailLayoutSelect.addEventListener("change", () => {
  if (!state.activeClipIndex) {
    return;
  }
  updateDraft(state.activeClipIndex, { layout: detailLayoutSelect.value });
});

detailCropZoom.addEventListener("input", () => {
  if (!state.activeClipIndex) {
    return;
  }
  updateDraft(state.activeClipIndex, { cropZoom: Number(detailCropZoom.value) });
});

detailCropFocusX.addEventListener("input", () => {
  if (!state.activeClipIndex) {
    return;
  }
  updateDraft(state.activeClipIndex, { cropFocusX: Number(detailCropFocusX.value) });
});

detailCropFocusY.addEventListener("input", () => {
  if (!state.activeClipIndex) {
    return;
  }
  updateDraft(state.activeClipIndex, { cropFocusY: Number(detailCropFocusY.value) });
});

detailSafeZone.addEventListener("change", () => {
  if (!state.activeClipIndex) {
    return;
  }
  updateDraft(state.activeClipIndex, { showSafeZone: detailSafeZone.checked });
});

detailSubtitleSize.addEventListener("input", () => {
  if (!state.activeClipIndex) {
    return;
  }
  updateDraft(state.activeClipIndex, { subtitleSize: Number(detailSubtitleSize.value) });
});

detailSubtitleY.addEventListener("input", () => {
  if (!state.activeClipIndex) {
    return;
  }
  updateDraft(state.activeClipIndex, { subtitleY: Number(detailSubtitleY.value) });
});

detailSubtitleBackground.addEventListener("change", () => {
  if (!state.activeClipIndex) {
    return;
  }
  updateDraft(state.activeClipIndex, { subtitleBackground: detailSubtitleBackground.checked });
});

detailChannelEnabled.addEventListener("change", () => {
  if (!state.activeClipIndex) {
    return;
  }
  updateDraft(state.activeClipIndex, { channelEnabled: detailChannelEnabled.checked });
});

detailChannelInput.addEventListener("input", () => {
  if (!state.activeClipIndex) {
    return;
  }
  updateDraft(state.activeClipIndex, { channelName: detailChannelInput.value });
});

detailChannelSize.addEventListener("input", () => {
  if (!state.activeClipIndex) {
    return;
  }
  updateDraft(state.activeClipIndex, { channelSize: Number(detailChannelSize.value) });
});

resetDetailButton.addEventListener("click", () => {
  const clip = getActiveClip();
  if (!clip) {
    return;
  }
  state.clipDrafts.set(clip.index, buildDefaultDraft(clip));
  renderCandidates();
  renderDetailPanel();
});

tagForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!state.activeClipIndex) {
    return;
  }
  addTag(state.activeClipIndex, detailTagInput.value);
  detailTagInput.value = "";
});

urlInput.value = "";
render();
