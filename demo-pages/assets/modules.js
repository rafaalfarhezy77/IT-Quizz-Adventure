/* Method-specific pages share the static site's CSS, shell and storage contract. */
(function(){
  'use strict';
  const packs=window.DemoPacks,e=window.DemoMethods,app=document.getElementById('app');
  const memory={},notices={};let storage=true,slug=null,pack=null,state=null;
  let storageError='Penyimpanan browser tidak tersedia. Progres hanya bertahan selama halaman ini terbuka; refresh akan menghapusnya.';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const handles=()=>!!packs[location.hash.slice(1).split('/')[0]];
  function resumeLinks(){
    return Object.values(packs).map(pos=>{
      let saved=memory[pos.slug]||null;
      try{if(storage)saved=e.decode(localStorage.getItem(e.key(pos.slug)),pos,Date.now()).state;}catch(_){}
      if(!saved)return '';return `<a class="button" href="#${pos.slug}/${saved.status==='RUNNING'?saved.phase:'result'}">${saved.status==='RUNNING'?'Lanjutkan':'Lihat Hasil'} ${esc(pos.title)}</a>`;
    }).join('');
  }
  window.DemoPagesMulti={handles,resumeLinks};
  function locationInfo(){const parts=location.hash.slice(1).split('/');return {slug:parts[0],page:parts[1]||'rules'};}
  function load(){
    if(!handles())return;slug=locationInfo().slug;pack=packs[slug];
    if(!storage){const decoded=e.decode(memory[slug]?JSON.stringify(memory[slug]):null,pack,Date.now());state=decoded.state;memory[slug]=state;if(decoded.error)notices[slug]=decoded.error;return;}
    try{const decoded=e.decode(localStorage.getItem(e.key(slug)),pack,Date.now());state=decoded.state;memory[slug]=state;if(decoded.error){notices[slug]=decoded.error;localStorage.removeItem(e.key(slug));}}
    catch(_){storage=false;state=memory[slug]||null;notices[slug]='Penyimpanan browser tidak tersedia. Progres hanya bertahan selama halaman ini terbuka; refresh akan menghapusnya.';}
  }
  function save(){memory[slug]=state;if(!storage)return;try{localStorage.setItem(e.key(slug),JSON.stringify(state));}catch(_){storage=false;storageError='Progres gagal disimpan. Jangan refresh halaman ini; izinkan penyimpanan untuk percobaan berikutnya.';notices[slug]=storageError;}}
  function go(page){const hash=slug+'/'+page;if(location.hash.slice(1)===hash)render();else location.hash=hash;}
  function fresh(){load();if(!state){go('rules');return false;}if(e.expire(state,pack,Date.now())){save();go(state.phase);return false;}return state.status==='RUNNING';}
  function dialog(title,text,label,callback){
    document.querySelector('dialog')?.remove();const el=document.createElement('dialog');el.setAttribute('aria-labelledby','confirm-title');
    el.innerHTML=`<h2 id="confirm-title">${esc(title)}</h2><p>${esc(text)}</p><div class="actions"><button class="button" data-cancel>Kembali Periksa</button><button class="button primary" data-confirm>${esc(label)}</button></div>`;
    document.body.append(el);el.querySelector('[data-cancel]').onclick=()=>{el.close();el.remove();};el.querySelector('[data-confirm]').onclick=()=>{el.close();el.remove();callback();};el.addEventListener('cancel',()=>el.remove());el.showModal();el.querySelector('[data-cancel]').focus();
  }
  const badge='<span class="badge">Mode Demo · Soal latihan</span>';
  const button=(action,text)=>`<button class="button primary" data-module-action="${action}">${text}</button>`;
  const actions=()=>`<div class="actions">${button('start','Coba Lagi')}<a class="button" href="#stations">Kembali ke Pilihan Pos</a></div>`;
  const timer=()=>'<div><div class="timer-label">SISA WAKTU</div><div class="timer" id="module-timer" role="timer">--:--</div><div class="timer-label" id="module-overall"></div></div>';
  const title=()=>`<header class="panel quiz-header"><div>${badge}<h1>${esc(pack.title)}</h1><span class="eyebrow">${pack.method==='networking'?'TAHAP '+state.stage+' / 3 · '+pack.stageNames[state.stage-1]:'TIM SIMULASI · LATIHAN MANDIRI'}</span></div>${timer()}<span class="saved" id="module-save-status" role="status">${storage?'Tersimpan di browser':'Belum tersimpan permanen'}</span></header>`;
  function buildcoresGuide(open=false){return `<details class="panel buildcores-guide" ${open?'open':''}>
    <summary><strong>Panduan Menggunakan BuildCores</strong></summary>
    <p>Pelajari alat perakitan yang digunakan pada lomba resmi sebelum menekan <strong>Mulai Demo</strong>. Membaca panduan pada halaman aturan belum menjalankan timer. Jika dibuka saat pengerjaan, timer tetap berjalan.</p>
    <ol>
      <li><strong>Buat rakitan baru.</strong> Buka BuildCores, lalu pilih Create New Build atau Start Building.</li>
      <li><strong>Pilih casing.</strong> Cari model melalui pencarian atau filter. Komponen berlabel 3D mendukung pratinjau tiga dimensi.</li>
      <li><strong>Tambahkan komponen.</strong> Pilih CPU, motherboard, GPU, RAM, storage, dan PSU. Tambahkan pendingin atau kipas jika diminta dalam tantangan.</li>
      <li><strong>Periksa kecocokan.</strong> Cocokkan socket CPU/motherboard, jenis RAM, ukuran komponen terhadap casing, dan kebutuhan daya PSU. Perhatikan peringatan kompatibilitas.</li>
      <li><strong>Periksa harga dan tampilan.</strong> Tinjau total harga, mata uang, dan spesifikasi terhadap budget serta target tantangan. Putar atau zoom pratinjau 3D untuk memeriksa tata letak.</li>
      <li><strong>Simpan bukti rakitan.</strong> Gunakan Share Build atau fitur berbagi yang tersedia. Untuk lomba resmi, siapkan tautan rakitan dan screenshot komponen, total harga, serta status kompatibilitas sesuai instruksi panitia.</li>
    </ol>
    <p><strong>Video langkah demi langkah:</strong> Build Your Dream Gaming PC in Minutes Using BuildCores – Step-by-Step Guide, oleh MrKnow.</p>
    <div class="actions">
      <a class="button primary" href="https://www.buildcores.com/builds" target="_blank" rel="noopener noreferrer">Buka BuildCores ↗</a>
      <a class="button" href="https://www.youtube.com/watch?v=82eJ6YFSess" target="_blank" rel="noopener noreferrer">Tonton Tutorial BuildCores ↗</a>
      <a class="button" href="https://www.darkflash.com/id-ID/article/visualize-pc-build-in-3D-with-buildcores" target="_blank" rel="noopener noreferrer">Panduan Bahasa Indonesia ↗</a>
      <a class="button" href="https://www.youtube.com/@BuildCores" target="_blank" rel="noopener noreferrer">Kanal Resmi BuildCores ↗</a>
    </div>
    <p class="muted">Tutorial MrKnow berasal dari pihak ketiga. Nama tombol dapat berbeda pada versi terbaru. Semua tautan terbuka di tab baru dan memerlukan internet. Latihan ini dinilai dari komponen katalog demo yang Anda pilih; hasil BuildCores dapat dipakai sebagai bahan belajar.</p>
  </details>`;}
  function rules(){
    let text='';
    if(slug==='cyber')text='<p>Jawab enam soal pilihan ganda A–D tentang keamanan akun dan data. Tanpa rotasi anggota; satu orang dapat mensimulasikan diskusi tim.</p>';
    if(slug==='networking')text='<ol><li>Signal Check: 3 soal A–E, 90 detik, 30 poin.</li><li>True or Trap: 4 pernyataan Benar/Salah, 60 detik, 40 poin.</li><li>Case Signal: 5 isian singkat, 150 detik, 30 poin.</li></ol><p>Pilihan tahap 1/2 langsung terkunci setelah tersimpan; jawab berurutan. Tahap berikutnya dimulai dari halaman transisi, sementara batas keseluruhan tetap berjalan. Isian tahap 3 boleh diedit sebelum submit. Penilaian menerima variasi terdaftar tanpa membedakan kapitalisasi dan spasi berlebih. Minimal 4 dari 5 benar pada tahap 3 memperoleh Stempel Latihan. Penalti demo 0.</p>';
    if(slug==='hardware')text=`<p>Baca kasus studio podcast, lalu pilih CPU, motherboard, GPU, RAM, storage, dan PSU dari katalog sintetis. Tulis alasan singkat (maksimal 1000 karakter); alasan disimpan tanpa nilai otomatis.</p><p>Budget USD ${pack.rules.budget}, target CPU ${pack.rules.cpu}, GPU ${pack.rules.gpu}. Cocokkan socket dan jenis RAM; PSU harus memenuhi daya CPU + GPU + cadangan 100 W.</p><p>Bobot: kompatibilitas 20, budget 15, CPU 15, GPU 20, kelengkapan 10, efisiensi 15. Bonus maksimal 5 berdasarkan proporsi waktu tersisa. Skor akhir maksimal 100. Tidak memerlukan BuildCores atau upload.</p>${buildcoresGuide(true)}`;
    return `<section class="panel">${badge}<h1>Aturan ${esc(pack.title)}</h1>${text}<p>Durasi ${pack.duration/60} menit termasuk membaca dan transisi. Timer dimulai setelah konfirmasi Mulai Demo. Refresh mempertahankan waktu dan progres.</p>${slug!=='hardware'?'<p>Benar 10 poin (isian Networking 6), salah/kosong 0. Skor akhir = skor jawaban + sisa detik keseluruhan × 1.</p>':''}<p>Waktu habis menilai progres tersimpan dengan bonus nol. Sesi tersedia 24 jam. Gunakan satu tab untuk pengerjaan. Ini simulasi browser; nilai tidak dihitung dalam lomba.</p><div class="actions">${button('start','Mulai Demo')}${state?`<a class="button" href="#${slug}/${state.status==='RUNNING'?state.phase:'result'}">${state.status==='RUNNING'?'Lanjutkan Percobaan':'Lihat Hasil Terakhir'}</a>`:''}<a class="button" href="#stations">Kembali ke Pilihan Pos</a></div></section>`;
  }
  function quiz(){
    const all=e.activeQuestions(state,pack),network=slug==='networking';
    if(network&&state.stage===3)return title()+`<section class="panel"><h2>Case Signal · Isian Singkat</h2>${all.map(q=>`<label class="short-label" for="short-${q.id}">${q.id}. ${esc(q.text)}</label><input class="module-input" id="short-${q.id}" data-short="${q.id}" maxlength="255" value="${esc(state.answers[q.id]||'')}" autocomplete="off">`).join('')}<div class="actions">${button('complete','Kirim Semua Jawaban')}</div></section>`;
    const q=network?all.find(q=>!state.answers[q.id]):all[state.active];
    if(!q)return title()+`<section class="panel"><h2>Seluruh soal tahap ini tersimpan</h2><p>Pilihan sudah dikunci. Lanjutkan ke transisi tahap berikutnya.</p>${button('complete','Selesaikan Tahap '+state.stage)}</section>`;
    const nav=network?`<p>Soal ${all.indexOf(q)+1} / ${all.length}. Pilihan akan langsung dikunci setelah tersimpan.</p>`:`<aside class="card navigator"><h2>NAVIGATOR SOAL</h2><p>${Object.keys(state.answers).length} / ${all.length} terjawab</p><div class="nav-buttons">${all.map((q,i)=>`<button class="nav-button ${state.answers[q.id]?'answered':''} ${state.active===i?'active':''}" data-module-nav="${i}" aria-label="Soal ${q.id}" ${state.active===i?'aria-current="step"':''}>${q.id}</button>`).join('')}</div></aside>`;
    const card=`<section class="card question"><div class="q-header"><span>SOAL #${q.id}</span><span>BOBOT ${q.weight} POIN</span></div><h2 id="module-question" class="question-text">${esc(q.text)}</h2><div class="options" role="radiogroup" aria-labelledby="module-question">${q.options.map((text,i)=>`<label class="option"><input type="radio" name="module-answer" data-module-question="${q.id}" value="${'ABCDE'[i]}" ${state.answers[q.id]==='ABCDE'[i]?'checked':''}><strong>${'ABCDE'[i]}</strong><span>${esc(text)}</span></label>`).join('')}</div>${!network?`<div class="question-actions"><button class="button" data-module-nav="${Math.max(0,state.active-1)}" ${state.active===0?'disabled':''}>Sebelumnya</button><button class="button" data-module-nav="${Math.min(all.length-1,state.active+1)}" ${state.active===all.length-1?'disabled':''}>Berikutnya</button></div>`:''}</section>`;
    return title()+(network?nav+card:`<div class="quiz-layout">${nav}${card}</div><section class="panel">${button('complete','Kirim Semua Jawaban Tim')}</section>`);
  }
  function catalogueLabel(item){return item.name+' · USD '+item.price+(item.score?' · skor '+item.score:'')+(item.socket?' · socket '+item.socket:'')+(item.ram?' · '+item.ram:'')+(item.watts?' · '+item.watts+' W':'')+(item.capacity?' · '+item.capacity+(item.ram?' GB':' GB storage'):'');}
  function hardware(){return title()+`<a class="button small" href="#hardware/case">Buka Studi Kasus</a>${buildcoresGuide()}<section class="panel" style="margin-top:24px"><h2>Rakitan Studio Podcast</h2><p>Harga dan performa sintetis. Budget USD ${pack.rules.budget}; CPU ${pack.rules.cpu}; GPU ${pack.rules.gpu}.</p><div class="grid">${Object.entries(pack.catalogue).map(([cat,items])=>`<div><label class="short-label" for="build-${cat}">${cat.toUpperCase()}</label><select id="build-${cat}" class="module-input" data-component="${cat}"><option value="">Pilih komponen</option>${items.map(item=>`<option value="${item.id}" ${state.components[cat]===item.id?'selected':''}>${esc(catalogueLabel(item))}</option>`).join('')}</select></div>`).join('')}</div><p id="hardware-total"></p><label class="short-label" for="rationale">Alasan rakitan</label><textarea class="module-input" id="rationale" maxlength="1000" rows="4">${esc(state.rationale)}</textarea><div class="actions">${button('complete','Kirim Rakitan')}</div></section>`;}
  function result(){
    const r=state.result;let details='';
    if(slug==='hardware'){
      const weights={compatibility:20,budget:15,cpu:15,gpu:20,completeness:10,efficiency:15};
      details=`<section class="panel"><h2>Rincian Rakitan dan Pembahasan</h2><p>Total USD ${r.price} / ${pack.rules.budget} · kebutuhan daya ${r.power} W</p>${Object.entries(r.items).map(([cat,item])=>`<p>${cat.toUpperCase()}: ${esc(item.name||'Belum dipilih')}</p>`).join('')}${Object.entries(r.checks).map(([name,ok])=>`<p>${name.toUpperCase()}: ${ok?'Sesuai':'Belum sesuai'}</p>`).join('')}${Object.entries(r.breakdown).map(([name,points])=>`<p>${name}: ${points} / ${weights[name]} poin</p>`).join('')}<p>Alasan Anda: ${esc(state.rationale||'Belum diisi')}. Alasan tidak dinilai otomatis.</p><p>Kompatibilitas mensyaratkan enam pilihan, socket CPU/board dan RAM yang sesuai, serta PSU cukup. Budget mendapat nilai penuh hanya jika harga positif dan tidak melewati batas. CPU/GPU dinilai proporsional hingga target. Kelengkapan mengikuti lima aspek CPU, GPU, RAM, storage, PSU. Efisiensi = (skor CPU + GPU) / total harga, dengan target ${pack.rules.efficiency}.</p><h2>Contoh rakitan yang memenuhi target</h2>${Object.entries(pack.catalogue).map(([cat,items])=>`<p>${cat.toUpperCase()}: ${esc(catalogueLabel(items[0]))}</p>`).join('')}<p>Contoh memakai socket S1, DDR4, dan PSU cukup. Ini hasil simulasi, bukan verifikasi panitia.</p></section>`;
    }else{
      details=(slug==='networking'?`<section class="panel"><h2>Hasil per Tahap</h2><p>Signal Check ${r.stages[1]}/30 · True or Trap ${r.stages[2]}/40 · Case Signal ${r.stages[3]}/30</p><p>${r.stamp?'Stempel Latihan diperoleh':'Stempel Latihan belum diperoleh'} · ${r.stage3}/5 benar pada tahap 3 · penalti 0. Penilaian latihan otomatis, bukan verifikasi fasilitator resmi.</p></section>`:'')+pack.questions.map(q=>{const value=state.answers[q.id];const format=v=>q.options.length?v+' · '+q.options['ABCDE'.indexOf(v)]:v;return `<article class="card ${e.matches(q,value)?'correct':'incorrect'}"><h3>${q.id}. ${esc(q.text)}</h3><p>Jawaban Anda: ${value?esc(format(value)):'Belum dijawab'}</p><p><strong>Jawaban benar: ${esc(format(q.key))}</strong></p><p>${esc(q.explanation)}</p></article>`;}).join('');
    }
    return `<section class="panel">${badge}<h1>Hasil ${esc(pack.title)}</h1><p>Status: <strong>${state.status==='TIMED_OUT'?'Waktu habis':'Selesai dikirim'}</strong>${slug!=='hardware'?' · '+r.answered+'/'+pack.questions.length+' terjawab · '+r.correct+' benar':''}</p><div class="grid">${[['Skor jawaban / aspek',r.raw],['Bonus waktu',r.bonus],['Skor akhir',r.total]].map(([name,value])=>`<div class="card score">${name}<strong>${value}</strong></div>`).join('')}</div><p>Nilai demo tidak dihitung dalam lomba dan tidak masuk leaderboard, rekap, atau ekspor resmi.</p><p>Versi: ${esc(pack.version)} · simulasi browser.</p>${actions()}</section>${details}${actions()}`;
  }
  function render(){
    if(!handles())return;load();document.querySelector('dialog')?.remove();let page=locationInfo().page;
    if(!['rules','case','quiz','transition','result'].includes(page)){notices[slug]='Halaman tidak tersedia. Baca aturan untuk memulai.';go('rules');return;}
    if(state&&e.expire(state,pack,Date.now()))save();
    if(page!=='rules'){
      if(!state){go('rules');return;}
      if(state.status!=='RUNNING'&&page!=='result'){go('result');return;}
      if(state.status==='RUNNING'&&(page==='result'||(page==='transition'&&state.phase!=='transition')||(page==='quiz'&&(state.phase==='transition'||!state.seen)))){go(state.phase);return;}
      if(page==='case'&&!pack.caseText){go(state.phase);return;}
    }
    let html='';if(page==='rules')html=rules();
    if(page==='case')html=`<section class="panel"><div class="quiz-header">${badge}${timer()}</div><h1>${esc(pack.caseTitle)}</h1><p>${esc(pack.caseText)}</p><p>Waktu membaca termasuk timer.</p>${button('read',state.seen?'Kembali ke Rakitan':'Mulai Kerjakan')}</section>`;
    if(page==='transition')html=`<section class="panel"><div class="quiz-header">${badge}${timer()}</div><h1>Lanjut ke Tahap ${state.stage+1}</h1><p>Jawaban tahap sebelumnya dikunci. Waktu keseluruhan tetap berjalan; tahap berikutnya dimulai setelah menekan tombol di bawah.</p>${button('continue','Mulai Tahap '+(state.stage+1))}</section>`;
    if(page==='quiz')html=slug==='hardware'?hardware():quiz();if(page==='result')html=result();
    const warning=notices[slug]||(!storage?storageError:'');
    app.innerHTML=(warning?`<div class="notice" role="status">${esc(warning)}</div>`:'')+html;
    document.title=pack.title+' · Mode Demo';app.focus({preventScroll:true});tick();total();
  }
  function total(){
    if(slug!=='hardware'||!state||!document.getElementById('hardware-total'))return;
    document.getElementById('hardware-total').textContent='Total harga latihan: USD '+e.hardware(pack,state,0).price+' / '+pack.rules.budget;
    document.querySelectorAll('[data-component]').forEach(select=>{
      let detail=document.getElementById('component-details-'+select.dataset.component);
      if(!detail){detail=document.createElement('p');detail.id='component-details-'+select.dataset.component;detail.className='muted';select.after(detail);}
      const item=pack.catalogue[select.dataset.component].find(item=>item.id===state.components[select.dataset.component]);detail.textContent=item?catalogueLabel(item):'Belum dipilih';
    });
  }
  function tick(){
    if(!handles()||!state||state.status!=='RUNNING')return;
    if(Date.now()>=state.expires){load();render();return;}
    if(e.expire(state,pack,Date.now())){save();go(state.phase);return;}
    const el=document.getElementById('module-timer');if(el){const end=slug==='networking'&&state.phase==='quiz'?state.stageDeadline:state.deadline;const remaining=Math.max(0,Math.ceil((end-Date.now())/1000));el.textContent=String(Math.floor(remaining/60)).padStart(2,'0')+':'+String(remaining%60).padStart(2,'0');el.classList.toggle('critical',remaining<=30);const overall=document.getElementById('module-overall');if(overall&&slug==='networking')overall.textContent='Keseluruhan: '+Math.max(0,Math.ceil((state.deadline-Date.now())/1000))+' detik';}
  }
  function changed(event){
    if(!handles())return;const input=event.target;
    if(!input.matches('[data-module-question],[data-short],[data-component],#rationale'))return;
    if(!fresh()){render();return;}
    if(input.dataset.moduleQuestion){const choice=input.value;e.answer(state,pack,Number(input.dataset.moduleQuestion),choice);save();render();app.querySelector(`input[name="module-answer"][value="${choice}"]`)?.focus({preventScroll:true});}
    if(input.dataset.short){e.answer(state,pack,Number(input.dataset.short),input.value);save();}
    if(input.dataset.component){e.build(state,pack,input.dataset.component,input.value);save();total();}
    if(input.id==='rationale'){state.rationale=input.value.slice(0,1000);state.revision++;save();}
    const status=document.getElementById('module-save-status');if(status)status.textContent=storage?'Tersimpan di browser':'Belum tersimpan permanen';
    if(!storage&&!document.querySelector('.notice')){const warning=document.createElement('div');warning.className='notice';warning.setAttribute('role','status');warning.textContent=notices[slug]||storageError;app.prepend(warning);}
  }
  app.addEventListener('change',changed);app.addEventListener('input',event=>{if(event.target.matches('[data-short],#rationale'))changed(event);});
  app.addEventListener('click',event=>{
    if(!handles())return;const el=event.target.closest('button');if(!el||el.disabled)return;const action=el.dataset.moduleAction;
    if(action==='start'){const selected=locationInfo().slug;dialog('Mulai Demo?','Timer mulai setelah konfirmasi. Percobaan lama pos ini akan diganti; progres pos lain tetap tersimpan.','Mulai Demo',()=>{if(!handles()||locationInfo().slug!==selected)return;state=e.create(pack,Date.now(),'pages_'+(crypto.randomUUID?crypto.randomUUID():Date.now().toString(36)+Math.random().toString(36).slice(2)));notices[slug]='';save();go(state.phase);});return;}
    if(!action&&el.dataset.moduleNav===undefined)return;if(!fresh()){render();return;}
    if(el.dataset.moduleNav!==undefined){state.active=Number(el.dataset.moduleNav);state.revision++;save();render();}
    if(action==='read'){state.seen=true;state.phase='quiz';state.revision++;save();go('quiz');}
    if(action==='continue'){e.nextStage(state,pack,Date.now());save();go(state.phase);}
    if(action==='complete'&&state.phase==='quiz'){
      if(slug==='hardware'&&(Object.keys(state.components).length!==6||!state.rationale.trim())){notices[slug]='Pilih keenam komponen dan tulis alasan sebelum mengirim. Saat timeout, rakitan yang tersimpan tetap dinilai.';render();return;}
      if(slug==='networking'&&state.stage<3&&e.activeQuestions(state,pack).some(q=>!state.answers[q.id]))return;
      const id=state.id,stage=state.stage,selected=slug;const next=slug==='networking'&&stage<3;
      dialog(next?'Selesaikan Tahap '+stage+'?':'Kirim Hasil Demo?','Jawaban akan dikunci. Soal kosong bernilai 0. '+(next?'Timer keseluruhan tetap berjalan.':'Hasil dan pembahasan akan ditampilkan.'),next?'Kunci & Lanjutkan':'Ya, Kirim',()=>{if(!handles()||locationInfo().slug!==selected||!fresh()||state.id!==id||state.stage!==stage||state.phase!=='quiz'){render();return;}if(next){state.phase='transition';state.revision++;}else e.finish(state,pack,Date.now());save();go(state.phase);});
    }
  });
  window.addEventListener('hashchange',()=>{render();window.scrollTo(0,0);});window.addEventListener('storage',event=>{if(handles()&&(event.key===e.key(locationInfo().slug)||event.key===null)){render();}});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)render();});setInterval(tick,250);render();
}());
