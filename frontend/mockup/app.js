const API_BASE = window.location.protocol === "file:"
  ? "http://127.0.0.1:8000/api/v1"
  : `${window.location.origin}/api/v1`;
const projectName = "THE_TRAP";
const placeholderPreview = "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?auto=format&fit=crop&w=1200&q=80";
const LOCAL_CACHE_TTL_MS = 1000 * 60 * 15;
const LOCAL_CACHE_VERSION = "vis-review-v10";

let scenes = [];
let sceneShots = {};
let sceneLoadPromises = {};
let shotDetailPromises = {};
let currentProject = projectName;
let currentSceneCode = null;
let selectedSceneCodes = new Set();
let selectedShotCode = null;
let activeStatusFilters = new Set(["ALL"]);
let currentView = "scenes";
let searchQuery = "";
let allShotsMode = false;

const projectList = document.getElementById("projectList");
const shotTable = document.getElementById("shotTable");
const stepList = document.getElementById("stepList");
const metaGrid = document.getElementById("metaGrid");
const paneResizer = document.getElementById("paneResizer");
const appShell = document.querySelector(".app-shell");
const updateButton = document.getElementById("updateButton");
const sceneOverviewButton = document.getElementById("sceneOverviewButton");
const searchInput = document.getElementById("searchInput");

function getCache(key) {
  try {
    const raw = localStorage.getItem(`${LOCAL_CACHE_VERSION}:${key}`);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    if (!parsed.savedAt || Date.now() - parsed.savedAt > LOCAL_CACHE_TTL_MS) {
      localStorage.removeItem(`${LOCAL_CACHE_VERSION}:${key}`);
      return null;
    }
    return parsed.data;
  } catch {
    return null;
  }
}

function setCache(key, data) {
  try {
    localStorage.setItem(`${LOCAL_CACHE_VERSION}:${key}`, JSON.stringify({ savedAt: Date.now(), data }));
  } catch {
    // ignore localStorage quota issues
  }
}

function isOmitValue(value) {
  return /omit|omitted|오밋|제외/i.test(String(value || ""));
}

function hasMeaningfulShotData(shot) {
  const hasDetailText = [
    shot.shotDescription,
    shot.directionLighting,
    shot.retakeNote,
    shot.cam,
  ].some((value) => String(value || "").trim());
  const hasDuration = Number(shot.duration) > 0;
  const hasUsefulTask = (shot.visualStatuses || []).some((task) => {
    return [task.artist, task.status].some((value) => {
      const text = String(value || "").trim().toLowerCase();
      return text && text !== "none" && text !== "app" && !isOmitValue(text);
    });
  });
  return hasDuration || hasDetailText || hasUsefulTask;
}

function filterOmittedScenes(items) {
  return (items || []).filter((scene) => {
    return ![scene.scene_code, scene.scene_label, scene.shotlist_name].some(isOmitValue);
  });
}

function filterOmittedShots(items) {
  return (items || []).filter((shot) => {
    return ![shot.shot_code, shot.shotCode, shot.title].some(isOmitValue)
      && shot.summaryBucket !== "OMIT"
      && hasMeaningfulShotData(shot);
  });
}

function buildSceneFromApi(rawScene) {
  const sceneCode = normalizeSceneCode(rawScene.scene_code);
  return {
    ...rawScene,
    scene_code: sceneCode,
    compositingProgress: rawScene.compositing_progress ?? rawScene.compositingProgress ?? null,
  };
}

function renderProjects() {
  projectList.innerHTML = "";
  sceneOverviewButton?.classList.toggle("active", currentView === "scenes");

  const allButton = document.createElement("button");
  allButton.className = `project-card project-card-all ${allShotsMode ? "active" : ""}`;
  allButton.innerHTML = "<strong>ALL</strong>";
  allButton.addEventListener("click", selectAllShots);
  projectList.appendChild(allButton);

  scenes.forEach((scene) => {
    const button = document.createElement("button");
    button.className = `project-card ${!allShotsMode && currentView === "shots" && selectedSceneCodes.has(scene.scene_code) ? "active" : ""} ${sceneProgressClass(scene.compositingProgress)}`;
    button.innerHTML = `
      <strong>${formatSceneCode(scene.scene_code)}</strong>
    `;
    button.addEventListener("click", (event) => {
      selectScene(scene.scene_code, event);
    });
    button.addEventListener("dblclick", (event) => {
      event.preventDefault();
      openSceneShotList(scene.scene_code);
    });
    button.addEventListener("auxclick", (event) => {
      if (event.button === 1) {
        event.preventDefault();
        openSceneShotList(scene.scene_code);
      }
    });
    projectList.appendChild(button);
  });
}

