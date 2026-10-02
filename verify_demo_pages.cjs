/* Real Chromium checks; Node 22+. Served only by Python's static HTTP server. */
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const [browser, profile, base] = process.argv.slice(2);
const output = 'scratch/demo-pages-browser';
fs.mkdirSync(output,{recursive:true});
const child = spawn(browser,['--headless=new','--remote-debugging-port=0','--no-first-run','--no-default-browser-check','--disable-background-networking','--user-data-dir='+profile,'about:blank'],{windowsHide:true});
const delay = ms => new Promise(resolve=>setTimeout(resolve,ms));
let socket,seq=0; const pending=new Map(); const requests=[],errors=[];
async function run() {
  const address=await new Promise((resolve,reject)=>{
    let log=''; const timeout=setTimeout(()=>reject(new Error('Browser startup timeout')),20000);
    child.stderr.on('data',data=>{log+=data; const match=log.match(/DevTools listening on (ws:\/\/[^\s]+)/);if(match){clearTimeout(timeout);resolve(match[1]);}});
    child.on('error',reject);
  });
  socket=new WebSocket(address); await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
  socket.onmessage=event=>{
    const msg=JSON.parse(event.data);
    if(msg.method==='Network.requestWillBeSent') requests.push(msg.params.request.url);
    if(msg.method==='Runtime.exceptionThrown') errors.push(msg.params.exceptionDetails);
    if(msg.method==='Network.responseReceived' && msg.params.response.status>=400) errors.push(msg.params.response);
    const waiter=pending.get(msg.id);if(!waiter)return;pending.delete(msg.id);
    msg.error?waiter.reject(new Error(JSON.stringify(msg.error))):waiter.resolve(msg.result);
  };
  function cdp(method,params={},sessionId){return new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));});}
  async function tab(context,width=1366,height=900){
    const {targetId}=await cdp('Target.createTarget',{url:'about:blank',browserContextId:context});
    const {sessionId}=await cdp('Target.attachToTarget',{targetId,flatten:true});
    const cmd=(method,params)=>cdp(method,params,sessionId);
    await cmd('Page.enable');await cmd('Network.enable');await cmd('Runtime.enable');
    await cmd('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<600});
    const evaluate=async expression=>{const result=await cmd('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
    const wait=async expression=>{for(let i=0;i<100;i++){try{if(await evaluate(`document.readyState === 'complete' && (${expression})`))return;}catch(_){}await delay(75);}throw new Error('Timed out '+expression);};
    const navigate=async hash=>{await cmd('Page.navigate',{url:base+hash});await wait('!!window.DemoEngine && !!document.querySelector("#app h1")');};
    const click=async selector=>{await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);await delay(60);};
    const state=()=>evaluate('JSON.parse(localStorage.getItem(DemoEngine.STORAGE_KEY))');
    const screen=async name=>{
      const bounds=await evaluate('({viewport:innerWidth,width:document.documentElement.scrollWidth})');assert.ok(bounds.width<=bounds.viewport+1, name+' overflow '+JSON.stringify(bounds));
      const {data}=await cmd('Page.captureScreenshot',{format:'png'});fs.writeFileSync(output+'/'+name+'.png',Buffer.from(data,'base64'));
    };
    return {cmd,evaluate,wait,navigate,click,state,screen};
  }
  let firstContext,firstId;
  for(const [label,width,height] of [['desktop',1366,900],['mobile',390,844]]){
    const {browserContextId}=await cdp('Target.createBrowserContext');if(!firstContext)firstContext=browserContextId;
    const t=await tab(browserContextId,width,height);
    await t.navigate('#home');await delay(1600);await t.screen(label+'-home');
    await t.click('a[href="#stations"]');await t.wait('location.hash === "#stations"');await t.screen(label+'-stations');
    assert.equal(await t.evaluate('document.querySelectorAll(".unavailable button,.unavailable a").length'),0);
    await t.click('a[href="#software/rules"]');await t.wait('location.hash === "#software/rules"');await t.screen(label+'-rules');
    assert.equal(await t.state(),null);
    await t.click('[data-action="start"]');await t.click('[data-cancel]');assert.equal(await t.state(),null);
    await t.click('[data-action="start"]');await t.click('[data-confirm]');await t.wait('location.hash === "#case"');await t.screen(label+'-case');
    const initial=await t.state();if(label==='desktop')firstId=initial.id;else assert.notEqual(initial.id,firstId);
    assert.equal(initial.deadline-initial.start,240000);
    await t.click('[data-action="read"]');await t.wait('location.hash === "#quiz"');await t.screen(label+'-quiz');
    assert.equal(await t.evaluate('document.querySelectorAll(".correct,.incorrect").length'),0);
    if(label==='mobile') await t.cmd('Network.emulateNetworkConditions',{offline:true,latency:0,downloadThroughput:0,uploadThroughput:0});
    for(let member=1;member<=3;member++){
      for(let i=0;i<3;i++){
        await t.click(`[data-nav="${i}"]`);
        const id=(member-1)*3+i+1;const answer='ABCD'[(id-1)%4];
        await t.click(`input[value="${answer}"]`);
      }
      if(member===1){
        if(label==='mobile') await t.cmd('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
        await t.cmd('Page.reload');await t.wait('!!document.querySelector("[data-action=complete]")');
        assert.equal((await t.state()).deadline,initial.deadline);assert.equal(Object.keys((await t.state()).answers).length,3);
      }
      await t.click('[data-action="complete"]');await t.screen(label+'-confirm-'+member);await t.click('[data-confirm]');
      if(member<3){await t.wait('location.hash === "#transition"');await t.screen(label+'-transition-'+member);await t.click('[data-action="continue"]');await t.wait('location.hash === "#quiz"');}
    }
    await t.wait('location.hash === "#result"');await t.screen(label+'-result');
    const done=await t.state();assert.equal(done.result.raw,90);assert.equal(done.result.correct,9);assert.equal(done.status,'SUBMITTED');
    await t.cmd('Page.reload');await t.wait('!!document.querySelector(".correct")');assert.deepEqual(await t.state(),done);
    await t.navigate('#quiz');await t.wait('location.hash === "#result"');assert.deepEqual(await t.state(),done);
    await t.click('[data-action="start"]');await t.click('[data-cancel]');assert.equal((await t.state()).id,done.id);
    await t.click('[data-action="start"]');await t.click('[data-confirm]');await t.wait('location.hash === "#case"');assert.notEqual((await t.state()).id,done.id);assert.deepEqual((await t.state()).answers,{});
    // Valid expired-deadline record: refresh must finalize, never grant fresh time.
    await t.evaluate(`{const s=JSON.parse(localStorage.getItem(DemoEngine.STORAGE_KEY));s.start=Date.now()-241000;s.deadline=s.start+240000;s.expires=s.start+DemoEngine.TTL;localStorage.setItem(DemoEngine.STORAGE_KEY,JSON.stringify(s));}`);
    await t.cmd('Page.reload');await t.wait('location.hash === "#result"');assert.equal((await t.state()).status,'TIMED_OUT');assert.equal((await t.state()).result.bonus,0);
    await t.evaluate(`localStorage.setItem('unrelated-app-key','keep');localStorage.setItem(DemoEngine.STORAGE_KEY,'{broken');`);
    await t.cmd('Page.reload');await t.wait('location.hash === "#rules"');assert.equal(await t.state(),null);assert.equal(await t.evaluate('localStorage.getItem("unrelated-app-key")'),'keep');assert.match(await t.evaluate('document.querySelector(".notice").textContent'),/tidak dapat dibaca/);
    await t.click('[data-action="start"]');await t.click('[data-confirm]');await t.wait('location.hash === "#case"');
    await t.evaluate(`{const s=JSON.parse(localStorage.getItem(DemoEngine.STORAGE_KEY));s.version='obsolete';localStorage.setItem(DemoEngine.STORAGE_KEY,JSON.stringify(s));}`);
    await t.cmd('Page.reload');await t.wait('location.hash === "#rules"');assert.match(await t.evaluate('document.querySelector(".notice").textContent'),/Versi/);
    await t.navigate('#missing-route');await t.wait('location.hash === "#stations"');
    // All additional stations complete with independent keys and static assets.
    // Seed the exact legacy Software Engineering shape, without new fields.
    await t.evaluate(`localStorage.setItem(DemoEngine.STORAGE_KEY,JSON.stringify(DemoEngine.create(DemoPack,Date.now(),'pages_legacy_123456')));`);
    for(const slug of ['cyber','networking','hardware']){
      const savedSoftware=await t.state();
      await t.navigate('#'+slug+'/rules');await t.screen(label+'-'+slug+'-rules');
      if(slug==='hardware'){
        assert.equal(await t.evaluate('document.querySelector(".buildcores-guide").open'),true);
        assert.equal(await t.evaluate('document.querySelectorAll(".buildcores-guide ol li").length'),6);
        assert.equal(await t.evaluate(`document.querySelectorAll('.buildcores-guide a[target="_blank"][rel="noopener noreferrer"]').length`),4);
        assert.equal(await t.evaluate(`!!document.querySelector('.buildcores-guide a[href="https://www.youtube.com/watch?v=82eJ6YFSess"]')`),true);
        assert.equal(await t.evaluate('document.querySelectorAll("iframe,video").length'),0);
      }
      await t.click('[data-module-action="start"]');await t.click('[data-confirm]');
      const mstate=()=>t.evaluate(`JSON.parse(localStorage.getItem(DemoMethods.key('${slug}')))`);
      await t.wait(`location.hash === '#${slug}/${slug==='hardware'?'case':'quiz'}'`);
      const initial=await mstate();
      if(slug==='hardware'){await t.screen(label+'-hardware-case');await t.click('[data-module-action="read"]');await t.wait('location.hash === "#hardware/quiz"');}
      if(slug==='cyber'){
        for(let i=0;i<6;i++){await t.click(`[data-module-nav="${i}"]`);const choice=await t.evaluate(`DemoPacks.cyber.questions[${i}].key`);await t.click(`input[value="${choice}"]`);}
        await t.screen(label+'-cyber-quiz');await t.click('[data-module-action="complete"]');await t.click('[data-confirm]');
      }
      if(slug==='networking'){
        for(let stage=1;stage<=3;stage++){
          await t.screen(label+'-networking-stage-'+stage);
          if(stage<3){const questions=await t.evaluate(`DemoPacks.networking.questions.filter(q=>q.stage===${stage}).map(q=>({id:q.id,key:q.key}))`);for(const q of questions)await t.click(`input[data-module-question="${q.id}"][value="${q.key}"]`);}
          else await t.evaluate(`DemoPacks.networking.questions.filter(q=>q.stage===3).forEach(q=>{const input=document.querySelector('[data-short="'+q.id+'"]');input.value=q.id===11?'  Virtual   LAN  ':q.key;input.dispatchEvent(new Event('input',{bubbles:true}));});`);
          await t.cmd('Page.reload');await t.wait('!!document.querySelector("[data-module-action=complete]")');assert.equal((await mstate()).deadline,initial.deadline);
          await t.click('[data-module-action="complete"]');await t.click('[data-confirm]');
          if(stage<3){await t.wait('location.hash === "#networking/transition"');await t.screen(label+'-networking-transition-'+stage);await t.click('[data-module-action="continue"]');await t.wait('location.hash === "#networking/quiz"');}
        }
      }
      if(slug==='hardware'){
        await t.evaluate(`document.querySelectorAll('[data-component]').forEach(select=>{select.selectedIndex=1;select.dispatchEvent(new Event('change',{bubbles:true}));});const text=document.querySelector('#rationale');text.value='Socket S1, RAM DDR4 dan daya PSU mencukupi; memenuhi target studio.';text.dispatchEvent(new Event('input',{bubbles:true}));`);
        await t.screen(label+'-hardware-build');await t.cmd('Page.reload');await t.wait('!!document.querySelector("#rationale")');assert.equal((await mstate()).deadline,initial.deadline);assert.equal(Object.keys((await mstate()).components).length,6);
        await t.click('[data-module-action="complete"]');await t.click('[data-confirm]');
      }
      await t.wait(`location.hash === '#${slug}/result'`);await t.screen(label+'-'+slug+'-result');
      const result=await mstate();assert.equal(result.status,'SUBMITTED');assert.equal(result.result.raw,slug==='cyber'?60:slug==='networking'?100:95);if(slug==='networking')assert.equal(result.result.stamp,true);
      await t.cmd('Page.reload');await t.wait('!!document.querySelector("[data-module-action=start]")');assert.deepEqual(await mstate(),result);
      assert.deepEqual(await t.state(),savedSoftware,'Other pos must not alter software progress');
      await t.click('[data-module-action="start"]');await t.click('[data-cancel]');assert.equal((await mstate()).id,result.id);
      await t.click('[data-module-action="start"]');await t.click('[data-confirm]');await t.wait(`location.hash === '#${slug}/${slug==='hardware'?'case':'quiz'}'`);assert.notEqual((await mstate()).id,result.id);
      await t.evaluate(`{const key=DemoMethods.key('${slug}'),s=JSON.parse(localStorage.getItem(key));s.start=Date.now()-DemoPacks.${slug}.duration*1000-1000;s.deadline=s.start+DemoPacks.${slug}.duration*1000;s.expires=s.start+DemoMethods.TTL;s.stageStart=s.start;s.stageDeadline=DemoPacks.${slug}.stageSeconds?s.start+90000:null;localStorage.setItem(key,JSON.stringify(s));}`);
      await t.cmd('Page.reload');await t.wait(`location.hash === '#${slug}/result'`);assert.equal((await mstate()).status,'TIMED_OUT');assert.equal((await mstate()).result.bonus,0);
      await t.evaluate(`localStorage.setItem(DemoMethods.key('${slug}'),'{broken');`);await t.cmd('Page.reload');await t.wait(`location.hash === '#${slug}/rules'`);assert.equal(await mstate(),null);
      await t.click('[data-module-action="start"]');await t.click('[data-confirm]');await t.wait(`location.hash === '#${slug}/${slug==='hardware'?'case':'quiz'}'`);
      await t.evaluate(`{const key=DemoMethods.key('${slug}'),s=JSON.parse(localStorage.getItem(key));s.version='old';localStorage.setItem(key,JSON.stringify(s));}`);await t.cmd('Page.reload');await t.wait(`location.hash === '#${slug}/rules'`);assert.equal(await mstate(),null);
      // Restore the completed result to prove later positions preserve it too.
      await t.evaluate(`localStorage.setItem(DemoMethods.key('${slug}'),${JSON.stringify(JSON.stringify(result))});`);
      if(slug!=='cyber')assert.equal(await t.evaluate(`JSON.parse(localStorage.getItem(DemoMethods.key('cyber'))).result.raw`),60);
    }
    console.log(label+': all four stations, refresh, offline, lock, retry, timeout, corrupt storage and version handling PASS');
  }
  // Two tabs in the same browser synchronize saved progress.
  const a=await tab(firstContext),b=await tab(firstContext);
  await a.navigate('#rules');await a.click('[data-action="start"]');await a.click('[data-confirm]');await a.wait('location.hash === "#case"');await a.click('[data-action="read"]');await a.wait('location.hash === "#quiz"');
  await b.navigate('#quiz');await a.click('input[value="A"]');await b.wait('!!document.querySelector("input[value=A]:checked")');
  assert.deepEqual((await a.state()).answers,(await b.state()).answers);
  await a.navigate('#cyber/rules');await a.click('[data-module-action="start"]');await a.click('[data-confirm]');await a.wait('location.hash === "#cyber/quiz"');
  await b.navigate('#cyber/quiz');await a.click('input[value="B"]');await b.wait('!!document.querySelector("input[value=B]:checked")');
  assert.equal(await b.evaluate('JSON.parse(localStorage.getItem(DemoMethods.key("cyber"))).answers[1]'),'B');
  // A live stage timer opens transition, where refresh must retain its deadline.
  await a.navigate('#networking/rules');await a.click('[data-module-action="start"]');await a.click('[data-confirm]');await a.wait('location.hash === "#networking/quiz"');
  await a.evaluate('window.realNow=Date.now;window.timeOffset=91000;Date.now=()=>realNow()+timeOffset;');await a.wait('location.hash === "#networking/transition"');
  const deadline=await a.evaluate('JSON.parse(localStorage.getItem(DemoMethods.key("networking"))).deadline');
  await a.cmd('Page.reload');await a.wait('location.hash === "#networking/transition"');assert.equal(await a.evaluate('JSON.parse(localStorage.getItem(DemoMethods.key("networking"))).deadline'),deadline);
  // Storage-denied browsers get a clear in-memory fallback, without JS crashes.
  const {browserContextId}=await cdp('Target.createBrowserContext');const denied=await tab(browserContextId);
  await denied.cmd('Page.addScriptToEvaluateOnNewDocument',{source:`Storage.prototype.getItem=function(){throw new DOMException('denied','SecurityError');};Storage.prototype.setItem=function(){throw new DOMException('denied','SecurityError');};`});
  await denied.navigate('#rules');assert.match(await denied.evaluate('document.querySelector(".notice").textContent'),/tidak tersedia/);
  await denied.click('[data-action="start"]');await denied.click('[data-confirm]');await denied.wait('location.hash === "#case"');await denied.click('[data-action="read"]');await denied.click('input[value="A"]');assert.equal(await denied.evaluate('!!document.querySelector("input[value=A]:checked")'),true);
  await denied.navigate('#cyber/rules');await denied.click('[data-module-action="start"]');await denied.click('[data-confirm]');await denied.wait('location.hash === "#cyber/quiz"');await denied.click('input[value="B"]');assert.equal(await denied.evaluate('!!document.querySelector("input[value=B]:checked")'),true);assert.match(await denied.evaluate('document.querySelector(".notice").textContent'),/tidak tersedia/);
  assert.deepEqual(errors,[],'No JavaScript errors or HTTP errors');
  assert.ok(requests.length>0);assert.ok(requests.every(url=>url==='about:blank'||url.startsWith('data:')||url.startsWith(base)), 'All page requests are local static assets under repository subfolder');
  assert.ok(requests.every(url=>!url.includes('/api/')&&!url.includes('/participant/')));
  console.log('Two-tab synchronization, storage fallback, relative assets, no backend requests PASS');
}
run().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>{if(socket)socket.close();child.kill();});
