/* Deadline anchored to server time and monotonic elapsed time. */
(function () {
  'use strict';
  const el = document.getElementById('session-timer');
  if (!el) return;
  let deadline = Number(el.dataset.deadline);
  let anchorServer = Number(el.dataset.serverNow);
  let anchorLocal = performance.now();
  let ended = false;
  let syncing = false;
  const notice = document.createElement('p');
  notice.setAttribute('role', 'status');
  el.parentElement.appendChild(notice);
  function finish() {
    if (ended) return;
    ended = true;
    location.assign(el.dataset.redirectUrl);
  }
  function render() {
    const seconds = Math.max(0, Math.ceil(deadline - anchorServer - (performance.now() - anchorLocal) / 1000));
    el.querySelector('.timer-digits').textContent = String(Math.floor(seconds / 60)).padStart(2, '0') + ':' + String(seconds % 60).padStart(2, '0');
    el.classList.toggle('timer-critical', seconds <= 30);
    if (seconds <= 0) finish();
  }
  async function sync() {
    if (ended || syncing) return;
    syncing = true;
    try {
      const response = await fetch(el.dataset.syncUrl, {cache: 'no-store'});
      if ([404, 410].includes(response.status)) { finish(); return; }
      if (!response.ok) throw new Error('sync');
      const data = await response.json();
      if (data.status !== 'RUNNING') { finish(); return; }
      if (data.awaiting_stage && window.DEMO_MODULE_CONFIG) { finish(); return; }
      deadline = data.deadline;
      anchorServer = data.server_time;
      anchorLocal = performance.now();
      notice.textContent = '';
      if (window.QUIZ_CONFIG && data.member !== window.QUIZ_CONFIG.currentMember) location.reload();
      const config = window.QUIZ_CONFIG || window.DEMO_MODULE_CONFIG;
      if (config && !config.busy && data.revision > config.revision) location.reload();
      render();
    } catch (_) {
      notice.textContent = 'Koneksi terputus. Timer tetap berjalan; periksa status penyimpanan jawaban.';
    } finally { syncing = false; }
  }
  render();
  setInterval(render, 250);
  setInterval(sync, 5000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) sync(); });
  window.addEventListener('online', sync);
}());
