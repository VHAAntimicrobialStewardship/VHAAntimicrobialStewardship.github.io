// Phase 0 nav-model snapshot: builds the sidebar menu tree offline (the same code the browser runs)
// from each station's OMJSON and compares it to a saved baseline.
//
//   node scripts/nav-snapshot.js --write   save reports/nav-model-baseline.json
//   node scripts/nav-snapshot.js           compare against the baseline (exit 1 on any difference)
//
// Run after compile-cms.py; any data cleanup must leave the tree identical.
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..');
const BASELINE = path.join(ROOT, 'reports', 'nav-model-baseline.json');
const STATIONS = require('./stations.json').stations.map((s) => [s.folder, `${s.prefix}OMJSON.json`]);

function loadNav() {
  const sandbox = { window: { location: { search: '' } }, URLSearchParams, console };
  vm.runInNewContext(fs.readFileSync(path.join(ROOT, 'shared', 'cdss-sidebar.js'), 'utf8'), sandbox);
  return sandbox.window.CDSSNav;
}

// Plain-data copy of a node (drops ids and parent links).
function plain(node) {
  const out = { type: node.type, label: node.label };
  if (node.target) out.target = node.target;
  if (node.level) out.level = node.level;
  out.children = (node.children || []).map(plain);
  return out;
}

function snapshot() {
  const nav = loadNav();
  const result = {};
  STATIONS.forEach(([station, file]) => {
    const data = JSON.parse(fs.readFileSync(path.join(ROOT, 'stations', station, file), 'utf8'));
    const model = nav.buildNavModel(data.menus || data, { welcomeId: 'welcome', mainMenuId: 'main-menu' });
    result[station] = {
      nodeCount: model.nodeCount,
      headerMenus: model.headerMenus,
      treeSections: model.treeSections.map((s) => ({ label: s.label, children: s.children.map(plain) }))
    };
  });
  return result;
}

function diffPaths(a, b, where, out) {
  if (out.length >= 15) return;
  if (JSON.stringify(a) === JSON.stringify(b)) return;
  if (a && b && typeof a === 'object' && typeof b === 'object') {
    const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
    keys.forEach((k) => diffPaths(a[k], b[k], `${where}/${k}`, out));
  } else {
    out.push(`${where}: ${JSON.stringify(a)} -> ${JSON.stringify(b)}`);
  }
}

const current = snapshot();
if (process.argv.includes('--write')) {
  fs.writeFileSync(BASELINE, JSON.stringify(current, null, 1) + '\n');
  Object.entries(current).forEach(([s, m]) => console.log(`${s}: ${m.nodeCount} tree nodes, ${m.headerMenus.length} header menus`));
  console.log('Baseline written to reports/nav-model-baseline.json');
} else {
  const baseline = JSON.parse(fs.readFileSync(BASELINE, 'utf8'));
  const diffs = [];
  diffPaths(baseline, current, '', diffs);
  if (diffs.length) {
    console.log('Nav model differs from baseline:');
    diffs.forEach((d) => console.log('  ' + d));
    process.exitCode = 1;
  } else {
    console.log('Nav model identical to baseline for all stations.');
  }
}
