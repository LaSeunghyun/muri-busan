/**
 * 무리없이 부산 — 공유 카드 생성.
 */
(async function () {
  const shareCard = document.getElementById('shareCard');
  const shareBtns = document.getElementById('shareBtns');
  const params = new URLSearchParams(window.location.search);
  let token = params.get('token') || localStorage.getItem('mb_share_token');
  let shareUrl = window.location.href;
  let currentCourse = null;

  async function ensureShareUrl(course) {
    if (token) {
      shareUrl = window.location.href;
      return;
    }

    const result = await apiPost('/api/share', { course_id: course.id, course: course });
    if (result && result.token) {
      token = result.token;
      shareUrl = new URL(result.url, window.location.origin).toString();
      localStorage.setItem('mb_share_token', token);
      window.history.replaceState({}, '', result.url);
    }
  }

  async function init() {
    if (token) {
      currentCourse = await apiGet('/api/share/' + token);
    }

    if (!currentCourse) {
      currentCourse = AppState.selected_course;
    }

    if (!currentCourse) {
      shareCard.innerHTML = '<div class="empty-state"><div class="icon" aria-hidden="true">📭</div><h3>공유 데이터가 없습니다</h3><p>코스 상세에서 공유 버튼을 눌러주세요.</p></div>';
      return;
    }

    await ensureShareUrl(currentCourse);
    renderShareCard(currentCourse);
  }

  function renderShareCard(course) {
    const spots = course.spots || [];
    const avgGrade = course.accessibility_avg || 3;
    const stopsHtml = spots.map(function (spot, index) {
      return `<div class="share-stop"><span class="num">${index + 1}</span><span>${escapeHtml(spot.name)}</span></div>`;
    }).join('');

    const accessBadges = [];
    const hasWheelchair = spots.every(function (spot) { return spot.wheelchair_accessible; });
    const hasStroller = spots.every(function (spot) { return spot.stroller_accessible; });
    const hasRestroom = spots.every(function (spot) { return spot.restroom_accessible; });
    const fatigueLabel = course.total_fatigue <= 50 ? '낮음' : course.total_fatigue <= 80 ? '보통' : '높음';

    if (hasWheelchair) accessBadges.push('<span class="badge badge-green">♿ 휠체어 OK</span>');
    if (hasStroller) accessBadges.push('<span class="badge badge-green">🍼 유아차 OK</span>');
    if (hasRestroom) accessBadges.push('<span class="badge badge-blue">🚻 화장실 완비</span>');

    shareCard.innerHTML = `
      <div class="share-card-header">
        <div class="service-name"><span aria-hidden="true">♿</span> 무리없이 부산</div>
        <h2>이동약자 맞춤 코스</h2>
        <h3>${escapeHtml(course.name)}</h3>
        <p>${spots.length}개 관광지 · ${course.total_time_min}분 코스</p>
      </div>
      <div class="share-card-body">
        <div class="share-meta-row">
          <div class="share-meta-item"><div class="lbl">총 소요시간</div><div class="val">${course.total_time_min}분</div></div>
          <div class="share-meta-item"><div class="lbl">이동거리</div><div class="val">${course.distance_km}km</div></div>
          <div class="share-meta-item"><div class="lbl">피로도</div><div class="val">${course.total_fatigue} (${fatigueLabel})</div></div>
          <div class="share-meta-item"><div class="lbl">접근성</div><div class="val">${gradeLabel(Math.round(avgGrade))}</div></div>
        </div>
        <div class="share-stops">${stopsHtml}</div>
        <div class="share-access-badges" style="display:flex;flex-wrap:wrap;gap:5px">${accessBadges.join('')}</div>
      </div>
      <div class="share-card-footer">
        <p>무리없이 부산 · 공공데이터 기반 추천</p>
        <div class="share-url-badge">공유 링크 준비됨</div>
      </div>`;

    shareBtns.style.display = 'flex';
    shareBtns.style.flexDirection = 'column';
    shareBtns.style.gap = '10px';
  }

  async function copyShareLink() {
    try {
      await navigator.clipboard.writeText(shareUrl);
      showToast('링크가 복사되었습니다!', 'success');
    } catch (e) {
      const ta = document.createElement('textarea');
      ta.value = shareUrl;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      showToast('링크가 복사되었습니다!', 'success');
    }
  }

  async function shareWithDevice() {
    const title = currentCourse ? currentCourse.name : '무리없이 부산 코스';
    const text = currentCourse ? `${currentCourse.name} 코스를 확인해보세요.` : '무리없이 부산 코스를 확인해보세요.';

    if (navigator.share) {
      try {
        await navigator.share({ title, text, url: shareUrl });
        return;
      } catch (e) {
        if (e && e.name === 'AbortError') {
          return;
        }
      }
    }

    await copyShareLink();
    showToast('기기 공유를 지원하지 않아 링크 복사로 대체했어요.', 'info');
  }

  function showQRCode() {
    const modal = document.createElement('div');
    modal.className = 'qr-modal';
    modal.innerHTML =
      '<div class="qr-modal-inner" role="dialog" aria-modal="true" aria-label="QR 코드">' +
        '<h3>QR 코드로 공유</h3>' +
        '<div id="qrCanvas"></div>' +
        '<p>스캔하면 코스를 바로 확인할 수 있어요</p>' +
        '<button class="btn-outline" onclick="this.closest(\'.qr-modal\').remove()">닫기</button>' +
      '</div>';
    document.body.appendChild(modal);

    new QRCode(document.getElementById('qrCanvas'), {
      text: shareUrl,
      width: 200,
      height: 200,
    });

    modal.addEventListener('click', function (e) {
      if (e.target === modal) modal.remove();
    });
  }

  function shareKakao(courseName) {
    if (!window.Kakao) {
      copyShareLink();
      showToast('카카오 공유 기능을 불러오지 못했습니다. 링크를 복사했어요.', 'warning');
      return;
    }

    if (!Kakao.isInitialized()) {
      copyShareLink();
      showToast('카카오 로그인이 필요합니다. 링크를 복사했어요.', 'info');
      return;
    }

    Kakao.Share.sendDefault({
      objectType: 'feed',
      content: {
        title: courseName || '무리없이 부산 — 이동약자 맞춤 코스',
        description: '접근성 기반 부산 관광 코스를 확인하세요.',
        imageUrl: 'https://murineopsi.busan.kr/images/og-image.png',
        link: {
          mobileWebUrl: shareUrl,
          webUrl: shareUrl,
        },
      },
    });
  }

  document.getElementById('deviceShareBtn').addEventListener('click', function () {
    shareWithDevice();
  });

  document.getElementById('copyLinkBtn').addEventListener('click', function () {
    copyShareLink();
  });

  document.getElementById('kakaoShareBtn').addEventListener('click', function () {
    const heading = shareCard.querySelector('h3');
    const courseName = heading ? heading.textContent : '';
    shareKakao(courseName);
  });

  document.getElementById('qrBtn').addEventListener('click', function () {
    showQRCode();
  });

  init();
})();
