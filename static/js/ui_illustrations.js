/* Local vector illustrations for static and live interface text. */
(() => {
  'use strict';
  const drawings = {
    warning: '<path d="m12 3 10 18H2Z"/><path d="M12 9v5m0 3v.1"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    arrow: '<path d="M3 12h18m-7-7 7 7-7 7"/>',
    globe: '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
    tools: '<path d="m14 6 4 4 4-4a6 6 0 0 1-8 8l-7 7-4-4 7-7a6 6 0 0 1 8-8Z"/>',
    network: '<path d="M8 5a6 6 0 0 1 11 6M6 2a10 10 0 0 1 16 11M9 12l3-3 3 3-3 3Z"/><path d="m10 14-4 7H2l5-10m-1 6h8l3 4"/>',
    computer: '<rect x="3" y="3" width="18" height="13" rx="1"/><path d="M8 21h8m-4-5v5M3 12h18"/>',
    shield: '<path d="m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6Z"/><path d="m8 12 3 3 5-6"/>',
    edit: '<path d="m16 3 5 5-12 12-6 1 1-6ZM13 6l5 5"/>',
    map: '<path d="m2 5 7-3 6 3 7-3v17l-7 3-6-3-7 3ZM9 2v17m6-14v17"/>',
    bolt: '<path d="m14 2-10 12h7l-1 8 10-12h-7Z"/>',
    search: '<circle cx="10" cy="10" r="7"/><path d="m15 15 7 7"/>',
    trophy: '<path d="M7 3h10v7a5 5 0 0 1-10 0ZM7 5H3v3a4 4 0 0 0 4 4m10-7h4v3a4 4 0 0 1-4 4m-5 3v5m-5 2h10"/>',
    star: '<path d="m12 2 3 6 7 1-5 5 1 8-6-4-6 4 1-8-5-5 7-1Z"/>',
    teams: '<circle cx="9" cy="7" r="4"/><path d="M2 21v-3a7 7 0 0 1 14 0v3M17 4a4 4 0 0 1 0 8m2 3a5 5 0 0 1 3 5"/>',
    clipboard: '<rect x="5" y="4" width="14" height="18" rx="1"/><rect x="9" y="2" width="6" height="4" rx="1"/><path d="M9 11h6m-6 5h6"/>',
    download: '<path d="M12 2v13m-5-5 5 5 5-5M3 16v5h18v-5"/>',
    medal: '<path d="m5 2 5 10m9-10-5 10M5 2h5l7 12M19 2h-5l-3 6"/><circle cx="12" cy="17" r="5"/>',
    lock: '<rect x="4" y="10" width="16" height="12" rx="2"/><path d="M7 10V7a5 5 0 0 1 10 0v3m-5 5v3"/>',
    refresh: '<path d="M20 8a9 9 0 0 0-16-2M4 16a9 9 0 0 0 16 2M20 2v6h-6M4 22v-6h6"/>',
    settings: '<path d="m9 3 1-1h4l1 3 3 1 3-1 2 4-2 2v3l2 2-2 4-3-1-3 1-1 3h-4l-1-3-3-1-3 1-2-4 2-2v-3L1 9l2-4 3 1 3-1Z"/><circle cx="12" cy="12" r="3"/>',
    pin: '<path d="m8 2 8 0-1 7 4 5H5l4-5ZM12 14v8"/>',
    save: '<path d="M3 2h15l3 3v17H3ZM7 2v7h9V2M7 22v-8h10v8"/>',
    rocket: '<path d="M9 15C9 6 15 2 22 2c0 7-4 13-13 13ZM9 7H5l-3 7h7m8 1v4l-7 3v-7m-3 3-4 3"/><circle cx="16" cy="8" r="2"/>',
    school: '<path d="m2 10 10-8 10 8M4 9v13h16V9M9 22v-7h6v7M8 10h1m6 0h1"/>',
    idea: '<path d="M8 16a7 7 0 1 1 8 0v3H8Zm1 6h6M12 3v2M5 6l2 2m12-2-2 2"/>',
    book: '<path d="M12 5C8 2 4 2 2 3v17c3-1 7 0 10 2 3-2 7-3 10-2V3c-2-1-6-1-10 2ZM12 5v17"/>',
    handshake: '<path d="m2 10 4-6 6 3 6-3 4 6-4 4-5 6-3-1-3-3-5-6Zm5 6 4-4m-1 7 4-4m-2-8-3 4 3 2 3-3 5 5"/>',
    document: '<path d="M5 2h10l5 5v15H5ZM15 2v5h5M9 12h7m-7 4h7"/>',
    megaphone: '<path d="m3 9 18-6v18L3 15ZM3 9v6m4 1 2 6h4l-2-5M17 5v14"/>',
    blocked: '<circle cx="12" cy="12" r="9"/><path d="m6 6 12 12"/>',
    game: '<path d="M7 7h10c4 0 6 11 3 13l-5-4H9l-5 4C1 18 3 7 7 7ZM6 12h5m-2-2v5m7-3h.1m3 2h.1"/>',
    crown: '<path d="m2 5 5 5 5-8 5 8 5-5-3 15H5ZM5 16h14"/>',
    link: '<path d="m9 15 6-6m-5-2 3-3a5 5 0 0 1 7 7l-3 3m-3 3-3 3a5 5 0 0 1-7-7l3-3"/>',
    chart: '<path d="M3 2v20h19M7 18v-5h3v5m3 0V9h3v9m3 0V5h3v13"/>',
    scroll: '<path d="M6 3h14v15a3 3 0 0 1-6 0H3v2a3 3 0 0 0 3 3h11M6 3a3 3 0 0 0-3 3v3h3V3m4 5h6m-6 4h6"/>',
    flag: '<path d="M4 22V2h16v12H4M9 2v12m6-12v12M4 8h16"/>',
    target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    folder: '<path d="M2 5h8l2 3h10v13H2Z"/>',
    mailbox: '<path d="M3 11h18v10H3ZM3 11l3-8h12l3 8M3 14h5l2 3h4l2-3h5"/>',
    eye: '<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12Z"/><circle cx="12" cy="12" r="3"/>',
    trash: '<path d="M3 6h18M9 6V2h6v4M5 6l1 16h12l1-16M10 10v8m4-8v8"/>',
    package: '<path d="m12 2 10 5v10l-10 5-10-5V7ZM2 7l10 5 10-5M12 12v10M7 4l10 5"/>',
    balance: '<path d="M12 2v20M6 22h12M3 6h18M6 6l-4 9h8Zm12 0-4 9h8ZM2 15a4 4 0 0 0 8 0m4 0a4 4 0 0 0 8 0"/>',
    spark: '<path d="m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3Z"/>'
  };
  const names = {
    0x2605:'star', 0x2696:'balance', 0x2699:'settings', 0x26a0:'warning', 0x26a1:'bolt',
    0x2705:'check', 0x270e:'edit', 0x270f:'edit', 0x2713:'check', 0x2714:'check',
    0x2715:'close', 0x2716:'close', 0x2717:'close', 0x2726:'spark', 0x2794:'arrow',
    0x1f3ae:'game', 0x1f3af:'target', 0x1f3c1:'flag', 0x1f3c6:'trophy', 0x1f4d6:'book',
    0x1f3eb:'school', 0x1f310:'globe', 0x1f441:'eye', 0x1f451:'crown', 0x1f465:'teams',
    0x1f4a1:'idea', 0x1f4bb:'computer', 0x1f4be:'save', 0x1f4c1:'folder', 0x1f4c2:'folder',
    0x1f4c4:'document', 0x1f4ca:'chart', 0x1f4cb:'clipboard', 0x1f4cc:'pin', 0x1f4dc:'scroll',
    0x1f4dd:'edit', 0x1f4e2:'megaphone', 0x1f4e5:'download', 0x1f4ed:'mailbox', 0x1f4e1:'network',
    0x1f50d:'search', 0x1f512:'lock', 0x1f504:'refresh', 0x1f517:'link', 0x1f5d1:'trash',
    0x1f5fa:'map', 0x1f6ab:'blocked', 0x1f6e0:'tools', 0x1f6e1:'shield', 0x1f680:'rocket',
    0x1f91d:'handshake', 0x1f948:'medal', 0x1f949:'medal', 0x1f396:'medal', 0x1f4e6:'package'
  };
  const symbols = Object.keys(names).map(code => String.fromCodePoint(Number(code)));
  const pattern = new RegExp('[' + symbols.join('') + '][\\uFE0E\\uFE0F]?', 'gu');
  const excluded = 'script, style, textarea, select, input, pre, code, svg, [contenteditable], .landing-body';
  const namespace = 'http://www.w3.org/2000/svg';

  function illustration(character) {
    const name = names[character.codePointAt(0)];
    const svg = document.createElementNS(namespace, 'svg');
    svg.setAttribute('class', 'ui-illustration ui-illustration-' + name);
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '1.8');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    svg.innerHTML = drawings[name];
    return svg;
  }

  function replaceText(node) {
    if (!node.parentElement || node.parentElement.closest(excluded)) return;
    const value = node.nodeValue;
    const matches = [...value.matchAll(pattern)];
    if (!matches.length) return;
    const fragment = document.createDocumentFragment();
    let cursor = 0;
    for (const match of matches) {
      if (match.index > cursor) fragment.append(document.createTextNode(value.slice(cursor, match.index)));
      fragment.append(illustration(match[0]));
      cursor = match.index + match[0].length;
    }
    if (cursor < value.length) fragment.append(document.createTextNode(value.slice(cursor)));
    node.replaceWith(fragment);
  }

  function decorate(root) {
    if (root.nodeType === Node.TEXT_NODE) return replaceText(root);
    if (root.nodeType !== Node.ELEMENT_NODE || root.closest(excluded)) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(replaceText);
  }

  function start() {
    if (document.body.classList.contains('landing-body')) return;
    decorate(document.body);
    const observer = new MutationObserver(records => {
      observer.disconnect();
      for (const record of records) {
        if (record.type === 'characterData') decorate(record.target);
        else record.addedNodes.forEach(decorate);
      }
      observer.observe(document.body, {childList:true, characterData:true, subtree:true});
    });
    observer.observe(document.body, {childList:true, characterData:true, subtree:true});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once:true});
  else start();
})();
