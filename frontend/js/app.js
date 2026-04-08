/**
 * 무리없이 부산 — 공통 유틸리티 및 상태 관리.
 */

/* ── 상태 관리 (localStorage) ── */
function _lsGet(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key) || JSON.stringify(fallback)); }
  catch { localStorage.removeItem(key); return fallback; }
}

const AppState = {
  get mobility_types() { return _lsGet('mb_types', []); },
  set mobility_types(v) { localStorage.setItem('mb_types', JSON.stringify(v)); },
  get days() {
    return parseInt(localStorage.getItem('mb_days') || '1', 10);
  },
  set days(v) { localStorage.setItem('mb_days', String(v)); },
  get start_date() { return localStorage.getItem('mb_start_date') || ''; },
  set start_date(v) { localStorage.setItem('mb_start_date', v || ''); },
  get areas() { return _lsGet('mb_areas', []); },
  set areas(v) { localStorage.setItem('mb_areas', JSON.stringify(v)); },
  get courses() { return _lsGet('mb_courses', []); },
  set courses(v) { localStorage.setItem('mb_courses', JSON.stringify(v)); },
  get recommendation_meta() { return _lsGet('mb_recommendation_meta', null); },
  set recommendation_meta(v) { localStorage.setItem('mb_recommendation_meta', JSON.stringify(v)); },
  get selected_course() { return _lsGet('mb_selected', null); },
  set selected_course(v) { localStorage.setItem('mb_selected', JSON.stringify(v)); },
  clear() {
    ['mb_types', 'mb_days', 'mb_start_date', 'mb_areas', 'mb_courses', 'mb_recommendation_meta', 'mb_selected', 'mb_share_token'].forEach(k =>
      localStorage.removeItem(k)
    );
  }
};

/* ── API 호출 ── */
const API_BASE = '';

async function apiPost(path, body) {
  try {
    const resp = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  } catch (err) {
    showToast(`API 오류: ${err.message}`, 'error');
    return null;
  }
}

async function apiGet(path) {
  try {
    const resp = await fetch(`${API_BASE}${path}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  } catch (err) {
    showToast(`API 오류: ${err.message}`, 'error');
    return null;
  }
}

function buildRecommendationPayload() {
  const payload = {
    mobility_types: AppState.mobility_types,
    days: AppState.days,
    areas: AppState.areas,
  };
  // 여행 시작일 → YYYYMMDD 형식으로 변환
  if (AppState.start_date) {
    payload.start_date = AppState.start_date.replace(/-/g, '');
  }
  return payload;
}

function hasRecommendationContext() {
  return AppState.mobility_types.length > 0;
}

function storeRecommendationResult(result) {
  AppState.courses = result?.courses || [];
  AppState.recommendation_meta = result?.summary || null;
  return result;
}

async function requestRecommendations(payload = buildRecommendationPayload()) {
  const result = await apiPost('/api/recommend', payload);
  if (result && Array.isArray(result.courses)) {
    return storeRecommendationResult(result);
  }
  return result;
}

/* ── 토스트 알림 ── */
function showToast(message, type = 'info') {
  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    container.setAttribute('role', 'status');
    container.setAttribute('aria-live', 'polite');
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

/* ── 유틸 ── */
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function navigateTo(page) {
  window.location.href = page;
}

function gradeLabel(grade) {
  if (grade >= 5) return '최우수';
  if (grade >= 4) return '우수';
  if (grade >= 3) return '양호';
  return '주의';
}

function gradeBadgeClass(grade) {
  if (grade >= 4) return 'badge-green';
  if (grade >= 3) return 'badge-blue';
  return 'badge-orange';
}

function renderAccessDots(grade, max = 5) {
  let html = '<span class="access-dots">';
  for (let i = 0; i < max; i++) {
    html += `<span class="dot ${i < grade ? 'dot-filled' : 'dot-empty'}"></span>`;
  }
  html += '</span>';
  return html;
}

/* ── 즐겨찾기 ── */
const AppFavorites = {
  get list() { return JSON.parse(localStorage.getItem('mb_favorites') || '[]'); },
  toggle(courseId) {
    const list = this.list;
    const idx = list.indexOf(courseId);
    if (idx === -1) list.push(courseId); else list.splice(idx, 1);
    localStorage.setItem('mb_favorites', JSON.stringify(list));
    return idx === -1;
  },
  has(courseId) { return this.list.includes(courseId); }
};
