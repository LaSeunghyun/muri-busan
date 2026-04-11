/**
 * 무리없이 부산 — 추천 결과 렌더링.
 */

async function loadWeather() {
  const banner = document.getElementById('weatherBanner');
  if (!banner) return;
  let weather;
  try {
    const data = await apiGet('/api/weather');
    if (data && data.available) {
      weather = data;
      banner.innerHTML = `<span>${escapeHtml(data.icon)} 부산 현재 날씨 ${escapeHtml(data.sky)} ${escapeHtml(data.tmp)}</span>`;
      banner.style.display = 'flex';
    }
  } catch(e) { weather = { icon: '🌤', desc: '날씨 정보 없음' }; showToast('날씨 정보를 불러올 수 없습니다'); }
}
loadWeather();

(function () {
  const resultList = document.getElementById('resultList');
  const resultSummary = document.getElementById('resultSummary');
  const filterTabs = document.getElementById('filterTabs');
  const dayTabs = document.getElementById('dayTabs');
  const dayTabBar = document.getElementById('dayTabBar');
  const loadingState = document.getElementById('loadingState');

  const typeLabels = {
    wheelchair: '휠체어',
    stroller: '유아차',
    senior: '시니어',
    carrier: '보행보조',
  };

  const dayLabelsMap = { 1: '첫째 날', 2: '둘째 날', 3: '셋째 날', 4: '넷째 날', 5: '다섯째 날' };

  let allCourses = [];
  let activeFilter = 'all';
  let activeDay = 1;  // 0 = 전체 보기, 1+ = 특정 day만

  function showSkeletons() {
    if (loadingState) {
      loadingState.style.display = 'none';
    }
    resultList.innerHTML = '';
    for (let i = 0; i < 3; i++) {
      const sk = document.createElement('div');
      sk.className = 'skeleton-card';
      sk.innerHTML = `
        <div class="sk sk-title"></div>
        <div class="sk sk-text"></div>
        <div class="sk sk-text sk-short"></div>`;
      resultList.appendChild(sk);
    }
  }

  function hideSkeletons() {
    resultList.querySelectorAll('.skeleton-card').forEach(el => el.remove());
  }

  function getFilterLabel() {
    if (activeFilter === 'favorites') {
      return '즐겨찾기';
    }
    if (activeFilter === 'low-fatigue') {
      return '저피로순';
    }
    if (activeFilter === 'many-spots') {
      return '관광지 많은순';
    }
    return '전체';
  }

  function updateFilterTabs() {
    if (!filterTabs) return;
    filterTabs.querySelectorAll('.filter-tab').forEach(function (tab) {
      tab.classList.toggle('active', tab.dataset.filter === activeFilter);
    });
  }

  function getFilteredCourses() {
    let filtered = [...allCourses];
    // Day 필터 (멀티데이일 때만 적용)
    const totalDays = parseInt(AppState.days, 10) || 1;
    if (totalDays > 1 && activeDay > 0) {
      filtered = filtered.filter(course => (course.day || 1) === activeDay);
    }
    if (activeFilter === 'favorites') {
      filtered = filtered.filter(course => AppFavorites.has(course.id));
    } else if (activeFilter === 'low-fatigue') {
      filtered.sort((a, b) => a.total_fatigue - b.total_fatigue);
    } else if (activeFilter === 'many-spots') {
      filtered.sort((a, b) => b.spots.length - a.spots.length);
    }
    return filtered;
  }

  function renderDayTabs() {
    if (!dayTabs || !dayTabBar) return;
    const totalDays = parseInt(AppState.days, 10) || 1;
    if (totalDays <= 1) {
      dayTabBar.style.display = 'none';
      return;
    }
    // 코스가 있는 day만 탭으로 노출
    const dayCounts = new Map();
    allCourses.forEach(c => {
      const d = c.day || 1;
      dayCounts.set(d, (dayCounts.get(d) || 0) + 1);
    });
    // 1일 이하로 코스가 생성되었으면 탭 숨김 (외로운 Day 탭 방지)
    if (dayCounts.size <= 1) {
      dayTabBar.style.display = 'none';
      return;
    }
    const sortedDays = Array.from(dayCounts.keys()).sort((a, b) => a - b);
    // activeDay가 코스 없는 day면 첫 번째 가용 day로 보정
    if (!dayCounts.has(activeDay)) activeDay = sortedDays[0];

    dayTabBar.style.display = '';
    dayTabs.innerHTML = sortedDays.map(d => {
      const isActive = d === activeDay;
      const label = dayLabelsMap[d] || `${d}일차`;
      const count = dayCounts.get(d);
      return `<button class="day-tab${isActive ? ' active' : ''}" data-day="${d}" aria-pressed="${isActive}">
        <span class="day-tab-num">Day ${d}</span>
        <span class="day-tab-label">${label}</span>
        <span class="day-tab-count">${count}코스</span>
      </button>`;
    }).join('');

    dayTabs.querySelectorAll('.day-tab').forEach(btn => {
      btn.addEventListener('click', function () {
        const requested = parseInt(this.dataset.day, 10);
        const availableDays = Array.from(dayCounts.keys()).sort((a, b) => a - b);
        // 요청: "첫째날 선택하면 둘째날" — 같은 day를 다시 클릭하면 다음 day로 이동
        if (requested === activeDay) {
          const idx = availableDays.indexOf(activeDay);
          activeDay = availableDays[(idx + 1) % availableDays.length];
        } else {
          activeDay = requested;
        }
        renderDayTabs();
        renderCurrentFilter();
        // 결과 영역 상단으로 부드럽게 스크롤
        if (resultList) resultList.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });
  }

  function formatTripPeriod(startDate, days) {
    if (!startDate) return '';
    const start = new Date(startDate);
    if (isNaN(start.getTime())) return startDate;
    const dayCount = Math.max(1, parseInt(days, 10) || 1);
    if (dayCount === 1) {
      return startDate;
    }
    const end = new Date(start);
    end.setDate(start.getDate() + dayCount - 1);
    const pad = (n) => String(n).padStart(2, '0');
    const endStr = `${end.getFullYear()}-${pad(end.getMonth() + 1)}-${pad(end.getDate())}`;
    return `${startDate} ~ ${endStr}`;
  }

  function weatherChip(weather) {
    if (!weather) return '';
    // available=false여도 sky/tmp가 있으면 표시
    const icon = weather.icon || '⛅';
    const sky = weather.sky || '';
    const tmp = weather.tmp || '';
    const parts = [icon];
    if (sky) parts.push(sky);
    if (tmp) parts.push(tmp);
    if (parts.length === 1) return ''; // 아이콘만 있으면 표시 X
    return `<span class="summary-chip summary-chip-weather">날씨 ${parts.join(' ')}</span>`;
  }

  function renderSummary(courses) {
    const meta = AppState.recommendation_meta || {};
    const selectedTypes = AppState.mobility_types.map(type => typeLabels[type] || type).join(' · ') || '선택 없음';
    const selectedAreas = AppState.areas.length ? AppState.areas.join(' · ') : '부산 전역';
    const appliedAreas = (meta.applied_areas || []).length ? meta.applied_areas.join(' · ') : selectedAreas;
    const fallbackBanner = meta.fallback_used ? `
      <div class="result-advisory" role="status" aria-live="polite">
        <strong>권역 확장 안내</strong>
        <span>${meta.message || '선택 권역에서 결과가 부족해 추천 범위를 넓혔습니다.'}</span>
      </div>` : '';
    const festivalCount = meta.festival_count || 0;
    const festivalBanner = festivalCount > 0 ? `
      <div class="result-advisory" role="status" style="background:#fff8e1;border-color:#ffe082">
        <strong>🎪 행사 ${festivalCount}건 포함</strong>
        <span>여행 기간 중 진행되는 행사·축제가 코스에 자동 반영되었습니다.</span>
      </div>` : '';

    resultSummary.innerHTML = `
      <div class="result-summary-head">
        <div>
          <div class="info"><strong>${courses.length}개</strong> 코스 추천</div>
          <p class="result-summary-copy">${getFilterLabel()} 기준으로 정렬된 결과예요.</p>
        </div>
        <div class="result-summary-actions">
          <button class="btn-outline summary-btn" id="refreshResultsBtn">다시 분석</button>
          <button class="btn-primary summary-btn" id="editConditionsBtn">조건 수정</button>
        </div>
      </div>
      <div class="result-summary-chips" aria-label="추천 조건 요약">
        <span class="summary-chip">여행자 ${selectedTypes}</span>
        <span class="summary-chip">${AppState.days}일 일정</span>
        ${AppState.start_date ? `<span class="summary-chip">기간 ${formatTripPeriod(AppState.start_date, AppState.days)}</span>` : ''}
        ${weatherChip(meta.weather)}
        <span class="summary-chip">요청 권역 ${selectedAreas}</span>
        <span class="summary-chip">적용 권역 ${appliedAreas}</span>
      </div>
      ${fallbackBanner}
      ${festivalBanner}`;

    const refreshBtn = document.getElementById('refreshResultsBtn');
    const editBtn = document.getElementById('editConditionsBtn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', function () {
        rerunRecommendations();
      });
    }
    if (editBtn) {
      editBtn.addEventListener('click', function () {
        navigateTo('/onboarding.html');
      });
    }
  }

  function renderEmptyState() {
    const title = activeFilter === 'favorites'
      ? '즐겨찾기한 코스가 없습니다'
      : '조건에 맞는 코스가 없습니다';
    const message = activeFilter === 'favorites'
      ? '마음에 드는 코스를 찜해두면 여기서 빠르게 다시 볼 수 있어요.'
      : '권역이나 여행자 유형을 조금 넓혀서 다시 추천받아보세요.';
    resultList.innerHTML = `
      <div class="empty-state">
        <div class="icon" aria-hidden="true">${activeFilter === 'favorites' ? '♡' : '📭'}</div>
        <h3>${title}</h3>
        <p>${message}</p>
      </div>`;
  }

  function renderCourses(courses) {
    if (loadingState) {
      loadingState.style.display = 'none';
    }
    resultList.innerHTML = '';

    if (courses.length === 0) {
      renderEmptyState();
      return;
    }

    // 멀티데이: Day별 그룹 헤더 삽입
    const days = AppState.days || 1;
    const dayLabels = { 1: '첫째 날', 2: '둘째 날', 3: '셋째 날', 4: '넷째 날', 5: '다섯째 날' };
    let lastDay = 0;
    const dayCounts = new Map();
    courses.forEach(function (c) { dayCounts.set(c.day, (dayCounts.get(c.day) || 0) + 1); });

    courses.forEach(function (course) {
      if (days > 1 && course.day && course.day !== lastDay) {
        lastDay = course.day;
        const header = document.createElement('div');
        header.className = 'day-group-header';
        header.setAttribute('role', 'heading');
        header.setAttribute('aria-level', '2');
        header.innerHTML = `
          <span class="day-group-badge">Day ${course.day}</span>
          <span class="day-group-label">${dayLabels[course.day] || course.day + '일차'}</span>
          <span class="day-group-count">${dayCounts.get(course.day) || 0}개 코스</span>`;
        resultList.appendChild(header);
      }
      const spotsNames = course.spots.map(s => escapeHtml(s.name)).join(' → ');
      const avgGrade = course.accessibility_avg || 3;
      const gradeText = gradeLabel(Math.round(avgGrade));
      const wheelchairStatus = course.spots.every(s => s.wheelchair_accessible === true) ? 'ok'
        : course.spots.some(s => s.wheelchair_accessible === false) ? 'fail' : 'unknown';
      const strollerStatus = course.spots.every(s => s.stroller_accessible === true) ? 'ok'
        : course.spots.some(s => s.stroller_accessible === false) ? 'fail' : 'unknown';
      const restroomStatus = course.spots.every(s => s.restroom_accessible === true) ? 'ok'
        : course.spots.some(s => s.restroom_accessible === false) ? 'fail' : 'unknown';
      const hasElevator = course.spots.some(s => s.elevator);
      const accessChecks = [];
      const fatigueClass = course.total_fatigue <= 50 ? 'badge-green'
        : course.total_fatigue <= 80 ? 'badge-orange'
        : 'badge-red';
      const isFav = AppFavorites.has(course.id);
      const thumbUrl = course.spots[0] && course.spots[0].image_url;

      accessChecks.push(wheelchairStatus === 'ok' ? { label: '✓ 휠체어 OK', ok: true, status: 'ok' }
        : wheelchairStatus === 'fail' ? { label: '✗ 휠체어 제한', ok: false, status: 'fail' }
        : { label: '? 휠체어 미확인', ok: false, status: 'unknown' });
      accessChecks.push(strollerStatus === 'ok' ? { label: '✓ 유아차 OK', ok: true, status: 'ok' }
        : strollerStatus === 'fail' ? { label: '✗ 유아차 제한', ok: false, status: 'fail' }
        : { label: '? 유아차 미확인', ok: false, status: 'unknown' });
      accessChecks.push(restroomStatus === 'ok' ? { label: '✓ 장애인화장실', ok: true, status: 'ok' }
        : restroomStatus === 'fail' ? { label: '✗ 화장실 제한', ok: false, status: 'fail' }
        : { label: '? 화장실 미확인', ok: false, status: 'unknown' });
      if (hasElevator) accessChecks.push({ label: '✓ 엘리베이터', ok: true, status: 'ok' });

      const card = document.createElement('article');
      card.className = 'course-card';
      card.setAttribute('role', 'button');
      card.setAttribute('tabindex', '0');
      card.setAttribute('aria-label', `${course.name} 코스 상세 보기`);
      card.innerHTML = `
        ${thumbUrl ? `<div class="course-card-thumb" style="height:140px;overflow:hidden;position:relative">
          <img src="${escapeHtml(thumbUrl)}" alt="${escapeHtml(course.spots[0].name)}" loading="lazy" style="width:100%;height:100%;object-fit:cover;display:block;transition:transform 0.4s ease">
          <div style="position:absolute;inset:0;background:linear-gradient(180deg,transparent 50%,rgba(0,0,0,0.4) 100%)"></div>
          <div style="position:absolute;bottom:8px;left:12px;display:flex;gap:6px;flex-wrap:wrap">
            <span class="badge badge-blue" style="backdrop-filter:blur(4px);background:rgba(235,240,248,0.9)">📍 ${course.spots.length}개소</span>
            <span class="badge ${fatigueClass}" style="backdrop-filter:blur(4px)">피로도 ${course.total_fatigue}</span>
          </div>
        </div>` : ''}
        <div class="course-card-header">
          <div class="course-card-top">
            <div class="access-grade">
              <span class="access-label">${gradeText}</span>
              <div class="access-progress-wrap">
                <div class="access-progress-bar" aria-label="접근성 등급 ${gradeText}" title="${gradeText}">
                  <div class="access-progress-fill grade-${Math.round(avgGrade)}"></div>
                </div>
              </div>
            </div>
            <div class="course-card-top-right">
              <button class="fav-btn" aria-label="즐겨찾기" data-id="${course.id}">${isFav ? '♥' : '♡'}</button>
            </div>
          </div>
          <div class="course-name">${escapeHtml(course.name)}</div>
          <div class="course-stops">${spotsNames}</div>
        </div>
        ${course.ai_description ? `
        <div class="course-ai-block">
          <span class="course-ai-label">✦ AI 추천 이유</span>
          <p class="course-ai-desc">${escapeHtml(course.ai_description)}</p>
          ${course.ai_highlights?.length ? `<div class="course-ai-chips">${course.ai_highlights.map(h=>`<span class="ai-chip">${escapeHtml(h)}</span>`).join('')}</div>` : ''}
          ${course.ai_tip ? `<div class="course-ai-tip">💡 ${escapeHtml(course.ai_tip)}</div>` : ''}
        </div>` : ''}
        <div class="course-meta">
          <div class="course-meta-item">
            <span class="ico" aria-hidden="true">⏱</span>
            <span>약 <strong>${course.total_time_min}분</strong></span>
          </div>
          <div class="course-meta-item">
            <span class="ico" aria-hidden="true">📏</span>
            <span><strong>${course.distance_km}km</strong></span>
          </div>
          <div class="course-meta-item">
            <span class="ico" aria-hidden="true">🚻</span>
            <span>쉼터 <strong>${course.rest_spots}</strong></span>
          </div>
        </div>
        <div class="course-access-checks">
          ${accessChecks.map(check =>
            `<span class="check-chip ${check.status === 'ok' ? '' : check.status === 'unknown' ? 'unknown' : 'warn'}">${check.label}${check.status === 'unknown' ? '<span class="check-chip-info" title="TourAPI에 접근성 정보가 없는 장소입니다. 방문 전 확인 권장">&#8505;</span>' : ''}</span>`
          ).join('')}
        </div>
        <div class="course-card-footer">
          <span class="source">${course.ai_description ? 'AI + 공공데이터 기반 추천' : '공공데이터 기반 추천'}</span>
          <span class="arrow" aria-hidden="true">→</span>
        </div>`;

      const favBtn = card.querySelector('.fav-btn');
      favBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        const added = AppFavorites.toggle(course.id);
        favBtn.textContent = added ? '♥' : '♡';
        favBtn.style.color = added ? 'var(--primary)' : '';
        if (activeFilter === 'favorites') {
          renderCurrentFilter();
        }
      });
      if (isFav) {
        favBtn.style.color = 'var(--primary)';
      }

      card.addEventListener('click', function () {
        AppState.selected_course = course;
        navigateTo('/course.html?id=' + course.id);
      });
      card.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') card.click();
      });

      resultList.appendChild(card);
    });
  }

  function renderCurrentFilter() {
    updateFilterTabs();
    renderDayTabs();
    const filtered = getFilteredCourses();
    renderSummary(filtered);
    renderCourses(filtered);
  }

  function showRetryError() {
    hideSkeletons();
    resultList.innerHTML = `
      <div class="empty-state">
        <div class="icon" aria-hidden="true">⚠️</div>
        <h3>추천 결과를 불러오지 못했습니다</h3>
        <p>네트워크 연결을 확인하고 다시 시도해주세요.</p>
        <button class="btn-outline" id="retryBtn" style="width:auto;padding:0 24px;margin-top:8px">다시 시도</button>
      </div>`;
    const retryBtn = document.getElementById('retryBtn');
    if (retryBtn) {
      retryBtn.addEventListener('click', function () {
        rerunRecommendations();
      });
    }
  }

  async function rerunRecommendations() {
    showSkeletons();
    const result = await requestRecommendations();
    if (!result?.courses?.length) {
      showRetryError();
      return;
    }
    hideSkeletons();
    allCourses = result.courses;
    renderCurrentFilter();
    showToast('추천 결과를 최신 조건으로 다시 분석했어요.', 'success');
    if (result.summary?.fallback_used) {
      showToast('선택 지역에 코스가 부족해 인근 지역을 포함했어요', 'info');
    }
    // 추천 요청 로그 저장 (fire-and-forget, 실패해도 UX 영향 없음)
    if (typeof logRecommendationSilent === 'function') {
      logRecommendationSilent(result).catch(() => {});
    }
    // 만족도 조사는 course.html에서 처리
  }

  async function init() {
    const stored = AppState.courses || [];

    if (stored.length === 0) {
      if (!hasRecommendationContext()) {
        if (loadingState) {
          loadingState.innerHTML = `
            <div class="empty-state">
              <div class="icon" aria-hidden="true">🔍</div>
              <h3>추천 결과가 없습니다</h3>
              <p>온보딩을 먼저 완료해주세요.<br>조건에 맞는 관광지가 없을 수도 있습니다.</p>
              <button class="btn-outline" style="width:auto;padding:0 24px;margin-top:8px" onclick="navigateTo('/onboarding.html')">다시 설정하기</button>
            </div>`;
        }
        renderSummary([]);
        return;
      }
      await rerunRecommendations();
      return;
    }

    allCourses = stored;
    renderCurrentFilter();
    if (AppState.recommendation_meta?.fallback_used) {
      showToast('선택 지역에 코스가 부족해 인근 지역을 포함했어요', 'info');
    }
    // 만족도 조사는 course.html에서 처리
  }

  // ── 만족도 조사 블록 ─────────────────────────────────
  function setupSatisfactionBlock() {
    const block = document.getElementById('satisfactionBlock');
    if (!block || !allCourses.length) return;
    // 이미 제출한 세션이면 노출 금지
    if (sessionStorage.getItem('mb_survey_done') === '1') {
      block.hidden = true;
      return;
    }
    // 초기화 (이미 바인딩된 경우 중복 방지)
    if (block.dataset.bound === '1') {
      block.hidden = false;
      return;
    }
    block.dataset.bound = '1';
    block.hidden = false;

    const scaleEl = document.getElementById('satisfactionScale');
    const panelEl = document.getElementById('satisfactionReasonPanel');
    const chipsEl = document.getElementById('satisfactionReasonChips');
    const textEl = document.getElementById('satisfactionText');
    const countEl = document.getElementById('satisfactionCharCount');
    const submitEl = document.getElementById('satisfactionSubmit');
    const skipEl = document.getElementById('satisfactionSkip');
    const doneEl = document.getElementById('satisfactionDone');

    let selectedScore = 0;

    function openReasonPanel(open) {
      if (!panelEl) return;
      if (open) {
        panelEl.classList.add('open');
        panelEl.setAttribute('aria-hidden', 'false');
      } else {
        panelEl.classList.remove('open');
        panelEl.setAttribute('aria-hidden', 'true');
      }
    }

    if (scaleEl) {
      scaleEl.querySelectorAll('.satisfaction-btn').forEach(btn => {
        btn.addEventListener('click', function () {
          const score = parseInt(this.dataset.score, 10);
          selectedScore = score;
          scaleEl.querySelectorAll('.satisfaction-btn').forEach(b => {
            b.setAttribute('aria-checked', b === this ? 'true' : 'false');
          });
          if (submitEl) submitEl.disabled = false;
          openReasonPanel(score <= 2);
        });
      });
    }

    if (chipsEl) {
      chipsEl.querySelectorAll('.satisfaction-reason-chip').forEach(chip => {
        chip.addEventListener('click', function () {
          const pressed = this.getAttribute('aria-pressed') === 'true';
          this.setAttribute('aria-pressed', pressed ? 'false' : 'true');
        });
      });
    }

    if (textEl && countEl) {
      textEl.addEventListener('input', function () {
        countEl.textContent = String(this.value.length);
      });
    }

    if (submitEl) {
      submitEl.addEventListener('click', async function () {
        if (!selectedScore) return;
        submitEl.disabled = true;
        const selectedReasons = chipsEl
          ? Array.from(chipsEl.querySelectorAll('.satisfaction-reason-chip[aria-pressed="true"]'))
              .map(c => c.dataset.reason)
          : [];
        const text = textEl ? textEl.value.trim() : '';
        const res = typeof submitSatisfactionSurvey === 'function'
          ? await submitSatisfactionSurvey(selectedScore, selectedReasons, text)
          : { ok: false };
        if (res && res.ok) {
          sessionStorage.setItem('mb_survey_done', '1');
          if (scaleEl) scaleEl.style.display = 'none';
          openReasonPanel(false);
          if (document.querySelector('.satisfaction-actions')) {
            document.querySelector('.satisfaction-actions').style.display = 'none';
          }
          if (doneEl) doneEl.hidden = false;
        } else {
          submitEl.disabled = false;
          showToast('의견 저장에 실패했어요. 잠시 후 다시 시도해주세요.', 'error');
        }
      });
    }

    if (skipEl) {
      skipEl.addEventListener('click', function () {
        sessionStorage.setItem('mb_survey_done', '1');
        block.hidden = true;
      });
    }
  }

  document.addEventListener('click', function (e) {
    const tab = e.target.closest('[data-filter]');
    if (!tab) return;
    activeFilter = tab.dataset.filter;
    renderCurrentFilter();
  });

  init();
})();
