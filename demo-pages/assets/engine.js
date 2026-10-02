/* Storage validation and scoring have no DOM or backend dependencies. */
(function (root) {
  'use strict';
  const STORAGE_KEY = 'itquest:github-pages:software:attempt:v1';
  const TTL = 24 * 60 * 60 * 1000;
  function create(pack, now, id) {
    return {schema: 1, version: pack.version, id, start: now,
      deadline: now + pack.duration * 1000, expires: now + TTL,
      status: 'RUNNING', member: 1, phase: 'case', seen: false,
      answers: {}, active: 0, revision: 0, finished: null, result: null};
  }
  function score(state, pack) {
    const correct = pack.questions.filter(q => state.answers[q.id] === q.key).length;
    const remaining = state.status === 'TIMED_OUT' ? 0 : Math.max(0, Math.floor((state.deadline - state.finished) / 1000));
    const raw = correct * 10;
    const bonus = remaining * pack.bonusPerSecond;
    return {correct, answered: Object.keys(state.answers).length, raw, bonus, total: raw + bonus};
  }
  function finish(state, pack, now, timedOut = false) {
    if (state.status !== 'RUNNING') return false;
    state.status = timedOut || now >= state.deadline ? 'TIMED_OUT' : 'SUBMITTED';
    state.finished = state.status === 'TIMED_OUT' ? state.deadline : Math.max(state.start, now);
    state.phase = 'result'; state.result = score(state, pack); state.revision++;
    return true;
  }
  function validate(state, pack, now) {
    if (!state || typeof state !== 'object' || Array.isArray(state)) return 'Data latihan rusak.';
    if (state.schema !== 1 || state.version !== pack.version) return 'Versi latihan telah diperbarui. Mulai percobaan baru.';
    if (typeof state.id !== 'string' || !/^pages_[a-zA-Z0-9_-]{8,100}$/.test(state.id)) return 'Identitas latihan tidak valid.';
    if (![state.start, state.deadline, state.expires].every(Number.isSafeInteger) ||
      state.deadline !== state.start + pack.duration * 1000 || state.expires !== state.start + TTL || state.start > now + 60000) return 'Waktu latihan tidak valid.';
    if (now >= state.expires) return 'Latihan kedaluwarsa setelah 24 jam. Mulai lagi.';
    if (!['RUNNING', 'SUBMITTED', 'TIMED_OUT'].includes(state.status) ||
      !['case', 'quiz', 'transition', 'result'].includes(state.phase) ||
      !Number.isInteger(state.member) || state.member < 1 || state.member > pack.members ||
      !Number.isInteger(state.active) || state.active < 0 || state.active > 2 ||
      !Number.isSafeInteger(state.revision) || state.revision < 0 || typeof state.seen !== 'boolean') return 'Progres latihan tidak valid.';
    if (!state.answers || typeof state.answers !== 'object' || Array.isArray(state.answers)) return 'Jawaban tersimpan rusak.';
    if (Object.entries(state.answers).some(([id, choice]) => !pack.questions.some(q => String(q.id) === id) || !/^[ABCD]$/.test(choice) || Number(id) > state.member * 3)) return 'Jawaban tersimpan tidak valid.';
    if (state.status === 'RUNNING' && (state.phase === 'result' || state.finished !== null || state.result !== null)) return 'Status latihan tidak valid.';
    if (state.phase === 'transition' && state.member === 1) return 'Giliran latihan tidak valid.';
    if (state.status !== 'RUNNING') {
      if (state.phase !== 'result' || !Number.isSafeInteger(state.finished) || state.finished < state.start || state.finished > state.deadline ||
        (state.status === 'TIMED_OUT' && state.finished !== state.deadline)) return 'Hasil latihan rusak.';
      // Recompute rather than trust any stored score.
      state.result = score(state, pack);
    }
    return null;
  }
  function decode(raw, pack, now) {
    if (raw === null) return {state: null, error: null};
    try {
      if (raw.length > 16000) throw new Error('oversize');
      const state = JSON.parse(raw);
      const error = validate(state, pack, now);
      return error ? {state: null, error} : {state, error: null};
    } catch (_) { return {state: null, error: 'Data latihan tidak dapat dibaca. Mulai percobaan baru.'}; }
  }
  function answer(state, id, choice) {
    if (state.status !== 'RUNNING' || state.phase !== 'quiz' || !Number.isInteger(id) || id <= (state.member - 1) * 3 || id > state.member * 3 || !/^[ABCD]$/.test(choice)) return false;
    state.answers[id] = choice; state.revision++; return true;
  }
  const engine = {STORAGE_KEY, TTL, create, finish, decode, score, answer};
  root.DemoEngine = engine;
  if (typeof module !== 'undefined') module.exports = engine;
}(globalThis));
