/* Run with: node verify_ui_illustrations.js */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/js/ui_illustrations.js', 'utf8');

class TestNode {
  constructor(tag, text = '') {
    this.tag = tag; this.nodeType = tag === '#text' ? 3 : 1;
    this.nodeValue = text; this.children = []; this.attributes = {};
    this.classList = {contains: name => (this.attributes.class || '').split(' ').includes(name)};
  }
  setAttribute(key, value) {this.attributes[key] = value;}
  append(...nodes) {
    for (const node of nodes) {
      if (node.tag === '#fragment') this.append(...node.children);
      else {node.parentElement = this; this.children.push(node);}
    }
  }
  closest() {
    let node = this;
    while (node) {
      if (['script','style','textarea','select','input','pre','code','svg'].includes(node.tag) ||
          node.classList.contains('landing-body') || node.attributes.contenteditable !== undefined) return node;
      node = node.parentElement;
    }
    return null;
  }
  replaceWith(fragment) {
    const parent = this.parentElement;
    const index = parent.children.indexOf(this);
    parent.children.splice(index, 1, ...fragment.children);
    fragment.children.forEach(node => {node.parentElement = parent;});
  }
}

function harness(landing = false) {
  const body = new TestNode('body');
  if (landing) body.setAttribute('class', 'landing-body');
  const node = new TestNode('span');
  node.append(new TestNode('#text', '\u{1F6E0}\uFE0F Verifikasi \u{1F3C6}'));
  body.append(node);
  const editor = new TestNode('textarea');
  editor.append(new TestNode('#text', '\u{1F4BB} jawaban peserta'));
  body.append(editor);
  const unsafe = new TestNode('script');
  unsafe.append(new TestNode('#text', "const status = '\u26A0\uFE0F';"));
  body.append(unsafe);
  let observer;
  const context = {
    Node: {TEXT_NODE:3, ELEMENT_NODE:1}, NodeFilter:{SHOW_TEXT:4},
    MutationObserver: class {constructor(fn) {observer = fn;} disconnect() {} observe() {}},
    document: {
      body, readyState:'complete',
      createElementNS: (_, tag) => new TestNode(tag),
      createTextNode: text => new TestNode('#text', text),
      createDocumentFragment: () => new TestNode('#fragment'),
      createTreeWalker: root => {
        const list = [];
        const collect = node => node.children.forEach(child => child.nodeType === 3 ? list.push(child) : collect(child));
        collect(root);
        let index = 0;
        return {nextNode() {this.currentNode = list[index++]; return Boolean(this.currentNode);}};
      }
    }
  };
  vm.runInNewContext(source, context);
  return {body, node, editor, unsafe, update:records => observer(records)};
}

const live = harness();
assert.equal(live.node.children.filter(n => n.tag === 'svg').length, 2);
assert.equal(live.node.children[0].attributes.class, 'ui-illustration ui-illustration-tools');
assert.equal(live.node.children[2].attributes.class, 'ui-illustration ui-illustration-trophy');
assert.equal(live.node.children[1].nodeValue, ' Verifikasi ');
assert.equal(live.editor.children[0].nodeValue, '\u{1F4BB} jawaban peserta');
assert.equal(live.unsafe.children[0].nodeValue, "const status = '\u26A0\uFE0F';");
const updated = new TestNode('#text', '\u26A0\uFE0F Gagal Simpan');
live.node.children = []; live.node.append(updated);
live.update([{type:'characterData', target:updated}]);
assert.equal(live.node.children[0].attributes.class, 'ui-illustration ui-illustration-warning');
assert.equal(live.node.children[1].nodeValue, ' Gagal Simpan');
const added = new TestNode('span'); added.append(new TestNode('#text', '\u{1F512} Terkunci'));
live.body.append(added);
live.update([{type:'childList', addedNodes:[added]}]);
assert.equal(added.children[0].attributes.class, 'ui-illustration ui-illustration-lock');
const landing = harness(true);
assert.equal(landing.node.children.length, 1);
assert.equal(landing.node.children[0].nodeValue, '\u{1F6E0}\uFE0F Verifikasi \u{1F3C6}');

// Every symbol currently used by interface templates and scripts must have a drawing.
const covered = new Set([...source.matchAll(/0x([0-9a-f]+):'/g)].map(m => parseInt(m[1], 16)));
function audit(directory) {
  for (const entry of fs.readdirSync(directory, {withFileTypes:true})) {
    const file = directory + '/' + entry.name;
    if (entry.isDirectory()) audit(file);
    else if (/\.(html|js|py)$/.test(file) && entry.name !== 'landing.html') {
      for (const char of fs.readFileSync(file, 'utf8')) {
        const code = char.codePointAt(0);
        if ((code >= 0x1f000 && code <= 0x1faff) || (code >= 0x2600 && code <= 0x27bf)) {
          assert(covered.has(code), `Missing illustration for U+${code.toString(16)} in ${file}`);
        }
      }
    }
  }
}
['templates','static/js','routes'].forEach(audit);
console.log('PASS: illustration coverage, static text, live updates, editor safety, and landing exclusion');
