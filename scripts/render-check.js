// Phase 0 render check: renders every cms-data page (Text and Therapy) with the planned marked
// configuration and reports content that would be lost, swallowed or misrendered.
//
//   node scripts/render-check.js                      all four stations, summary
//   node scripts/render-check.js --station 541-Cleveland
//   node scripts/render-check.js --page <PageID>      details for one page (all stations)
//   node scripts/render-check.js --fixtures           also write reports/markdown-fixtures.json
//
// Writes reports/markdown-render-check.json. Exit code 1 when hard errors exist.
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { renderHtml } = require('./lib/markdown-config');

const ROOT = path.resolve(__dirname, '..');
const STATIONS = ['001-TestStation', '506-AnnArbor', '539-Cincinnati', '541-Cleveland'];
const FIELDS = ['Text', 'Therapy'];
const HARD = ['text-mismatch', 'table-extra-divider', 'indented-code', 'runaway-emphasis', 'blockquote-marker', 'separator-line', 'table-not-rendered'];

const doc = new JSDOM('').window.document;

function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? walk(path.join(dir, e.name)) : e.name.endsWith('.json') ? [path.join(dir, e.name)] : []
  );
}

const LINK_RE = /\[((?:[^\[\]]|\[[^\]]*\])*)\]\((?:[^()\s]|\([^)]*\))*(?:\s+"[^"]*")?\)/g;
const DROP_RE = /[\s*_~`|]/g;
const ENTITIES = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'", '&nbsp;': ' ' };

// Text a reader should see, with markdown syntax removed (same characters dropped from both sides).
function expectedText(source) {
  let inFence = false;
  const out = [];
  source.split(/\r?\n/).forEach((raw) => {
    if (/^\s*```/.test(raw)) {
      inFence = !inFence;
      return;
    }
    if (inFence) {
      out.push(raw);
      return;
    }
    if (/^\s{0,3}(-{3,}|\*{3,}|_{3,})\s*$/.test(raw)) return;
    if (raw.includes('|') && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/.test(raw)) return;
    let line = raw;
    if (/^\s{0,3}#{1,6}\s+/.test(line)) {
      line = line.replace(/^\s{0,3}#{1,6}\s+/, '');
    } else {
      line = line.replace(/^(?:\s{0,3}>\s?)+/, '').replace(/^\s*([-*+]|\d{1,9}[.)])\s+/, '');
    }
    line = line.replace(/!\[[^\]]*\]\([^)]*\)/g, '').replace(LINK_RE, '$1');
    line = line.replace(/<((?:https?|mailto):[^>\s]+)>/g, '$1');
    out.push(line);
  });
  return out
    .join('\n')
    .replace(/&(?:amp|lt|gt|quot|#39|nbsp);/g, (m) => ENTITIES[m])
    .replace(/\\([\\`*_{}\[\]()#+\-.!|<>~$&])/g, '$1')
    .replace(DROP_RE, '');
}

function renderedText(html) {
  const holder = doc.createElement('div');
  holder.innerHTML = html;
  return { holder, text: holder.textContent.replace(DROP_RE, '') };
}

function firstDiff(a, b) {
  let i = 0;
  while (i < a.length && i < b.length && a[i] === b[i]) i++;
  return { at: i, expected: a.slice(Math.max(0, i - 25), i + 40), rendered: b.slice(Math.max(0, i - 25), i + 40) };
}

function checkField(source) {
  const findings = [];
  const info = { listLines: 0, tags: new Set(), tables: 0, hasColumns: /<!--\s*(?:RIGHT )?COLUMN/i.test(source) };
  const lines = source.split(/\r?\n/);
  let inFence = false;
  lines.forEach((line, i) => {
    if (/^\s*```/.test(line)) inFence = !inFence;
    if (inFence) return;
    if (/^( {4,}|\t)\S/.test(line) && (i === 0 || !lines[i - 1].trim())) {
      findings.push({ type: 'indented-code', line: i + 1, sample: line.slice(0, 70) });
    }
    if (/^\s{0,3}>/.test(line) && !/^\s{0,3}#{1,6}\s/.test(line)) {
      findings.push({ type: 'blockquote-marker', line: i + 1, sample: line.slice(0, 70) });
    }
    if (/^\s*([-*+]|\d{1,9}[.)])\s+\S/.test(line)) info.listLines++;
    for (const m of line.replace(/<!--.*?-->/g, '').matchAll(/<\/?([A-Za-z][\w-]*)/g)) info.tags.add(m[1]);
  });

  const html = renderHtml(source);
  const { holder, text } = renderedText(html);
  const expected = expectedText(source);
  if (expected !== text) {
    findings.push({ type: 'text-mismatch', ...firstDiff(expected, text) });
  }
  if (/^\|.*\|\s*$/m.test(source) && !holder.querySelector('table')) {
    findings.push({ type: 'table-not-rendered' });
  }
  holder.querySelectorAll('table').forEach((table) => {
    info.tables++;
    if ([...table.querySelectorAll('td,th')].some((c) => /^-{3,}$/.test(c.textContent.trim()))) {
      findings.push({ type: 'table-extra-divider' });
    }
  });
  holder.querySelectorAll('em,strong').forEach((el) => {
    const t = el.textContent;
    if (/^[\s_*=\-]+$/.test(t)) {
      findings.push({ type: 'separator-line', sample: t.slice(0, 70) });
    } else if (el.querySelector('br')) {
      findings.push({ type: 'runaway-emphasis', sample: t.slice(0, 70) });
    } else if (t.length > 150) {
      findings.push({ type: 'long-emphasis', sample: t.slice(0, 70) });
    }
  });
  return { findings, info, html, holder };
}

