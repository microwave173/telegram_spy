const collectList = document.getElementById("collect-list");
const analyzeList = document.getElementById("analyze-list");
const listenList = document.getElementById("listen-list");
const refreshStatus = document.getElementById("refresh-status");
const stepCollect = document.getElementById("step-collect");
const stepAnalyze = document.getElementById("step-analyze");
const stepListen = document.getElementById("step-listen");
const maxJoinsInput = document.getElementById("max-joins");
const groupBufferMaxMessagesInput = document.getElementById("group-buffer-max-messages");
const saveConfigButton = document.getElementById("save-config-button");
const startButton = document.getElementById("start-button");
const resetHitCountsButton = document.getElementById("reset-hit-counts-button");
const pipelineStatus = document.getElementById("pipeline-status");
const configStatus = document.getElementById("config-status");
const keywordsText = document.getElementById("keywords-text");
const detectorText = document.getElementById("detector-text");
const pipelineLog = document.getElementById("pipeline-log");
const metricsGrid = document.getElementById("metrics-grid");
const MAX_LISTEN_EVENTS = 12;
let openAnalyzeChatId = null;

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function emptyNode(text) {
  const div = document.createElement("div");
  div.className = "empty";
  div.textContent = text;
  return div;
}

function renderCollect(items) {
  collectList.innerHTML = "";
  if (!items.length) {
    collectList.appendChild(emptyNode("还没有监听中的群组"));
    return;
  }

  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "card";
    const keywords = (item.source_keywords || []).join(", ");
    const links = (item.source_links || []).join(", ");
    const statusText = item.added_this_run ? "本轮新加入" : "已在监听";
    const badge = item.added_this_run ? '<span class="mini-badge">NEW</span>' : "";
    card.innerHTML = `
      <div class="card-title-row">
        <div class="card-title">${item.title || item.username || item.chat_id}</div>
        ${badge}
      </div>
      <div class="card-meta">chat_id: ${item.chat_id}
username: ${item.username || "-"}
detect_hits: ${item.hit_count ?? 0}
status: ${statusText}
last_added_at: ${formatTime(item.last_added_at)}
keywords: ${keywords || "-"}
source_links: ${links || "-"}</div>
    `;
    collectList.appendChild(card);
  });
}

function renderMetrics(metrics) {
  metricsGrid.innerHTML = "";
  const items = [
    ["监听群组总数", metrics.monitored_groups_total ?? 0],
    ["本次新加入群组", metrics.collect_new_groups_this_run ?? 0],
    ["本次报告命中数", metrics.reports_this_run ?? 0],
    ["命中频率", `${metrics.report_hit_rate_per_hour ?? 0} 条/小时`],
    ["本次监听消息数", metrics.incoming_messages_this_run ?? 0],
    ["本次活跃群组数", metrics.active_groups_this_run ?? 0],
  ];
  items.forEach(([label, value]) => {
    const card = document.createElement("div");
    card.className = "metric-card";
    card.innerHTML = `
      <div class="metric-label">${label}</div>
      <div class="metric-value">${value}</div>
    `;
    metricsGrid.appendChild(card);
  });
}

async function markGroupRead(chatId) {
  await fetch(`/api/groups/${chatId}/read`, { method: "POST" });
}

function createReportCard(report) {
  const card = document.createElement("div");
  card.className = "report-card";
  const meta = document.createElement("div");
  meta.className = "report-time";
  meta.textContent = `${formatTime(report.generated_at)} · ${report.source}`;
  const body = document.createElement("div");
  body.className = "report-body";
  body.textContent = report.body || "";
  card.appendChild(meta);
  card.appendChild(body);
  return card;
}

