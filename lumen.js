/* ═══════════════════════════════════════
   LUMEN AIOps — Main JavaScript
═══════════════════════════════════════ */

'use strict';

/* ── THEME ── */
const THEME_KEY = 'lumen-theme';

function getTheme() {
  return localStorage.getItem(THEME_KEY) || 'light';
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  const sun  = document.getElementById('icon-sun');
  const moon = document.getElementById('icon-moon');
  if (sun)  sun.style.display  = theme === 'dark' ? 'block' : 'none';
  if (moon) moon.style.display = theme === 'dark' ? 'none'  : 'block';
}

function toggleTheme() {
  const next = getTheme() === 'light' ? 'dark' : 'light';
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
}

/* ── INIT ── */
document.addEventListener('DOMContentLoaded', function () {
  // Theme
  applyTheme(getTheme());

  const themeBtn = document.getElementById('theme-toggle-btn');
  if (themeBtn) themeBtn.addEventListener('click', toggleTheme);

  // Sidebar aktif link vurgula
  highlightActiveSidebarItem();

  // Auto-refresh live stream (her 30sn)
  if (document.getElementById('live-stream-container')) {
    setInterval(refreshLiveStream, 30000);
  }
});

/* ── SIDEBAR ── */
function highlightActiveSidebarItem() {
  const path = window.location.pathname;
  document.querySelectorAll('.sb-item').forEach(function (el) {
    if (el.getAttribute('href') === path) {
      el.classList.add('active');
    }
  });
}

/* ── LIVE STREAM ── */
function refreshLiveStream() {
  fetch('/api/v1/anomalies/recent?limit=5')
    .then(r => r.json())
    .then(data => {
      const container = document.getElementById('live-stream-container');
      if (!container || !data.items) return;
      container.innerHTML = data.items.map(function (item) {
        const colorMap = { DISASTER: 'red', HIGH: 'orange', WARNING: 'amber' };
        const c = colorMap[item.severity] || 'txt2';
        return `<div class="log-row">
          <div class="log-ts">${item.time}</div>
          <div class="log-svc" style="color:var(--${c})">${truncate(item.service, 12)}</div>
          <div class="log-msg">${item.type} · %${item.error_rate} · ${item.elapsed}ms</div>
        </div>`;
      }).join('');
    })
    .catch(function () {});
}

/* ── UTILS ── */
function truncate(str, n) {
  return str && str.length > n ? str.slice(0, n) + '…' : str;
}

function setTimeFilter(btn, val) {
  document.querySelectorAll('.card-actions .btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  // Sayfaya özel davranış için override edilebilir
  if (window.onTimeFilterChange) window.onTimeFilterChange(val);
}

/* ── TOAST ── */
function showToast(msg, type) {
  type = type || 'info';
  const colors = { info: 'var(--blue)', success: 'var(--green)', error: 'var(--red)', warning: 'var(--orange)' };
  const toast = document.createElement('div');
  toast.style.cssText = `
    position:fixed;bottom:20px;right:20px;z-index:9999;
    background:var(--card);border:1px solid var(--border);
    border-left:3px solid ${colors[type]};
    padding:12px 16px;border-radius:6px;
    font-size:13px;color:var(--txt);
    box-shadow:0 4px 12px rgba(0,0,0,.15);
    animation:slideIn .2s ease;
    max-width:320px;
  `;
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(function () { toast.remove(); }, 3500);
}

/* ── API HELPERS ── */
async function apiGet(url) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' }
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function apiPost(url, data) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

/* ── LLM RCA MODAL ── */
function openLLMModal(title) {
  const modal = document.getElementById('llm-modal');
  if (modal) {
    document.getElementById('llm-modal-title').textContent = title || 'LLM Analizi';
    document.getElementById('llm-modal-body').textContent  = 'Yükleniyor...';
    modal.style.display = 'flex';
  }
}

function closeLLMModal() {
  const modal = document.getElementById('llm-modal');
  if (modal) modal.style.display = 'none';
}

/* ── CHART HELPERS ── */
function severityColor(sev) {
  const map = { DISASTER: '#dc3545', HIGH: '#fd7e14', WARNING: '#ffc107' };
  return map[sev] || '#7a7a7a';
}

/* ── ANIMATE ── */
const style = document.createElement('style');
style.textContent = `
  @keyframes slideIn {
    from { transform: translateX(100%); opacity: 0; }
    to   { transform: translateX(0);   opacity: 1; }
  }
`;
document.head.appendChild(style);
