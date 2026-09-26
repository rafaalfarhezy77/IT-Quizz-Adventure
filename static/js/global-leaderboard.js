(() => {
  const root = document.querySelector('[data-leaderboard]');
  if (!root) return;
  const body = root.querySelector('[data-leaderboard-body]');
  const head = root.querySelector('[data-leaderboard-head]');
  const status = root.querySelector('[data-live-status]');
  const empty = root.querySelector('[data-empty]');
  const nodes = new Map();
  const number = new Intl.NumberFormat('id-ID', { maximumFractionDigits: 6 });
  let stationSignature = '', timer, stopped = false, lastUpdate = '';
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  function cell(tag, value, className) {
    const element = document.createElement(tag);
    element.textContent = value;
    if (className) element.className = className;
    return element;
  }
  function render(data) {
    const signature = JSON.stringify(data.stations);
    if (signature !== stationSignature) {
      const row = document.createElement('tr');
      ['Peringkat', 'Tim / Sekolah', 'Kelompok', ...data.stations.map(s => s.name), 'Total'].forEach(text => {
        const th = cell('th', text); th.scope = 'col'; row.append(th);
      });
      head.replaceChildren(row); stationSignature = signature;
    }
    const previous = new Map([...nodes].map(([id, row]) => [id, row.getBoundingClientRect().top]));
    const ids = new Set(data.rows.map(row => row.team_id));
    for (const [id, row] of nodes) if (!ids.has(id)) { row.remove(); nodes.delete(id); }
    for (const team of data.rows) {
      let row = nodes.get(team.team_id);
      if (!row) { row = document.createElement('tr'); nodes.set(team.team_id, row); }
      const contentSignature = JSON.stringify(team);
      if (row.dataset.content !== contentSignature || row.dataset.stations !== signature) {
        const oldPoints = row.dataset.points;
        const points = JSON.stringify([team.points, team.total]);
        const name = cell('td', '');
        name.append(cell('strong', `${team.team_code} · ${team.team_name}`, 'leaderboard-team-name'), cell('span', team.school, 'leaderboard-team-detail'));
        row.replaceChildren(cell('td', team.rank), name, cell('td', team.group_code),
          ...data.stations.map(st => cell('td', team.points[String(st.id)] == null ? '—' : number.format(team.points[String(st.id)]))),
          cell('td', number.format(team.total), 'leaderboard-total'));
        row.dataset.content = contentSignature; row.dataset.stations = signature;
        row.dataset.points = points; row.dataset.podium = String(team.rank <= 3);
        if (oldPoints && oldPoints !== points && !reduced.matches && row.animate) {
          row.querySelectorAll('td').forEach(td => td.animate([{ backgroundColor: '#e4ffb5' }, { backgroundColor: '#fff' }], { duration: 1400 }));
        }
      }
      body.append(row);
    }
    if (!reduced.matches) for (const [id, row] of nodes) {
      const old = previous.get(id);
      const delta = old == null ? 0 : old - row.getBoundingClientRect().top;
      if (delta && row.animate) row.animate([{ transform: `translateY(${delta}px)` }, { transform: 'translateY(0)' }], { duration: 500, easing: 'ease-out' });
    }
    empty.hidden = data.rows.length > 0;
    lastUpdate = new Date(data.updated_at).toLocaleTimeString('id-ID');
    status.textContent = `LIVE · Diperbarui ${lastUpdate} · Interval 2 detik`;
  }
  async function poll() {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(root.dataset.api, { cache: 'no-store', credentials: 'same-origin', signal: controller.signal });
      if (response.status === 401 || response.status === 403) {
        stopped = true;
        const login = cell('a', 'Login kembali'); login.href = root.dataset.login;
        status.replaceChildren(document.createTextNode('Sesi admin berakhir. '), login);
        return;
      }
      if (!response.ok) throw new Error('Request failed');
      render(await response.json());
    } catch (error) {
      status.textContent = `Koneksi terputus · Mencoba kembali${lastUpdate ? ` · Data terakhir ${lastUpdate}` : ''}`;
    } finally {
      clearTimeout(timeout);
      if (!stopped) timer = setTimeout(poll, 2000);
    }
  }
  window.addEventListener('pagehide', () => { stopped = true; clearTimeout(timer); });
  window.addEventListener('pageshow', event => { if (event.persisted) { stopped = false; poll(); } });
  const fullscreen = root.querySelector('[data-fullscreen]');
  if (fullscreen) {
    fullscreen.addEventListener('click', async () => {
      try {
        if (document.fullscreenElement) await document.exitFullscreen();
        else await document.body.requestFullscreen();
      } catch (error) { status.textContent = 'Fullscreen tidak tersedia. Tampilan khusus tetap dapat digunakan.'; }
    });
    document.addEventListener('fullscreenchange', () => { fullscreen.textContent = document.fullscreenElement ? 'KELUAR LAYAR PENUH' : 'LAYAR PENUH'; });
    let hideTimer;
    const reveal = () => {
      document.body.classList.add('show-controls'); clearTimeout(hideTimer);
      hideTimer = setTimeout(() => document.body.classList.remove('show-controls'), 2500);
    };
    ['pointermove', 'pointerdown', 'keydown'].forEach(event => document.addEventListener(event, reveal));
  }
  poll();
})();
