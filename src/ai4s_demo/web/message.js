import {escapeHTML as esc} from './api.js';

// A small, escaped Markdown subset for model replies. Raw HTML and links are
// displayed as text; generated output never supplies tags or attributes.
export function renderMessage(text, parameterNames = []) {
  const parameters = new Set(parameterNames);
  function inline(value) {
    const tokens = /`([^`\n]+)`|\*\*([^*\n]+)\*\*|\b[A-Za-z_][A-Za-z0-9_]*\b/g;
    let html = '', start = 0;
    for (const match of value.matchAll(tokens)) {
      html += esc(value.slice(start, match.index));
      if (match[1] !== undefined) html += `<code>${esc(match[1])}</code>`;
      else if (match[2] !== undefined) html += `<strong>${inline(match[2])}</strong>`;
      else html += parameters.has(match[0]) ? `<code>${esc(match[0])}</code>` : esc(match[0]);
      start = match.index + match[0].length;
    }
    return html + esc(value.slice(start));
  }

  const blocks = [];
  let paragraph = [], list = null, code = null;
  function listItem(value) {
    const group = value.match(/^([^:：]{1,80})([:：])\s*(.+)$/);
    const fields = group?.[3].match(/\b[A-Za-z_][A-Za-z0-9_]*\b/g) || [];
    if (group && fields.some(field => parameters.has(field))) {
      return `<li><span class="message-item-label">${inline(group[1] + group[2])}</span><span class="message-item-detail">${inline(group[3])}</span></li>`;
    }
    return `<li>${inline(value)}</li>`;
  }
  function flushParagraph() {
    if (paragraph.length) blocks.push(`<p>${inline(paragraph.join(' '))}</p>`);
    paragraph = [];
  }
  function flushList() {
    if (list) blocks.push(`<${list.tag}>${list.items.map(listItem).join('')}</${list.tag}>`);
    list = null;
  }
  function flushCode() {
    blocks.push(`<pre><code>${esc(code.join('\n'))}</code></pre>`);
    code = null;
  }
  for (const line of String(text ?? '').replace(/\r\n?/g, '\n').split('\n')) {
    if (/^\s*```/.test(line)) {
      if (code !== null) flushCode();
      else { flushParagraph(); flushList(); code = []; }
      continue;
    }
    if (code !== null) { code.push(line); continue; }
    if (!line.trim()) { flushParagraph(); flushList(); continue; }
    const heading = line.match(/^\s*#{1,4}\s+(.+)$/);
    if (heading) {
      flushParagraph(); flushList();
      blocks.push(`<h4>${inline(heading[1])}</h4>`);
      continue;
    }
    const item = line.match(/^\s*(?:([-*+•])\s+|\d+[.)、]\s+)(.+)$/);
    if (item) {
      flushParagraph();
      const tag = item[1] ? 'ul' : 'ol';
      if (list?.tag !== tag) { flushList(); list = {tag, items: []}; }
      list.items.push(item[2]);
    } else if (list && /^\s{2,}\S/.test(line)) {
      list.items[list.items.length - 1] += ' ' + line.trim();
    } else {
      flushList(); paragraph.push(line.trim());
    }
  }
  if (code !== null) flushCode();
  flushParagraph(); flushList();
  return blocks.join('');
}
