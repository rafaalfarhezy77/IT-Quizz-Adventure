/**
 * IT Quest Adventure — Synchronized Session Countdown Timer (Langkah 6)
 * Server-authoritative timer: local 1s countdown with periodic server resync (5s)
 * and automatic tab visibility realignment.
 */
(function () {
  'use strict';

  function initTimer() {
    const timerEl = document.getElementById('session-timer');
    if (!timerEl) return;

    const syncUrl = timerEl.getAttribute('data-sync-url');
    const redirectUrl = timerEl.getAttribute('data-redirect-url');
    let currentStatus = timerEl.getAttribute('data-status') || 'WAITING';
    let remainingSeconds = parseInt(timerEl.getAttribute('data-remaining'), 10) || 0;

    const digitsEl = timerEl.querySelector('.timer-digits') || timerEl;
    const warningMsgEl = document.getElementById('timer-warning-msg');
    const isAdminTimer = !redirectUrl;
    let lastSuccessfulSync = Date.now();
    let connectionNotice = null;

    if (isAdminTimer) {
      connectionNotice = document.createElement('p');
      connectionNotice.className = 'session-connection-notice';
      connectionNotice.setAttribute('role', 'status');
      connectionNotice.hidden = true;
      connectionNotice.textContent = 'Koneksi ke server terputus. Status tim mungkin tertinggal; timer akan disinkronkan kembali saat jaringan pulih.';
      timerEl.parentElement.appendChild(connectionNotice);
    }

    let localInterval = null;
    let syncInterval = null;
    let isTimeoutHandled = false;

    function formatTime(totalSeconds) {
      const s = Math.max(0, Math.floor(totalSeconds));
      const hours = Math.floor(s / 3600);
      const mins = Math.floor((s % 3600) / 60);
      const secs = s % 60;

      const pad = (n) => String(n).padStart(2, '0');

      if (hours > 0) {
        return `${pad(hours)}:${pad(mins)}:${pad(secs)}`;
      }
      return `${pad(mins)}:${pad(secs)}`;
    }

    function updateVisualClasses(rem) {
      timerEl.classList.remove('timer-normal', 'timer-warning', 'timer-critical');

      if (rem <= 30) {
        timerEl.classList.add('timer-critical');
        if (warningMsgEl) warningMsgEl.textContent = 'PERINGATAN: Sisa waktu kurang dari 30 detik!';
      } else if (rem <= 120) {
        timerEl.classList.add('timer-warning');
        if (warningMsgEl) warningMsgEl.textContent = 'PERHATIAN: Sisa waktu kurang dari 2 menit.';
      } else {
        timerEl.classList.add('timer-normal');
        if (warningMsgEl) warningMsgEl.textContent = 'Waktu sinkron langsung dengan server pos.';
      }
    }

    function renderTimer() {
      digitsEl.textContent = formatTime(remainingSeconds);
      updateVisualClasses(remainingSeconds);
    }

    function handleTimeout() {
      if (isTimeoutHandled) return;
      isTimeoutHandled = true;

      remainingSeconds = 0;
      renderTimer();

      if (localInterval) clearInterval(localInterval);
      if (syncInterval) clearInterval(syncInterval);

      if (warningMsgEl) {
        warningMsgEl.textContent = 'WAKTU PENGERJAAN TELAH HABIS!';
      }

      // Redirect to ended page if configured (participant quiz)
      if (redirectUrl) {
        setTimeout(() => {
          window.location.href = redirectUrl;
        }, 1000);
      } else {
        // Reload admin page to reflect final state
        setTimeout(() => {
          window.location.reload();
        }, 1500);
      }
    }

    function localTick() {
      if (currentStatus !== 'RUNNING') return;

      remainingSeconds--;

      if (remainingSeconds <= 0) {
        handleTimeout();
      } else {
        renderTimer();
      }
    }

    async function syncWithServer() {
      if (!syncUrl || isTimeoutHandled) return;

      try {
        const resp = await fetch(syncUrl, {
          method: 'GET',
          cache: 'no-store',
          headers: {
            'Accept': 'application/json',
            'Cache-Control': 'no-store, no-cache',
          },
        });

        if (!resp.ok) throw new Error('HTTP ' + resp.status);

        const data = await resp.json();
        lastSuccessfulSync = Date.now();
        if (connectionNotice) connectionNotice.hidden = true;
        if (isAdminTimer && data.status !== currentStatus) {
          window.location.reload();
          return;
        }
        const previousStatus = currentStatus;
        currentStatus = data.status;

        if (data.status === 'FINISHED' || (data.remaining_seconds !== undefined && data.remaining_seconds <= 0)) {
          if (previousStatus === 'RUNNING') handleTimeout();
          return;
        }

        if (data.status === 'RUNNING' && typeof data.remaining_seconds === 'number') {
          const serverRem = data.remaining_seconds;

          // Realign if drift exceeds 1 second
          if (Math.abs(remainingSeconds - serverRem) > 1) {
            remainingSeconds = serverRem;
            renderTimer();
          }
        }
      } catch (e) {
        console.warn('[Timer] Resync error:', e);
        if (connectionNotice && Date.now() - lastSuccessfulSync > 10000) connectionNotice.hidden = false;
      }
    }

    // Initial render
    renderTimer();

    // If status is RUNNING, kick off countdown and periodic resync
    if (currentStatus === 'RUNNING') {
      localInterval = setInterval(localTick, 1000);
    }
    syncInterval = setInterval(syncWithServer, 5000);
    if (isAdminTimer) {
      setInterval(() => {
        if (currentStatus === 'RUNNING' && !document.hidden && !connectionNotice?.hidden) return;
        if (currentStatus === 'RUNNING' && !document.hidden) window.location.reload();
      }, 15000);
    }

    // Handle visibility change (tab refocus after throttle/lag)
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden && currentStatus === 'RUNNING') {
        syncWithServer();
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTimer);
  } else {
    initTimer();
  }
})();