function renderShotTable() {
  shotTable.innerHTML = "";
  renderShotHeader();
  const sourceShots = getCurrentShotScope();
  const currentShots = getVisibleShots(sourceShots).filter(matchesShotSearch);
  document.getElementById("shotGridTitle").textContent = shotGridTitle();
  document.getElementById("projectTitle").textContent = "";

  currentShots.forEach((shot) => {
    const row = document.createElement("article");
    row.className = `table-row ${shotRowStateClass(shot)} ${shot.shotCode === selectedShotCode ? "active" : ""}`;
    row.innerHTML = `
      <div class="shot-primary">
        <strong>${shot.shotCode.split("_").pop()}</strong>
        <span>${shot.shotCode}</span>
      </div>
      <div class="preview-cell">
        ${renderThumbMarkup(shot.cachedPreviewImage, "table-preview-thumb", shot.previewImage)}
        <button class="anim-link" type="button" onclick="event.stopPropagation(); openAnim('${shot.shotCode}', '${shot.sequence}')">Anim</button>
      </div>
      <div>${renderShotLevelBadge(shot.shotLevel)}</div>
      <div>${shot.duration}f</div>
      <div>${shot.cam || "-"}</div>
      ${renderTaskCell(shot, /ani.*dt/i)}
      ${renderTaskCell(shot, /ani.*pl/i)}
      ${renderTaskCell(shot, /ani.*ao/i)}
      ${renderTaskCell(shot, /cfx|cloth/i)}
      ${renderTaskCell(shot, /water/i)}
      ${renderTaskCell(shot, /render/i)}
      ${renderTaskCell(shot, /composit/i)}
      <div>${renderThumbMarkup(shot.renderPreview, "table-render-thumb")}</div>
      <div><button class="table-action ${shot.renderable ? "" : "disabled"}">${shot.renderable ? "Render" : "Check"}</button></div>
    `;

    row.addEventListener("click", () => {
      selectedShotCode = shot.shotCode;
      updateDashboard();
    });

    const actionButton = row.querySelector(".table-action");
    actionButton.addEventListener("click", (event) => {
      event.stopPropagation();
      selectedShotCode = shot.shotCode;
      updateDashboard();
    });

    shotTable.appendChild(row);
  });
}

function renderSceneTable() {
  shotTable.innerHTML = "";
  renderSceneHeader();
  document.getElementById("shotGridTitle").textContent = "Scene List";
  document.getElementById("projectTitle").textContent = "";

  getVisibleScenes().forEach((scene) => {
    const row = document.createElement("article");
    row.className = `table-row scene-table-row ${sceneProgressClass(scene.compositingProgress)}`;
    row.innerHTML = `
      <div class="shot-primary">
        <strong>${scene.scene_code}</strong>
        <span>${scene.scene_label || "-"}</span>
      </div>
      <div>${scene.total_shots ?? "-"}</div>
      <div>${formatSceneDuration(scene)}</div>
      <div>${scene.total_frames ?? "-"}</div>
      <div>${formatPercent(scene.compositingProgress)}</div>
      <div class="scene-sheet-name">${scene.shotlist_name || "-"}</div>
    `;
    row.addEventListener("click", () => {
      selectScene(scene.scene_code);
    });
    row.addEventListener("dblclick", () => openSceneShotList(scene.scene_code));
    row.addEventListener("auxclick", (event) => {
      if (event.button === 1) {
        event.preventDefault();
        openSceneShotList(scene.scene_code);
      }
    });
    shotTable.appendChild(row);
  });
}

function renderShotHeader() {
  document.querySelector(".table-header").className = "table-header";
  document.querySelector(".table-header").innerHTML = `
    <span>Shot</span>
    <span>Preview</span>
    <span>Level</span>
    <span>Duration</span>
    <span>Cam</span>
    <span>ANI DT</span>
    <span>ANI PL</span>
    <span>ANI AO</span>
    <span>CFX Cloth</span>
    <span>FX Water</span>
    <span>Rendering</span>
    <span>Compositing</span>
    <span>Render Preview</span>
    <span>Action</span>
  `;
  document.querySelector(".shot-grid-legend").style.display = "";
}

function renderSceneHeader() {
  document.querySelector(".table-header").className = "table-header scene-table-header";
  document.querySelector(".table-header").innerHTML = `
    <span>Scene</span>
    <span>Shots</span>
    <span>Duration</span>
    <span>Frames</span>
    <span>COM</span>
    <span>Shot List</span>
  `;
  document.querySelector(".shot-grid-legend").style.display = "none";
}

