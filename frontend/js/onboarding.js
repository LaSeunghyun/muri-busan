/**
 * 무리없이 부산 — 온보딩 3단계 로직 (모바일 + PC 동기화).
 */
(function () {
  let currentStep = 1;

  // 모바일/PC 공통 헬퍼
  function getAll(id) {
    const els = [];
    if (document.getElementById(id)) els.push(document.getElementById(id));
    if (document.getElementById(id + 'Pc')) els.push(document.getElementById(id + 'Pc'));
    return els;
  }

  const steps = [
    document.getElementById('step1'),
    document.getElementById('step2'),
    document.getElementById('step3'),
  ];
  const progressFill = document.getElementById('progressFill');
  const headerTitle = document.getElementById('headerTitle');
  const stepIndicator = document.getElementById('stepIndicator');
  const backBtn = document.getElementById('backBtn');

  function showStep(n) {
    currentStep = n;
    steps.forEach((s, i) => {
      if (s) s.style.display = i === n - 1 ? 'block' : 'none';
    });
    if (progressFill) progressFill.style.width = Math.round((n / 3) * 100) + '%';
    if (stepIndicator) stepIndicator.textContent = n + ' / 3';
    const titles = ['여행자 정보 입력', '여행 기간', '권역 선택'];
    if (headerTitle) headerTitle.textContent = titles[n - 1];
    // PC 스텝바 active/completed 상태 갱신
    ['pcStep1', 'pcStep2', 'pcStep3'].forEach(function (id, i) {
      var el = document.getElementById(id);
      if (!el) return;
      el.classList.toggle('active', i === n - 1);
      el.classList.toggle('done', i < n - 1);
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  /* 뒤로 가기 */
  if (backBtn) {
    backBtn.addEventListener('click', function () {
      if (currentStep > 1) showStep(currentStep - 1);
      else navigateTo('/');
    });
  }

  /* ── Step 1: 유형 선택 ── */
  function syncTypeCards() {
    const selectedTypes = AppState.mobility_types;
    getAll('typeGrid').forEach(function (grid) {
      grid.querySelectorAll('.ob-choice-card').forEach(function (card) {
        const sel = selectedTypes.includes(card.dataset.type);
        card.classList.toggle('selected', sel);
        card.setAttribute('aria-checked', sel ? 'true' : 'false');
      });
    });
    const disabled = selectedTypes.length === 0;
    getAll('step1Next').forEach(function (btn) { btn.disabled = disabled; });
  }

  getAll('typeGrid').forEach(function (grid) {
    grid.addEventListener('click', function (e) {
      const card = e.target.closest('.ob-choice-card');
      if (!card) return;
      const types = AppState.mobility_types.slice();
      const t = card.dataset.type;
      const idx = types.indexOf(t);
      if (idx === -1) types.push(t); else types.splice(idx, 1);
      AppState.mobility_types = types;
      syncTypeCards();
    });
    grid.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        const card = e.target.closest('.ob-choice-card');
        if (card) card.click();
      }
    });
  });

  getAll('step1Next').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (AppState.mobility_types.length > 0) showStep(2);
    });
  });

  /* ── Step 2: 시작일 + 기간 선택 ── */
  // 날짜 동기화 (모바일/PC)
  ['startDate', 'startDatePc'].forEach(function (id) {
    const el = document.getElementById(id);
    if (!el) return;
    // 기본값: 오늘
    if (!AppState.start_date) {
      AppState.start_date = new Date().toISOString().slice(0, 10);
    }
    el.value = AppState.start_date;
    el.min = new Date().toISOString().slice(0, 10);
    el.addEventListener('change', function () {
      AppState.start_date = el.value;
      // 다른 필드도 동기화
      ['startDate', 'startDatePc'].forEach(function (otherId) {
        const other = document.getElementById(otherId);
        if (other && other !== el) other.value = el.value;
      });
    });
  });

  function syncDurationChips() {
    const days = AppState.days;
    getAll('durationRow').forEach(function (row) {
      row.querySelectorAll('.duration-chip').forEach(function (chip) {
        const sel = parseInt(chip.dataset.days, 10) === days;
        chip.classList.toggle('selected', sel);
        chip.setAttribute('aria-checked', sel ? 'true' : 'false');
      });
    });
    const disabled = days === 0;
    getAll('step2Next').forEach(function (btn) { btn.disabled = disabled; });
  }

  getAll('durationRow').forEach(function (row) {
    row.addEventListener('click', function (e) {
      const chip = e.target.closest('.duration-chip');
      if (!chip) return;
      AppState.days = parseInt(chip.dataset.days, 10);
      syncDurationChips();
    });
    row.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        const chip = e.target.closest('.duration-chip');
        if (chip) chip.click();
      }
    });
  });

  getAll('step2Next').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (AppState.days > 0) showStep(3);
    });
  });

  /* ── Step 3: 권역 선택 ── */
  function syncAreaChips() {
    const areas = AppState.areas;
    getAll('areaGrid').forEach(function (grid) {
      grid.querySelectorAll('.area-chip').forEach(function (chip) {
        const sel = areas.includes(chip.dataset.area);
        chip.classList.toggle('selected', sel);
        chip.setAttribute('aria-checked', sel ? 'true' : 'false');
      });
    });
  }

  getAll('areaGrid').forEach(function (grid) {
    grid.addEventListener('click', function (e) {
      const chip = e.target.closest('.area-chip');
      if (!chip) return;
      const areas = AppState.areas.slice();
      const a = chip.dataset.area;
      const idx = areas.indexOf(a);
      if (idx === -1) areas.push(a); else areas.splice(idx, 1);
      AppState.areas = areas;
      syncAreaChips();
    });
    grid.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        const chip = e.target.closest('.area-chip');
        if (chip) chip.click();
      }
    });
  });

  getAll('step3Next').forEach(function (btn) {
    btn.addEventListener('click', async function () {
      getAll('step3Next').forEach(function (b) {
        b.disabled = true;
        b.textContent = '추천 코스 분석 중...';
      });

      const result = await requestRecommendations();

      if (result && result.courses) {
        navigateTo('/results.html');
      } else {
        getAll('step3Next').forEach(function (b) {
          b.disabled = false;
          b.textContent = '코스 추천받기 →';
        });
        showToast('추천 결과를 가져올 수 없습니다. 다시 시도해주세요.', 'error');
      }
    });
  });

  /* ── 초기 상태 복원 ── */
  syncTypeCards();
  syncDurationChips();
  syncAreaChips();
  showStep(1);
})();
