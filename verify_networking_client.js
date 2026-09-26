/* Run with: node verify_networking_client.js */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const template = fs.readFileSync('templates/participant/networking.html', 'utf8');
const scripts = [...template.matchAll(/<script>([\s\S]*?)<\/script>/g)];
const code = scripts.at(-1)[1] + '\nglobalThis.testApi = {sendAnswerToServer, confirmSubmitStage, selectOption, showActiveQuestion};';
const tick = () => new Promise(resolve => setImmediate(resolve));
function createHarness(withTimer = false, stage = 3) {
  const requests = [];
  let submitHandler;
  let submitted = 0;
  let timerCallback;
  let now = 0;
  const input = {dataset: {qid: '21'}, value: 'WAN'};
  const cards = stage < 3 ? [1,2].map(id => {
    const card = {dataset: {answered: 'false'}, hidden: id !== 1};
    const buttons = ['A','B'].map(answer => {
      const classes = new Set();
      return {disabled:false, classList:{add: name=>classes.add(name),remove:name=>classes.delete(name)},selected:()=>classes.has('selected'),closest:()=>card,dataset:{qid:String(id),ans:answer}};
    });
    card.buttons=buttons;card.querySelectorAll=()=>buttons;card.querySelector=selector=>selector==='button.selected'?buttons.find(b=>b.selected()):null;
    return card;
  }) : [];
  const button = {disabled: false};
  const form = {addEventListener: (_event, handler) => {submitHandler = handler;}, submit: () => {submitted++;}};
  const nodes = {
    'networking-quiz-data': {textContent: JSON.stringify({remainingSec: 10, currentStage: stage, saveUrl: '/save'})},
    stageSubmitForm: form, submitStageBtn: button,
  };
  if (withTimer) nodes.timerDisplay = {innerText: ''};
  const context = vm.createContext({
    document: {getElementById: id => nodes[id] || null, querySelectorAll: query => query === '.net-q-card[id]' ? cards : query === '.short-text-input' ? (stage===3?[input]:[]) : query === 'button.selected[data-qid]' ? cards.flatMap(card=>card.buttons).filter(b=>b.selected()) : []},
    fetch: (_url, options) => new Promise(resolve => requests.push({answer: JSON.parse(options.body), release: () => resolve({json: async () => ({success: true})})})),
    setTimeout, clearTimeout, setInterval: fn => {timerCallback = fn;return 1;}, clearInterval: () => {},
    Date: {now: () => now}, confirm: () => true, alert: () => {}, console,
  });
  vm.runInContext(code, context);
  return {context, requests, button, form, input, cards, submit: () => submitHandler({preventDefault(){}}), get submitted(){return submitted;}, advance: ms => {now += ms;timerCallback();}};
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
  const choices = createHarness(false,1);
  assert.equal(choices.cards.filter(card=>!card.hidden).length,1);
  assert.equal(choices.cards[0].hidden,false);
  const selecting = choices.context.testApi.selectOption(choices.cards[0].buttons[0],'1','A');
  await tick();assert.equal(choices.cards[0].buttons[1].disabled,true);
  choices.requests[0].release();await selecting;
  assert.equal(choices.cards[0].dataset.answered,'true');
  assert.equal(choices.cards[0].hidden,true);assert.equal(choices.cards[1].hidden,false);
  await choices.context.testApi.selectOption(choices.cards[0].buttons[1],'1','B');
  assert.equal(choices.requests.length,1,'An already submitted choice must stay locked');
  const secondChoice=choices.context.testApi.selectOption(choices.cards[1].buttons[0],'2','A');
  await tick();choices.requests[1].release();await secondChoice;
  assert.equal(choices.button.hidden,false,'Stage completion becomes available after all answers');
  console.log('Networking client: autosave ordering, submit flush, click guard, and wall-clock timer passed.');
})().catch(error => {console.error(error);process.exitCode = 1;});