function renderDetailPanel() {
  const currentShots = getVisibleShots(getCurrentShotScope()).filter(matchesShotSearch);
  const shot = currentShots.find((item) => item.shotCode === selectedShotCode);
  if (!shot) {
    clearDetailPanel();
    return;
  }

  document.getElementById("projectTitle").textContent = "";
  document.getElementById("detailShotCode").textContent = shot.shotCode;
  const detailPreviewImage = document.getElementById("previewImage");
  detailPreviewImage.onerror = () => {
    if (shot.previewImage && detailPreviewImage.src !== shot.previewImage) {
      detailPreviewImage.src = shot.previewImage;
      return;
    }
    detailPreviewImage.src = placeholderPreview;
  };
  detailPreviewImage.src = shot.cachedPreviewImage || shot.previewImage || placeholderPreview;

  if (!shot.detailLoaded && !shot.detailLoading) {
    loadShotDetail(shot);
  }

  const metaItems = [
    ["Shot Description", shot.detailLoading ? "Loading..." : shot.shotDescription || "-"],
    ["Direction Note", shot.detailLoading ? "Loading..." : shot.directionLighting || "-"],
    ["Retake Note", shot.detailLoading ? "Loading..." : shot.retakeNote || "-"],
  ];

  metaGrid.innerHTML = "";
  metaItems.forEach(([label, value]) => {
    const card = document.createElement("div");
    card.className = "meta-card";
    const labelElement = document.createElement("span");
    const valueElement = document.createElement("strong");
    labelElement.textContent = label;
    valueElement.textContent = value;
    card.append(labelElement, valueElement);
    metaGrid.appendChild(card);
  });
}

function updateMetrics() {
  if (currentView === "scenes") {
    const visibleScenes = getVisibleScenes();
    const done = visibleScenes.filter((scene) => Number(scene.compositingProgress) >= 100).length;
    const mid = visibleScenes.filter((scene) => Number(scene.compositingProgress) >= 50 && Number(scene.compositingProgress) < 100).length;
    const low = visibleScenes.filter((scene) => Number(scene.compositingProgress) > 0 && Number(scene.compositingProgress) < 50).length;
    const none = visibleScenes.length - done - mid - low;

    document.getElementById("totalCount").textContent = String(visibleScenes.length);
    document.getElementById("appCount").textContent = String(done);
    document.getElementById("openCount").textContent = String(none);
    document.getElementById("wipCount").textContent = String(mid);
    document.getElementById("readyCount").textContent = String(low);
    document.getElementById("retakeCount").textContent = "0";
    updateWorkingDayTotal([]);
    updateOverviewActiveState();
    return;
  }

  const shots = getCurrentShotScope().filter(matchesShotSearch);
  const displayedShots = getVisibleShots(shots);

  const total = shots.length;
  const app = shots.filter((shot) => shot.summaryBucket === "APP").length;
  const open = shots.filter((shot) => shot.summaryBucket === "OPEN").length;
  const wip = shots.filter((shot) => shot.summaryBucket === "WIP").length;
  const ready = shots.filter((shot) => shot.summaryBucket === "READY").length;
  const retake = shots.filter((shot) => shot.summaryBucket === "RETAKE").length;

  document.getElementById("totalCount").textContent = String(total);
  document.getElementById("appCount").textContent = String(app);
  document.getElementById("openCount").textContent = String(open);
  document.getElementById("wipCount").textContent = String(wip);
  document.getElementById("readyCount").textContent = String(ready);
  document.getElementById("retakeCount").textContent = String(retake);
  updateWorkingDayTotal(displayedShots);
  updateOverviewActiveState();
}

function updateWorkingDayTotal(shots) {
  const element = document.getElementById("workingDayTotal");
  if (!element) {
    return;
  }
  const totalDays = (shots || []).reduce((sum, shot) => {
    return sum + Number(shot.shotLevel?.staffDays || 0);
  }, 0);
  element.textContent = `Working day total ${totalDays.toFixed(1)}d`;
}

function updateDashboard() {
  renderProjects();
  updateMetrics();
  if (currentView === "scenes") {
    renderSceneTable();
    clearDetailPanel();
    return;
  }
  renderShotTable();
  renderDetailPanel();
}

function getVisibleShots(shots) {
  if (activeStatusFilters.has("ALL")) {
    return shots;
  }
  return shots.filter((shot) => activeStatusFilters.has(shot.summaryBucket));
}

function getCurrentShotScope() {
  if (allShotsMode) {
    return scenes.flatMap((scene) => sceneShots[scene.scene_code] || []);
  }
  return [...selectedSceneCodes].flatMap((sceneCode) => sceneShots[sceneCode] || []);
}

function shotGridTitle() {
  if (allShotsMode) {
    return "All Scenes";
  }
  const selected = [...selectedSceneCodes];
  if (selected.length === 1) {
    return `Scene ${selected[0]}`;
  }
  if (selected.length > 1) {
    return `Scenes ${selected.join(", ")}`;
  }
  return "Scene Shots";
}

function getVisibleScenes() {
  return scenes.filter(matchesSceneSearch);
}

function updateOverviewActiveState() {
  document.querySelectorAll("[data-filter]").forEach((button) => {
    button.classList.toggle("active", currentView === "shots" && activeStatusFilters.has(button.dataset.filter));
  });
}

function clearDetailPanel() {
  document.getElementById("detailShotCode").textContent = "-";
  metaGrid.innerHTML = "";
}

function labelFor(status) {
  const labels = {
    ready: "Ready",
    running: "Running",
    blocked: "Blocked",
    waiting: "Waiting",
    done: "Done",
  };
  return labels[status] || status;
}

