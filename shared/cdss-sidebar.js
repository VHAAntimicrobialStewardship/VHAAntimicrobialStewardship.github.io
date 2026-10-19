// ===========================================================================
// CDSS sidebar layout (optional, opt-in per station page)
//
// Turns a station page into: header menus + search on top, a persistent
// collapsible menu tree on the left, the page in the middle and, when the page
// has Therapy content, a Therapy panel on the right.
//
// Enable on a station page by
//   - setting   var Layout = 'sidebar';   in its configuration block,
//   - loading   /shared/cdss-sidebar.css  in <head>, and
//   - loading   /shared/cdss-sidebar.js   BEFORE /shared/cdss-app.js.
// Append ?layout=classic to the URL to get the original layout back.
//
// The station page markup is NOT changed: this script re-arranges the existing
// header elements (so every id used by cdss-app.js keeps working) and adds the
// new containers. All page rendering still happens in cdss-app.js, which calls
// the hooks exported at the bottom of this file (beforeRender, afterRender,
// onDataReady, syncUrl) when the layout is enabled.
//
// The menu tree and header menus are derived from existing content - no extra
// authoring: the main menu page (main-menu) supplies the top-level sections, and
// every "navigation page" (a page that is mostly markdown link lines) is
// expanded into sub-menus, recursively.
// ===========================================================================
(function () {
  'use strict';

  // -------------------------------------------------------------------------
  // CONFIGURATION
  // -------------------------------------------------------------------------

  // main-menu sections shown as header drop-downs instead of in the tree.
  // `section` is the main-menu "## Heading"; `label` is the header button text.
  const HEADER_MENUS = [
    { section: 'General and Miscellaneous', label: 'General and Misc', includeWelcome: true },
    { section: 'Important Antimicrobial Information', label: 'Important Antimicrobial Info' },
    { section: 'Help', label: 'Support' }
  ];
  // main-menu sections that appear nowhere in the tree/menus (the header has an Index button).
  const IGNORED_SECTIONS = ['index'];
  // How many levels of navigation pages the tree expands below a main-menu entry.
  const MAX_TREE_DEPTH = 4;
  // Below this viewport width the menu tree becomes a slide-over drawer.
  const DRAWER_MAX_WIDTH = 1000; // keep in sync with the media query in cdss-sidebar.css

  const params = new URLSearchParams(window.location.search);
  const enabled =
    typeof Layout !== 'undefined' && Layout === 'sidebar' && params.get('layout') !== 'classic';
  const welcomeId = (typeof WelcomePage !== 'undefined' && WelcomePage) || 'welcome';
  const mainMenuId = (typeof combinedMenu !== 'undefined' && combinedMenu) || 'main-menu';

  // -------------------------------------------------------------------------
  // NAVIGATION MODEL (pure functions; no DOM)
  // -------------------------------------------------------------------------

  const LINK_LINE_RE = /^\[((?:[^\[\]]|\[[^\]]*\])*)\]\(([^)\s]+)\)$/;
  const HEADING_RE = /^(#{1,6})\s+(.*?)\s*$/;
  const COMMENT_RE = /^<!--.*-->$/;
  const CLICK_HERE_RE = /^click here/i;
  const BOLD_LINE_RE = /^\*\*([^*]+)\*\*:?$/;

  // Plain-text version of a markdown label (escapes and emphasis markers removed).
  function stripMarkdown(text) {
    return (text || '')
      .replace(/\\(.)/g, '$1')
      .replace(/(\*\*|__|\*|_)(.+?)\1/g, '$2')
      .replace(/`/g, '')
      .trim();
  }

  // Parses a navigation page's markdown into menu items:
  //   { type: 'link', label, target, children: [] }       one pure "[label](target)" line
  //   { type: 'section', label, children: [link, ...] }   a "## Heading" and the links under it
  // The page title (a leading "# Title"), HTML comments (column markers) and
  // plain-text lines are ignored. "Click here" links take their heading's label.
  function parseNavText(text) {
    const items = [];
    let section = null;
    let seenContent = false;

    (text || '').split(/\r?\n/).forEach((rawLine) => {
      const line = rawLine.trim();
      if (!line || COMMENT_RE.test(line)) {
        return;
      }

      const heading = line.match(HEADING_RE);
      if (heading) {
        const isTitle = !seenContent && heading[1].length === 1;
        seenContent = true;
        if (isTitle) {
          return;
        }
        const rawLabel = heading[2].trim();
        if (!rawLabel || /^[_\-=\s]+$/.test(rawLabel)) {
          section = null; // a horizontal-rule style heading
          return;
        }
        section = { type: 'section', level: 1, label: stripMarkdown(rawLabel), children: [] };
        items.push(section);
        return;
      }

      seenContent = true;
      const boldLine = line.match(BOLD_LINE_RE);
      if (boldLine) {
        // A line that is only bold text acts as a sub-heading (e.g. "**Empiric Treatment**").
        section = { type: 'section', level: 2, label: stripMarkdown(boldLine[1]), children: [] };
        items.push(section);
        return;
      }
      const link = line.match(LINK_LINE_RE);
      if (link) {
        const node = { type: 'link', label: stripMarkdown(link[1]), target: link[2].trim(), children: [] };
        (section ? section.children : items).push(node);
      }
    });

    const result = [];
    items.forEach((item) => {
      if (item.type !== 'section') {
        result.push(item);
        return;
      }
      if (item.children.length === 0) {
        return; // heading with no links (plain text only)
      }
      if (item.children.length === 1 && CLICK_HERE_RE.test(item.children[0].label)) {
        // "## Viral Skin Infections" + "[Click here](ssti-viral)": the heading is the link.
        result.push({ type: 'link', label: item.label, target: item.children[0].target, children: [] });
        return;
      }
      item.children.forEach((child) => {
        if (CLICK_HERE_RE.test(child.label)) {
          child.label = item.label;
        }
      });
      result.push(item);
    });
    return result;
  }

  // A navigation page is mostly pure link lines (headings/comments excluded).
  function isNavPage(record) {
    if (!record || typeof record.Text !== 'string') {
      return false;
    }
    const lines = record.Text.split(/\r?\n/)
      .map((l) => l.trim())
      .filter((l) => l && !COMMENT_RE.test(l) && !HEADING_RE.test(l));
    const linkLines = lines.filter((l) => LINK_LINE_RE.test(l)).length;
    return linkLines >= 2 && linkLines / lines.length >= 0.5;
  }

  // Builds the navigation model from the page records:
  //   headerMenus: [{ label, items: [{ label, target }] }]
  //   treeSections: [{ label, children: [node] }]   node = { id, type, label, target?, children, parent }
  //   byTarget: Map(lower-case page name -> [link nodes])
  function buildNavModel(records, options) {
    const opts = options || {};
    const welcome = opts.welcomeId || 'welcome';
    const mainId = opts.mainMenuId || 'main-menu';
    const byName = new Map();
    records.forEach((r) => byName.set((r.Name || '').trim().toLowerCase(), r));
    const lookup = (name) => byName.get((name || '').trim().toLowerCase());

    const model = { headerMenus: [], treeSections: [], byTarget: new Map(), nodeCount: 0 };
    let seq = 0;

    function toNode(link, ancestors, depth) {
      const record = lookup(link.target);
      if (!record || ancestors.has(record.Name)) {
        return null;
      }
      const node = { id: ++seq, type: 'link', label: link.label, target: record.Name, children: [], parent: null };
      const key = record.Name.toLowerCase();
      if (!model.byTarget.has(key)) {
        model.byTarget.set(key, []);
      }
      model.byTarget.get(key).push(node);

      if (depth < MAX_TREE_DEPTH && isNavPage(record)) {
        const nextAncestors = new Set(ancestors).add(record.Name);
        parseNavText(record.Text).forEach((item) => {
          if (item.type === 'section') {
            const section = { id: ++seq, type: 'section', level: item.level, label: item.label, children: [], parent: node };
            item.children.forEach((child) => {
              const childNode = toNode(child, nextAncestors, depth + 1);
              if (childNode) {
                childNode.parent = section;
                section.children.push(childNode);
              }
            });
            if (section.children.length) {
              node.children.push(section);
            }
          } else {
            const childNode = toNode(item, nextAncestors, depth + 1);
            if (childNode) {
              childNode.parent = node;
              node.children.push(childNode);
            }
          }
        });
      }
      return node;
    }

    const mainMenu = lookup(mainId);
    if (!mainMenu) {
      return model;
    }
    const headerBySection = new Map(HEADER_MENUS.map((m) => [m.section.toLowerCase(), m]));

    parseNavText(mainMenu.Text).forEach((section) => {
      if (section.type !== 'section') {
        return;
      }
      const key = section.label.toLowerCase();
      if (IGNORED_SECTIONS.includes(key)) {
        return;
      }

      const headerDef = headerBySection.get(key);
      if (headerDef) {
        const items = [];
        if (headerDef.includeWelcome && lookup(welcome)) {
          items.push({ label: 'Welcome', target: lookup(welcome).Name });
        }
        section.children.forEach((link) => {
          const record = lookup(link.target);
          if (record) {
            items.push({ label: link.label, target: record.Name });
          }
        });
        model.headerMenus.push({ label: headerDef.label, items });
        return;
      }

      const treeSection = { label: section.label, children: [] };
      section.children.forEach((link) => {
        const node = toNode(link, new Set([mainMenu.Name]), 1);
        if (node) {
          treeSection.children.push(node);
        }
      });
      if (treeSection.children.length) {
        model.treeSections.push(treeSection);
      }
    });

    // Keep the header menus in the configured order.
    model.headerMenus.sort(
      (a, b) =>
        HEADER_MENUS.findIndex((m) => m.label === a.label) - HEADER_MENUS.findIndex((m) => m.label === b.label)
    );
    model.nodeCount = seq;
    return model;
  }

  // Exposed for offline testing (node) even when the layout is disabled.
  window.CDSSNav = { parseNavText, isNavPage, buildNavModel };

  if (!enabled || typeof document === 'undefined' || !document.getElementById('resultContainer')) {
    window.CDSSSidebar = { enabled: false };
    return;
  }

  // -------------------------------------------------------------------------
  // SHELL: re-arrange the existing page into header / nav / main / therapy
  // -------------------------------------------------------------------------

  const byId = (id) => document.getElementById(id);

  function make(tag, id, className) {
    const element = document.createElement(tag);
    if (id) element.id = id;
    if (className) element.className = className;
    return element;
  }

  let navToggleButton = null;

  function buildShell() {
    const body = document.body;
    body.classList.add('layout-sidebar');

    const header = byId('header');
    const resultContainer = byId('resultContainer');

    // Row 1: header menus. The drop-downs are added once data is loaded;
    // Help/Legend, Index and Feedback are the existing buttons, moved here.
    const menuBar = make('div', 'cdssMenuBar');
    menuBar.setAttribute('role', 'navigation');
    menuBar.setAttribute('aria-label', 'Site menu');
    ['helpLegendButton', 'indexButton', 'feedbackButton'].forEach((id) => {
      const button = byId(id);
      if (button) menuBar.appendChild(button);
    });
    const helpButton = menuBar.querySelector('#helpLegendButton');
    if (helpButton) helpButton.textContent = 'Help/Legend';

    // Row 2: drawer toggle, station home button, search, install/home buttons.
    const headerRow = make('div', 'cdssHeaderRow');
    navToggleButton = make('button', 'cdssNavToggle');
    navToggleButton.type = 'button';
    navToggleButton.textContent = '\u2630 Menu';
    navToggleButton.setAttribute('aria-controls', 'cdssNav');
    navToggleButton.setAttribute('aria-expanded', 'false');
    headerRow.appendChild(navToggleButton);
    ['goBackButton', 'goForwardButton'].forEach((id) => {
      const button = byId(id);
      if (button) headerRow.appendChild(button);
    });
    headerRow.appendChild(byId('mainMenuButton'));
    headerRow.appendChild(header.querySelector('.search-container'));
    // The Install App button stays in the DOM (cdss-app.js binds to it) but is hidden by CSS.
    const homeButton = byId('homeButton');
    if (homeButton) {
      homeButton.title = 'Back to regular site';
      headerRow.appendChild(homeButton);
    }

    header.insertBefore(headerRow, header.firstChild);
    header.insertBefore(menuBar, header.firstChild);

    // Body: left menu tree, centre page, right therapy panel.
    const nav = make('nav', 'cdssNav');
    nav.setAttribute('aria-label', 'Guidance menu');
    nav.appendChild(make('div', 'cdssTree'));

    const main = make('main', 'cdssMain');
    main.appendChild(resultContainer);
    const footer = make('div', 'cdssFooter');
    ['.picture-container', '#versionTag'].forEach((selector) => {
      const element = document.querySelector(selector);
      if (element) footer.appendChild(element);
    });
    main.appendChild(footer);

    const therapy = make('aside', 'cdssTherapy');
    therapy.setAttribute('aria-label', 'Therapy');
    therapy.hidden = true;
    const therapyTitle = make('h2', null, 'cdss-therapy-title');
    therapyTitle.textContent = 'Therapy';
    therapy.appendChild(therapyTitle);
    therapy.appendChild(make('div', 'cdssTherapyContent'));

    const shell = make('div', 'cdssBody');
    shell.appendChild(nav);
    shell.appendChild(main);
    shell.appendChild(therapy);
    header.parentNode.insertBefore(shell, header.nextSibling);

    // The empty <table class="table"> and old footer rows are not used in this layout.
    document.querySelectorAll('body > table.table').forEach((table) => table.remove());

    navToggleButton.addEventListener('click', () => setDrawerOpen(!body.classList.contains('nav-open')));
    document.addEventListener('click', (event) => {
      if (body.classList.contains('nav-open') && !event.target.closest('#cdssNav') && !event.target.closest('#cdssNavToggle')) {
        setDrawerOpen(false);
      }
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        closeAllMenus();
        setDrawerOpen(false);
      }
    });
  }

  function setDrawerOpen(open) {
    document.body.classList.toggle('nav-open', open);
    if (navToggleButton) navToggleButton.setAttribute('aria-expanded', String(open));
  }

  // -------------------------------------------------------------------------
  // NAVIGATION: opening pages from menu links
  // -------------------------------------------------------------------------

  function hrefFor(page) {
    return '#' + encodeURIComponent(page);
  }

  // True while a page opened from a menu link is being shown (see setActivePage).
  let openedFromMenu = false;

  // Click handler for every menu link: normal clicks open the page in place;
  // modified clicks fall through to the browser (new tab via the #page-id URL).
  function bindPageLink(anchor, page, onNavigate) {
    anchor.href = hrefFor(page);
    anchor.addEventListener('click', (event) => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.button !== 0) {
        return;
      }
      event.preventDefault();
      openedFromMenu = true;
      if (onNavigate) onNavigate();
      closeAllMenus();
      if (window.innerWidth < DRAWER_MAX_WIDTH) setDrawerOpen(false);
      handleRowClick({ Item: page });
    });
  }

  // -------------------------------------------------------------------------
  // HEADER DROP-DOWN MENUS
  // -------------------------------------------------------------------------

  const openMenus = [];

  function closeAllMenus() {
    openMenus.forEach((menu) => {
      menu.list.hidden = true;
      menu.button.setAttribute('aria-expanded', 'false');
    });
  }

  function buildHeaderMenus(model) {
    const menuBar = byId('cdssMenuBar');
    const firstFixedButton = byId('helpLegendButton');

    model.headerMenus.forEach((menuDef) => {
      if (!menuDef.items.length) return;

      const wrapper = make('div', null, 'cdss-menu');
      const button = make('button', null, 'cdss-menu-button');
      button.type = 'button';
      button.textContent = menuDef.label + ' \u25BE';
      button.setAttribute('aria-haspopup', 'true');
      button.setAttribute('aria-expanded', 'false');

      const list = make('ul', null, 'cdss-menu-list');
      list.hidden = true;
      menuDef.items.forEach((item) => {
        const li = document.createElement('li');
        const anchor = document.createElement('a');
        anchor.textContent = item.label;
        bindPageLink(anchor, item.target);
        li.appendChild(anchor);
        list.appendChild(li);
      });

      const entry = { button, list };
      openMenus.push(entry);
      button.addEventListener('click', (event) => {
        event.stopPropagation();
        const wasHidden = list.hidden;
        closeAllMenus();
        list.hidden = !wasHidden;
        button.setAttribute('aria-expanded', String(wasHidden));
      });

      wrapper.appendChild(button);
      wrapper.appendChild(list);
      menuBar.insertBefore(wrapper, firstFixedButton);
    });

    document.addEventListener('click', closeAllMenus);
  }

  // -------------------------------------------------------------------------
  // MENU TREE
  // -------------------------------------------------------------------------

  let model = null;
  let activeNode = null;
  let clickedNode = null; // tree node the user just clicked (disambiguates repeated pages)

  function renderList(nodes) {
    const list = document.createElement('ul');
    list.className = 'cdss-tree-list';
    nodes.forEach((node) => list.appendChild(renderNode(node)));
    return list;
  }

  function renderNode(node) {
    const li = document.createElement('li');
    node.el = li;

    if (node.type === 'section') {
      li.className = 'cdss-tree-heading' + (node.level === 2 ? ' level-2' : '');
      const label = make('div', null, 'cdss-tree-heading-label');
      label.textContent = node.label;
      li.appendChild(label);
      li.appendChild(renderList(node.children));
      return li;
    }

    const row = make('div', null, 'cdss-tree-row');
    node.rowEl = row;
    const hasChildren = node.children.length > 0;

    if (hasChildren) {
      const toggle = make('button', null, 'cdss-tree-toggle');
      toggle.type = 'button';
      toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-label', 'Expand ' + node.label);
      toggle.addEventListener('click', () => setExpanded(node, !node.open));
      row.appendChild(toggle);
      node.toggleEl = toggle;
    } else {
      row.appendChild(make('span', null, 'cdss-tree-spacer'));
    }

    const anchor = make('a', null, 'cdss-tree-link');
    anchor.textContent = node.label;
    bindPageLink(anchor, node.target, () => {
      clickedNode = node;
    });
    row.appendChild(anchor);
    node.linkEl = anchor;
    li.appendChild(row);
    return li;
  }

  // Opens/closes a node. Child lists are built the first time a node opens.
  function setExpanded(node, open) {
    if (!node.children.length || !node.el) return;
    if (open && !node.childListEl) {
      node.childListEl = renderList(node.children);
      node.el.appendChild(node.childListEl);
    }
    node.open = open;
    if (node.childListEl) node.childListEl.hidden = !open;
    node.el.classList.toggle('open', open);
    if (node.toggleEl) {
      node.toggleEl.setAttribute('aria-expanded', String(open));
      node.toggleEl.setAttribute('aria-label', (open ? 'Collapse ' : 'Expand ') + node.label);
    }
  }

  function renderTree() {
    const container = byId('cdssTree');
    container.innerHTML = '';
    if (!model.treeSections.length) {
      container.textContent = 'No menu available.';
      return;
    }
    model.treeSections.forEach((section) => {
      const block = make('section', null, 'cdss-tree-section');
      const title = make('h3', null, 'cdss-tree-section-title');
      title.textContent = section.label;
      block.appendChild(title);
      block.appendChild(renderList(section.children));
      container.appendChild(block);
    });
  }

  function ancestorsOf(node) {
    const chain = [];
    for (let current = node.parent; current; current = current.parent) {
      chain.unshift(current);
    }
    return chain;
  }

  // Picks which tree occurrence of a page to highlight (pages often appear in several
  // places): the one just clicked, else the one sharing the most ancestors with the
  // previously highlighted node, else the first.
  function chooseNode(candidates) {
    if (clickedNode && candidates.includes(clickedNode)) {
      return clickedNode;
    }
    if (!activeNode) {
      return candidates[0];
    }
    const activeChain = new Set(ancestorsOf(activeNode));
    let best = candidates[0];
    let bestScore = -1;
    candidates.forEach((candidate) => {
      const score = ancestorsOf(candidate).filter((a) => activeChain.has(a)).length;
      if (score > bestScore) {
        best = candidate;
        bestScore = score;
      }
    });
    return best;
  }

  function scrollNavTo(row) {
    const nav = byId('cdssNav');
    if (!nav || !row) return;
    const rowRect = row.getBoundingClientRect();
    const navRect = nav.getBoundingClientRect();
    const margin = 48;
    if (rowRect.top < navRect.top + margin) {
      nav.scrollTop -= navRect.top + margin - rowRect.top;
    } else if (rowRect.bottom > navRect.bottom - margin) {
      nav.scrollTop += rowRect.bottom - (navRect.bottom - margin);
    }
  }

  function setActivePage(pageName) {
    const fromMenu = openedFromMenu;
    openedFromMenu = false;
    const candidates = (model && model.byTarget.get((pageName || '').toLowerCase())) || [];
    if (!candidates.length) {
      // Pages that are not menu entries (e.g. a sub-page opened from a page's text) keep the
      // previous highlight as context; the Welcome page and header-menu pages clear it.
      if (fromMenu || pageName === welcomeId) {
        if (activeNode && activeNode.rowEl) {
          activeNode.rowEl.classList.remove('active');
          activeNode.linkEl.removeAttribute('aria-current');
        }
        activeNode = null;
      }
      clickedNode = null;
      return;
    }
    if (activeNode && activeNode.rowEl) {
      activeNode.rowEl.classList.remove('active');
      activeNode.linkEl.removeAttribute('aria-current');
    }

    const node = chooseNode(candidates);
    clickedNode = null;
    ancestorsOf(node).forEach((ancestor) => {
      if (ancestor.type === 'link') setExpanded(ancestor, true);
    });
    if (node.children.length) setExpanded(node, true);

    if (node.rowEl) {
      node.rowEl.classList.add('active');
      node.linkEl.setAttribute('aria-current', 'page');
      scrollNavTo(node.rowEl);
    }
    activeNode = node;
  }

  // -------------------------------------------------------------------------
  // URL ROUTING (#page-id) so that browser Back/Forward and bookmarks work
  // -------------------------------------------------------------------------

  let suppressUrlUpdate = false;
  let urlStateStarted = false;

  function pageFromUrl() {
    try {
      return decodeURIComponent(window.location.hash.replace(/^#/, '')).trim();
    } catch (error) {
      return '';
    }
  }

  // Called by pushHistory() whenever a page is opened.
  function syncUrl(pageName) {
    if (suppressUrlUpdate || !pageName) return;
    const hash = hrefFor(pageName);
    if (window.location.hash === hash && urlStateStarted) return;
    const url = window.location.pathname + window.location.search + hash;
    if (!urlStateStarted) {
      urlStateStarted = true;
      window.history.replaceState({ page: pageName }, '', url);
    } else {
      window.history.pushState({ page: pageName }, '', url);
    }
  }

  // Back/Forward or an edited URL: open the page named in the hash without adding history.
  function syncFromUrl() {
    const page = pageFromUrl();
    if (!page || !omData.length || (selectedData && selectedData.Name === page)) return;
    suppressUrlUpdate = true;
    Promise.resolve(handleRowClick({ Item: page })).finally(() => {
      suppressUrlUpdate = false;
    });
  }

  window.addEventListener('popstate', syncFromUrl);
  window.addEventListener('hashchange', syncFromUrl);

  // -------------------------------------------------------------------------
  // HOOKS CALLED BY cdss-app.js
  // -------------------------------------------------------------------------

  let pageHasTherapy = false;

  // Data is loaded: build the tree and header menus.
  function onDataReady(records) {
    model = buildNavModel(records, { welcomeId, mainMenuId });
    renderTree();
    buildHeaderMenus(model);
    if (window.console && console.info) {
      console.info('CDSS sidebar: ' + model.nodeCount + ' tree nodes, ' + model.headerMenus.length + ' header menus');
    }
  }

  // Before a page is rendered: show/hide the therapy panel so the centre column has
  // its final width when the renderer measures it.
  function beforeRender(record) {
    pageHasTherapy = Boolean(record && typeof record.Therapy === 'string' && record.Therapy.trim());
    document.body.classList.toggle('has-therapy', pageHasTherapy);
    byId('cdssTherapy').hidden = !pageHasTherapy;
  }

  // After a page is rendered into #resultContainer.
  function afterRender(record) {
    if (!record) return;

    const therapyContent = byId('cdssTherapyContent');
    therapyContent.innerHTML = '';
    if (pageHasTherapy) {
      therapyContent.appendChild(buildRichTextTable({ Name: record.Name, Text: record.Therapy }, false));
    }

    if (record.Name === welcomeId) {
      const back = make('p', null, 'cdss-back-link');
      const anchor = document.createElement('a');
      anchor.href = typeof homeButtonUrl !== 'undefined' ? homeButtonUrl : '/';
      anchor.textContent = 'Back to regular site';
      back.appendChild(anchor);
      byId('resultContainer').appendChild(back);
    }

    setActivePage(record.Name);
    document.title = (record.Term1 ? record.Term1 + ' - ' : '') + (typeof Title !== 'undefined' ? Title : '');
  }

  buildShell();

  window.CDSSSidebar = {
    enabled: true,
    welcomeId,
    pageFromUrl,
    onDataReady,
    beforeRender,
    afterRender,
    syncUrl
  };
})();