function renderAnalyze(groups) {
  analyzeList.innerHTML = "";
  if (!groups.length) {
    openAnalyzeChatId = null;
    analyzeList.appendChild(emptyNode("还没有生成报告"));
    return;
  }

  let hasOpenGroup = false;
  groups.forEach((group) => {
    const wrapper = document.createElement("div");
    wrapper.className = "card group-card";

    const button = document.createElement("button");
    button.className = "group-button";
    const unread = group.unread_count || 0;
    button.innerHTML = `
      <div class="card-title-row">
        <div class="card-title">${group.title}</div>
        <span class="badge ${unread ? "" : "hidden"}">${unread}</span>
      </div>
      <div class="card-meta">chat_id: ${group.chat_id}
reports: ${group.reports.length}
latest: ${formatTime(group.latest_generated_at)}</div>
    `;

    const reportList = document.createElement("div");
    reportList.className = "report-list";
    group.reports.forEach((report) => reportList.appendChild(createReportCard(report)));

    if (group.chat_id === openAnalyzeChatId) {
      wrapper.classList.add("open");
      hasOpenGroup = true;
    }

    button.addEventListener("click", async () => {
      const willOpen = !wrapper.classList.contains("open");
      document.querySelectorAll(".group-card.open").forEach((node) => {
        if (node !== wrapper) node.classList.remove("open");
      });
      wrapper.classList.toggle("open");
      openAnalyzeChatId = willOpen ? group.chat_id : null;
      if (willOpen) {
        await markGroupRead(group.chat_id);
        const badge = button.querySelector(".badge");
        badge.classList.add("hidden");
        badge.textContent = "0";
      }
    });

    wrapper.appendChild(button);
    wrapper.appendChild(reportList);
    analyzeList.appendChild(wrapper);
  });

  if (!hasOpenGroup) {
    openAnalyzeChatId = null;
  }
}

function renderListen(events) {
  listenList.innerHTML = "";
  const recentEvents = (events || []).slice(0, MAX_LISTEN_EVENTS);
  if (!recentEvents.length) {
    listenList.appendChild(emptyNode("还没有实时监听事件"));
    return;
  }

  recentEvents.forEach((event) => {
    const card = document.createElement("div");
    card.className = "card";
    const tag = document.createElement("div");
    tag.className = "listen-tag";
    tag.textContent = `${event.event_type} · ${event.chat_type}`;
    const row = document.createElement("div");
    row.className = "card-title-row";
    const title = document.createElement("div");
    title.className = "card-title";
    title.textContent = event.chat_id;
    row.appendChild(title);
    const meta = document.createElement("div");
    meta.className = "card-meta";
    meta.textContent = `time: ${formatTime(event.timestamp)}`;
    const body = document.createElement("div");
    body.className = "report-body";
    body.textContent = event.text || "";
    card.appendChild(tag);
    card.appendChild(row);
    card.appendChild(meta);
    card.appendChild(body);
    listenList.appendChild(card);
  });
}

function selectedSteps() {
  const steps = [];
  if (stepCollect.checked) steps.push("collect");
  if (stepAnalyze.checked) steps.push("analyze");
  if (stepListen.checked) steps.push("listen");
  return steps;
}

function renderPipelineStatus(status) {
  if (!status) {
    pipelineStatus.textContent = "尚未启动";
    startButton.disabled = false;
    return;
  }
  const steps = (status.steps || []).join(", ") || "-";
  const maxJoins = status.max_joins ?? "-";
  const groupBufferMaxMessages = status.group_buffer_max_messages ?? "-";
  if (status.running) {
    pipelineStatus.textContent = `运行中 · steps=${steps} · max_joins=${maxJoins} · buffer=${groupBufferMaxMessages} · pid=${status.pid} · started_at=${formatTime(status.started_at)}`;
    startButton.disabled = true;
  } else if (status.started_at) {
    pipelineStatus.textContent = `已结束 · steps=${steps} · max_joins=${maxJoins} · buffer=${groupBufferMaxMessages} · exit_code=${status.exit_code} · started_at=${formatTime(status.started_at)} · finished_at=${formatTime(status.finished_at)}`;
    startButton.disabled = false;
  } else {
    pipelineStatus.textContent = "尚未启动";
    startButton.disabled = false;
  }
}

function currentConfigPayload() {
  return {
    keywords_text: keywordsText.value,
    detector_description_text: detectorText.value,
  };
}

async function refreshPipelineStatus() {
  try {
    const response = await fetch("/api/pipeline/status", { cache: "no-store" });
    const data = await response.json();
    renderPipelineStatus(data);
  } catch (error) {
    pipelineStatus.textContent = "无法获取运行状态";
  }
}

async function refreshPipelineLog() {
  try {
    const response = await fetch("/api/pipeline/log", { cache: "no-store" });
    const data = await response.json();
    const nextText = data.text || "还没有日志输出";
    const shouldStickToBottom =
      pipelineLog.scrollTop + pipelineLog.clientHeight >= pipelineLog.scrollHeight - 24;
    pipelineLog.textContent = nextText;
    if (shouldStickToBottom) {
      pipelineLog.scrollTop = pipelineLog.scrollHeight;
    }
  } catch (error) {
    pipelineLog.textContent = "无法获取日志";
  }
}