function renderThumbMarkup(src, className, fallbackSrc) {
  if (!src) {
    return '<div class="table-thumb-empty">none</div>';
  }
  const fallback = fallbackSrc || placeholderPreview;
  return `<img src="${src}" alt="preview" class="${className}" onerror="this.onerror=null; this.src='${fallback}'">`;
}

function renderTaskCell(shot, matcher) {
  const task = findTaskStatus(shot, matcher);
  const status = normalizeVisualStatus(task?.status);
  const artist = normalizeArtist(task?.artist);
  return `
    <div class="task-cell">
      <strong class="artist-badge ${artistClass(artist)}">${artist}</strong>
      <span class="task-status ${status.className}">${status.label}</span>
    </div>
  `;
}

function shotRowStateClass(shot) {
  const renderStatus = normalizeVisualStatus(findTaskStatus(shot, /render/i)?.status).bucket;
  const compStatus = normalizeVisualStatus(findTaskStatus(shot, /composit/i)?.status).bucket;
  const pair = [renderStatus, compStatus];
  if (pair.includes("OMIT")) {
    return "row-omit";
  }
  if (pair.includes("RETAKE")) {
    return "row-retake";
  }
  if (pair.includes("WIP")) {
    return "row-wip";
  }
  if (pair.every((status) => status === "APP")) {
    return "row-app";
  }
  if (pair.every((status) => status === "READY" || status === "APP")) {
    return "row-ready";
  }
  return "";
}

function artistClass(value) {
  const normalizedArtist = normalizeArtist(value);
  const artist = normalizedArtist.toUpperCase();
  const aliases = {
    "초롱": "artist-ckr",
    "김초롱": "artist-ckr",
    "다슬": "artist-sds",
    "성다슬": "artist-sds",
    "가현": "artist-lgh",
    "이가현": "artist-lgh",
    "지원": "artist-sjw",
    "신지원": "artist-sjw",
  };
  if (artist === "HSH") return "artist-hsh";
  if (artist === "CKR" || artist === "KCR") return "artist-ckr";
  if (artist === "SDS") return "artist-sds";
  if (artist === "LGH") return "artist-lgh";
  if (artist === "SJW") return "artist-sjw";
  return aliases[normalizedArtist] || "";
}

function sceneProgressClass(value) {
  const progress = Number(value);
  if (!Number.isFinite(progress) || progress <= 0) {
    return "";
  }
  if (progress >= 100) {
    return "scene-progress-done";
  }
  if (progress >= 50) {
    return "scene-progress-mid";
  }
  return "scene-progress-low";
}

function formatSceneCode(sceneCode) {
  return normalizeSceneCode(sceneCode);
}

function normalizeSceneCode(sceneCode) {
  const match = String(sceneCode || "").match(/\d{4}/);
  return match ? match[0] : String(sceneCode || "");
}

function formatSceneDuration(scene) {
  if (scene.total_minutes != null) {
    return `${Number(scene.total_minutes).toFixed(1)}m`;
  }
  if (scene.total_seconds != null) {
    return `${Number(scene.total_seconds).toFixed(1)}s`;
  }
  return "-";
}

function formatPercent(value) {
  const progress = Number(value);
  return Number.isFinite(progress) ? `${progress.toFixed(1)}%` : "-";
}

function matchesSceneSearch(scene) {
  const query = searchQuery.trim().toLowerCase();
  if (!query) {
    return true;
  }
  return [
    scene.scene_code,
    scene.scene_label,
    scene.shotlist_name,
    scene.total_shots,
    scene.total_frames,
    scene.compositingProgress,
  ].some((value) => String(value ?? "").toLowerCase().includes(query));
}

function matchesShotSearch(shot) {
  const query = searchQuery.trim().toLowerCase();
  if (!query) {
    return true;
  }
  const taskText = (shot.visualStatuses || [])
    .map((task) => `${task.label || ""} ${task.artist || ""} ${task.status || ""}`)
    .join(" ");
  return [
    shot.shotCode,
    shot.artist,
    shot.cam,
    shot.duration,
    shot.statusLabel,
    shot.shotDescription,
    shot.directionLighting,
    shot.retakeNote,
    taskText,
  ].some((value) => String(value ?? "").toLowerCase().includes(query));
}

function renderShotLevelBadge(level) {
  const shotLevel = level || calculateShotLevel([], 0);
  return `
    <div class="shot-level shot-level-${shotLevel.waterLevel}">
      <strong>${shotLevel.label.split(" ")[0]}</strong>
      <span>${shotLevel.staffDays.toFixed(1)}d</span>
    </div>
  `;
}

function formatShotLevel(level) {
  const shotLevel = level || calculateShotLevel([], 0);
  const durationSuffix = shotLevel.durationWeight ? ` + ${shotLevel.durationWeight.toFixed(2)} duration` : "";
  return `${shotLevel.label} / staff ${shotLevel.staffDays.toFixed(2)}d / lead ${shotLevel.leadDays.toFixed(2)}d / score ${shotLevel.score.toFixed(2)}${durationSuffix}`;
}

