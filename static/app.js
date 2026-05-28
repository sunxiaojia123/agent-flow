/** Agent Flow — Skill Scheduling Trading System */

// ── State ──
let state = {
  convId: null,
  messages: [],
  isStreaming: false,
  currentAsstMsg: null,
  phase: 'idle',
};

// ── DOM refs ──
const $ = (s) => document.querySelector(s);
const chatMessages = $('#chatMessages');
const chatInput = $('#chatInput');
const sendBtn = $('#sendBtn');
const nodeTimeline = $('#nodeTimeline');
const decisionList = $('#decisionList');
const eventLog = $('#eventLog');
const skillList = $('#skillList');
const statusConv = $('#statusConv');
const statusPhase = $('#statusPhase');
const statusConn = $('#statusConn');

// ── Init ──
loadSkills();
chatInput.focus();

sendBtn.addEventListener('click', sendMessage);
chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
$('#reloadSkillsBtn').addEventListener('click', reloadSkills);

// ── Core: Send message ──
async function sendMessage(text) {
  if (state.isStreaming) return;
  const content = text || chatInput.value.trim();
  if (!content) return;

  chatInput.value = '';
  setStreaming(true);
  addUserMessage(content);

  resetSchedulingPanel();
  addEventLog('info', '发送: ' + content.slice(0, 40));

  try {
    const response = await fetch('/api/v1/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: content, conversation_id: state.convId }),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = processSSEBuffer(buffer);
    }
  } catch (err) {
    addEventLog('error', '连接失败: ' + err.message);
    setStreaming(false);
  }
}

// ── SSE parser ──
function processSSEBuffer(buffer) {
  const parts = buffer.split('\n\n');
  const remainder = parts.pop() || '';

  for (const part of parts) {
    if (!part.trim()) continue;
    const lines = part.split('\n');
    let eventType = 'message';
    let data = '';
    for (const line of lines) {
      if (line.startsWith('event: ')) eventType = line.slice(7).trim();
      else if (line.startsWith('data: ')) data = line.slice(6);
    }
    if (data) {
      try {
        const parsed = JSON.parse(data);
        handleSSEEvent(eventType, parsed);
      } catch (e) { /* skip partial chunks */ }
    }
  }
  return remainder;
}

// ── Event router ──
function handleSSEEvent(eventType, data) {
  switch (data.type) {
    case 'meta': handleMetaEvent(data); break;
    case 'text_delta': handleTextDelta(data); break;
    case 'text_done': handleTextDone(); break;
    case 'popup': handlePopup(data); break;
    case 'card': handleCard(data); break;
    case 'error': handleError(data); break;
    case 'done': handleDone(data); break;
  }

  let detail = formatEventDetail(data);
  addEventLog(data.type, detail);
}

// ── Meta: node execution & supervisor decisions ──
function handleMetaEvent(data) {
  if (data.conversation_id && !state.convId) {
    state.convId = data.conversation_id;
    updateStatus();
  }

  // Phase tracking
  if (data.phase === 'tool_planned') {
    addDecision(`调用 ${data.tool_name}(${JSON.stringify(data.tool_args || {})})`);
    updatePhase(`工具调用: ${data.tool_name}`);
    addTimelineItem(data.tool_name, 'active');
  } else if (data.phase === 'supervisor_end') {
    addDecision(`结束: ${data.next} — ${data.reasoning || ''}`);
    updatePhase(`决策: ${data.next}`);
  } else if (data.phase === 'tool_done') {
    updateTimelineItem(data.tool_name, 'done');
  }

  // Node start/end
  if (data.node && data.status === 'start') {
    let displayName = NODE_DISPLAY[data.node] || data.node;
    addTimelineItem(displayName, 'active');
    updatePhase(`节点: ${displayName}`);
  } else if (data.node && data.status === 'end') {
    let displayName = NODE_DISPLAY[data.node] || data.node;
    updateTimelineItem(displayName, 'done');
  }

  if (data.message) {
    // Keep last active node highlighted
  }
}

const NODE_DISPLAY = {
  coordinator: '协调员 (Coordinator)',
  planner: '规划员 (Planner)',
  supervisor: '主管 (Supervisor)',
  tools: '工具执行 (ToolNode)',
  formatter_text: '文本回复',
  formatter_popup: '弹窗收集',
  formatter_card: '卡片展示',
};

