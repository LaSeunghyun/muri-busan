/**
 * 무리없이 부산 — 공통 유틸리티 및 상태 관리.
 */

/* ── 상태 관리 (localStorage + 인메모리 폴백) ── */
// 개인정보보호 모드 등 localStorage 접근 불가 시 인메모리 객체로 대체
const _mem = {};

function _lsSet(key, val) {
  try { localStorage.setItem(key, val); } catch { _mem[key] = val; }
}

function _lsGetRaw(key) {
  try { const v = localStorage.getItem(key); return v !== null ? v : (_mem[key] ?? null); }
  catch { return _mem[key] ?? null; }
}

function _lsRemove(key) {
  try { localStorage.removeItem(key); } catch { /* ignore */ }
  delete _mem[key];
}

function _lsGet(key, fallback) {
  try { return JSON.parse(_lsGetRaw(key) || JSON.stringify(fallback)); }
  catch { _lsRemove(key); return fallback; }
}

function _ensureSessionId() {
  let sid = _lsGetRaw('mb_session_id');
  if (!sid) {
    try {
      sid = (crypto && crypto.randomUUID) ? crypto.randomUUID()
        : ('s-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10));
    } catch {
      sid = 's-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
    }
    _lsSet('mb_session_id', sid);
  }
  return sid;
}

const AppState = {
  get session_id() { return _ensureSessionId(); },
  get mobility_types() { return _lsGet('mb_types', []); },
  set mobility_types(v) { _lsSet('mb_types', JSON.stringify(v)); },
  get days() {
    return parseInt(_lsGetRaw('mb_days') || '1', 10);
  },
  set days(v) { _lsSet('mb_days', String(v)); },
  get start_date() { return _lsGetRaw('mb_start_date') || ''; },
  set start_date(v) { _lsSet('mb_start_date', v || ''); },
  get areas() { return _lsGet('mb_areas', []); },
  set areas(v) { _lsSet('mb_areas', JSON.stringify(v)); },
  get courses() { return _lsGet('mb_courses', []); },
  set courses(v) { _lsSet('mb_courses', JSON.stringify(v)); },
  get recommendation_meta() { return _lsGet('mb_recommendation_meta', null); },
  set recommendation_meta(v) { _lsSet('mb_recommendation_meta', JSON.stringify(v)); },
  get selected_course() { return _lsGet('mb_selected', null); },
  set selected_course(v) { _lsSet('mb_selected', JSON.stringify(v)); },
  get log_id() { return _lsGetRaw('mb_log_id') || null; },
  set log_id(v) { v ? _lsSet('mb_log_id', v) : _lsRemove('mb_log_id'); },
  clear() {
    ['mb_types', 'mb_days', 'mb_start_date', 'mb_areas', 'mb_courses', 'mb_recommendation_meta', 'mb_selected', 'mb_share_token', 'mb_log_id'].forEach(k =>
      _lsRemove(k)
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
  return null;
}

/* ── 분석/로깅 (fire-and-forget, 실패해도 UX 영향 없음) ── */
async function logRecommendationSilent(result) {
  try {
    const courses = (result && result.courses) || [];
    const summary = (result && result.summary) || {};
    const body = {
      session_id: AppState.session_id,
      days: parseInt(AppState.days, 10) || 1,
      mobility_types: AppState.mobility_types,
      areas: AppState.areas,
      start_date: AppState.start_date || null,
      course_ids: courses.map(c => c.id).filter(Boolean),
      course_count: courses.length,
      fallback_used: !!summary.fallback_used,
      ai_enabled: !!summary.ai_enabled,
    };
    const resp = await fetch('/api/log/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    if (data && data.log_id) AppState.log_id = data.log_id;
    return data;
  } catch (_) {
    return null;
  }
}

async function submitSatisfactionSurvey(score, reasonCategories, reasonText) {
  try {
    const body = {
      session_id: AppState.session_id,
      log_id: AppState.log_id || null,
      score: parseInt(score, 10),
      reason_categories: reasonCategories || [],
      reason_text: (reasonText || '').trim() || null,
    };
    const resp = await fetch('/api/log/survey', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    return await resp.json();
  } catch (err) {
    return { ok: false, error: err.message };
  }
}

/* ── 인터랙션 로그 (fire-and-forget) ── */
function logInteraction(eventType, eventData = {}) {
  try {
    const body = JSON.stringify({
      session_id: AppState.session_id,
      log_id: AppState.log_id || null,
      event_type: eventType,
      event_data: eventData,
    });
    // sendBeacon 우선 (페이지 이탈 시에도 전송 보장), 폴백은 fetch keepalive
    const url = '/api/log/interaction';
    if (navigator.sendBeacon) {
      navigator.sendBeacon(url, new Blob([body], { type: 'application/json' }));
    } else {
      fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true }).catch(() => {});
    }
  } catch (_) { /* 로깅 실패는 무시 */ }
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
window.gradeLabel = gradeLabel;

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

/* ── 공통 푸터 (개인정보 고지 + 데이터 출처) ── */
function renderAppFooter() {
  if (document.querySelector('.app-footer')) return;
  const footer = document.createElement('footer');
  footer.className = 'app-footer';
  footer.setAttribute('role', 'contentinfo');
  footer.innerHTML = `
    <div class="app-footer-inner">
      <p class="app-footer-copy">© 무리없이 부산 · 이동약자 맞춤 부산 관광 코스 추천</p>
      <p class="app-footer-notice">추천 품질 개선을 위해 익명 세션 식별자 기반 사용 통계(코스 열람·만족도 응답)를 수집합니다. 성명·연락처 등 개인식별정보는 수집하지 않으며, 만족도 자유 입력란의 내용은 서비스 개선 목적으로만 활용합니다.</p>
      <p class="app-footer-data">데이터 출처: 한국관광공사 TourAPI(KorService2·무장애 여행 정보) · 기상청 단기예보 · 카카오 지도 SDK · OpenStreetMap(OSRM)</p>
    </div>`;
  document.body.appendChild(footer);
}
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', renderAppFooter);
} else {
  renderAppFooter();
}

/* ── 즐겨찾기 ── */
const AppFavorites = {
  get list() { return _lsGet('mb_favorites', []); },
  toggle(courseId) {
    const list = this.list;
    const idx = list.indexOf(courseId);
    if (idx === -1) list.push(courseId); else list.splice(idx, 1);
    _lsSet('mb_favorites', JSON.stringify(list));
    return idx === -1;
  },
  has(courseId) { return this.list.includes(courseId); }
};