function loadPages(stations) {
  const pages = [];
  stations.forEach((station) => {
    const dir = path.join(ROOT, 'cms-data', station, 'pages');
    if (!fs.existsSync(dir)) return;
    walk(dir).forEach((file) => {
      const data = JSON.parse(fs.readFileSync(file, 'utf8'));
      FIELDS.forEach((field) => {
        if (typeof data[field] === 'string' && data[field].trim()) {
          pages.push({ station, file: path.relative(ROOT, file).replace(/\\/g, '/'), pageId: path.basename(file, '.json'), field, source: data[field] });
        }
      });
    });
  });
  return pages;
}

function pickFixtures(rows) {
  const by = (pred, score, n = 3) =>
    rows
      .filter(pred)
      .sort((a, b) => score(b) - score(a))
      .filter((r, i, arr) => arr.findIndex((x) => x.pageId === r.pageId) === i)
      .slice(0, n)
      .map((r) => `${r.station}/${r.pageId} (${r.field})`);
  const count = (re, s) => (s.match(re) || []).length;
  return {
    'table (GFM already)': by((r) => r.tables > 0, (r) => r.tables),
    'numbered list': by((r) => r.listLines > 0 && /^\s*\d+[.)]\s/m.test(r.source), (r) => r.listLines),
    'bullet list': by((r) => /^\s*[-*+]\s/m.test(r.source), (r) => r.listLines),
    'link heavy': by((r) => r.field === 'Text', (r) => count(/^\[[^\]]+\]\([^)]+\)\s*$/gm, r.source)),
    'order blocks (< OR >)': by(() => true, (r) => count(/<\s*(?:OR|AND)\s*>/g, r.source)),
    'raw tag-like text': by((r) => r.tags.size > 0 && !r.hasColumns, (r) => r.tags.size),
    'long references': by((r) => /references/i.test(r.source), (r) => r.source.split(/references/i).pop().split('\n').length),
    'column delimiters': by((r) => r.hasColumns, (r) => count(/COLUMN/g, r.source)),
    'indented lines': by((r) => r.findings.some((f) => f.type === 'indented-code'), (r) => r.findings.length),
    'emphasis suspects': by((r) => r.findings.some((f) => f.type === 'runaway-emphasis'), (r) => r.findings.length)
  };
}

function main() {
  const args = process.argv.slice(2);
  const arg = (name) => (args.includes(name) ? args[args.indexOf(name) + 1] : null);
  const stations = arg('--station') ? [arg('--station')] : STATIONS;
  const onlyPage = arg('--page');

  const rows = loadPages(stations)
    .filter((p) => !onlyPage || p.pageId === onlyPage)
    .map((p) => {
      const { findings, info } = checkField(p.source);
      return { ...p, findings, listLines: info.listLines, tags: info.tags, tables: info.tables, hasColumns: info.hasColumns };
    });

  const counts = {};
  const pagesWith = {};
  rows.forEach((r) => {
    const kinds = new Set(r.findings.map((f) => f.type));
    if (r.hasColumns) kinds.add('column-page');
    if (r.tags.size && !r.hasColumns) kinds.add('tag-like-text');
    if (r.tables) kinds.add('has-table');
    if (r.listLines) kinds.add('has-list');
    kinds.forEach((k) => {
      counts[k] = (counts[k] || 0) + 1;
      (pagesWith[k] = pagesWith[k] || []).push(`${r.station}/${r.pageId}:${r.field}`);
    });
  });

  console.log(`Checked ${rows.length} fields (Text/Therapy) across ${stations.length} station(s)`);
  Object.keys(counts)
    .sort()
    .forEach((k) => console.log(`  ${HARD.includes(k) ? 'ERROR' : 'info '} ${k.padEnd(22)} ${counts[k]}`));

  const hardRows = rows.filter((r) => !r.hasColumns && r.findings.some((f) => HARD.includes(f.type)));
  console.log(`Fields with hard errors (excluding column pages): ${hardRows.length}`);
  if (onlyPage) {
    rows.forEach((r) => console.log(JSON.stringify({ station: r.station, field: r.field, findings: r.findings, tags: [...r.tags] }, null, 2)));
  }

  const report = {
    generated: new Date().toISOString(),
    counts,
    hardErrors: hardRows.map((r) => ({ station: r.station, page: r.pageId, field: r.field, findings: r.findings.filter((f) => HARD.includes(f.type)).slice(0, 5) })),
    columnPages: rows.filter((r) => r.hasColumns).map((r) => `${r.station}/${r.pageId}:${r.field}`),
    tagLikeText: Object.fromEntries(rows.filter((r) => r.tags.size && !r.hasColumns).map((r) => [`${r.station}/${r.pageId}:${r.field}`, [...r.tags]]))
  };
  fs.writeFileSync(path.join(ROOT, 'reports', 'markdown-render-check.json'), JSON.stringify(report, null, 2) + '\n');
  if (args.includes('--fixtures')) {
    const fixtures = pickFixtures(rows);
    fs.writeFileSync(path.join(ROOT, 'reports', 'markdown-fixtures.json'), JSON.stringify(fixtures, null, 2) + '\n');
    console.log('Wrote reports/markdown-fixtures.json');
  }
  process.exitCode = hardRows.length ? 1 : 0;
}

main();