async function loadStartupConfig() {
  try {
    const response = await fetch("/api/config/startup", { cache: "no-store" });
    const data = await response.json();
    keywordsText.value = data.keywords_text || "";
    detectorText.value = data.detector_description_text || "";
    maxJoinsInput.value = data.default_max_joins ?? 5;
    groupBufferMaxMessagesInput.value = data.default_group_buffer_max_messages ?? 8;
    const autoJoinText = data.collect_auto_join_enabled
      ? "collect 阶段默认会自动加入搜到的公开群组。"
      : "collect 阶段当前不会自动加入搜到的公开群组。";
    configStatus.textContent = `${autoJoinText} 本次最大加群数默认是 ${maxJoinsInput.value}，群消息缓冲条数默认是 ${groupBufferMaxMessagesInput.value}。`;
  } catch (error) {
    configStatus.textContent = "无法加载开始界面配置";
  }
}

async function saveStartupConfig() {
  saveConfigButton.disabled = true;
  configStatus.textContent = "保存中...";
  try {
    const response = await fetch("/api/config/startup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentConfigPayload()),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      configStatus.textContent = data.error || "保存失败";
      return false;
    }
    configStatus.textContent = `已保存。collect 阶段默认会自动加入搜到的公开群组。本次最大加群数是 ${maxJoinsInput.value}，群消息缓冲条数是 ${groupBufferMaxMessagesInput.value}。`;
    return true;
  } catch (error) {
    configStatus.textContent = "保存失败";
    return false;
  } finally {
    saveConfigButton.disabled = false;
  }
}

async function startPipelineRun() {
  const steps = selectedSteps();
  if (!steps.length) {
    pipelineStatus.textContent = "请至少勾选一个阶段";
    return;
  }
  const maxJoins = Number.parseInt(maxJoinsInput.value, 10);
  if (Number.isNaN(maxJoins) || maxJoins < 0) {
    configStatus.textContent = "本次最大加群数需要是大于等于 0 的整数";
    return;
  }
  const groupBufferMaxMessages = Number.parseInt(groupBufferMaxMessagesInput.value, 10);
  if (Number.isNaN(groupBufferMaxMessages) || groupBufferMaxMessages <= 0) {
    configStatus.textContent = "群消息缓冲条数需要是大于 0 的整数";
    return;
  }
  const saved = await saveStartupConfig();
  if (!saved) return;
  startButton.disabled = true;
  pipelineStatus.textContent = "启动中...";
  try {
    const response = await fetch("/api/pipeline/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ steps, max_joins: maxJoins, group_buffer_max_messages: groupBufferMaxMessages }),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      pipelineStatus.textContent = data.error || "启动失败";
      startButton.disabled = false;
      return;
    }
    renderPipelineStatus(data.status);
    await refreshPipelineLog();
  } catch (error) {
    pipelineStatus.textContent = "启动失败";
    startButton.disabled = false;
  }
}

async function refreshDashboard() {
  try {
    refreshStatus.textContent = "刷新中...";
    const response = await fetch("/api/dashboard", { cache: "no-store" });
    const data = await response.json();
    renderCollect(data.monitored_groups || []);
    renderAnalyze(data.analyze_groups || []);
    renderListen(data.listen_events || []);
    renderMetrics(data.metrics || {});
    refreshStatus.textContent = `已刷新 ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    refreshStatus.textContent = "刷新失败";
    console.error(error);
  }
}

async function resetHitCounts() {
  resetHitCountsButton.disabled = true;
  try {
    const response = await fetch("/api/hit-counts/reset", { method: "POST" });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      configStatus.textContent = data.error || "清零失败";
      return;
    }
    configStatus.textContent = `命中次数已清零，已备份 ${data.backed_up_groups} 个群到 ${data.backup_path}`;
    await refreshDashboard();
  } catch (error) {
    configStatus.textContent = "清零失败";
  } finally {
    resetHitCountsButton.disabled = false;
  }
}

saveConfigButton.addEventListener("click", saveStartupConfig);
startButton.addEventListener("click", startPipelineRun);
resetHitCountsButton.addEventListener("click", resetHitCounts);

loadStartupConfig();
refreshDashboard();
refreshPipelineStatus();
refreshPipelineLog();
setInterval(refreshDashboard, 4000);
setInterval(refreshPipelineStatus, 4000);
setInterval(refreshPipelineLog, 2000);
