/* Run with: node verify_networking_client.js */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const template = fs.readFileSync('templates/participant/networking.html', 'utf8');
const scripts = [...template.matchAll(/<script>([\s\S]*?)<\/script>/g)];
const code = scripts.at(-1)[1] + '\nglobalThis.testApi = {sendAnswerToServer, confirmSubmitStage};';
const tick = () => new Promise(resolve => setImmediate(resolve));
function createHarness(withTimer = false) {
  const requests = [];
  let submitHandler;
  let submitted = 0;
  let timerCallback;
  let now = 0;
  const input = {dataset: {qid: '21'}, value: 'WAN'};
  const button = {disabled: false};
  const form = {addEventListener: (_event, handler) => {submitHandler = handler;}, submit: () => {submitted++;}};
  const nodes = {
    'networking-quiz-data': {textContent: JSON.stringify({remainingSec: 10, currentStage: 3, saveUrl: '/save'})},
    stageSubmitForm: form, submitStageBtn: button,
  };
  if (withTimer) nodes.timerDisplay = {innerText: ''};
  const context = vm.createContext({
    document: {getElementById: id => nodes[id] || null, querySelectorAll: query => query === '.short-text-input' ? [input] : []},
    fetch: (_url, options) => new Promise(resolve => requests.push({answer: JSON.parse(options.body), release: () => resolve({json: async () => ({success: true})})})),
    setTimeout, clearTimeout, setInterval: fn => {timerCallback = fn;return 1;}, clearInterval: () => {},
    Date: {now: () => now}, confirm: () => true, alert: () => {}, console,
  });
  vm.runInContext(code, context);
  return {context, requests, button, form, input, submit: () => submitHandler({preventDefault(){}}), get submitted(){return submitted;}, advance: ms => {now += ms;timerCallback();}};
}
(async () => {
  const h = createHarness();
  assert.equal(h.context.testApi.confirmSubmitStage({preventDefault(){}}), true);
  assert.equal(h.button.disabled, false, 'Click confirmation must not cancel native form submission by disabling the button');
  const first = h.context.testApi.sendAnswerToServer('21', 'PAN');
  const second = h.context.testApi.sendAnswerToServer('21', 'WAN');
  await tick();
  assert.equal(h.requests.length, 1, 'Saves for one question must be serialized');
  h.requests[0].release();await first;await tick();
  assert.equal(h.requests.length, 2);
  h.requests[1].release();await second;
  const submitting = h.submit();await tick();
  assert.equal(h.submitted, 0, 'Stage submission must wait for trailing input to persist');
  assert.equal(h.requests[2].answer.answer_value, 'WAN');
  h.requests[2].release();await submitting;
  assert.equal(h.submitted, 1);
  const timer = createHarness(true);
  timer.advance(20000);
  assert.equal(timer.submitted, 1, 'Elapsed wall time must expire a background-tab timer');
  console.log('Networking client: autosave ordering, submit flush, click guard, and wall-clock timer passed.');
})().catch(error => {console.error(error);process.exitCode = 1;});
