import React from 'react';

/* Tiny, safe markdown renderer for chat text (no innerHTML).
   Supports: **bold**, *italic*, `code`, "- " / "* " / "• " bullets, "1. " lists, "# " headings. */

const stripStray = (s) => s.replace(/\*\*/g, '');

export function plain(text) {
  return String(text || '').replace(/\*\*(.+?)\*\*/g, '$1').replace(/\*\*/g, '');
}

function inline(text, keyBase) {
  const re = /\*\*(.+?)\*\*|`([^`]+)`|\*([^*\s][^*]*?)\*/g; // fresh regex per call (safe for recursion)
  const out = [];
  let last = 0, m, i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(stripStray(text.slice(last, m.index)));
    const key = `${keyBase}-${i++}`;
    if (m[1] !== undefined) out.push(<strong key={key}>{inline(m[1], key)}</strong>);
    else if (m[2] !== undefined) out.push(<code key={key}>{m[2]}</code>);
    else out.push(<em key={key}>{m[3]}</em>);
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(stripStray(text.slice(last)));
  return out;
}

function parse(text) {
  const blocks = [];
  let para = [], list = null;
  const flushPara = () => { if (para.length) { blocks.push({ t: 'p', lines: para }); para = []; } };
  const flushList = () => { if (list) { blocks.push(list); list = null; } };
  for (const raw of String(text || '').replace(/\r/g, '').split('\n')) {
    const line = raw.trimEnd();
    if (!line.trim()) { flushPara(); flushList(); continue; }
    const h = line.match(/^\s{0,3}#{1,4}\s+(.*)$/);
    const ul = line.match(/^\s*[-*•]\s+(.*)$/);
    const ol = line.match(/^\s*(\d+)[.)]\s+(.*)$/);
    if (h) { flushPara(); flushList(); blocks.push({ t: 'h', text: h[1] }); }
    else if (ul) { flushPara(); if (!list || list.t !== 'ul') { flushList(); list = { t: 'ul', items: [] }; } list.items.push(ul[1]); }
    else if (ol) { flushPara(); if (!list || list.t !== 'ol') { flushList(); list = { t: 'ol', start: Number(ol[1]), items: [] }; } list.items.push(ol[2]); }
    else { flushList(); para.push(line.trim()); }
  }
  flushPara(); flushList();
  return blocks;
}

export default function Rich({ text, className = '' }) {
  const blocks = parse(text);
  return (
    <div className={`rich ${className}`}>
      {blocks.map((b, i) => {
        if (b.t === 'h') return <div className="rich-h" key={i}>{inline(b.text, `h${i}`)}</div>;
        if (b.t === 'ul') return <ul key={i}>{b.items.map((it, j) => <li key={j}>{inline(it, `u${i}-${j}`)}</li>)}</ul>;
        if (b.t === 'ol') return <ol key={i} start={b.start}>{b.items.map((it, j) => <li key={j}>{inline(it, `o${i}-${j}`)}</li>)}</ol>;
        return <p key={i}>{b.lines.map((l, j) => <React.Fragment key={j}>{j > 0 && <br />}{inline(l, `p${i}-${j}`)}</React.Fragment>)}</p>;
      })}
    </div>
  );
}