// ── Text streaming ──
function handleTextDelta(data) {
  if (!state.currentAsstMsg) {
    state.currentAsstMsg = addAsstMessage('');
    state.currentAsstMsg.classList.add('streaming');
    state.currentAsstMsg._rawText = '';
  }
  state.currentAsstMsg._rawText += data.content;
  const contentEl = state.currentAsstMsg.querySelector('.msg-content');
  contentEl.innerHTML = mdToHtml(state.currentAsstMsg._rawText);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function handleTextDone() {
  if (state.currentAsstMsg) {
    state.currentAsstMsg.classList.remove('streaming');
    delete state.currentAsstMsg._rawText;
    state.currentAsstMsg = null;
  }
}

// ── Popup ──
function handlePopup(data) {
  handleTextDone();
  const card = cloneTemplate('tmplPopupCard');
  const fieldsDiv = card.querySelector('.popup-fields');

  if (data.message) {
    card.querySelector('.popup-header').textContent = data.message;
  }

  (data.fields || []).forEach(f => {
    const div = document.createElement('div');
    div.className = 'popup-field';
    div.innerHTML = `<div class="popup-field-label">${f.label}${f.required ? '<span class="required"> *</span>' : ''}</div>`;

    if (f.type === 'select' && f.options) {
      const select = document.createElement('select');
      select.name = f.name;
      select.innerHTML = '<option value="">请选择...</option>' + (f.options || []).map(o =>
        typeof o === 'string'
          ? `<option value="${o}">${o}</option>`
          : `<option value="${o.value}">${o.label || o.value}</option>`
      ).join('');
      div.appendChild(select);
    } else if (f.type === 'number') {
      const input = document.createElement('input');
      input.type = 'number'; input.name = f.name;
      if (f.min != null) input.min = f.min;
      div.appendChild(input);
    } else {
      const input = document.createElement('input');
      input.type = 'text'; input.name = f.name;
      div.appendChild(input);
    }
    fieldsDiv.appendChild(div);
  });

  card.querySelector('.popup-submit').addEventListener('click', () => {
    const values = [];
    fieldsDiv.querySelectorAll('input, select').forEach(el => {
      if (el.value) {
        const field = (data.fields || []).find(f => f.name === el.name);
        const label = field ? field.label : el.name;
        values.push(`${label}: ${el.value}`);
      }
    });
    if (values.length > 0) {
      card.querySelector('.popup-submit').disabled = true;
      sendMessage(values.join('，'));
    }
  });

  chatMessages.appendChild(card);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ── Card ──
function handleCard(data) {
  handleTextDone();
  if (data.card_type === 'selection') {
    renderSelectionCard(data.data);
  } else {
    renderTradeCard(data.data);
  }
  updatePhase('卡片已展示');
}

function renderTradeCard(d) {
  if (!d || !d.recommendations) {
    // Try to render as simple text if no structured data
    addAsstMessage(JSON.stringify(d, null, 2));
    return;
  }

  const card = cloneTemplate('tmplTradeCard');
  const summary = card.querySelector('.trade-summary');
  const s = d.summary || {};
  summary.innerHTML = `<strong>${s.product || '采购推荐'}</strong> | ${s.quantity || '-'} ${s.unit || '吨'} | ${s.region || ''}`;

  const recsDiv = card.querySelector('.trade-recommendations');
  (d.recommendations || []).forEach((r, i) => {
    const div = document.createElement('div');
    div.className = 'trade-recommendation';
    div.innerHTML = `
      <div class="trade-rec-header">
        <span class="trade-rec-rank">#${r.rank || i+1}</span>
        <span class="trade-rec-name">${r.company_name || r.name || ''}</span>
        <span class="trade-rec-score">${r.match_score_label || r.match_score || ''}</span>
      </div>
      <div class="trade-rec-meta">${r.city || ''} · ${r.scale || ''} · ${r.rating ? '★'.repeat(Math.round(r.rating)) : ''}</div>
      <div class="trade-rec-products">主营: ${(r.main_products || []).join('、') || '-'}</div>
      <div class="trade-rec-highlights">
        ${(r.highlights || []).map(h => `<span class="highlight-tag">${h}</span>`).join('')}
      </div>
      <div class="trade-rec-actions">
        <button class="btn btn-sm btn-detail" data-name="${r.company_name || r.name}">了解详情</button>
        <button class="btn btn-sm btn-select" data-name="${r.company_name || r.name}">选这家</button>
      </div>
    `;
    recsDiv.appendChild(div);
  });

  card.querySelectorAll('.btn-detail').forEach(btn => {
    btn.addEventListener('click', () => sendMessage(`介绍一下${btn.dataset.name}的优势和详细情况`));
  });
  card.querySelectorAll('.btn-select').forEach(btn => {
    btn.addEventListener('click', () => sendMessage(`选${btn.dataset.name}`));
  });

  chatMessages.appendChild(card);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function renderSelectionCard(d) {
  const sc = d.company || {};
  const order = d.order || {};
  const el = document.createElement('div');
  el.className = 'selection-card';
  el.innerHTML = `
    <div class="selection-header">已选定供应商</div>
    <div class="selection-company">
      <span class="selection-company-name">${sc.company_name || sc.name || ''}</span>
      <span class="selection-company-meta">${sc.city || ''} · ${sc.scale || ''} · ★${sc.rating || '-'}</span>
    </div>
    <div class="selection-order">
      <div class="selection-order-title">采购信息</div>
      <table class="selection-table">
        <tr><td>品类</td><td><strong>${order.product || '-'}</strong></td></tr>
        <tr><td>数量</td><td><strong>${order.quantity || '-'} ${order.unit || '吨'}</strong></td></tr>
        <tr><td>地区</td><td>${order.region || ''} ${order.city || ''}</td></tr>
      </table>
    </div>
    <div class="selection-highlights">
      ${(sc.highlights || []).map(h => `<span class="highlight-tag">${h}</span>`).join('')}
    </div>
    ${sc.contact ? `<div class="selection-contact">联系电话: ${sc.contact.phone || sc.contact || '暂无'}</div>` : ''}
    <div class="selection-footer">${d.message || '请确认以上交易信息'}</div>
  `;
  chatMessages.appendChild(el);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ── Error ──
function handleError(data) {
  handleTextDone();
  const msg = addAsstMessage('错误: ' + data.message);
  msg.querySelector('.msg-content').style.color = 'var(--error)';
}

// ── Done ──
function handleDone(data) {
  handleTextDone();
  setStreaming(false);
  updatePhase('就绪');
  if (data.conversation_id && !state.convId) {
    state.convId = data.conversation_id;
    updateStatus();
  }
}

// ── Scheduling panel helpers ──
const timelineItems = new Map();

function resetSchedulingPanel() {
  nodeTimeline.innerHTML = '<div class="empty-hint">等待执行...</div>';
  decisionList.innerHTML = '<div class="empty-hint">等待决策...</div>';
  timelineItems.clear();
}

function addTimelineItem(id, status) {
  if (timelineItems.has(id)) return;
  if (nodeTimeline.querySelector('.empty-hint')) {
    nodeTimeline.innerHTML = '';
  }

  const item = cloneTemplate('tmplNodeItem');
  item.dataset.id = id;
  item.querySelector('.node-label').textContent = id;
  item.classList.add(status);
  if (status === 'active') {
    item.querySelector('.node-icon').textContent = '●';
  }
  nodeTimeline.appendChild(item);
  timelineItems.set(id, item);
}

function updateTimelineItem(id, status) {
  let item = timelineItems.get(id);
  if (!item) {
    // Find by label text
    const items = nodeTimeline.querySelectorAll('.node-item');
    for (const el of items) {
      if (el.querySelector('.node-label').textContent === id) {
        item = el;
        break;
      }
    }
    if (!item) {
      addTimelineItem(id, status);
      item = timelineItems.get(id);
    }
  }
  if (!item) return;

  item.classList.remove('active', 'done');
  item.classList.add(status);
  if (status === 'active') {
    item.querySelector('.node-icon').textContent = '●';
  } else if (status === 'done') {
    item.querySelector('.node-icon').textContent = '✓';
    item.querySelector('.node-icon').style.background = 'var(--success)';
    item.querySelector('.node-icon').style.color = '#fff';
  }
  nodeTimeline.scrollTop = nodeTimeline.scrollHeight;
}

function addDecision(text) {
  if (decisionList.querySelector('.empty-hint')) {
    decisionList.innerHTML = '';
  }
  const item = cloneTemplate('tmplDecisionItem');
  item.querySelector('.decision-content').textContent = text;
  decisionList.appendChild(item);
  decisionList.scrollTop = decisionList.scrollHeight;

  // Keep max 50 decisions
  while (decisionList.children.length > 50) {
    decisionList.firstElementChild.remove();
  }
}

// ── Skill list ──
async function loadSkills() {
  try {
    const res = await fetch('/api/v1/skills');
    const data = await res.json();
    renderSkills(data.skills || []);
  } catch (e) {
    skillList.innerHTML = '<div class="empty-hint">加载失败</div>';
  }
}

async function reloadSkills() {
  try {
    await fetch('/api/v1/skills/reload', { method: 'POST' });
    loadSkills();
  } catch (e) {
    console.error('Reload failed', e);
  }
}

function renderSkills(skills) {
  if (skills.length === 0) {
    skillList.innerHTML = '<div class="empty-hint">无可用技能</div>';
    return;
  }
  skillList.innerHTML = '';
  skills.forEach(s => {
    const item = cloneTemplate('tmplSkillItem');
    item.querySelector('.skill-name').textContent = `${s.display_name} (${s.name})`;
    item.querySelector('.skill-desc').textContent = s.description || '';
    const apisDiv = item.querySelector('.skill-apis');
    (s.apis || []).forEach(api => {
      const tag = document.createElement('span');
      tag.className = 'skill-api-tag';
      tag.textContent = api;
      apisDiv.appendChild(tag);
    });
    skillList.appendChild(item);
  });
}

// ── Markdown → HTML ──
function mdToHtml(text) {
  let html = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>');
  return '<p>' + html + '</p>';
}

// ── UI helpers ──
function addUserMessage(content) {
  const msg = cloneTemplate('tmplUserMsg');
  msg.querySelector('.msg-content').innerHTML = mdToHtml(content);
  msg.querySelector('.msg-time').textContent = now();
  chatMessages.appendChild(msg);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return msg;
}

function addAsstMessage(content) {
  const msg = cloneTemplate('tmplAsstMsg');
  msg.querySelector('.msg-content').innerHTML = mdToHtml(content);
  msg.querySelector('.msg-time').textContent = now();
  chatMessages.appendChild(msg);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return msg;
}

function cloneTemplate(id) {
  const tmpl = document.getElementById(id);
  return tmpl.content.firstElementChild.cloneNode(true);
}

function setStreaming(v) {
  state.isStreaming = v;
  sendBtn.disabled = v;
  chatInput.disabled = v;
}

function updateStatus() {
  statusConv.textContent = '会话: ' + (state.convId ? state.convId.slice(0, 8) + '...' : '新建');
}

function updatePhase(phase) {
  state.phase = phase;
  statusPhase.textContent = '阶段: ' + phase;
}

function now() {
  return new Date().toLocaleTimeString('zh-CN', { hour12: false });
}

function addEventLog(type, detail) {
  const item = cloneTemplate('tmplEventItem');
  item.querySelector('.event-time').textContent = now();
  const tag = item.querySelector('.event-tag');
  tag.textContent = type;
  tag.className = 'event-tag tag-' + (
    type === 'meta' ? 'meta' :
    type === 'text_delta' ? 'text' :
    type === 'popup' ? 'popup' :
    type === 'card' ? 'card' :
    type === 'error' ? 'error' :
    type === 'done' ? 'done' :
    type === 'tool' ? 'tool' : 'meta'
  );
  item.querySelector('.event-detail').textContent = detail || '';
  eventLog.appendChild(item);
  eventLog.scrollTop = eventLog.scrollHeight;

  while (eventLog.children.length > 200) {
    eventLog.firstElementChild.remove();
  }
}

function formatEventDetail(data) {
  if (data.type === 'meta') {
    if (data.phase === 'tool_planned') return `Supervisor → ${data.tool_name}`;
    if (data.phase === 'supervisor_end') return `Supervisor → ${data.next}: ${data.reasoning || ''}`;
    return `${data.node || ''} ${data.status || ''}`;
  }
  if (data.type === 'text_delta') return (data.content || '').slice(0, 60);
  if (data.type === 'popup') return `fields: ${(data.fields || []).map(f => f.name).join(', ')}`;
  if (data.type === 'card') return `${data.card_type}: ${(data.data?.recommendations || []).length || 0} 项`;
  if (data.type === 'done') return `会话: ${(state.convId || '').slice(0, 8)}`;
  return '';
}
