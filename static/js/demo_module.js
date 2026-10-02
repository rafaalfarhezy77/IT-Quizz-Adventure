(function () {
  'use strict';
  const config = window.DEMO_MODULE_CONFIG;
  const form = document.getElementById('demo-module-form');
  const status = document.getElementById('module-save-status');
  let queue = Promise.resolve();
  let debounce;
  function payload() {
    const data = {revision: config.revision, member: config.member, stage: config.stage, answers: {}, components: {}, rationale: ''};
    new FormData(form).forEach((value, key) => {
      if (key.startsWith('question_') && value.trim()) data.answers[key.slice(9)] = value;
      if (key.startsWith('component_') && value) data.components[key.slice(10)] = value;
      if (key === 'rationale') data.rationale = value;
    });
    // Disabled networking answers are already stored; no client need resend them.
    return data;
  }
  function showActive() {
    if (config.method !== 'networking' || config.stage === 3) return;
    const cards = Array.from(document.querySelectorAll('.net-question'));
    const next = cards.find(card => !config.answers[card.dataset.questionId]);
    cards.forEach(card => {card.hidden = card !== next;});
    document.getElementById('module-submit').hidden = !!next;
    if (!next) status.textContent = 'Seluruh soal tahap ini tersimpan. Selesaikan tahap untuk melanjutkan.';
  }
  function total() {
    if (config.method !== 'hardware') return;
    const chosen = payload().components;
    const price = Object.entries(chosen).reduce((sum, [category, id]) => sum + (config.catalogue[category].find(item => item.id === id)?.price || 0), 0);
    document.getElementById('hardware-total').textContent = 'Total harga latihan: USD ' + price + ' / 1500';
  }
  function enqueue() {
    config.busy = true;
    const data = payload();
    queue = queue.then(async () => {
      data.revision = config.revision;
      status.textContent = 'Menyimpan...';
      try {
        const response = await fetch(config.answerUrl, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': config.csrfToken}, body: JSON.stringify(data)});
        const result = await response.json();
        if (!response.ok) {
          if (response.status === 409) config.conflict = true;
          throw new Error(result.error || 'Gagal menyimpan');
        }
        config.revision = result.revision;
        Object.assign(config.answers, data.answers);
        status.textContent = 'Tersimpan';
        if (config.method === 'networking' && config.stage < 3) {
          Object.keys(data.answers).forEach(id => form.querySelectorAll('[name="question_' + id + '"]').forEach(input => {input.disabled = true;}));
          showActive();
        }
      } catch (error) {
        status.textContent = error instanceof TypeError ? 'Koneksi terputus. Jawaban belum tersimpan.' : error.message;
      } finally { config.busy = false; }
    });
  }
  form.addEventListener('change', () => {clearTimeout(debounce); total(); enqueue();});
  form.addEventListener('input', event => {
    if (event.target.type === 'radio' || event.target.tagName === 'SELECT') return;
    clearTimeout(debounce); debounce = setTimeout(enqueue, 500);
  });
  window.addEventListener('online', enqueue);
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!confirm('Selesaikan bagian ini? Jawaban akan dikunci.')) return;
    clearTimeout(debounce);
    await queue;
    if (config.conflict) {location.reload(); return;}
    form.querySelector('[name="revision"]').value = config.revision;
    document.getElementById('module-submit').disabled = true;
    form.submit();
  });
  showActive(); total();
}());
