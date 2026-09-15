/**
 * IT Quest Adventure — Waiting Room Polling Script (Langkah 6)
 * Polls server session status every 2 seconds and automatically redirects
 * to /participant/quiz once the admin starts the session.
 */
(function () {
  'use strict';

  const POLLING_INTERVAL_MS = 2000;
  const STATUS_API_URL = '/api/participant/session-status';
  const TARGET_QUIZ_URL = '/participant/quiz';

  const statusElement = document.getElementById('session-status');
  let pollTimer = null;
  let isRedirecting = false;

  async function checkSessionStatus() {
    if (isRedirecting) return;

    try {
      const response = await fetch(STATUS_API_URL, {
        method: 'GET',
        cache: 'no-store',
        headers: {
          'Accept': 'application/json',
          'Cache-Control': 'no-store, no-cache',
        },
      });

      if (!response.ok) {
        if (response.status === 403) {
          // Participant session invalid or reset
          console.warn('[WaitingRoom] Sesi peserta tidak valid, diarahkan ke beranda.');
          clearInterval(pollTimer);
          window.location.href = '/';
        }
        return;
      }

      const data = await response.json();

      if (data.status === 'RUNNING') {
        isRedirecting = true;
        clearInterval(pollTimer);

        if (statusElement) {
          statusElement.setAttribute('data-status', 'RUNNING');
          const statusText = statusElement.querySelector('.status-text');
          if (statusText) {
            statusText.textContent = 'STATUS: SESI DIMULAI! MENGALIHKAN...';
          }
        }

        // Transition immediately to quiz placeholder
        window.location.href = TARGET_QUIZ_URL;
      } else if (data.status === 'FINISHED') {
        isRedirecting = true;
        clearInterval(pollTimer);
        window.location.href = '/participant/session-ended';
      }
    } catch (err) {
      console.warn('[WaitingRoom] Polling connection error:', err);
    }
  }

  // Start periodic polling
  pollTimer = setInterval(checkSessionStatus, POLLING_INTERVAL_MS);

  // Initial immediate check
  checkSessionStatus();
})();
