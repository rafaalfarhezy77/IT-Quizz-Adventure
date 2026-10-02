const {test} = require('node:test');
const assert = require('node:assert/strict');
const pack = require('../assets/questions.js');
const e = require('../assets/engine.js');
const now = 1700000000000;
const make = () => e.create(pack, now, 'pages_test_123456');
test('dedicated storage key, nine original questions and three members', () => {
  assert.equal(e.STORAGE_KEY, 'itquest:github-pages:software:attempt:v1');
  assert.equal(pack.questions.length, 9); assert.equal(pack.members, 3);
  assert.equal(new Set(pack.questions.map(q => q.id)).size, 9);
});
test('new attempts start with four-minute deadline and independent answers', () => {
  const a = make(), b = make(); a.answers[1] = 'A';
  assert.deepEqual(b.answers, {}); assert.equal(a.deadline, now + 240000);
});
test('refresh retains deadline, member and answers', () => {
  const a = make(); a.phase = 'quiz'; a.seen = true; e.answer(a, 1, 'B');
  const {state,error} = e.decode(JSON.stringify(a),pack,now+2000);
  assert.equal(error,null); assert.equal(state.deadline,a.deadline); assert.equal(state.answers[1],'B');
});
test('corrupt JSON and malformed records rejected', () => {
  for (const raw of ['{', 'null', '[]', '{}', 'x'.repeat(16001)]) assert.ok(e.decode(raw,pack,now).error);
});
test('changed question version invalidates saved attempt', () => {
  const a = make(); a.version = 'old-version'; assert.match(e.decode(JSON.stringify(a),pack,now).error,/Versi/);
});
test('expired attempt rejected', () => assert.match(e.decode(JSON.stringify(make()),pack,now+e.TTL).error,/kedaluwarsa/));
test('invalid deadline rejected', () => {
  const a = make(); a.deadline += 100000; assert.ok(e.decode(JSON.stringify(a),pack,now).error);
});
test('bad answers and progress rejected', () => {
  for (const mutate of [a => a.answers[1]='Z', a => a.answers[9]='A', a => a.member=5, a => a.active=-1, a => a.answers=null, a => a.phase='result']) {
    const a=make(); mutate(a); assert.ok(e.decode(JSON.stringify(a),pack,now).error);
  }
});
test('answers only allowed in active member during quiz', () => {
  const a=make(); assert.equal(e.answer(a,1,'A'),false); a.phase='quiz'; a.seen=true;
  assert.equal(e.answer(a,1,'B'),true); assert.equal(e.answer(a,4,'A'),false);
  a.member=2; assert.equal(e.answer(a,1,'A'),false); assert.equal(a.answers[1],'B');
});
test('score includes correct answers and remaining whole seconds', () => {
  const a=make(); a.answers={1:'A',2:'D',3:'C'};
  e.finish(a,pack,now+30500); assert.deepEqual(a.result,{correct:2,answered:3,raw:20,bonus:209,total:229});
});
test('timeout scores saved answers with zero bonus', () => {
  const a=make(); a.answers={1:'A'}; e.finish(a,pack,now+250000);
  assert.equal(a.status,'TIMED_OUT'); assert.equal(a.result.total,10); assert.equal(a.result.bonus,0);
});
test('double submit leaves result unchanged and completed answers locked', () => {
  const a=make(); a.phase='quiz'; e.answer(a,1,'A'); e.finish(a,pack,now+40000);
  const snapshot=JSON.stringify(a); assert.equal(e.finish(a,pack,now+50000),false);
  assert.equal(e.answer(a,1,'B'),false); assert.equal(JSON.stringify(a),snapshot);
});
test('stored result recomputed rather than trusting stored points', () => {
  const a=make(); e.finish(a,pack,now+1000); a.result={total:999999};
  const decoded=e.decode(JSON.stringify(a),pack,now+2000); assert.equal(decoded.error,null); assert.equal(decoded.state.result.total,239);
});
test('unknown or future timestamps and invalid finalization rejected', () => {
  const a=make(); a.start=now+120000; a.deadline=a.start+240000; a.expires=a.start+e.TTL;
  assert.ok(e.decode(JSON.stringify(a),pack,now).error);
  const b=make(); e.finish(b,pack,now+1000); b.finished=b.deadline+1;
  assert.ok(e.decode(JSON.stringify(b),pack,now).error);
});
