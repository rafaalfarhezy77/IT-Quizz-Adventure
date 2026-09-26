const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const template=fs.readFileSync('templates/admin/networking/question_form.html','utf8');
const code=[...template.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];
function makeElement(value=''){
 return {value,hidden:false,disabled:false,listeners:{},addEventListener(event,fn){this.listeners[event]=fn;},replaceChildren(...options){this.options=options;}};
}
function load(stage='1',key='E'){
 const elements={};
 for(const name of ['stage','question_type','weight','order_number','correct_answer','networking-key-choice','networking-text-key','networking-options','networking-variants','networking-number-help','networking-key-help'])elements[name]=makeElement();
 Object.assign(elements.stage,{value:stage});elements.correct_answer.value=key;elements['networking-text-key'].value=key;elements.order_number.value={1:'1',2:'11',3:'21'}[stage];
 const options=Array.from({length:5},()=>makeElement('option'));
 vm.runInNewContext(code,{document:{getElementById:id=>elements[id],querySelectorAll:()=>options,createElement:()=>makeElement()}});
 return {elements,options};
}
const {elements,options}=load();
assert.equal(elements.question_type.value,'multiple_choice');assert.equal(elements.weight.value,3);
assert.deepEqual(elements['networking-key-choice'].options.map(o=>o.value),['A','B','C','D','E']);
assert.equal(elements.correct_answer.value,'E');assert.equal(elements['networking-options'].hidden,false);
elements.stage.value='2';elements.stage.listeners.change();
assert.equal(elements.question_type.value,'true_false');assert.equal(elements.weight.value,4);
assert.equal(elements.order_number.value,11);assert.equal(elements['networking-options'].hidden,true);
assert.equal(options.every(option=>option.disabled),true);
assert.deepEqual(elements['networking-key-choice'].options.map(o=>o.value),['Benar','Salah']);
elements['networking-text-key'].value='PAN';elements.stage.value='3';elements.stage.listeners.change();
assert.equal(elements.question_type.value,'short_text');assert.equal(elements.weight.value,6);
assert.equal(elements.order_number.value,21);assert.equal(elements['networking-key-choice'].hidden,true);
assert.equal(elements['networking-text-key'].hidden,false);assert.equal(elements['networking-variants'].hidden,false);
assert.equal(elements.correct_answer.value,'PAN');
assert.equal(load('2','False').elements.correct_answer.value,'Salah');
assert.equal(load('2','True').elements.correct_answer.value,'Benar');
console.log('Networking editor: stage-specific fields, A–E/Benar-Salah/text keys, weights, ranges, and legacy keys passed.');
