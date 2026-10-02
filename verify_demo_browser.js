/* Chromium DevTools checks. Node 22+; launched by verify_demo_browser.py. */
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const [browser, profile, base] = process.argv.slice(2);
const output = 'scratch/demo-browser';
fs.mkdirSync(output, {recursive: true});
const child = spawn(browser, ['--headless=new', '--remote-debugging-port=0',
  '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
  '--user-data-dir=' + profile, 'about:blank'], {windowsHide: true});
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let socket;
let seq = 0;
const pending = new Map();
async function run() {
  const address = await new Promise((resolve, reject) => {
    let log = '';
    const timer = setTimeout(() => reject(new Error('Chromium startup timeout')), 20000);
    child.stderr.on('data', chunk => {
      log += chunk.toString();
      const match = log.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) {clearTimeout(timer); resolve(match[1]);}
    });
    child.on('error', reject);
  });
  socket = new WebSocket(address);
  await new Promise((resolve, reject) => {socket.onopen = resolve; socket.onerror = reject;});
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    const waiter = pending.get(message.id);
    if (!waiter) return;
    pending.delete(message.id);
    message.error ? waiter.reject(new Error(JSON.stringify(message.error))) : waiter.resolve(message.result);
  };
  function cdp(method, params = {}, sessionId) {
    return new Promise((resolve, reject) => {
      const id = ++seq;
      pending.set(id, {resolve, reject});
      socket.send(JSON.stringify({id, method, params, ...(sessionId ? {sessionId} : {})}));
    });
  }
  for (const [label, width, height] of [['desktop', 1366, 900], ['mobile', 390, 844]]) {
    const {browserContextId} = await cdp('Target.createBrowserContext');
    const {targetId} = await cdp('Target.createTarget', {url: 'about:blank', browserContextId});
    const {sessionId} = await cdp('Target.attachToTarget', {targetId, flatten: true});
    const cmd = (method, params) => cdp(method, params, sessionId);
    await cmd('Page.enable');
    await cmd('Page.addScriptToEvaluateOnNewDocument', {source: 'window.confirm = () => true;'});
    await cmd('Network.enable');
    // Existing optional Google fonts must not make a local check depend on internet.
    await cmd('Network.setBlockedURLs', {urls: ['https://fonts.googleapis.com/*', 'https://fonts.gstatic.com/*']});
    await cmd('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: 1, mobile: label === 'mobile'});
    async function evaluate(expression) {
      const result = await cmd('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
      if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
      return result.result.value;
    }
    async function wait(expression) {
      for (let i = 0; i < 200; i++) {
        try {if (await evaluate('document.readyState === "complete" && (' + expression + ')')) return;} catch (_) {}
        await delay(100);
      }
      const details = await evaluate('({path:location.pathname,ready:document.readyState,text:document.body.textContent.slice(-1500)})');
      throw new Error('Browser condition timed out: ' + expression + '\n' + JSON.stringify(details));
    }
    async function screenshot(name) {
      await delay(150);
      const dimensions = await evaluate('({viewport:innerWidth,width:document.documentElement.scrollWidth})');
      assert(dimensions.width <= dimensions.viewport + 1, label + ' overflow at ' + name + JSON.stringify(dimensions));
      const clipped = await evaluate(`Array.from(document.querySelectorAll('.demo-panel,.quiz-top-sticky,.quiz-nav-sidebar,.question-card.active-question,.quiz-action-bar')).filter(el => {const r=el.getBoundingClientRect();return r.width>0 && (r.right>innerWidth+1 || r.left< -1)}).map(el=>el.className)`);
      assert.deepEqual(clipped, [], label + ' clipped panels at ' + name);
      const {data} = await cmd('Page.captureScreenshot', {format: 'png', captureBeyondViewport: false});
      fs.writeFileSync(`${output}/${label}-${name}.png`, Buffer.from(data, 'base64'));
    }
    await cmd('Page.navigate', {url: base + '/'});
    await wait('!!document.querySelector("a[href=\'/demo/\']")');
    await screenshot('landing');
    await evaluate('document.querySelector("a[href=\'/demo/\']").click()');
    await wait('location.pathname === "/demo/" && !!document.querySelector("a[href=\'/demo/hardware/rules\']")');
    await screenshot('select');
    await evaluate('document.querySelector("a[href=\'/demo/software/rules\']").click()');
    await wait('!!document.querySelector("form[action=\'/demo/software/start\']")');
    await screenshot('rules');
    await evaluate('document.querySelector("form[action=\'/demo/software/start\'] button").click()');
    await wait('location.pathname.endsWith("/case-study") && !!document.getElementById("session-timer")');
    await screenshot('case');
    await evaluate('document.querySelector("form button").click()');
    await wait('location.pathname.endsWith("/quiz") && !!window.QUIZ_CONFIG');
    await screenshot('quiz');
    const deadline = await evaluate('document.getElementById("session-timer").dataset.deadline');
    await evaluate('document.querySelector("input[name=question_1][value=A]").click()');
    await wait('document.getElementById("save-status-text").textContent === "Tersimpan"');
    await evaluate('document.querySelector(".quiz-action-bar").scrollIntoView({block:"end"})');
    await screenshot('quiz-actions');
    await cmd('Page.reload');
    await wait('!!document.querySelector("input[name=question_1][value=A]:checked")');
    assert.equal(await evaluate('document.getElementById("session-timer").dataset.deadline'), deadline);
    if (label === 'mobile') {
      await cmd('Network.emulateNetworkConditions', {offline: true, latency: 0, downloadThroughput: -1, uploadThroughput: -1});
      await evaluate('document.querySelector("input[name=question_1][value=B]").click()');
      await wait('document.getElementById("save-status-text").textContent === "Koneksi terputus"');
      await cmd('Network.emulateNetworkConditions', {offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1});
      await evaluate('window.dispatchEvent(new Event("online"))');
      await wait('document.getElementById("save-status-text").textContent === "Tersimpan"');
    }
    for (const member of [1, 2]) {
      await evaluate('document.getElementById("btn-trigger-member-submit").click()');
      await wait('document.getElementById("modal-member-confirm").style.display === "flex"');
      await evaluate('document.getElementById("btn-member-confirm").click()');
      await wait('location.pathname.endsWith("/advance") && document.body.textContent.includes("Giliran Anggota ' + (member + 1) + '")');
      await screenshot('transition-' + member);
      await evaluate('document.querySelector("a[href$=\'/quiz\']").click()');
      await wait('!!window.QUIZ_CONFIG && window.QUIZ_CONFIG.currentMember === ' + (member + 1));
    }
    await evaluate('document.querySelector("input[name=question_9][value=A]").click()');
    await evaluate('document.getElementById("btn-trigger-final-submit").click()');
    await wait('document.getElementById("modal-submit-confirm").style.display === "flex"');
    await screenshot('submit-confirm');
    await evaluate('document.getElementById("btn-modal-confirm-submit").click()');
    await wait('location.pathname.endsWith("/result") && document.body.textContent.includes("Jawaban benar")');
    await screenshot('result');
    await evaluate('document.querySelector(".demo-panel article").scrollIntoView({block:"center"})');
    await screenshot('result-review');
    await evaluate('document.querySelector("form[action=\'/demo/software/start\']").scrollIntoView({block:"center"})');
    await screenshot('result-actions');
    console.log(label + ': full flow, autosave, refresh, rotation, submit, and viewport checks passed');
    for (const slug of ['cyber', 'networking', 'hardware']) {
      await cmd('Page.navigate', {url: base + '/demo/' + slug + '/rules'});
      await wait('!!document.querySelector("form[action=\'/demo/' + slug + '/start\']")');
      await screenshot(slug + '-rules');
      await evaluate('document.querySelector("form[action=\'/demo/' + slug + '/start\'] button").click()');
      if (slug === 'hardware') {
        await wait('location.pathname.endsWith("/case-study") && !!document.querySelector("form button")');
        await evaluate('document.querySelector("form button").click()');
      }
      await wait('location.pathname.endsWith("/quiz") && !!(window.QUIZ_CONFIG || window.DEMO_MODULE_CONFIG)');
      if (slug === 'cyber') {
        await screenshot('cyber-quiz');
        for (const [id, answer] of Object.entries({1:'B',2:'A',3:'C',4:'D',5:'A',6:'B'})) {
          const revision = await evaluate('window.QUIZ_CONFIG.revision');
          await evaluate('document.querySelector(".q-nav-btn[data-question-id=\'' + id + '\']").click(); document.querySelector("input[name=question_' + id + '][value=' + answer + ']").click()');
          await wait('window.QUIZ_CONFIG.revision > ' + revision);
        }
        await evaluate('document.getElementById("btn-trigger-final-submit").click();document.getElementById("btn-modal-confirm-submit").click()');
      } else if (slug === 'networking') {
        for (const stage of [1, 2, 3]) {
          await wait('!!window.DEMO_MODULE_CONFIG && window.DEMO_MODULE_CONFIG.stage === ' + stage);
          await screenshot('networking-stage-' + stage);
          const answers = stage === 1 ? {1:'C',2:'A',3:'B'} : stage === 2 ? {4:'Benar',5:'Salah',6:'Benar',7:'Salah'} : {8:'DHCP',9:'DNS',10:'switch',11:'subnet mask',12:'gateway'};
          for (const [id, answer] of Object.entries(answers)) {
            const revision = await evaluate('window.DEMO_MODULE_CONFIG.revision');
            if (stage < 3) await evaluate('document.querySelector("input[name=question_' + id + '][value=' + answer + ']").click()');
            else await evaluate('document.querySelector("input[name=question_' + id + ']").value = ' + JSON.stringify(answer) + ';document.querySelector("input[name=question_' + id + ']").dispatchEvent(new Event("input",{bubbles:true}))');
            await wait('window.DEMO_MODULE_CONFIG.revision > ' + revision);
          }
          await evaluate('document.getElementById("module-submit").click()');
          if (stage < 3) {
            await wait('location.pathname.endsWith("/advance") && !!document.querySelector("form[action$=\'/begin-stage\']")');
            await screenshot('networking-transition-' + stage);
            await evaluate('document.querySelector("form[action$=\'/begin-stage\'] button").click()');
          }
        }
      } else {
        await screenshot('hardware-build');
        await evaluate('document.querySelectorAll("select[name^=component_]").forEach(select=>{select.selectedIndex=1;select.dispatchEvent(new Event("change",{bubbles:true}));});document.getElementById("rationale").value="Komponen sesuai budget dan target kelas";document.getElementById("rationale").dispatchEvent(new Event("input",{bubbles:true}));');
        await evaluate('document.getElementById("module-submit").scrollIntoView({block:"center"})');
        await screenshot('hardware-components');
        await evaluate('document.getElementById("module-submit").click()');
      }
      await wait('location.pathname.endsWith("/result") && document.body.textContent.includes("Hasil Mode Demo")');
      await screenshot(slug + '-result');
      assert(await evaluate('document.body.textContent.includes("60.0")') || slug !== 'cyber');
      if (slug === 'networking') assert(await evaluate('document.body.textContent.includes("Stempel Latihan diperoleh")'));
      if (slug === 'hardware') assert(await evaluate('document.body.textContent.includes("830")'));
      console.log(label + ': ' + slug + ' full flow and viewport passed');
    }
    if (label === 'desktop') {
      await cmd('Page.navigate', {url: base + '/admin/login'});
      await wait('!!document.getElementById("username")');
      await evaluate('document.getElementById("username").value="guide-admin";document.getElementById("password").value="guide-test-password";document.querySelector("form").requestSubmit()');
      await wait('location.pathname === "/admin/station-select"');
      await cmd('Page.navigate', {url: base + '/admin/access-settings'});
      await wait('!!document.getElementById("public-mode")');
      await screenshot('admin-access');
      await evaluate('document.getElementById("public-mode").value="DEMO_ONLY";document.getElementById("public-mode").form.requestSubmit()');
      await wait('document.getElementById("public-mode").value === "DEMO_ONLY"');
      await screenshot('admin-demo-only');
    }
    await cdp('Target.disposeBrowserContext', {browserContextId});
  }
  await cdp('Browser.close');
}
run().catch(error => {console.error(error); process.exitCode = 1;}).finally(() => {
  if (socket) socket.close();
  child.kill();
});