function normalizeArtist(value) {
  const raw = String(value || "").trim();
  return !raw || raw.toLowerCase() === "none" ? "-" : raw;
}

function findTaskStatus(shot, matcher) {
  return (shot.visualStatuses || []).find((task) => matcher.test(task.label || task.task_key || ""));
}

function normalizeVisualStatus(value) {
  const raw = String(value || "").trim();
  const normalized = raw.toLowerCase();
  if (!raw || normalized === "-") {
    return { label: "open", bucket: "OPEN", className: "status-text-open" };
  }
  if (normalized === "none") {
    return { label: "app", bucket: "APP", className: "status-text-app" };
  }
  if (/omit|omitted/i.test(normalized)) {
    return { label: raw, bucket: "OMIT", className: "status-text-omit" };
  }
  if (/retake|fix|^re$/i.test(normalized)) {
    return { label: raw, bucket: "RETAKE", className: "status-text-retake" };
  }
  if (/wip|review|ren|render/i.test(normalized)) {
    return { label: raw, bucket: "WIP", className: "status-text-wip" };
  }
  if (/ready|rdy/i.test(normalized)) {
    return { label: raw, bucket: "READY", className: "status-text-ready" };
  }
  if (/app|approved|pub|cbb/i.test(normalized)) {
    return { label: raw, bucket: "APP", className: "status-text-app" };
  }
  if (/open|hold/i.test(normalized)) {
    return { label: raw, bucket: "OPEN", className: "status-text-open" };
  }
  return { label: raw, bucket: "OPEN", className: "status-text-open" };
}

function summarizeVisualStatuses(visualStatuses, hasDuration) {
  const renderTask = findTaskLike(visualStatuses, /render/i);
  const compTask = findTaskLike(visualStatuses, /composit/i);
  if (!renderTask && !compTask) {
    return hasDuration ? "READY" : "OPEN";
  }

  const renderStatus = normalizeVisualStatus(renderTask?.status).bucket;
  const compStatus = normalizeVisualStatus(compTask?.status).bucket;
  const buckets = [renderStatus, compStatus];
  if (buckets.includes("OMIT")) {
    return "OMIT";
  }
  if (buckets.every((bucket) => bucket === "APP")) {
    return "APP";
  }
  if (buckets.includes("RETAKE")) {
    return "RETAKE";
  }
  if (buckets.includes("WIP")) {
    return "WIP";
  }
  if (buckets.every((bucket) => bucket === "READY" || bucket === "APP")) {
    return "READY";
  }
  return "OPEN";
}

function findTaskLike(visualStatuses, matcher) {
  return (visualStatuses || []).find((task) => matcher.test(`${task.label || ""} ${task.task_key || ""}`));
}

function calculateShotLevel(visualStatuses, durationFrames) {
  const waterTask = (visualStatuses || []).find((task) => /water/i.test(`${task.label || ""} ${task.task_key || ""}`));
  const waterLevel = parseWaterLevel(waterTask?.artist);
  const durationWeight = getDurationWeight(Number(durationFrames) || 0);
  const labels = {
    0: "L0 Normal",
    1: "L1 Calm Water",
    2: "L2 Splash Water",
    3: "L3 Hero Water",
  };
  const score = 1 + waterLevel + durationWeight;

  return {
    waterLevel,
    durationWeight,
    score: Number(score.toFixed(2)),
    staffDays: Number((score * 0.32).toFixed(2)),
    leadDays: Number((score * 0.23).toFixed(2)),
    label: labels[waterLevel],
  };
}

function parseWaterLevel(value) {
  const normalized = String(value || "").toLowerCase();
  for (const level of [3, 2, 1]) {
    if (new RegExp(`(?:(?:lv|level|\\uB808\\uBCA8|\\uB808\\uBC8C)[\\W_]*${level}|${level}[\\W_]*\\uB2E8\\uACC4)`).test(normalized)) {
      return level;
    }
  }
  return 0;
}

function getDurationWeight(durationFrames) {
  if (durationFrames <= 0) {
    return 0;
  }
  return Number(Math.min(durationFrames / 96, 2).toFixed(2));
}

function normalizeShotLevel(rawLevel, visualStatuses, durationFrames) {
  if (!rawLevel) {
    return calculateShotLevel(visualStatuses, durationFrames);
  }
  const score = rawLevel.score ?? 1;
  return {
    waterLevel: rawLevel.water_level ?? rawLevel.waterLevel ?? 0,
    waterLabel: rawLevel.water_label ?? rawLevel.waterLabel ?? "",
    durationWeight: rawLevel.duration_weight ?? rawLevel.durationWeight ?? 0,
    score,
    staffDays: rawLevel.staff_days ?? rawLevel.staffDays ?? Number((score * 0.32).toFixed(2)),
    leadDays: rawLevel.lead_days ?? rawLevel.leadDays ?? Number((score * 0.23).toFixed(2)),
    label: rawLevel.label || "L0 Normal",
  };
}

