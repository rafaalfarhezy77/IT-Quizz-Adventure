(function(root){
  'use strict';
  const TTL=86400000;
  const key=slug=>'itquest:github-pages:'+slug+':attempt:v1';
  const round=value=>Math.round((value+Number.EPSILON)*100)/100;
  const normalize=value=>String(value||'').trim().toLowerCase().replace(/\s+/g,' ');
  function create(pack,now,id){return {schema:1,version:pack.version,id,start:now,deadline:now+pack.duration*1000,expires:now+TTL,status:'RUNNING',phase:pack.caseText?'case':'quiz',seen:!pack.caseText,answers:{},active:0,revision:0,finished:null,result:null,stage:1,stageStart:now,stageDeadline:pack.stageSeconds?now+pack.stageSeconds[0]*1000:null,components:{},rationale:''};}
  function matches(q,value){return [q.key,...(q.accepted||[])].some(key=>normalize(key)===normalize(value));}
  function hardware(pack,state,remaining){
    const items=Object.fromEntries(Object.entries(pack.catalogue).map(([cat,list])=>[cat,list.find(item=>item.id===state.components[cat])||{}]));
    const price=Object.values(items).reduce((sum,item)=>sum+(item.price||0),0), power=(items.cpu.watts||0)+(items.gpu.watts||0)+100;
    const checks={socket:!!items.cpu.id&&!!items.motherboard.id&&items.cpu.socket===items.motherboard.socket,ram:!!items.ram.id&&!!items.motherboard.id&&items.ram.ram===items.motherboard.ram,psu:!!items.psu.id&&items.psu.watts>=power};
    const compatibility=Object.values(items).every(item=>item.id)&&Object.values(checks).every(Boolean)?20:0;
    const budget=price>0&&price<=pack.rules.budget?15:0;
    const cpu=round(Math.min(1,(items.cpu.score||0)/pack.rules.cpu)*15),gpu=round(Math.min(1,(items.gpu.score||0)/pack.rules.gpu)*20);
    const completeness=round([items.cpu.id,items.gpu.id,items.ram.capacity>0,items.storage.capacity>0,items.psu.id].filter(Boolean).length/5*10);
    const efficiency=price>0?Math.min(15,round(((items.cpu.score||0)+(items.gpu.score||0))/price/pack.rules.efficiency*15)):0;
    const breakdown={compatibility,budget,cpu,gpu,completeness,efficiency};const raw=round(Object.values(breakdown).reduce((sum,v)=>sum+v,0));
    const bonus=round(Math.min(1,remaining/pack.duration)*5);
    return {raw,bonus,total:Math.min(100,round(raw+bonus)),breakdown,checks,price,power,items};
  }
  function score(state,pack){
    const remaining=state.status==='TIMED_OUT'?0:Math.max(0,Math.floor((state.deadline-state.finished)/1000));
    if(pack.method==='hardware')return hardware(pack,state,remaining);
    const correct=pack.questions.filter(q=>matches(q,state.answers[q.id])),raw=correct.reduce((sum,q)=>sum+q.weight,0),bonus=remaining*pack.bonusPerSecond;
    const stages=pack.method==='networking'?Object.fromEntries([1,2,3].map(stage=>[stage,correct.filter(q=>q.stage===stage).reduce((sum,q)=>sum+q.weight,0)])):null;
    const stage3=correct.filter(q=>q.stage===3).length;
    return {correct:correct.length,answered:Object.values(state.answers).filter(Boolean).length,raw,bonus,total:raw+bonus,stages,stage3,stamp:stage3>=4};
  }
  function finish(state,pack,now,timeout=false){if(state.status!=='RUNNING')return false;state.status=timeout||now>=state.deadline?'TIMED_OUT':'SUBMITTED';state.finished=state.status==='TIMED_OUT'?Math.min(state.deadline,pack.method==='networking'&&state.stage===3?state.stageDeadline:state.deadline):Math.max(state.start,now);state.phase='result';state.result=score(state,pack);state.revision++;return true;}
  function expire(state,pack,now){
    if(state.status!=='RUNNING')return false;
    if(now>=state.deadline){finish(state,pack,now,true);return true;}
    if(pack.method==='networking'&&state.phase==='quiz'&&now>=state.stageDeadline){
      if(state.stage===3)finish(state,pack,now,true);else {state.phase='transition';state.revision++;}return true;
    }return false;
  }
  function activeQuestions(state,pack){return pack.method==='networking'?pack.questions.filter(q=>q.stage===state.stage):pack.questions;}
  function answer(state,pack,id,value){
    if(state.status!=='RUNNING'||state.phase!=='quiz')return false;
    const items=activeQuestions(state,pack),q=items.find(q=>q.id===id);if(!q)return false;
    if(pack.method==='networking'&&state.stage<3){if(state.answers[id]||items.find(q=>!state.answers[q.id])?.id!==id)return false;}
    if(q.options.length&&!q.options['ABCDE'.indexOf(value)])return false;
    if(typeof value!=='string'||value.length>255)return false;
    state.answers[id]=value;state.revision++;return true;
  }
  function nextStage(state,pack,now){if(state.status!=='RUNNING'||state.phase!=='transition'||state.stage>=3||now>=state.deadline)return false;state.stage++;state.stageStart=now;state.stageDeadline=Math.min(state.deadline,now+pack.stageSeconds[state.stage-1]*1000);state.phase='quiz';state.active=0;state.revision++;return true;}
  function build(state,pack,category,id){if(state.status!=='RUNNING'||state.phase!=='quiz'||!pack.catalogue[category]||(id&&!pack.catalogue[category].some(item=>item.id===id)))return false;if(id)state.components[category]=id;else delete state.components[category];state.revision++;return true;}
  function decode(raw,pack,now){
    if(raw===null)return {state:null,error:null};
    try{
      if(raw.length>20000)throw Error('Data latihan terlalu besar.');const s=JSON.parse(raw);
      if(!s||typeof s!=='object'||Array.isArray(s))throw Error('Data latihan rusak.');
      if(s.schema!==1||s.version!==pack.version)throw Error('Versi latihan telah diperbarui. Mulai percobaan baru.');
      if(!/^pages_[a-zA-Z0-9_-]{8,100}$/.test(s.id))throw Error('Identitas latihan tidak valid.');
      if(![s.start,s.deadline,s.expires].every(Number.isSafeInteger)||s.deadline!==s.start+pack.duration*1000||s.expires!==s.start+TTL||s.start>now+60000)throw Error('Waktu latihan tidak valid.');
      if(now>=s.expires)throw Error('Latihan kedaluwarsa setelah 24 jam.');
      if(!['RUNNING','SUBMITTED','TIMED_OUT'].includes(s.status)||!['case','quiz','transition','result'].includes(s.phase)||!Number.isSafeInteger(s.revision)||s.revision<0||typeof s.seen!=='boolean'||!Number.isInteger(s.active)||s.active<0||s.active>=Math.max(1,pack.questions.length))throw Error('Progres latihan tidak valid.');
      if(!s.answers||typeof s.answers!=='object'||Array.isArray(s.answers))throw Error('Jawaban latihan rusak.');
      for(const [id,value] of Object.entries(s.answers)){const q=pack.questions.find(q=>String(q.id)===id);if(!q||typeof value!=='string'||value.length>255||(q.options.length&&!q.options['ABCDE'.indexOf(value)]))throw Error('Jawaban latihan tidak valid.');}
      if(pack.method==='networking'){
        if(!Number.isInteger(s.stage)||s.stage<1||s.stage>3||!Number.isSafeInteger(s.stageStart)||!Number.isSafeInteger(s.stageDeadline)||s.stageStart<s.start||s.stageStart>=s.deadline||s.stageDeadline!==Math.min(s.deadline,s.stageStart+pack.stageSeconds[s.stage-1]*1000)||Object.keys(s.answers).some(id=>pack.questions.find(q=>String(q.id)===id).stage>s.stage))throw Error('Tahap latihan tidak valid.');
        if(s.phase==='case'||(s.phase==='transition'&&s.stage===3))throw Error('Transisi latihan tidak valid.');
      }else if(s.phase==='transition'||(!pack.caseText&&s.phase==='case'))throw Error('Halaman latihan tidak valid.');
      if(pack.method==='hardware'){
        if(!s.components||typeof s.components!=='object'||Array.isArray(s.components)||typeof s.rationale!=='string'||s.rationale.length>1000||Object.entries(s.components).some(([cat,id])=>!pack.catalogue[cat]?.some(item=>item.id===id)))throw Error('Rakitan latihan tidak valid.');
      }
      if(s.status==='RUNNING'){if(s.phase==='result'||s.finished!==null||s.result!==null)throw Error('Status latihan tidak valid.');}
      else {if(s.phase!=='result'||!Number.isSafeInteger(s.finished)||s.finished<s.start||s.finished>s.deadline)throw Error('Hasil latihan tidak valid.');s.result=score(s,pack);}
      return {state:s,error:null};
    }catch(error){return {state:null,error:error instanceof SyntaxError?'Data latihan tidak dapat dibaca. Mulai percobaan baru.':error.message};}
  }
  const methods={key,TTL,create,decode,score,hardware,matches,expire,finish,activeQuestions,answer,nextStage,build};root.DemoMethods=methods;
  if(typeof module!=='undefined')module.exports=methods;
}(globalThis));
