(function () {
  'use strict';
  const pack = window.DemoPack, engine = window.DemoEngine;
  const app = document.getElementById('app');
  let attempt = null, notice = '', storageAvailable = true;
  const escape = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const key = engine.STORAGE_KEY;
  function load() {
    try {
      const decoded = engine.decode(localStorage.getItem(key), pack, Date.now());
      attempt = decoded.state;
      if (decoded.error) {notice = decoded.error; localStorage.removeItem(key);}
    } catch (_) {storageAvailable = false; notice = 'Penyimpanan browser tidak tersedia. Progres hanya bertahan selama halaman ini terbuka; refresh akan menghapusnya.';}
  }
  function save() {
    if (!storageAvailable || !attempt) return;
    try {localStorage.setItem(key, JSON.stringify(attempt));}
    catch (_) {storageAvailable = false; notice = 'Progres gagal disimpan. Jangan refresh halaman ini; izinkan penyimpanan browser untuk percobaan berikutnya.';}
  }
  function currentRoute() {return location.hash.slice(1).replace(/^software\//,'') || 'home';}
  function go(route) {
    if (currentRoute() === route) render();
    else location.hash = route;
  }
  // Reload the latest revision before any mutation so another tab is respected.
  function fresh() {
    if (storageAvailable) load();
    if (!attempt) {go('stations'); return false;}
    if (attempt.status === 'RUNNING' && Date.now() >= attempt.deadline) {
      engine.finish(attempt, pack, Date.now(), true); save(); go('result'); return false;
    }
    return attempt.status === 'RUNNING';
  }
  function confirmAction(title, text, label, callback) {
    const old = document.querySelector('dialog'); if (old) old.remove();
    const dialog = document.createElement('dialog');
    dialog.setAttribute('aria-labelledby', 'confirm-title');
    dialog.innerHTML = `<h2 id="confirm-title">${escape(title)}</h2><p>${escape(text)}</p><div class="actions"><button class="button" data-cancel>Kembali Periksa</button><button class="button primary" data-confirm>${escape(label)}</button></div>`;
    document.body.append(dialog);
    dialog.querySelector('[data-cancel]').onclick = () => {dialog.close(); dialog.remove();};
    dialog.querySelector('[data-confirm]').onclick = () => {dialog.close(); dialog.remove(); callback();};
    dialog.addEventListener('cancel', () => dialog.remove()); dialog.showModal();
    dialog.querySelector('[data-cancel]').focus();
  }
  function start() {
    confirmAction('Mulai Demo?', 'Timer empat menit mulai berjalan setelah konfirmasi, termasuk membaca studi kasus. Percobaan tersimpan sebelumnya akan diganti.', 'Mulai Demo', () => {
      const id = 'pages_' + (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2));
      attempt = engine.create(pack, Date.now(), id); notice = ''; save(); go('case');
    });
  }
  const timer = () => '<div><div class="timer-label">SISA WAKTU</div><div class="timer" role="timer" aria-label="Sisa waktu" id="timer">04:00</div></div>';
  const badge = '<span class="badge">Mode Demo · Soal latihan</span>';
  function resumeLink() {
    return (attempt ? `<a class="button" href="#${attempt.status === 'RUNNING' ? attempt.phase : 'result'}">${attempt.status === 'RUNNING' ? 'Lanjutkan Percobaan' : 'Lihat Hasil Terakhir'}</a>` : '') + window.DemoPagesMulti.resumeLinks();
  }
  function render() {
    if (window.DemoPagesMulti.handles()) return;
    document.querySelector('dialog')?.remove();
    if (attempt?.status === 'RUNNING' && Date.now() >= attempt.deadline) {engine.finish(attempt, pack, Date.now(), true); save();}
    let route = currentRoute();
    const known = ['home','stations','rules','case','quiz','transition','result'];
    if (!known.includes(route)) {notice = 'Halaman tidak tersedia. Pilih pos untuk mencoba latihan.'; go('stations'); return;}
    if (['case','quiz','transition','result'].includes(route)) {
      if (!attempt) {notice ||= 'Belum ada percobaan aktif. Baca aturan lalu mulai demo.'; go('rules'); return;}
      if (attempt.status !== 'RUNNING' && route !== 'result') {go('result'); return;}
      if (attempt.status === 'RUNNING') {
        if (route === 'result') {go(attempt.phase); return;}
        if (route === 'transition' && attempt.phase !== 'transition') {go(attempt.phase); return;}
        if (route === 'quiz' && (attempt.phase === 'transition' || !attempt.seen)) {go(attempt.phase); return;}
      }
    }
    const warning = notice ? `<div class="notice" role="status">${escape(notice)}</div>` : '';
    let html = '';
    if (route === 'home') html = `
      <section class="panel hero">
        <div class="hero-top-strip">
          <span class="badge">Mode Demo</span>
          <span class="badge-tag">MYTHIC 3.0</span>
        </div>
        <div class="hero-headline">
          <p class="eyebrow">// LATIHAN MANDIRI TANPA LOGIN</p>
          <h1 class="hero-title">IT QUEST <span class="highlight">ADVENTURE</span></h1>
          <p class="hero-lead">Simulasikan konsep kuis dan kompetisi cerdas cermat sebelum lomba resmi dimulai. Soal latihan interaktif dengan sistem timer realistis tanpa perlu login akun atau kode kelompok.</p>
        </div>
        <div class="hero-feature-grid">
          <div class="feature-item">
            <span class="feature-icon">⚡</span>
            <div class="feature-text">
              <strong>Simulasi Tim Mandiri</strong>
              <span>Satu peserta dapat mensimulasikan pengerjaan dan rotasi giliran anggota.</span>
            </div>
          </div>
          <div class="feature-item">
            <span class="feature-icon">⏱️</span>
            <div class="feature-text">
              <strong>Timer Realistis</strong>
              <span>Batas waktu per pos &amp; bonus sisa detik tersimpan otomatis di browser lokal.</span>
            </div>
          </div>
          <div class="feature-item">
            <span class="feature-icon">🛡️</span>
            <div class="feature-text">
              <strong>Aman &amp; Independen</strong>
              <span>Nilai latihan tidak memengaruhi skor leaderboard maupun hasil lomba resmi.</span>
            </div>
          </div>
        </div>
        <div class="hero-footer-cta">
          <div class="actions">
            <a class="button primary hero-btn" href="#stations">Coba Demo / Pilih Pos →</a>
            ${resumeLink()}
          </div>
          <p class="hero-note">⚡ Tersedia 4 Pos Latihan: Software Engineering · Cyber Security · Networking · Hardware</p>
        </div>
      </section>
      <section class="home-stations-preview">
        <div class="section-header-row">
          <div>
            <span class="badge">4 POS TERSEDIA</span>
            <h2 class="section-title">Pilihan Pos Demo</h2>
          </div>
          <a class="button small" href="#stations">Lihat Semua Pos →</a>
        </div>
        <div class="grid">
          <article class="card station-preview-card">
            <div class="station-card-top">
              <span class="station-icon">💻</span>
              <span class="badge-tag">9 Soal</span>
            </div>
            <h3>Software Engineering</h3>
            <p>Studi kasus sistem reservasi ruang belajar, rotasi 3 giliran anggota, dan kunci jawaban bertahap.</p>
            <div class="station-meta">
              <span>⏱️ 4 Menit</span>
              <span>👥 3 Anggota</span>
            </div>
            <a class="button primary small" href="#software/rules">Mulai Latihan →</a>
          </article>
          <article class="card station-preview-card">
            <div class="station-card-top">
              <span class="station-icon">🛡️</span>
              <span class="badge-tag">6 Soal</span>
            </div>
            <h3>Cyber Security</h3>
            <p>Tantangan keamanan akun dan data, proteksi sistem kredensial, dan simulasi diskusi tim.</p>
            <div class="station-meta">
              <span>⏱️ 4 Menit</span>
              <span>🔒 Kuis Cepat</span>
            </div>
            <a class="button primary small" href="#cyber/rules">Mulai Latihan →</a>
          </article>
          <article class="card station-preview-card">
            <div class="station-card-top">
              <span class="station-icon">🌐</span>
              <span class="badge-tag">3 Tahap</span>
            </div>
            <h3>Networking</h3>
            <p>Tiga tahap dinamis: Signal Check (A–E), True or Trap (B/S), dan Case Signal (isian singkat).</p>
            <div class="station-meta">
              <span>⏱️ 5 Menit</span>
              <span>⚡ 3 Tahap</span>
            </div>
            <a class="button primary small" href="#networking/rules">Mulai Latihan →</a>
          </article>
          <article class="card station-preview-card">
            <div class="station-card-top">
              <span class="station-icon">🖥️</span>
              <span class="badge-tag">Rakitan PC</span>
            </div>
            <h3>Hardware</h3>
            <p>Tantangan merakit PC studio podcast: periksa socket CPU, kompatibilitas RAM, budget &amp; daya PSU.</p>
            <div class="station-meta">
              <span>⏱️ 5 Menit</span>
              <span>🔧 Katalog 3D</span>
            </div>
            <a class="button primary small" href="#hardware/rules">Mulai Latihan →</a>
          </article>
        </div>
      </section>`;
    if (route === 'stations') html = `
      <section class="panel stations-header-panel">
        <div class="hero-top-strip">
          <span class="badge">PILIHAN POS</span>
          <span class="badge-tag">MYTHIC 3.0</span>
        </div>
        <div class="hero-headline">
          <p class="eyebrow">// KATALOG POS LATIHAN MANDIRI</p>
          <h1 class="hero-title">PILIH POS <span class="highlight">DEMO</span></h1>
          <p class="hero-lead">Pilih pos latihan mandiri untuk menguji pemahaman dan strategi tim sebelum lomba resmi. Setiap pos memiliki format studi kasus, batas waktu, dan mekanisme pengerjaan yang berbeda.</p>
        </div>
        <div class="stations-filter-info">
          <span class="info-pill">⚡ 4 Modul Latihan Tersedia</span>
          <span class="info-pill">⏱️ Timer &amp; Poin Realistis</span>
          <span class="info-pill">🔄 Bisa Dicoba Berulang Kali</span>
        </div>
      </section>
      <section class="stations-selection-section">
        <div class="grid">
          <article class="card station-grid-card">
            <div class="station-card-top">
              <span class="station-icon">💻</span>
              <span class="badge-tag">POS 01</span>
            </div>
            <div class="station-card-body">
              <h2>Software Engineering</h2>
              <p class="station-desc">Studi kasus sistem reservasi ruang belajar, rotasi 3 giliran anggota tim, dan penguncian jawaban bertahap.</p>
              <ul class="station-bullets">
                <li>⏱️ Durasi: <strong>4 Menit</strong></li>
                <li>👥 Format: <strong>3 Anggota Tim</strong></li>
                <li>📝 Soal: <strong>9 Pilihan Ganda (A–D)</strong></li>
                <li>🎯 Bobot: <strong>10 Poin / Soal + Bonus</strong></li>
              </ul>
            </div>
            <div class="station-card-footer">
              <a class="button primary station-start-btn" href="#software/rules">Coba Demo Software →</a>
            </div>
          </article>

          <article class="card station-grid-card">
            <div class="station-card-top">
              <span class="station-icon">🛡️</span>
              <span class="badge-tag">POS 02</span>
            </div>
            <div class="station-card-body">
              <h2>Cyber Security</h2>
              <p class="station-desc">Tantangan investigasi keamanan akun, proteksi kredensial, verifikasi data rahasia, dan mitigasi insiden siber.</p>
              <ul class="station-bullets">
                <li>⏱️ Durasi: <strong>4 Menit</strong></li>
                <li>🔒 Format: <strong>Kuis Mandiri Cepat</strong></li>
                <li>📝 Soal: <strong>6 Pilihan Ganda (A–D)</strong></li>
                <li>🎯 Bobot: <strong>10 Poin / Soal + Bonus</strong></li>
              </ul>
            </div>
            <div class="station-card-footer">
              <a class="button primary station-start-btn" href="#cyber/rules">Coba Demo Cyber →</a>
            </div>
          </article>

          <article class="card station-grid-card">
            <div class="station-card-top">
              <span class="station-icon">🌐</span>
              <span class="badge-tag">POS 03</span>
            </div>
            <div class="station-card-body">
              <h2>Networking</h2>
              <p class="station-desc">Tiga tahap berurutan: Signal Check (A–E), True or Trap (Benar/Salah), dan Case Signal (isian singkat interaktif).</p>
              <ul class="station-bullets">
                <li>⏱️ Durasi: <strong>5 Menit (Total)</strong></li>
                <li>⚡ Format: <strong>3 Tahap Dinamis</strong></li>
                <li>📝 Soal: <strong>3 PG + 4 B/S + 5 Isian</strong></li>
                <li>🎯 Bobot: <strong>100 Poin + Stempel</strong></li>
              </ul>
            </div>
            <div class="station-card-footer">
              <a class="button primary station-start-btn" href="#networking/rules">Coba Demo Networking →</a>
            </div>
          </article>

          <article class="card station-grid-card">
            <div class="station-card-top">
              <span class="station-icon">🖥️</span>
              <span class="badge-tag">POS 04</span>
            </div>
            <div class="station-card-body">
              <h2>Hardware</h2>
              <p class="station-desc">Tantangan merakit PC studio podcast: periksa socket CPU, motherboard, RAM, budget USD 1400 &amp; daya PSU.</p>
              <ul class="station-bullets">
                <li>⏱️ Durasi: <strong>5 Menit</strong></li>
                <li>🔧 Format: <strong>Simulasi Rakitan 3D</strong></li>
                <li>📝 Tugas: <strong>6 Komponen + Alasan</strong></li>
                <li>🎯 Bobot: <strong>95 Poin + Bonus</strong></li>
              </ul>
            </div>
            <div class="station-card-footer">
              <a class="button primary station-start-btn" href="#hardware/rules">Coba Demo Hardware →</a>
            </div>
          </article>
        </div>
      </section>
      <div class="stations-bottom-controls">
        <div class="actions">
          <a class="button" href="#home">← Kembali ke Beranda</a>
          ${resumeLink()}
        </div>
        <div class="notice station-guidance-note">
          <strong>💡 Panduan Latihan:</strong> Anda dapat mencoba pos mana saja sesuai keinginan. Nilai dan waktu latihan tersimpan mandiri di browser Anda tanpa memengaruhi pos lainnya.
        </div>
      </div>`;
    if (route === 'rules') html = `<section class="panel">${badge}<h1>Aturan Software Engineering</h1><ol><li>Baca studi kasus, lalu jawab sembilan soal pilihan ganda A–D.</li><li>Anggota 1 mengerjakan soal 1–3, anggota 2 soal 4–6, anggota 3 soal 7–9. Satu orang dapat mensimulasikan seluruh tim.</li><li>Durasi <strong>4 menit</strong>, termasuk membaca dan pergantian anggota. Timer mulai setelah menekan dan mengonfirmasi Mulai Demo.</li><li>Benar <strong>10 poin</strong>, salah atau kosong 0. Skor akhir = poin jawaban + sisa detik × 1. Jika waktu habis, bonus 0.</li><li>Jawaban giliran aktif boleh diubah. Setelah pergantian atau submit, jawaban terkunci. Kunci dan pembahasan ditampilkan di hasil.</li><li>Jawaban dan deadline disimpan otomatis di browser ini selama 24 jam. Refresh tidak mereset timer. Gunakan satu tab untuk mengerjakan.</li></ol><p>Ini simulasi statis: waktu dan nilai dihitung di browser, bukan nilai resmi lomba.</p><div class="actions"><button class="button primary" data-action="start">Mulai Demo</button>${resumeLink()}<a class="button" href="#stations">Kembali ke Pilihan Pos</a></div></section>`;
    if (route === 'case') html = `<section class="panel"><div class="quiz-header">${badge}${timer()}</div><h1>${escape(pack.caseTitle)}</h1><p class="case-text">${escape(pack.caseText)}</p><p>Waktu membaca termasuk dalam timer. Anda dapat membuka studi kasus kembali saat pengerjaan.</p><div class="actions"><button class="button primary" data-action="read">${attempt.seen ? 'Kembali ke Soal' : 'Mulai Kerjakan Soal'}</button></div></section>`;
    if (route === 'transition') html = `<section class="panel"><div class="quiz-header">${badge}${timer()}</div><h1>Giliran Anggota ${attempt.member}</h1><p>Jawaban anggota sebelumnya sudah dikunci. Simulasikan anggota berikutnya pada browser yang sama. Timer tetap berjalan.</p><button class="button primary" data-action="continue">Lanjutkan Anggota ${attempt.member}</button></section>`;
    if (route === 'quiz') {
      const offset = (attempt.member - 1) * 3, items = pack.questions.slice(offset, offset + 3), q = items[attempt.active];
      html = `<header class="panel quiz-header"><div>${badge}<h1>Software Engineering</h1><span class="eyebrow">ANGGOTA ${attempt.member} / 3 · TIM SIMULASI</span></div>${timer()}<div class="saved" id="save-status" role="status">${storageAvailable ? 'Tersimpan di browser' : 'Belum tersimpan permanen'}</div></header><div class="actions"><a class="button small" href="#case">Buka Studi Kasus</a></div><div class="quiz-layout" style="margin-top:24px"><aside class="card navigator"><h2>NAVIGATOR SOAL</h2><span>${items.filter(item => attempt.answers[item.id]).length} / 3 terjawab</span><div class="nav-buttons">${items.map((item, i) => `<button class="nav-button ${attempt.answers[item.id] ? 'answered' : ''} ${i === attempt.active ? 'active' : ''}" data-nav="${i}" aria-label="Soal ${item.id}" ${i === attempt.active ? 'aria-current="step"' : ''}>${item.id}${attempt.answers[item.id] ? ' ✓' : ''}</button>`).join('')}</div><p class="legend">Hijau: terjawab<br>Garis tebal: soal aktif</p></aside><section class="card question"><div class="q-header"><span>SOAL #${q.id} DARI 9</span><span>BOBOT: 10 POIN</span></div><h2 class="question-text" id="question-title">${escape(q.text)}</h2><div class="options" role="radiogroup" aria-labelledby="question-title">${q.options.map((text, i) => {const code = 'ABCD'[i]; return `<label class="option"><input type="radio" name="answer" value="${code}" data-question="${q.id}" ${attempt.answers[q.id] === code ? 'checked' : ''}><strong>${code}</strong><span>${escape(text)}</span></label>`;}).join('')}</div><div class="question-actions"><button class="button" data-action="previous" ${attempt.active === 0 ? 'disabled' : ''}>Sebelumnya</button><button class="button" data-action="next" ${attempt.active === 2 ? 'disabled' : ''}>Berikutnya</button></div></section></div><section class="panel"><p>Giliran aktif: soal ${offset + 1}–${offset + 3}. ${Object.keys(attempt.answers).length} dari 9 soal telah dijawab.</p><button class="button primary" data-action="complete">${attempt.member < 3 ? 'Selesaikan Bagian Anggota ' + attempt.member : 'Kirim Semua Jawaban Tim'}</button></section>`;
    }
    if (route === 'result') {
      const r = attempt.result;
      html = `<section class="panel">${badge}<h1>Hasil Software Engineering</h1><p>Status: <strong>${attempt.status === 'TIMED_OUT' ? 'Waktu habis' : 'Selesai dikirim'}</strong> · ${r.answered}/9 terjawab · ${r.correct}/9 benar</p><div class="grid"><div class="card score">Skor jawaban<strong>${r.raw}</strong></div><div class="card score">Bonus waktu<strong>${r.bonus}</strong></div><div class="card score">Skor akhir<strong>${r.total}</strong></div></div><p>Nilai demo tidak dihitung dalam lomba dan tidak masuk leaderboard, rekap, atau ekspor resmi.</p><p class="muted">Versi latihan: ${escape(pack.version)}. Waktu dan nilai merupakan simulasi di browser.</p><div class="actions"><button class="button primary" data-action="start">Coba Lagi</button><a class="button" href="#stations">Kembali ke Pilihan Pos</a></div></section><h2>Jawaban dan pembahasan</h2>${pack.questions.map(q => {const choice = attempt.answers[q.id]; return `<article class="card ${choice === q.key ? 'correct' : 'incorrect'}"><h3>${q.id}. ${escape(q.text)}</h3><p>Jawaban Anda: ${choice ? escape(choice + ' · ' + q.options['ABCD'.indexOf(choice)]) : 'Belum dijawab'}</p><p><strong>Jawaban benar: ${escape(q.key + ' · ' + q.options['ABCD'.indexOf(q.key)])}</strong></p><p>${escape(q.explanation)}</p></article>`;}).join('')}<div class="actions"><button class="button primary" data-action="start">Coba Lagi</button><a class="button" href="#stations">Kembali ke Pilihan Pos</a></div>`;
    }
    app.innerHTML = warning + html;
    document.title = (route === 'quiz' ? 'Anggota ' + attempt.member : route === 'result' ? 'Hasil Latihan' : 'IT Quest Adventure') + ' · Mode Demo';
    app.focus({preventScroll:true}); updateTimer();
  }
  function updateTimer() {
    if (window.DemoPagesMulti.handles()) return;
    if (!attempt || attempt.status !== 'RUNNING') return;
    if (Date.now() >= attempt.expires) {notice = 'Latihan kedaluwarsa. Mulai percobaan baru.'; attempt = null; try {localStorage.removeItem(key);} catch (_) {} go('rules'); return;}
    if (Date.now() >= attempt.deadline) {
      if (!fresh()) render();
      return;
    }
    const element = document.getElementById('timer');
    if (element) {
      const remaining = Math.max(0, Math.ceil((attempt.deadline - Date.now()) / 1000));
      element.textContent = `${String(Math.floor(remaining / 60)).padStart(2,'0')}:${String(remaining % 60).padStart(2,'0')}`;
      element.classList.toggle('critical', remaining <= 30);
    }
  }
  app.addEventListener('change', event => {
    if (window.DemoPagesMulti.handles()) return;
    const input = event.target;
    if (!input.matches('input[data-question]')) return;
    if (!fresh() || currentRoute() !== 'quiz') {render(); return;}
    const selected = input.value;
    engine.answer(attempt, Number(input.dataset.question), selected); save(); render();
    app.querySelector(`input[name="answer"][value="${selected}"]`)?.focus({preventScroll:true});
  });
  app.addEventListener('click', event => {
    if (window.DemoPagesMulti.handles()) return;
    const button = event.target.closest('button'); if (!button || button.disabled) return;
    const action = button.dataset.action;
    if (action === 'start') {start(); return;}
    if (!fresh()) {render(); return;}
    if (button.dataset.nav !== undefined || ['next','previous'].includes(action)) {
      if (attempt.phase !== 'quiz') {render(); return;}
      attempt.active = button.dataset.nav !== undefined ? Number(button.dataset.nav) : Math.max(0, Math.min(2, attempt.active + (action === 'next' ? 1 : -1)));
      attempt.revision++; save(); render();
    }
    if (action === 'read' || action === 'continue') {
      attempt.seen = true; attempt.phase = 'quiz'; attempt.revision++; save(); go('quiz');
    }
    if (action === 'complete' && attempt.phase === 'quiz') {
      const id = attempt.id, member = attempt.member;
      const final = member === 3;
      const count = final ? Object.keys(attempt.answers).length : pack.questions.slice((member - 1)*3,member*3).filter(q => attempt.answers[q.id]).length;
      confirmAction(final ? 'Kirim Semua Jawaban Tim?' : 'Kunci Bagian Anggota ' + member + '?', `${count} dari ${final ? 9 : 3} soal terjawab. Jawaban kosong bernilai 0. ${final ? 'Seluruh jawaban akan dikunci.' : 'Bagian ini akan dikunci dan giliran berikutnya dimulai. Timer tetap berjalan.'}`, final ? 'Ya, Kirim Jawaban' : 'Kunci Bagian & Lanjutkan', () => {
        if (!fresh() || attempt.id !== id || attempt.member !== member || attempt.phase !== 'quiz') {render(); return;}
        if (final) {engine.finish(attempt, pack, Date.now()); save(); go('result');}
        else {attempt.member++; attempt.active = 0; attempt.phase = 'transition'; attempt.revision++; save(); go('transition');}
      });
    }
  });
  function initSplash() {
    const splash = document.getElementById('splash-screen');
    if (!splash) return;
    const isInitial = !location.hash || location.hash === '#' || location.hash === '#home';
    let seen = false;
    try { seen = sessionStorage.getItem('itquest_demo_splash_seen'); } catch (_) {}
    if (!isInitial || seen) {
      splash.style.display = 'none';
      splash.remove();
      return;
    }
    try { sessionStorage.setItem('itquest_demo_splash_seen', '1'); } catch (_) {}
    function dismiss() {
      if (!splash.parentElement || splash.classList.contains('fade-out')) return;
      splash.classList.add('fade-out');
      setTimeout(function () {
        splash.style.display = 'none';
        splash.remove();
      }, 650);
    }
    splash.addEventListener('click', dismiss);
    window.addEventListener('hashchange', dismiss, { once: true });
    setTimeout(dismiss, 950);
  }
  window.addEventListener('hashchange', () => {if (storageAvailable) load(); render(); window.scrollTo(0,0);});
  window.addEventListener('storage', event => {if (event.key === key || event.key === null) {load(); notice ||= 'Progres diperbarui dari tab lain.'; render();}});
  document.addEventListener('visibilitychange', () => {if (!document.hidden) {if (storageAvailable) load(); render();}});
  load(); render(); initSplash(); setInterval(updateTimer, 250);
}());