function buildShotFromApi(rawShot, sceneCode) {
  const shotCode = rawShot.shot_code || `${sceneCode}_${String(Math.random()).slice(2, 6)}`;
  const visualStatuses = rawShot.visual_statuses || [];
  const shotLevel = normalizeShotLevel(rawShot.shot_level, visualStatuses, rawShot.duration_frames);
  const summaryBucket = summarizeVisualStatuses(visualStatuses, Boolean(rawShot.duration_frames));
  const leadTask = visualStatuses.find((task) => normalizeArtist(task.artist) !== "-");
  return {
    shotCode,
    title: "Shot detail synced from spreadsheet",
    artist: leadTask?.artist || null,
    duration: rawShot.duration_frames || 0,
    cam: rawShot.cam || null,
    previewImage: rawShot.preview_image_url,
    cachedPreviewImage: `${API_BASE}/local-media/preview?scene_code=${encodeURIComponent(sceneCode)}&shot_code=${encodeURIComponent(shotCode)}`,
    aniPreviewUrl: `${API_BASE}/local-media/ani/latest?scene_code=${encodeURIComponent(sceneCode)}&shot_code=${encodeURIComponent(shotCode)}`,
    renderPreview: null,
    shotLevel,
    visualStatuses,
    shotDescription: rawShot.shot_description ?? rawShot.shotDescription ?? "",
    directionLighting: rawShot.direction_lighting ?? rawShot.directionLighting ?? "",
    retakeNote: rawShot.retake_note ?? rawShot.retakeNote ?? "",
    sequence: sceneCode,
    task: rawShot.source_worksheet_title || "visual review",
    frameRange: rawShot.duration_frames ? `1-${rawShot.duration_frames}` : "-",
    updatedAt: "synced from Google Sheets",
    prep: rawShot.duration_frames ? "ready" : "blocked",
    render: "waiting",
    ae: "waiting",
    latest: visualStatuses.map((task) => `${task.label}:${task.status || "open"}`).join(" / ") || "no visual status",
    renderable: Boolean(rawShot.duration_frames),
    statusLabel: summaryBucket,
    badge: summaryBucket,
    summaryBucket,
    deliveryPath: `\\\\NAS\\sf_pipeline\\previews\\${projectName}\\${shotCode}.mp4`,
    steps: [
      { name: "AnimOut", detail: "Waiting for run", state: rawShot.duration_frames ? "ready" : "blocked" },
      { name: "Render Prep", detail: "Waiting for run", state: rawShot.duration_frames ? "ready" : "blocked" },
      { name: "Render", detail: "Not started", state: "waiting" },
      { name: "AE Precomp", detail: "Not started", state: "waiting" },
      { name: "Preview", detail: "No render preview yet", state: "waiting" },
    ],
  };
}

function shotDetailKey(sceneCode, shotCode) {
  return `${sceneCode}:${shotCode}`;
}

async function loadShotDetail(shot) {
  const sceneCode = normalizeSceneCode(shot.sequence || sceneCodeFromShotCode(shot.shotCode));
  const key = shotDetailKey(sceneCode, shot.shotCode);
  if (shotDetailPromises[key]) {
    return shotDetailPromises[key];
  }

  shot.detailLoading = true;
  const promise = fetchJson(
    `${API_BASE}/google-sheets/scene-list/${encodeURIComponent(sceneCode)}/shots/${encodeURIComponent(shot.shotCode)}/detail`,
  )
    .then((detail) => {
      shot.shotDescription = detail.shot_description ?? detail.shotDescription ?? "";
      shot.directionLighting = detail.direction_lighting ?? detail.directionLighting ?? "";
      shot.retakeNote = detail.retake_note ?? detail.retakeNote ?? "";
      shot.detailLoaded = true;
      return shot;
    })
    .catch((error) => {
      console.warn("failed to load shot detail", shot.shotCode, error);
      shot.detailLoaded = true;
      return shot;
    })
    .finally(() => {
      shot.detailLoading = false;
      delete shotDetailPromises[key];
      if (selectedShotCode === shot.shotCode) {
        renderDetailPanel();
      }
    });

  shotDetailPromises[key] = promise;
  renderDetailPanel();
  return promise;
}

async function openAnim(shotCode, sequenceCode) {
  const sceneCode = normalizeSceneCode(sequenceCode || sceneCodeFromShotCode(shotCode));
  if (!sceneCode || !shotCode) {
    return;
  }

  if (window.location.protocol !== "file:" && !["127.0.0.1", "localhost"].includes(window.location.hostname)) {
    window.open(
      `${API_BASE}/local-media/ani/latest?scene_code=${encodeURIComponent(sceneCode)}&shot_code=${encodeURIComponent(shotCode)}`,
      "_blank",
      "noopener",
    );
    return;
  }

  try {
    await fetchJson(
      `${API_BASE}/local-media/ani/open?scene_code=${encodeURIComponent(sceneCode)}&shot_code=${encodeURIComponent(shotCode)}`,
      { method: "POST" }
    );
  } catch (error) {
    console.error(error);
    alert("ANI video file was not found.");
  }
}

function sceneCodeFromShotCode(shotCode) {
  const match = String(shotCode || "").match(/^(.+)_\d+$/);
  return normalizeSceneCode(match ? match[1] : currentSceneCode || [...selectedSceneCodes][0]);
}

function openSceneShotList(sceneCode) {
  const scene = scenes.find((item) => item.scene_code === sceneCode);
  if (scene?.shotlist_url) {
    window.open(scene.shotlist_url, "_blank", "noopener");
  }
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

async function loadScenes() {
  const cachedScenes = getCache("scene-list");
  if (cachedScenes) {
    scenes = filterOmittedScenes(cachedScenes.map(buildSceneFromApi));
    updateDashboard();
  }

  const payload = await fetchJson(`${API_BASE}/google-sheets/scene-list`);
  scenes = filterOmittedScenes((payload.scenes || []).map(buildSceneFromApi));
  setCache("scene-list", scenes);
  updateDashboard();
}

async function selectScene(sceneCode, event) {
  currentView = "shots";
  allShotsMode = false;
  currentSceneCode = sceneCode;
  if (event?.shiftKey || event?.ctrlKey || event?.metaKey) {
    if (selectedSceneCodes.has(sceneCode)) {
      selectedSceneCodes.delete(sceneCode);
    } else {
      selectedSceneCodes.add(sceneCode);
    }
  } else {
    selectedSceneCodes = new Set([sceneCode]);
  }
  if (selectedSceneCodes.size === 0) {
    currentSceneCode = null;
    selectedShotCode = null;
    updateDashboard();
    return;
  }
  currentSceneCode = [...selectedSceneCodes][selectedSceneCodes.size - 1];
  await Promise.all([...selectedSceneCodes].map((code) => ensureSceneLoaded(code)));
  selectedShotCode = getVisibleShots(getCurrentShotScope()).filter(matchesShotSearch)[0]?.shotCode || null;
  updateDashboard();
}

async function selectAllShots() {
  currentView = "shots";
  allShotsMode = true;
  currentSceneCode = null;
  selectedSceneCodes = new Set();
  selectedShotCode = null;
  updateDashboard();
  await loadAllSceneShots();
  selectedShotCode = getVisibleShots(getCurrentShotScope()).filter(matchesShotSearch)[0]?.shotCode || null;
  updateDashboard();
}

async function loadAllSceneShots() {
  for (const scene of scenes) {
    if (!scene.scene_code || sceneShots[scene.scene_code]) {
      continue;
    }
    try {
      await ensureSceneLoaded(scene.scene_code);
      if (allShotsMode) {
        updateMetrics();
        renderShotTable();
      }
    } catch (error) {
      console.warn("failed to load scene shots", scene.scene_code, error);
    }
  }
}

function showSceneOverview() {
  currentView = "scenes";
  allShotsMode = false;
  currentSceneCode = null;
  selectedSceneCodes = new Set();
  selectedShotCode = null;
  activeStatusFilters = new Set(["ALL"]);
  updateDashboard();
}

async function ensureSceneLoaded(sceneCode) {
  if (sceneShots[sceneCode]) {
    return sceneShots[sceneCode];
  }

  const cached = getCache(`scene-shots:${sceneCode}`);
  if (cached) {
    sceneShots[sceneCode] = filterOmittedShots(cached);
    return sceneShots[sceneCode];
  }

  if (!sceneLoadPromises[sceneCode]) {
    sceneLoadPromises[sceneCode] = fetchJson(`${API_BASE}/google-sheets/scene-list/${sceneCode}/shots`)
      .then((payload) => {
        sceneShots[sceneCode] = filterOmittedShots((payload.shots || []).map((shot) => buildShotFromApi(shot, sceneCode)));
        setCache(`scene-shots:${sceneCode}`, sceneShots[sceneCode]);
        return sceneShots[sceneCode];
      })
      .catch((error) => {
        if (error.status === 429) {
          shotTable.innerHTML = `
            <article class="table-row">
              <div class="shot-primary">
                <strong>Quota</strong>
                <span>Google Sheets quota exceeded. Try this scene again shortly.</span>
              </div>
            </article>
          `;
        }
        throw error;
      })
      .finally(() => {
        delete sceneLoadPromises[sceneCode];
      });
  }

  return sceneLoadPromises[sceneCode];
}

async function refreshCurrentScene() {
  if (allShotsMode) {
    await warmSheetCache();
    return;
  }
  const targetScenes = [...selectedSceneCodes];
  if (!targetScenes.length) {
    return;
  }

  try {
    await Promise.all(targetScenes.map(async (sceneCode) => {
      const payload = await fetchJson(`${API_BASE}/google-sheets/scene-list/${sceneCode}/shots?refresh=true`);
      const shots = filterOmittedShots((payload.shots || []).map((shot) => buildShotFromApi(shot, sceneCode)));
      sceneShots[sceneCode] = shots;
      setCache(`scene-shots:${sceneCode}`, shots);
    }));
    selectedShotCode = getVisibleShots(getCurrentShotScope()).filter(matchesShotSearch)[0]?.shotCode || null;
    updateDashboard();
  } catch (error) {
    console.error(error);
    throw error;
  }
}

async function warmSheetCache() {
  await fetchJson(`${API_BASE}/google-sheets/cache/warm`, { method: "POST" });
}

async function updateData() {
  if (!updateButton) {
    return;
  }

  updateButton.textContent = "Updating...";
  updateButton.disabled = true;
  try {
    if (currentView === "shots" && selectedSceneCodes.size && !allShotsMode) {
      await refreshCurrentScene();
    } else {
      await fetchJson(`${API_BASE}/google-sheets/scene-list?refresh=true`);
      await warmSheetCache();
    }
    updateButton.textContent = "Updated";
  } catch (error) {
    console.error(error);
    updateButton.textContent = "Failed";
  } finally {
    window.setTimeout(() => {
      updateButton.textContent = "Update";
      updateButton.disabled = false;
    }, 1400);
  }
}

function prefetchRemainingScenes() {
  // Keep this manual for now; Google Sheets per-minute quota is easy to hit.
  return;

  const targets = scenes
    .map((scene) => scene.scene_code)
    .filter((sceneCode) => sceneCode && sceneCode !== currentSceneCode && !sceneShots[sceneCode])
    .slice(0, 6);

  let index = 0;
  const runNext = async () => {
    if (index >= targets.length) {
      return;
    }

    const sceneCode = targets[index++];
    try {
      await ensureSceneLoaded(sceneCode);
      updateMetrics();
    } catch (error) {
      console.warn("prefetch failed", sceneCode, error);
    }

    window.setTimeout(runNext, 120);
  };

  window.setTimeout(runNext, 150);
}

async function boot() {
  try {
    await loadScenes();
  } catch (error) {
    console.error(error);
    shotTable.innerHTML = `
      <article class="table-row">
        <div class="shot-primary">
          <strong>API connection failed</strong>
          <span>Run the backend server and refresh this page.</span>
        </div>
      </article>
    `;
  }
}

function setupPaneResizer() {
  if (!paneResizer || !appShell) {
    return;
  }

  let isDragging = false;

  paneResizer.addEventListener("mousedown", () => {
    isDragging = true;
    paneResizer.classList.add("dragging");
    document.body.style.userSelect = "none";
  });

  window.addEventListener("mousemove", (event) => {
    if (!isDragging || window.innerWidth <= 1280) {
      return;
    }

    const appRect = appShell.getBoundingClientRect();
    const sidebarWidth = 280;
    const gutter = 12;
    const resizerWidth = 8;
    const minMain = 420;
    const minDetail = 320;

    const pointerX = event.clientX - appRect.left;
    const totalWidth = appRect.width;
    const available = totalWidth - sidebarWidth - gutter - resizerWidth - gutter;
    let mainWidth = pointerX - sidebarWidth - gutter;
    let detailWidth = available - mainWidth;

    if (mainWidth < minMain) {
      mainWidth = minMain;
      detailWidth = available - mainWidth;
    }

    if (detailWidth < minDetail) {
      detailWidth = minDetail;
      mainWidth = available - detailWidth;
    }

    appShell.style.gridTemplateColumns = `${sidebarWidth}px ${mainWidth}px ${resizerWidth}px ${detailWidth}px`;
  });

  window.addEventListener("mouseup", () => {
    isDragging = false;
    paneResizer.classList.remove("dragging");
    document.body.style.userSelect = "";
  });
}

sceneOverviewButton?.addEventListener("click", showSceneOverview);
updateButton?.addEventListener("click", updateData);
searchInput?.addEventListener("input", (event) => {
  searchQuery = event.target.value || "";
  if (currentView === "shots") {
    selectedShotCode = getVisibleShots(getCurrentShotScope()).filter(matchesShotSearch)[0]?.shotCode || null;
  }
  updateDashboard();
});

document.querySelectorAll("[data-filter]").forEach((button) => {
  button.addEventListener("click", (event) => {
    if (!selectedSceneCodes.size && !allShotsMode) {
      return;
    }
    currentView = "shots";
    const filter = button.dataset.filter || "ALL";
    if (!event.shiftKey || filter === "ALL") {
      activeStatusFilters = new Set([filter]);
    } else {
      activeStatusFilters.delete("ALL");
      if (activeStatusFilters.has(filter)) {
        activeStatusFilters.delete(filter);
      } else {
        activeStatusFilters.add(filter);
      }
      if (activeStatusFilters.size === 0) {
        activeStatusFilters.add("ALL");
      }
    }
    selectedShotCode = getVisibleShots(getCurrentShotScope()).filter(matchesShotSearch)[0]?.shotCode || null;
    updateDashboard();
  });
});

setupPaneResizer();
boot();
