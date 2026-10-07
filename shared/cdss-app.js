// ===========================================================================
// CDSS station page application (shared by every active station page)
//
// Loaded by each stations/<id>/<Name>CDSS.html with
//     <script src="/shared/cdss-app.js"></script>
// as the LAST script in <body>, so that:
//   - the station's configuration block (CDSSlocation, Title, OMjson, ...) in
//     the page <head> has already run - its variables are global and are read
//     directly by the code below;
//   - the page markup (header buttons, #resultContainer, footer) exists.
//
// Station pages therefore contain only markup, styles and configuration;
// all behaviour lives here. Pages that omit the legacy tab buttons
// (combined-only production stations) work unchanged: every access to those
// buttons below tolerates them being absent.
// ===========================================================================

// ===========================================================================
// LAYOUT: responsive table width and font size
// ===========================================================================

// Table-cell font size (px) by viewport width. An entry applies to widths
// below its `maxWidth`; the last entry is the catch-all.
const FONT_SIZE_BREAKPOINTS = [
  { maxWidth: 400, px: 10 },
  { maxWidth: 800, px: 13 },
  { maxWidth: 1200, px: 16 },
  { maxWidth: 1600, px: 19 },
  { maxWidth: Infinity, px: 22 }
];

// Width (px) of the whole content table for a viewport width. Single-column
// pages (plain guidance text) get a wider table on phones than multi-column ones.
function getTableWidthPx(screenWidth, isSingleColumn) {
  if (screenWidth < 400) return isSingleColumn ? 900 : 500;
  if (screenWidth < 800) return isSingleColumn ? 1000 : 600;
  if (screenWidth < 1200) return 1000;
  if (screenWidth < 1600) return 1200;
  return 1400;
}

// Applies the table width and cell font size for the current viewport.
// Must be called after every render (new rows have no font size yet) and on resize.
function adjustFontSize() {
  const table = document.querySelector('.table');
  const tableRows = table.querySelectorAll('tr');
  const screenWidth = window.innerWidth / window.devicePixelRatio;
  const firstRow = tableRows[0];
  const columnsInFirstRow = firstRow ? firstRow.querySelectorAll('td').length : 0;
  const maxColumns = Math.min(columnsInFirstRow, 4);

  table.style.width = getTableWidthPx(screenWidth, maxColumns === 1) + 'px';

  const fontSize = FONT_SIZE_BREAKPOINTS.find(b => screenWidth < b.maxWidth).px + 'px';
  tableRows.forEach(row => {
    row.querySelectorAll('td').forEach(cell => {
      cell.style.fontSize = fontSize;
    });
  });
}

// Call the adjustFontSize function when the DOM is ready
document.addEventListener('DOMContentLoaded', function() {
  adjustFontSize();
});
  
// ===========================================================================
// DATA LOADING
// ===========================================================================
async function fetchJSON(url) {
  const response = await fetch(url);
  return response.json();
}

async function fetchOMData() { return fetchJSON(OMjson); }       // Menus / guidance pages
async function fetchODData() { return fetchJSON(ODjson); }       // VistA order dialogs (legacy)
async function fetchAbxLink() { return fetchJSON(AbxLinkjson); } // Drug name -> URL links

// ===========================================================================
// APPLICATION STATE
// ===========================================================================
let omData = [];            // OMJSON records: every guidance page / menu
let odData = [];            // ODJSON records: VistA order dialogs (legacy)
let selectedData = null;    // Record currently displayed
let currentVersion = null;  // Active tab: 'combined' (default); legacy: 'inpt' | 'outpt' | 'eruc'
let history = [];           // Page names visited, in order
let historyIndex = -1;      // Position of the current page within `history`
let abxLinkData = [];       // [{ Name, URL, RouteFilter }] drug links injected into page text

// Names of the current page's counterparts on the other tabs. Refreshed by
// checkMatchesAndSetButtonAppearance() after every render.
let matchedOutptName = null;
let matchedErucName = null;
let matchedCombinedName = null;

// ===========================================================================
// STATION-SPECIFIC HEADER / FOOTER SETUP
// ===========================================================================

// Station-switcher buttons (shown on the test station only). The button for
// the station we are currently on is hidden.
const STATION_SWITCH_BUTTON_IDS = {
  'Des Moines': 'desMoinesButton',
  'Black Hills': 'blackHillsButton',
  'Fargo': 'fargoButton',
  'Minneapolis': 'minneapolisButton',
  'Omaha': 'omahaButton',
  'St. Cloud': 'stCloudButton',
  'Sioux Falls': 'siouxFallsButton'
};
const ownStationButtonId = STATION_SWITCH_BUTTON_IDS[CDSSlocation];
if (ownStationButtonId) {
  document.getElementById(ownStationButtonId).style.display = 'none';
}

// Optional buttons controlled by the hideButtons* configuration flags.
// (hideButtonsDownloads is unused: the footer download buttons were removed.)
if (hideButtonsIndex === 'True') {
  document.getElementById('indexButton').style.display = 'none';
}
if (hideButtonsHome === 'True') {
  document.getElementById('homeButton').style.display = 'none';
}
if (hideButtonsVersions === 'True') {
  document.querySelector('.buttons-containerVersions').style.display = 'none';
}

// Apply configured text.
document.getElementById('versionTag').textContent = Version;
document.getElementById('pageTitle').textContent = Title;
document.getElementById('mainMenuButton').textContent = MainMenuButton;
document.getElementById('indexButton').textContent = IndexButton;

// ===========================================================================
// SEARCH BOX AND PAGE DROPDOWN
// The hidden <select id="filterDropdown"> is the source of truth for "which
// page is selected"; the search box filters/sorts its options.
// ===========================================================================

// In combined mode, legacy Inpt/Outpt/ERUC source records that have been
// superseded by a Combined page are hidden from the dropdown and from search.
function getVisibleOmData(data = omData) {
  return currentVersion === 'combined' ? data.filter(item => !item.Combined) : data;
}

// All non-empty "Term1".."Term99" values on a record (its searchable titles).
function getItemTerms(item) {
  const terms = [];
  for (let i = 1; i <= 99; i++) {
    const termKey = `Term${i}`;
    if (item[termKey]) {
      terms.push(item[termKey]);
    }
  }
  return terms;
}

// Rebuilds the dropdown: one option per Term of every visible record. Records
// with no Terms are added last as hidden options (still selectable by Name).
function populateDropdown(omData) {
  const dropdown = document.getElementById('filterDropdown');
  dropdown.innerHTML = '';

  const itemsWithoutTerms = [];

  getVisibleOmData(omData).forEach(item => {
    const terms = getItemTerms(item);

    if (terms.length === 0) {
      itemsWithoutTerms.push(item);
    } else {
      terms.forEach(term => {
        const option = document.createElement('option');
        option.value = item.Name;
        option.textContent = term;
        dropdown.appendChild(option);
      });
    }
  });

  itemsWithoutTerms.forEach(item => {
    const option = document.createElement('option');
    option.value = item.Name;
    option.textContent = item.DisplayText || item.Name;
    option.style.display = 'none'; // Make the option invisible
    dropdown.appendChild(option);
  });

  dropdown.scrollTop = 0;
}

// Scores one record against the search text and chooses which of its Terms to
// show in the results list. Returns { relevanceScore, sortTerm }.
//
// Scoring per Term:  exact match of the whole search text  +10000
//                    Term equals one search word           +1000
//                    Term contains one search word         +100
// plus, for legacy records with Contents: whole-word hit +10, substring hit +1.
function scoreSearchMatch(item, searchText, searchTerms) {
  let relevanceScore = 0;
  let matchingTerm = '';        // Term that matched the entire search text
  let closestMatchingTerm = ''; // Best partial match (shortest / earliest)
  const contentTexts = (item.Contents || []).map(content => content.Text ? content.Text.toLowerCase() : '').filter(Boolean);
  const Term1 = item.Term1 ? item.Term1.trim() : '';

  for (let i = 1; i <= 99; i++) {
    const termKey = `Term${i}`;
    if (item[termKey]) {
      const termText = item[termKey].trim();
      const termTextLower = termText.toLowerCase();

      // Check for exact match with the entire searchText
      if (termTextLower === searchText) {
        relevanceScore += 10000;
        matchingTerm = termText;
      } else {
        searchTerms.forEach(term => {
          if (termTextLower === term) {
            relevanceScore += 1000;
            if (!closestMatchingTerm || termText.length < closestMatchingTerm.length) {
              closestMatchingTerm = termText;
            }
          } else if (termTextLower.includes(term)) {
            relevanceScore += 100;
            if (!closestMatchingTerm ||
                termTextLower.indexOf(term) < closestMatchingTerm.toLowerCase().indexOf(term) ||
                (termTextLower.indexOf(term) === closestMatchingTerm.toLowerCase().indexOf(term) && termText.length < closestMatchingTerm.length) ||
                (termTextLower.startsWith(searchText) && !closestMatchingTerm.toLowerCase().startsWith(searchText))) {
              closestMatchingTerm = termText;
            }
          }

          contentTexts.forEach(text => {
            const regex = new RegExp(`\\b${term}\\b`, 'i'); // Match whole words only
            if (regex.test(text)) {
              relevanceScore += 10; // Search term found as a whole word in Contents
            }
            if (text.includes(term)) {
              relevanceScore += 1; // Search term found anywhere in Contents
            }
          });
        });
      }
    }
  }

  // Title shown in the results: exact match, else best partial match, else Term1.
  const sortTerm = matchingTerm || closestMatchingTerm || Term1;
  return { relevanceScore, sortTerm };
}

// Runs on every keystroke in the search box: rebuilds the dropdown with the
// matching pages, best match first (or the full alphabetical list when empty).
function searchData() {
  const searchInput = document.getElementById('searchInput');
  const dropdown = document.getElementById('filterDropdown');
  const searchText = searchInput.value.trim().toLowerCase();

  if (searchText === '') {
    populateDropdown(omData);
    sortDropdownByTerm();
  } else {
    const searchTerms = searchText.split(' ');

    const filteredData = getVisibleOmData()
      .map(item => ({ ...item, ...scoreSearchMatch(item, searchText, searchTerms) }))
      .filter(item => item.relevanceScore > 0)
      .sort((a, b) => b.relevanceScore - a.relevanceScore)
      .filter(item => !item.sortTerm.toLowerCase().includes('index'));

    dropdown.innerHTML = '';

    filteredData.forEach(item => {
      const option = document.createElement('option');
      option.value = item.Name;
      option.textContent = item.sortTerm;
      dropdown.appendChild(option);
    });

    // First line of the list: match count (not selectable)
    const matchCount = dropdown.length;
    const firstLine = document.createElement('option');
    if (matchCount === 0) {
      firstLine.textContent = 'No Matches';
      firstLine.style.color = 'red';
    } else {
      firstLine.textContent = `Matches: ${matchCount}`;
      firstLine.style.color = 'green';
    }
    firstLine.disabled = true;
    firstLine.selected = true;
    dropdown.insertBefore(firstLine, dropdown.firstChild);
  }

  dropdown.scrollTop = 0;
}

// Wires the search box to the dropdown list: typing selects matching options
// and shows the list; clicking elsewhere or choosing an option hides it.
// (Further search-box handlers are registered in the "Event wiring" section.)
function searchAndOpenDropdown() {
  const searchInput = document.getElementById('searchInput');
  const dropdown = document.getElementById('filterDropdown');

  // Select every option whose text contains filterText and show/hide the list.
  function filterDropdownOptions(filterText) {
    const options = dropdown.options;
    let matchFound = false;
    for (let i = 0; i < options.length; i++) {
      if (options[i].text.toLowerCase().indexOf(filterText) !== -1) {
        options[i].selected = true;
        matchFound = true;
      }
    }
    dropdown.size = options.length;
    dropdown.style.display = matchFound ? 'block' : 'none';
  }

  searchInput.addEventListener('input', function () {
    filterDropdownOptions(searchInput.value.trim().toLowerCase());
  });

  // Hide the list when the user clicks anywhere other than the search box or the list.
  document.addEventListener('click', function (event) {
    if (event.target !== searchInput && event.target !== dropdown) {
      dropdown.style.display = 'none';
    }
  });

  // Hide the list once an option is chosen.
  dropdown.addEventListener('change', function () {
    dropdown.style.display = 'none';
    checkMatchesAndSetButtonAppearance();
  });
}

// Call the searchAndOpenDropdown function initially
searchAndOpenDropdown();

// Add event listener to sort the dropdown alphabetically when the search box is clicked but no text has been entered
const searchInput = document.getElementById('searchInput');
searchInput.addEventListener('click', function () {
  if (searchInput.value.trim() === '') {
    filterData({ target: document.getElementById('filterDropdown') }, true);
  }
});

// Call the adjustFontSize function when the window is resized
window.addEventListener('resize', adjustFontSize);
    
// ===========================================================================
// TEXT / URL UTILITIES
// ===========================================================================

// True if `value` parses as an absolute URL (http:, https:, mailto:, ...).
function isValidURL(value) {
  try {
    new URL(value);
    return true;
  } catch (error) {
    return false;
  }
}

// decodeURIComponent that returns the input unchanged if it is malformed.
function safeDecodeURIComponent(value) {
  try {
    return decodeURIComponent(value);
  } catch (error) {
    return value;
  }
}

// Turns an image path written in CMS markdown into a site-absolute URL.
// Absolute URLs / data: / blob: pass through; relative paths are rooted at
// the site (bare filenames are assumed to be CMS uploads in /assets/uploads).
function normalizeContentAssetUrl(rawUrl) {
  const original = (rawUrl || '').trim();
  if (!original) {
    return '';
  }

  if (isValidURL(original) || original.startsWith('data:') || original.startsWith('blob:')) {
    return original;
  }

  if (original.startsWith('//')) {
    return `${window.location.protocol}${original}`;
  }

  let normalized = original.replace(/\\/g, '/');
  while (normalized.startsWith('./')) {
    normalized = normalized.substring(2);
  }
  while (normalized.startsWith('../')) {
    normalized = normalized.substring(3);
  }

  if (normalized.startsWith('/')) {
    return normalized;
  }

  if (normalized.startsWith('assets/')) {
    return `/${normalized}`;
  }

  if (normalized.startsWith('uploads/')) {
    return `/assets/${normalized}`;
  }

  // Sveltia markdown widget can emit bare filenames like "image.png".
  // Treat these as CMS uploads under /assets/uploads.
  if (!normalized.includes('/')) {
    return `/assets/uploads/${normalized}`;
  }

  return `/${normalized}`;
}

// Splits the part inside (...) of a markdown link/image into { url, title }.
// Handles: path "title", path 'title', path (title) and <path with spaces>.
function parseMarkdownTargetParts(rawTarget) {
  const raw = (rawTarget || '').trim();
  if (!raw) {
    return { url: '', title: '' };
  }

  let url = raw;
  let title = '';

  const titleMatch = raw.match(/^(.+?)\s+(?:"([^"]*)"|'([^']*)'|\(([^)]*)\))\s*$/);
  if (titleMatch) {
    url = (titleMatch[1] || '').trim();
    title = (titleMatch[2] || titleMatch[3] || titleMatch[4] || '').trim();
  }

  // Angle-bracket destination support: <path/to/file.png>
  if (url.startsWith('<') && url.endsWith('>')) {
    url = url.substring(1, url.length - 1).trim();
  }

  return { url, title };
}
  
  
// Smoothly scrolls the result table and the page back to the top (called after every navigation).
function scrollToTop() {
  const resultContainer = document.getElementById('resultContainer');
  resultContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
  window.scrollTo({
    top: 0,
    behavior: 'smooth'
  });
}
	
// Function to escape special characters in a string to use in a regular expression
  function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  // Lower-cases and strips everything except a-z and 0-9, so differently
  // punctuated names ('ORZID2 GMENU' vs 'orzid2-gmenu') compare equal.
  function normalizeComparableId(value) {
    return (value || '').toString().toLowerCase().replace(/[^a-z0-9]/g, '');
  }

  // True if `value` looks like a navigable page name: a PageID slug
  // ('septic-bursitis'), the main menu, or a legacy VistA GMENU name.
  function isGuidanceTargetName(value) {
    const trimmed = (value || '').trim();
    if (!trimmed) {
      return false;
    }
    if (/^[a-z0-9][a-z0-9\-]*$/.test(trimmed)) {
      return true;
    }
    const upper = trimmed.toUpperCase();
    if (upper === 'MAIN-MENU' || upper === 'INPT-MAIN') {
      return true;
    }
    return upper.includes('GMENU');
  }

  // In combined mode a link whose target is not a guidance page (e.g. a VistA
  // order item) is shown as plain text instead of a clickable link.
  function shouldSuppressCombinedInternalLink(target, resolvedItem) {
    if (currentVersion !== 'combined') {
      return false;
    }
    const candidate = (resolvedItem || target || '').trim();
    if (!candidate) {
      return false;
    }
    return !isGuidanceTargetName(candidate);
  }

  // ===========================================================================
  // MARKDOWN / RICH TEXT RENDERING (guidance page Text -> DOM)
  // ===========================================================================

  // Appends `text` to `container`, turning every drug name found in
  // abxLinkData (AbxLinks.json) into a green external link. Matching is
  // case-insensitive and whole-word; on overlap the earliest/longest match wins.
  function appendPlainTextWithAbxLinks(container, text) {
    const contentText = (text || '').toString();
    if (!contentText) {
      return;
    }

    if (!Array.isArray(abxLinkData) || abxLinkData.length === 0) {
      container.appendChild(document.createTextNode(contentText));
      return;
    }

    const matches = [];
    abxLinkData.forEach((item) => {
      const name = (item.Name || '').trim();
      const url = (item.URL || '').trim();
      if (!name || !url) {
        return;
      }

      const nameRegex = new RegExp(`\\b${escapeRegExp(name)}\\b`, 'gi');
      let match;
      while ((match = nameRegex.exec(contentText)) !== null) {
        matches.push({
          start: match.index,
          end: match.index + match[0].length,
          label: match[0],
          url
        });
      }
    });

    if (matches.length === 0) {
      container.appendChild(document.createTextNode(contentText));
      return;
    }

    matches.sort((a, b) => {
      if (a.start !== b.start) {
        return a.start - b.start;
      }
      return (b.end - b.start) - (a.end - a.start);
    });

    let cursor = 0;
    matches.forEach((match) => {
      if (match.start < cursor) {
        return;
      }
      if (match.start > cursor) {
        container.appendChild(document.createTextNode(contentText.substring(cursor, match.start)));
      }
      const linkElement = document.createElement('a');
      linkElement.href = match.url;
      linkElement.target = '_blank';
      linkElement.classList.add('AbxLink');
      linkElement.textContent = match.label;
      container.appendChild(linkElement);
      cursor = match.end;
    });

    if (cursor < contentText.length) {
      container.appendChild(document.createTextNode(contentText.substring(cursor)));
    }
  }

  // Index of the first `marker` at/after startIndex that is not escaped by an
  // odd number of backslashes, or -1.
  function findUnescapedMarker(text, marker, startIndex) {
    let index = text.indexOf(marker, startIndex);
    while (index !== -1) {
      let slashCount = 0;
      for (let i = index - 1; i >= 0 && text[i] === '\\'; i -= 1) {
        slashCount += 1;
      }
      if (slashCount % 2 === 0) {
        return index;
      }
      index = text.indexOf(marker, index + marker.length);
    }
    return -1;
  }

  // Appends plain text, optionally with drug-name links.
  function appendPlainTextSegment(container, text, enableAbxLinks) {
    const contentText = (text || '').toString();
    if (!contentText) {
      return;
    }

    if (enableAbxLinks) {
      appendPlainTextWithAbxLinks(container, contentText);
      return;
    }

    container.appendChild(document.createTextNode(contentText));
  }

  // Renders inline markdown (**bold**, __bold__, ~~strike~~, `code`, *italic*,
  // _italic_) into `container`. Finds the earliest opening marker with a
  // matching close, renders the text before it as plain text, and recurses into
  // the marked-up text (nesting is capped at depth 6).
  function appendInlineMarkdownText(container, text, enableAbxLinks = false, depth = 0) {
    const contentText = (text || '').toString();
    if (!contentText) {
      return;
    }

    if (depth > 6) {
      appendPlainTextSegment(container, contentText, enableAbxLinks);
      return;
    }

    const markers = [
      { token: '**', tag: 'strong' },
      { token: '__', tag: 'strong' },
      { token: '~~', tag: 's' },
      { token: '`', tag: 'code' },
      { token: '*', tag: 'em' },
      { token: '_', tag: 'em' }
    ];
    let cursor = 0;
    let renderedInline = false;

    while (cursor < contentText.length) {
      let openIndex = -1;
      let selectedMarker = null;

      markers.forEach((markerInfo) => {
        const candidate = findUnescapedMarker(contentText, markerInfo.token, cursor);
        if (candidate !== -1 && (openIndex === -1 || candidate < openIndex)) {
          openIndex = candidate;
          selectedMarker = markerInfo;
        }
      });

      if (openIndex === -1 || !selectedMarker) {
        break;
      }

      const closeIndex = findUnescapedMarker(
        contentText,
        selectedMarker.token,
        openIndex + selectedMarker.token.length
      );

      if (closeIndex === -1) {
        break;
      }

      if (openIndex > cursor) {
        appendPlainTextSegment(container, contentText.substring(cursor, openIndex), enableAbxLinks);
      }

      const inlineText = contentText.substring(openIndex + selectedMarker.token.length, closeIndex);
      if (inlineText) {
        const inlineElement = document.createElement(selectedMarker.tag);
        if (selectedMarker.tag === 'code') {
          inlineElement.classList.add('markdown-inline-code');
          inlineElement.textContent = inlineText;
        } else {
          appendInlineMarkdownText(inlineElement, inlineText, enableAbxLinks, depth + 1);
        }
        container.appendChild(inlineElement);
        renderedInline = true;
      }

      cursor = closeIndex + selectedMarker.token.length;
    }

    if (cursor < contentText.length) {
      appendPlainTextSegment(container, contentText.substring(cursor), enableAbxLinks);
    } else if (!renderedInline) {
      appendPlainTextSegment(container, contentText, enableAbxLinks);
    }
  }

  // Convenience wrapper: inline markdown with drug-name links enabled.
  function appendTextWithAbxLinks(container, text) {
    appendInlineMarkdownText(container, text, true);
  }

  // ===========================================================================
  // LINK RESOLUTION
  // ===========================================================================

  // Resolves the target of a markdown link ([label](target)) to the page/order
  // name that handleRowClick should open, or null if nothing matches.
  // Lookup order:
  //   0. 'cdss:<name>' prefix -> that name
  //   1. exact PageID (case-insensitive)
  //   2. OM (page) name equal after normalizeComparableId
  //   3. OD (order dialog) name equal after normalizeComparableId
  // (`selectedData` and `label` are unused; kept for existing call sites.)
  function resolveEmbeddedLinkTarget(selectedData, target, label = '') {
    const normalizedTarget = (target || '').trim();
    if (!normalizedTarget) {
      return null;
    }

    if (normalizedTarget.toLowerCase().startsWith('cdss:')) {
      return resolveTargetForCurrentVersion(normalizedTarget.substring(5).trim());
    }

    // 1. Direct PageID lookup: fastest path for combined page-to-page links
    const directPage = omData.find(m =>
      m.Name.trim().toLowerCase() === normalizedTarget.toLowerCase()
    );
    if (directPage) {
      return resolveTargetForCurrentVersion(directPage.Name);
    }

    // 2./3. Global fallback: match the target to OM/OD names by normalized identifier.
    const normalizedTargetId = normalizeComparableId(normalizedTarget);
    const omByNormalized = omData.find(menu =>
      normalizeComparableId(menu.Name) === normalizedTargetId
    );
    if (omByNormalized) {
      return resolveTargetForCurrentVersion(omByNormalized.Name);
    }

    const odByNormalized = odData.find(order =>
      normalizeComparableId(order.Name) === normalizedTargetId
    );
    if (odByNormalized) {
      return odByNormalized.Name;
    }

    return null;
  }

// Finds an OM record by Name (trimmed, case-insensitive), or null.
function findMenuByNameInsensitive(name) {
  const normalized = (name || '').trim().toLowerCase();
  if (!normalized) {
    return null;
  }
  return omData.find(item => (item.Name || '').trim().toLowerCase() === normalized) || null;
}

// Finds every [label](target) link in a line of text. Hand-written scanner
// (not a regex) so labels and targets may contain balanced nested brackets /
// parentheses, e.g. "[Drug [IV]](page-id)". Backslash escapes are skipped.
// Returns [{ index, end, fullMatch, label, target }] in source order.
function extractMarkdownLinks(lineText) {
  const links = [];
  let index = 0;

  while (index < lineText.length) {
    const labelStart = lineText.indexOf('[', index);
    if (labelStart === -1) {
      break;
    }

    let cursor = labelStart + 1;
    let labelDepth = 1;
    while (cursor < lineText.length && labelDepth > 0) {
      const ch = lineText[cursor];
      if (ch === '\\') {
        cursor += 2;
        continue;
      }
      if (ch === '[') {
        labelDepth += 1;
      } else if (ch === ']') {
        labelDepth -= 1;
      }
      cursor += 1;
    }

    if (labelDepth !== 0 || lineText[cursor] !== '(') {
      index = labelStart + 1;
      continue;
    }

    const labelEnd = cursor - 1;
    const targetStart = cursor + 1;
    cursor = targetStart;
    let targetDepth = 1;
    while (cursor < lineText.length && targetDepth > 0) {
      const ch = lineText[cursor];
      if (ch === '\\') {
        cursor += 2;
        continue;
      }
      if (ch === '(') {
        targetDepth += 1;
      } else if (ch === ')') {
        targetDepth -= 1;
      }
      cursor += 1;
    }

    if (targetDepth !== 0) {
      index = labelStart + 1;
      continue;
    }

    const targetEnd = cursor - 1;
    links.push({
      index: labelStart,
      end: cursor,
      fullMatch: lineText.substring(labelStart, cursor),
      label: lineText.substring(labelStart + 1, labelEnd),
      target: lineText.substring(targetStart, targetEnd)
    });
    index = cursor;
  }

  return links;
}

// Finds ![alt](target) images. Returns [{ index, end, fullMatch, alt, target }].
function extractMarkdownImages(lineText) {
  const images = [];
  const imageRegex = /!\[([^\]]*)\]\(([^)]+)\)/g;
  let match;

  while ((match = imageRegex.exec(lineText)) !== null) {
    images.push({
      index: match.index,
      end: match.index + match[0].length,
      fullMatch: match[0],
      alt: match[1],
      target: match[2]
    });
  }

  return images;
}

// Finds raw <img src="..." alt="..."> tags (same result shape as extractMarkdownImages).
function extractHtmlImages(lineText) {
  const images = [];
  const imageTagRegex = /<img\b[^>]*>/gi;
  let tagMatch;

  while ((tagMatch = imageTagRegex.exec(lineText)) !== null) {
    const fullTag = tagMatch[0];
    const srcMatch = fullTag.match(/\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/i);
    if (!srcMatch) {
      continue;
    }
    const altMatch = fullTag.match(/\balt\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/i);

    images.push({
      index: tagMatch.index,
      end: tagMatch.index + fullTag.length,
      fullMatch: fullTag,
      alt: altMatch ? (altMatch[1] || altMatch[2] || altMatch[3] || '') : '',
      target: srcMatch[1] || srcMatch[2] || srcMatch[3] || ''
    });
  }

  return images;
}

// Tab crosswalk. In combined mode, maps a legacy page name (an Inpt/Outpt/ERUC
// source menu) to its Combined equivalent, either via the source record's
// `Combined` field or by finding the combined page that points back to it.
// Outside combined mode (or with no mapping) the name is returned unchanged.
function resolveTargetForCurrentVersion(targetName) {
  const normalizedTarget = (targetName || '').trim();
  if (!normalizedTarget || currentVersion !== 'combined') {
    return normalizedTarget;
  }

  const directTarget = findMenuByNameInsensitive(normalizedTarget);
  if (directTarget && directTarget.Combined) {
    const mappedCombined = findMenuByNameInsensitive(directTarget.Combined);
    if (mappedCombined) {
      return mappedCombined.Name;
    }
  }

  const reverseMappedCombined = omData.find(item =>
    (item.Inpt || '').trim().toLowerCase() === normalizedTarget.toLowerCase() ||
    (item.Outpt || '').trim().toLowerCase() === normalizedTarget.toLowerCase() ||
    (item.ERUC || '').trim().toLowerCase() === normalizedTarget.toLowerCase()
  );
  if (reverseMappedCombined) {
    return reverseMappedCombined.Name;
  }

  return normalizedTarget;
}

// Classifies one source line by its block-level markdown syntax. Returns
// { text, classes, prefix }: the line text with the syntax removed, the CSS
// classes to apply (heading level, blockquote, list item, rule) and a bullet /
// number prefix for list items.
function parseRichTextLineSyntax(lineText) {
  const rawLine = (lineText || '').toString();
  const parsed = {
    text: rawLine,
    classes: [],
    prefix: ''
  };

  if (/^\s{0,3}(([-*_])\s*){3,}$/.test(rawLine)) {
    parsed.text = '';
    parsed.classes.push('markdown-rule');
    return parsed;
  }

  const headingMatch = rawLine.match(/^\s{0,3}(#{1,6})\s+(.*)$/);
  if (headingMatch) {
    const level = headingMatch[1].length;
    parsed.text = headingMatch[2];
    parsed.classes.push('bold', `markdown-heading-${level}`);
    return parsed;
  }

  const blockQuoteMatch = rawLine.match(/^\s{0,3}>\s?(.*)$/);
  if (blockQuoteMatch) {
    parsed.text = blockQuoteMatch[1];
    parsed.classes.push('markdown-blockquote');
    return parsed;
  }

  const unorderedListMatch = rawLine.match(/^\s{0,3}[-*+]\s+(.*)$/);
  if (unorderedListMatch) {
    parsed.text = unorderedListMatch[1];
    parsed.prefix = '\u2022 ';
    parsed.classes.push('markdown-list-item');
    return parsed;
  }

  const orderedListMatch = rawLine.match(/^\s{0,3}(\d+)\.\s+(.*)$/);
  if (orderedListMatch) {
    parsed.text = orderedListMatch[2];
    parsed.prefix = `${orderedListMatch[1]}. `;
    parsed.classes.push('markdown-list-item');
  }

  return parsed;
}

// Banner heading convention: a plain H1 ('# Title') as the VERY FIRST
// non-blank line of a page's Text is rendered as the full-width banner.
// This is ordinary markdown -- Sveltia's WYSIWYG shows it as a real heading
// -- so no special authoring syntax is needed; the runtime alone decides to
// give the first H1 the full-width/highlighted banner treatment instead of
// the normal inline heading treatment. Only the first line qualifies:
// an H1 appearing later in the document is just a regular heading.
const TOP_BANNER_HEADING_REGEX = /^\s{0,3}#\s+(.*?)\s*$/;

// Pulls the leading H1 (if any) out of an array of source lines so it can be
// rendered as a standalone full-width row above any column layout. Only the
// first non-blank line is ever eligible; blank lines before it are left in
// place (stripBlankLinesAroundTightLines/normal rendering handles those).
function extractTopBanner(lines) {
  let index = 0;
  while (index < lines.length && (lines[index] || '').trim() === '') {
    index++;
  }
  if (index < lines.length) {
    const bannerMatch = (lines[index] || '').match(TOP_BANNER_HEADING_REGEX);
    if (bannerMatch) {
      const remainingLines = lines.slice(0, index).concat(lines.slice(index + 1));
      return { bannerText: bannerMatch[1].trim(), remainingLines };
    }
  }
  return { bannerText: null, remainingLines: lines };
}

// Heading lines (## Title, including the top banner's # Title), and lines
// that are ENTIRELY a single markdown link ([label](target)), are all
// block-level elements that authors conventionally surround with a blank
// line in markdown source -- that's normal, purely structural markdown
// syntax (Sveltia's WYSIWYG never shows it as visible extra content: a link
// is just another inline element in the flow, and a blank line is just a
// paragraph separator). Our row-per-physical-line renderers
// (createRichTextTable / createStructuredRichTextNavigationTable), however,
// render every blank line as its own visible spacer row, which doubles up
// with the heading/link's own row and produces a large visible gap that
// isn't in the CMS preview. isTightBoundaryLine + stripBlankLinesAroundTightLines
// drop only the blank line(s) immediately touching one of these lines so
// they sit flush against surrounding content, while leaving blank lines
// elsewhere (real paragraph/section spacing) untouched.
function isTightBoundaryLine(line) {
  const text = (line || '').toString();
  if (/^\s{0,3}#{1,6}\s+.+$/.test(text)) {
    return true;
  }
  // A line that is nothing but a single markdown link (optionally with a
  // trailing punctuation mark), e.g. "[Septic bursitis](septic-bursitis)".
  return /^\s{0,3}\[[^\]]+\]\([^)]+\)[.,;:]?\s*$/.test(text);
}

function stripBlankLinesAroundTightLines(lines) {
  const result = [];
  let i = 0;
  while (i < lines.length) {
    if ((lines[i] || '').trim() === '') {
      let j = i;
      while (j < lines.length && (lines[j] || '').trim() === '') {
        j++;
      }
      const prevIsTight = i > 0 && isTightBoundaryLine(lines[i - 1]);
      const nextIsTight = j < lines.length && isTightBoundaryLine(lines[j]);
      if (!(prevIsTight || nextIsTight)) {
        for (let k = i; k < j; k++) {
          result.push(lines[k]);
        }
      }
      i = j;
      continue;
    }
    result.push(lines[i]);
    i++;
  }
  return result;
}

function appendBannerRow(tbody, bannerText, colSpan) {
  const bannerRow = document.createElement('tr');
  const bannerCell = document.createElement('td');
  bannerCell.colSpan = colSpan;
  bannerCell.style.backgroundColor = 'lightblue';
  // Classes go on an inner div (not the <td> itself) so it matches the same
  // markup shape as a regular "##" heading line (appendRichTextLineContent
  // puts classes on the line's div, never the td). Otherwise ".table td"'s
  // font-family rule (specificity 0,1,1) beats ".bold"/".markdown-heading-2"
  // (specificity 0,1,0) when applied straight to the td, and the banner text
  // silently renders in the regular (non-bold) font.
  const bannerTextElement = document.createElement('div');
  bannerTextElement.classList.add('bold', 'markdown-heading-2');
  bannerTextElement.textContent = bannerText;
  bannerCell.appendChild(bannerTextElement);
  bannerRow.appendChild(bannerCell);
  tbody.appendChild(bannerRow);
}

// Appends a fenced ``` code block as <pre><code>.
function appendCodeBlockElement(container, codeLines) {
  const pre = document.createElement('pre');
  pre.classList.add('markdown-code-block');
  const code = document.createElement('code');
  code.textContent = codeLines.join('\n');
  pre.appendChild(code);
  container.appendChild(pre);
}

// Renders lines as stacked <div>s inside ONE container (used for each column
// of the multi-column layouts), honouring ``` code fences. Blank lines become
// visible spacers unless skipEmptyLines is true.
function appendRichTextLinesWithCodeFences(container, lines, selectedData, skipEmptyLines = true) {
  let inCodeBlock = false;
  let codeLines = [];

  lines.forEach((line) => {
    const fenceMatch = (line || '').match(/^\s*```/);
    if (fenceMatch) {
      if (!inCodeBlock) {
        inCodeBlock = true;
        codeLines = [];
      } else {
        appendCodeBlockElement(container, codeLines);
        inCodeBlock = false;
        codeLines = [];
      }
      return;
    }

    if (inCodeBlock) {
      codeLines.push(line || '');
      return;
    }

    if (!line || !line.trim()) {
      if (!skipEmptyLines) {
        const emptyLine = document.createElement('div');
        emptyLine.classList.add('markdown-empty-line');
        emptyLine.textContent = '\u00a0';
        container.appendChild(emptyLine);
      }
      return;
    }

    const lineElement = document.createElement('div');
    appendRichTextLineContent(lineElement, line, selectedData);
    container.appendChild(lineElement);
  });

  if (inCodeBlock) {
    appendCodeBlockElement(container, codeLines);
  }
}

// Renders one markdown image token. An unusable image path is shown as its source text.
function appendImageToken(container, match, isCombined) {
  const imageParts = parseMarkdownTargetParts(match.target || '');
  const imageUrl = normalizeContentAssetUrl(safeDecodeURIComponent((imageParts.url || '').trim()));
  if (!imageUrl) {
    appendInlineMarkdownText(container, match.fullMatch, isCombined);
    return;
  }

  const imageElement = document.createElement('img');
  imageElement.src = imageUrl;
  imageElement.alt = (match.alt || '').trim();
  if (imageParts.title) {
    imageElement.title = imageParts.title;
  }
  imageElement.classList.add('markdown-image');
  container.appendChild(imageElement);
}

// Renders one [label](target) token as either
//   - an external link (target is an absolute URL), or
//   - an internal link: a clickable label that opens the target page, or
//   - plain text, when the target cannot be resolved (combined mode shows just
//     the label; legacy tabs show the raw markdown).
function appendLinkToken(container, match, selectedData, isCombined) {
  const label = (match.label || '').trim();
  const linkParts = parseMarkdownTargetParts(match.target || '');
  const target = safeDecodeURIComponent((linkParts.url || '').trim());

  if (isValidURL(target)) {
    const externalLink = document.createElement('a');
    externalLink.href = target;
    externalLink.target = '_blank';
    externalLink.classList.add('AbxLink');
    appendInlineMarkdownText(externalLink, label, false);
    container.appendChild(externalLink);
    return;
  }

  const resolvedItem = resolveEmbeddedLinkTarget(selectedData, target, label);
  if (resolvedItem && !shouldSuppressCombinedInternalLink(target, resolvedItem)) {
    const rowClickElement = document.createElement('a');
    rowClickElement.classList.add('clickable');
    appendInlineMarkdownText(rowClickElement, label, false);
    rowClickElement.addEventListener('click', () => {
      handleRowClick({ Item: resolvedItem, Text: label }, false);
    });
    container.appendChild(rowClickElement);
  } else {
    appendInlineMarkdownText(container, isCombined ? label : match.fullMatch, isCombined);
  }
}

// Images (markdown and <img>) and links found in a line, in source order.
// Each token is { type: 'image' | 'link', index, end, ... }. When tokens overlap,
// the one that starts first (then the longest) wins; the rest are skipped by the caller.
function findInlineTokens(contentText) {
  const tokens = [];
  extractMarkdownImages(contentText).forEach((image) => tokens.push({ type: 'image', ...image }));
  extractHtmlImages(contentText).forEach((image) => tokens.push({ type: 'image', ...image }));
  extractMarkdownLinks(contentText)
    .filter((link) => !(link.index > 0 && contentText[link.index - 1] === '!')) // "![" starts an image, not a link
    .forEach((link) => tokens.push({ type: 'link', ...link }));
  tokens.sort((a, b) => {
    if (a.index !== b.index) {
      return a.index - b.index;
    }
    return b.end - a.end;
  });
  return tokens;
}

// Renders ONE source line into `container`: block syntax (heading, list item,
// quote, rule) becomes CSS classes, the rest is inline content. Drug-name links
// are only injected in combined mode.
function appendRichTextLineContent(container, lineText, selectedData) {
  const parsedLine = parseRichTextLineSyntax(lineText);
  parsedLine.classes.forEach((className) => container.classList.add(className));

  if (parsedLine.classes.includes('markdown-rule')) {
    const hr = document.createElement('hr');
    hr.classList.add('markdown-rule');
    container.appendChild(hr);
    return;
  }

  if (parsedLine.prefix) {
    container.appendChild(document.createTextNode(parsedLine.prefix));
  }

  const isCombined = currentVersion === 'combined';
  const contentText = parsedLine.text;
  let currentIndex = 0;

  findInlineTokens(contentText).forEach((match) => {
    if (match.index < currentIndex) {
      return; // overlaps a token that was already rendered
    }

    const plainText = contentText.substring(currentIndex, match.index);
    if (plainText) {
      appendInlineMarkdownText(container, plainText, isCombined);
    }

    if (match.type === 'image') {
      appendImageToken(container, match, isCombined);
    } else {
      appendLinkToken(container, match, selectedData, isCombined);
    }
    currentIndex = match.end;
  });

  if (currentIndex < contentText.length) {
    appendInlineMarkdownText(container, contentText.substring(currentIndex), isCombined);
  }
}

// ===========================================================================
// PAGE LAYOUTS
// createOMTable() picks one renderer per page:
//   createStructuredRichTextNavigationTable - Text has <!-- COLUMN n --> markers
//   createCombinedMainMenuTable             - the combined main menu
//   createRichTextTable                     - ordinary single-column guidance page
//   createLegacyRowTable                    - legacy VistA menus (Contents rows/columns)
// All of them end by calling showTable().
// ===========================================================================

// A page uses the multi-column navigation layout if its Text contains a column
// delimiter: <!-- COLUMN 2 -->, <!-- COLUMN 3 -->, ... or the older
// <!-- RIGHT COLUMN --> (kept for backward compatibility).
function isStructuredRichTextNavigationPage(selectedData) {
  if (!selectedData || typeof selectedData.Text !== 'string') {
    return false;
  }
  return /<!--\s*(RIGHT COLUMN|COLUMN\s+\d+)\s*-->/i.test(selectedData.Text);
}

// Puts a finished table into #resultContainer (replacing the old page) and
// refreshes the tab/back/forward button states.
function showTable(table) {
  const resultContainer = document.getElementById('resultContainer');
  resultContainer.innerHTML = '';
  resultContainer.appendChild(table);
  checkMatchesAndSetButtonAppearance();
  forwardBackButtonActivate();
}

// Footer row under every page: "Page ID: <slug>", or "Page Target: <name>" for
// legacy (non-slug) names. `colSpan` is only set when given.
function appendPageIdRow(tbody, pageName, colSpan) {
  const itemRow = document.createElement('tr');
  const itemCell = document.createElement('td');
  if (colSpan !== undefined) {
    itemCell.colSpan = colSpan;
  }
  const isPageID = /^[a-z0-9][a-z0-9\-]*$/.test(pageName);
  itemCell.textContent = (isPageID ? 'Page ID: ' : 'Page Target: ') + pageName;
  itemRow.appendChild(itemCell);
  tbody.appendChild(itemRow);
}

// One table row holding a fenced code block.
function appendCodeBlockRow(tbody, codeLines) {
  const codeRow = document.createElement('tr');
  const codeCell = document.createElement('td');
  appendCodeBlockElement(codeCell, codeLines);
  codeRow.appendChild(codeCell);
  tbody.appendChild(codeRow);
}

// Multi-column navigation page. The Text is split at the column delimiters;
// on wide screens (>= 900px) each part becomes a column of ONE row, on narrow
// screens the parts are stacked in source order. A leading "# Title" becomes a
// full-width banner row.
function createStructuredRichTextNavigationTable(selectedData) {
  const table = document.createElement('table');
  table.classList.add('table');
  const tbody = document.createElement('tbody');
  const lines = (selectedData.Text || '').split(/\r?\n/);

  const { bannerText: topBanner, remainingLines: rawContentLines } = extractTopBanner(lines);
  const contentLines = stripBlankLinesAroundTightLines(rawContentLines);

  // Split content into sections at <!-- RIGHT COLUMN --> / <!-- COLUMN n --> markers.
  const delimiterRegex = /^<!--\s*(RIGHT COLUMN|COLUMN\s+\d+)\s*-->$/i;
  const sections = [[]];
  contentLines.forEach((line) => {
    if (delimiterRegex.test(line.trim())) {
      sections.push([]);
      return;
    }
    sections[sections.length - 1].push(line);
  });

  // Remove trailing empty sections caused by accidental extra delimiters
  while (sections.length > 1 && sections[sections.length - 1].every(line => !line.trim())) {
    sections.pop();
  }

  const screenWidth = window.innerWidth / (window.devicePixelRatio || 1);
  const useMultiColumns = sections.length > 1 && screenWidth >= 900;
  const colCount = useMultiColumns ? sections.length : 1;

  if (topBanner) {
    appendBannerRow(tbody, topBanner, colCount);
  }

  if (useMultiColumns) {
    const contentRow = document.createElement('tr');
    contentRow.style.verticalAlign = 'top';
    sections.forEach(sectionLines => {
      const cell = document.createElement('td');
      cell.style.verticalAlign = 'top';
      cell.style.width = (100 / sections.length) + '%';
      appendRichTextLinesWithCodeFences(cell, sectionLines, selectedData, false);
      contentRow.appendChild(cell);
    });
    tbody.appendChild(contentRow);
  } else {
    // Single column: one row per section, in source order
    sections.forEach(sectionLines => {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      appendRichTextLinesWithCodeFences(cell, sectionLines, selectedData, false);
      row.appendChild(cell);
      tbody.appendChild(row);
    });
  }

  appendPageIdRow(tbody, selectedData.Name, colCount);

  table.appendChild(tbody);
  showTable(table);
}

// Ordinary guidance page: one table row per source line (blank lines become
// spacer rows), plus an optional full-width banner row for a leading "# Title".
function createRichTextTable(selectedData) {
  const table = document.createElement('table');
  table.classList.add('table');
  const tbody = document.createElement('tbody');
  const content = typeof selectedData.Text === 'string' ? selectedData.Text : '';
  const allLines = content.split(/\r?\n/);

  const { bannerText: topBanner, remainingLines: rawLines } = extractTopBanner(allLines);
  const lines = stripBlankLinesAroundTightLines(rawLines);
  if (topBanner) {
    appendBannerRow(tbody, topBanner, 1);
  }

  let inCodeBlock = false;
  let codeLines = [];

  lines.forEach((line) => {
    if (/^\s*```/.test(line)) {
      // A ``` line opens a code block, or closes the open one.
      if (!inCodeBlock) {
        inCodeBlock = true;
        codeLines = [];
      } else {
        appendCodeBlockRow(tbody, codeLines);
        inCodeBlock = false;
        codeLines = [];
      }
      return;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      return;
    }

    const bodyRow = document.createElement('tr');
    const displayCell = document.createElement('td');
    const lineElement = document.createElement('div');

    if (line.trim() !== '') {
      appendRichTextLineContent(lineElement, line, selectedData);
    } else {
      lineElement.classList.add('markdown-empty-line');
      lineElement.textContent = '\u00a0';
    }

    displayCell.appendChild(lineElement);
    bodyRow.appendChild(displayCell);
    tbody.appendChild(bodyRow);
  });

  if (inCodeBlock) {
    appendCodeBlockRow(tbody, codeLines); // unterminated code fence
  }

  appendPageIdRow(tbody, selectedData.Name);

  table.appendChild(tbody);
  showTable(table);
}

// The combined main menu: each "## Heading" starts a section (heading plus its
// links). Sections are laid out in 2 columns (1 column below 900px).
function createCombinedMainMenuTable(selectedData) {
  const table = document.createElement('table');
  table.classList.add('table');
  const tbody = document.createElement('tbody');
  const content = typeof selectedData.Text === 'string' ? selectedData.Text : '';
  const lines = content.split(/\r?\n/);
  const sections = [];
  let currentSection = null;

  lines.forEach((line) => {
    const headingMatch = line.match(/^\s{0,3}#{1,6}\s+(.*)$/);
    if (headingMatch) {
      currentSection = { heading: headingMatch[1].trim(), lines: [] };
      sections.push(currentSection);
      return;
    }

    if (!line.trim()) {
      return;
    }

    if (!currentSection) {
      currentSection = { heading: '', lines: [] }; // text before the first heading
      sections.push(currentSection);
    }
    currentSection.lines.push(line);
  });

  const screenWidth = window.innerWidth / (window.devicePixelRatio || 1);
  const columns = screenWidth < 900 ? 1 : 2;

  for (let i = 0; i < sections.length; i += columns) {
    const bodyRow = document.createElement('tr');

    for (let c = 0; c < columns; c++) {
      const section = sections[i + c];
      const displayCell = document.createElement('td');
      if (!section) {
        bodyRow.appendChild(displayCell); // pad the last row
        continue;
      }

      if (section.heading) {
        const headingElement = document.createElement('div');
        headingElement.classList.add('bold');
        appendInlineMarkdownText(headingElement, section.heading, false);
        displayCell.appendChild(headingElement);
      }

      appendRichTextLinesWithCodeFences(displayCell, section.lines, selectedData, false);

      bodyRow.appendChild(displayCell);
    }

    tbody.appendChild(bodyRow);
  }

  appendPageIdRow(tbody, selectedData.Name, columns);

  table.appendChild(tbody);
  showTable(table);
}

// Entry point for rendering a page record (from OMJSON) into #resultContainer.
function createOMTable(selectedData) {
  if (!selectedData) {
    return;
  }

  if (isStructuredRichTextNavigationPage(selectedData)) {
    createStructuredRichTextNavigationTable(selectedData);
    return;
  }

  if (selectedData.Name === combinedMenu && typeof selectedData.Text === 'string') {
    createCombinedMainMenuTable(selectedData);
    return;
  }

  const hasLegacyContents = Array.isArray(selectedData.Contents) && selectedData.Contents.length > 0;
  if (!hasLegacyContents && typeof selectedData.Text === 'string') {
    createRichTextTable(selectedData);
    return;
  }

  createLegacyRowTable(selectedData);
}

// LEGACY: builds the text of one legacy table cell with drug names linked.
// Every drug is linked at most once per table row (`matchedTexts`), and
// `lastMatchedIndexes[rowIndex]` remembers where the last link in the row ended.
// (Combined pages use appendInlineMarkdownText instead.)
function buildLegacyAbxLinkedText(contentText, matchedTexts, lastMatchedIndexes, rowIndex) {
  const linkContainer = document.createElement('a');
  const lowerText = contentText.toLowerCase();
  const matchingURLs = abxLinkData
    .filter(item =>
      item &&
      typeof item.Name === 'string' && item.Name.trim() !== '' &&
      typeof item.URL === 'string' && item.URL.trim() !== ''
    )
    .filter(item => lowerText.includes(item.Name.toLowerCase()));
  const sortedMatchingURLs = matchingURLs.sort((a, b) => {
    return lowerText.indexOf(a.Name.toLowerCase()) - lowerText.indexOf(b.Name.toLowerCase());
  });

  let currentIndex = 0;
  sortedMatchingURLs.forEach(matchingURL => {
    const { Name, URL: linkUrl } = matchingURL;
    const escapedName = escapeRegExp(Name.trim());
    if (!escapedName) {
      return;
    }
    const nameRegex = new RegExp(`\\b${escapedName}\\b`, 'gi');
    let match;
    while ((match = nameRegex.exec(contentText)) !== null) {
      if (match[0].length === 0) {
        nameRegex.lastIndex++;
        continue;
      }
      if (currentIndex > match.index) {
        currentIndex = match.index + match[0].length;
        continue;
      }
      const nonLinkText = contentText.substring(currentIndex, match.index);
      const linkText = match[0].toLowerCase();
      if (matchedTexts.has(linkText)) {
        // Already linked once in this row: keep it as plain text
        const remainingText = contentText.substring(lastMatchedIndexes[rowIndex], match.index);
        linkContainer.appendChild(document.createTextNode(remainingText));
        currentIndex = match.index + match[0].length;
        continue;
      }
      const linkElement = document.createElement('a');
      linkElement.href = linkUrl;
      linkElement.classList.add('AbxLink');
      linkElement.target = '_blank';
      linkElement.textContent = match[0];
      linkContainer.appendChild(document.createTextNode(nonLinkText));
      linkContainer.appendChild(linkElement);
      matchedTexts.add(linkText);
      lastMatchedIndexes[rowIndex] = match.index + match[0].length;
      currentIndex = match.index + match[0].length;
    }
  });
  if (currentIndex < contentText.length) {
    const remainingText = contentText.substring(lastMatchedIndexes[rowIndex]);
    linkContainer.appendChild(document.createTextNode(remainingText));
  }
  return linkContainer;
}

// LEGACY: renders a VistA menu record whose Contents is a list of cells
// ({ Row, Column, Text, Item, Header, ... }). Cells whose Item is an order
// menu / link become clickable; other Items get an information symbol that
// opens the order dialog. Top rows written entirely in capitals get a banner colour.
function createLegacyRowTable(selectedData) {
  const table = document.createElement('table');
  table.classList.add('table');
  const tbody = document.createElement('tbody');
  const { Contents } = selectedData;
  const maxRow = Math.max(...Contents.map(item => item.Row));
  const columns = Math.max(...Contents.map(item => item.Column));

  // Where the last drug link in each row ended (see buildLegacyAbxLinkedText)
  const lastMatchedIndexes = new Array(maxRow).fill(0);

  for (let row = 1; row <= maxRow; row++) {
    const matchedTexts = new Set(); // drugs already linked in this row
    let allUpperCase = true;
    const bodyRow = document.createElement('tr');

    for (let column = 1; column <= columns; column++) {
      const matchingItems = Contents.filter(
        item => item.Row === row && item.Column === column
      );
      const displayCell = document.createElement('td');

      matchingItems.forEach(matchingItem => {
        const { Text, Item, Header, DisplayText } = matchingItem;
        const cellContent = Text || DisplayText || Item || '';
        const cellContentElement = document.createElement('Div');
        const isMenuOrLink = Boolean(Item) && (Item.startsWith(MenuPrefix) || Item.startsWith(LinkPrefix));

        if (isMenuOrLink) {
          const rowClickElement = document.createElement('a');
          rowClickElement.classList.add('clickable');
          rowClickElement.addEventListener('click', () => {
            handleRowClick(matchingItem, false);
          });
          rowClickElement.textContent = cellContent;
          cellContentElement.appendChild(rowClickElement);
        } else if (abxLinkData.length > 0) {
          cellContentElement.appendChild(
            buildLegacyAbxLinkedText(cellContent, matchedTexts, lastMatchedIndexes, row - 1)
          );
        } else {
          cellContentElement.textContent = cellContent;
        }

        // Order dialogs (any Item that is not a menu) get an information symbol
        if (Item && !Item.startsWith(MenuPrefix)) {
          const clickableSymbol = document.createElement('a');
          clickableSymbol.textContent = " \u24d8";
          clickableSymbol.classList.add('clickable');
          clickableSymbol.addEventListener('click', () => {
            handleRowClick(matchingItem, true);
          });
          cellContentElement.appendChild(clickableSymbol);
        }

        if (Header === 1) {
          cellContentElement.classList.add('bold');
          displayCell.classList.add('bold');
        }
        displayCell.appendChild(cellContentElement);
        if (cellContent !== cellContent.toUpperCase()) {
          allUpperCase = false;
        }
      });
      bodyRow.appendChild(displayCell);
    }

    if (allUpperCase && row <= 5 && bodyRow.innerText.trim() !== '') {
      bodyRow.style.backgroundColor = 'lightblue';
    }

    tbody.appendChild(bodyRow);
  }

  appendPageIdRow(tbody, selectedData.Name);

  table.appendChild(tbody);
  showTable(table);
}

// ===========================================================================
// NAVIGATION: back/forward buttons, row clicks, order-dialog lookups
// ===========================================================================

// Greys out a button (inactive) or restores it (active).
function setNavButtonActive(button, isActive) {
  button.classList.toggle('inactive-button', !isActive);
  button.style.color = isActive ? '' : 'grey';
}

// Enables/disables the back and forward buttons from the history position.
function forwardBackButtonActivate() {
  setNavButtonActive(document.getElementById('goForwardButton'), historyIndex < history.length - 1);
  setNavButtonActive(document.getElementById('goBackButton'), historyIndex > 0);
}

// Opens the page/order named by `item.Item` (a link or table cell was clicked).
//   1. A page (OMJSON record): shown via createOMTable. In combined mode the
//      name is first mapped to its Combined equivalent.
//   2. An order dialog (ODJSON record), legacy: with ClickSymbol (the info
//      symbol) the dialog is shown; a plain click on an order link looks up the
//      template-field URLs instead (findMatches).
async function handleRowClick(item, ClickSymbol) {
  const requestedTarget = item && item.Item ? item.Item : '';
  const resolvedTarget = resolveTargetForCurrentVersion(requestedTarget);
  const matchingItem = omData.find(
    omItem => omItem.Name.trim().toLowerCase() === resolvedTarget.trim().toLowerCase()
  );
  const dropdown = document.getElementById('filterDropdown');

  if (matchingItem) {
    selectedData = matchingItem;
    dropdown.value = matchingItem.Name;
    pushHistory(matchingItem.Name);
    createOMTable(matchingItem);
  } else {
    const matchingODItem = odData.find(
      odItem => odItem.Name.trim().toLowerCase() === requestedTarget.trim().toLowerCase()
    );

    if (matchingODItem) {
      if (ClickSymbol) {
        selectedData = matchingODItem;
        createODTable(selectedData);
        pushHistory(selectedData.Name);
      } else if (matchingODItem.Name.startsWith(LinkPrefix)) {
        await findMatches(matchingODItem);
      }
    }
  }
  scrollToTop();
  adjustFontSize();
}

// LEGACY: for an order dialog, finds the template fields (from the .txml file)
// referenced by its WordProcessing1..20 text. One matching URL is opened
// directly; several are listed in a new tab; none shows the order dialog table.
// Returns the list of matches.
async function findMatches(matchingItem) {
    try {
        const txmlData = await fetchAndParseXML(txmlFile);
        const odData = await fetchODData(); // fresh copy of the order dialogs

        const matches = [];

        const filteredODData = odData.filter(odItem =>
            odItem.Name.trim().toLowerCase() === matchingItem.Name.trim().toLowerCase()
        );

        for (const item of filteredODData) {
            const itemMatches = [];
            const urls = [];

            for (let i = 1; i <= 20; i++) {
                const wordProcessingField = item[`WordProcessing${i}`];
                if (wordProcessingField && wordProcessingField.trim() !== '') {
                    // txml field names may contain * wildcards
                    const matchesInTxml = txmlData.fields.filter(field => new RegExp(field.name.replace(/\*/g, '.*'), 'i').test(wordProcessingField));
                    matchesInTxml.forEach(match => {
                        itemMatches.push({
                            txmlName: match.name,
                            txmlURL: match.url,
                            txmlDefaultText: match.defaultText,
                            odItem: item
                        });
                        if (match.url) {
                            urls.push(match.url);
                        }
                    });
                }
            }

            matches.push(...itemMatches);

            if (urls.length === 1) {
                window.open(urls[0], '_blank');
            } else if (urls.length > 1) {
                const popupContent = itemMatches
                    .filter(match => match.txmlURL)
                    .map(match => `<a href="${match.txmlURL}" target="_self">${match.txmlDefaultText || match.txmlName}</a>`)
                    .join('<br>');

                const newTab = window.open("", "_blank");
                newTab.document.write(`<html><head><title>Select CDSS Link</title></head><body>Multiple links in CDSS order dialog. Select one below to open.<br>${popupContent}</body></html>`);
            } else {
                createODTable(item);
                pushHistory(item.Name);
            }
        }

        return matches;
    } catch (error) {
        console.error("Error finding matches:", error);
        return [];
    }
}

// LEGACY: loads the template-field (.txml) file and returns
// { boilerplateTexts: [...], fields: [{ name, type, url, defaultText, ... }] }.
// On any error, logs it and returns empty lists.
async function fetchAndParseXML(txmlFile) {
    try {
        const response = await fetch(txmlFile);
        if (!response.ok) {
            throw new Error('Network response was not ok ' + response.statusText);
        }
        const xmlText = await response.text();
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlText, "text/xml");

        const boilerplateTexts = Array.from(xmlDoc.querySelectorAll("BOILERPLATE_TEXT p"), p => p.textContent);

        const fields = Array.from(xmlDoc.querySelectorAll("TEMPLATE_FIELDS FIELD")).map(field => {
            // Text of the child element <selector>, or null if it is absent
            const childText = (selector) => {
                const element = field.querySelector(selector);
                return element ? element.textContent : null;
            };
            return {
                name: field.getAttribute("NAME"),
                type: childText("TYPE"),
                inactive: childText("INACTIVE"),
                length: childText("LENGTH"),
                defaultText: childText("DEFAULT_TEXT"),
                defaultIndex: childText("DEFAULT_INDEX"),
                required: childText("REQUIRED"),
                separateLines: childText("SEPARATE_LINES"),
                maxLength: childText("MAX_LENGTH"),
                indent: childText("INDENT"),
                pad: childText("PAD"),
                minValue: childText("MIN_VALUE"),
                maxValue: childText("MAX_VALUE"),
                increment: childText("INCREMENT"),
                url: childText("URL"),
                items: childText("ITEMS")
            };
        });

        return { boilerplateTexts, fields };
    } catch (error) {
        console.error("Error fetching or parsing the XML file:", error);
        return { boilerplateTexts: [], fields: [] };
    }
}

// LEGACY: shows a VistA order dialog (ODJSON record, or its Name) as a table:
// components (each with an info symbol that opens that component), the other
// fields, then WordProcessing fields whose info symbol appends the matching
// template-field details to the table.
async function createODTable(selectedItem) {
    // Check if selectedItem is already an object or a string
    const itemData = typeof selectedItem === 'string'
        ? odData.find(item => item.Name === selectedItem)
        : selectedItem;

    if (!itemData) {
        console.error('No matching data found for selected item:', selectedItem);
        return;
    }

    const table = document.createElement('table');
    table.classList.add('table');
    const tbody = document.createElement('tbody');

    // Create the header row with a bold header and a background color
    const headerRow = document.createElement('tr');
    const headerCell = document.createElement('td');
    headerCell.textContent = 'ORDER DIALOG INFORMATION';
    headerCell.style.fontFamily = 'PT Serif Bold, Arial, sans-serif';
    headerCell.style.fontWeight = 'bold';
    headerCell.style.backgroundColor = 'lightblue'; // Set background color
    headerCell.style.textAlign = 'left'; // Center align the header
    headerCell.colSpan = 1; // Span across one column
    headerRow.appendChild(headerCell);
    tbody.appendChild(headerRow);

      // Add rows for components with clickable symbols
    Object.keys(itemData).forEach(key => {
      if (/^Component\d+$/.test(key)) {
          const componentName = itemData[key];
          const componentItem = odData.find(item => item.Name === componentName);
  
          const row = document.createElement('tr');
          const cell = document.createElement('td');
          const nameAndSymbol = document.createElement('div');
  
          // Bold component name
          const nameText = document.createElement('span');
          nameText.innerHTML = `<b>${key}:</b> ${componentName}`;
          nameText.style.display = 'inline-block'; // Display inline for better alignment
  
          nameAndSymbol.appendChild(nameText);
  
          if (componentItem) {
              // Clickable symbol
              const clickableSymbol = document.createElement('a');
              clickableSymbol.textContent = " \u24d8"; // Unicode character for circled information symbol
              clickableSymbol.classList.add('clickable');
              clickableSymbol.title = 'Click for more information';
              clickableSymbol.style.marginLeft = '10px'; // Space between name and symbol
              clickableSymbol.addEventListener('click', (event) => {
                  event.preventDefault();
                  createODTable(componentItem); // Create new table for the component
                  pushHistory(componentItem.Name); // Add to history
              });
  
              nameAndSymbol.appendChild(clickableSymbol);
          } else {
              // If there's no match, just display the component name
              console.warn(`No matching component found for ${componentName}`);
          }
  
          cell.appendChild(nameAndSymbol);
          row.appendChild(cell);
          tbody.appendChild(row);
      }
    });

    // Create rows for other key-value pairs
    const wordProcessingFields = []; // To keep track of `WordProcessing` fields
    await Promise.all(Object.entries(itemData).map(async ([key, value]) => {
        if (!/^Component\d+$/.test(key) && value.trim() !== '') { // Exclude blank fields
            const row = document.createElement('tr');
            const cell = document.createElement('td');

            if (/^WordProcessing\d+$/.test(key)) {
                wordProcessingFields.push({ key, value }); // Store for later processing
            } else {
                cell.innerHTML = `<b>${key}:</b> ${value}`;
                row.appendChild(cell);
                tbody.appendChild(row);
            }
        }
    }));

    // Process `WordProcessing` fields separately
    for (const { key, value } of wordProcessingFields) {
        const row = document.createElement('tr');
        const cell = document.createElement('td');

        if (/^WordProcessing\d+$/.test(key)) {
            const txmlData = await fetchAndParseXML(txmlFile);
            const matchingTexts = txmlData.fields.filter(field =>
                new RegExp(field.name.replace(/\*/g, '.*'), 'i').test(value)
            );

            if (matchingTexts.length > 0) {
                const clickableSymbol = document.createElement('a');
                clickableSymbol.textContent = " \u24d8"; // Unicode character for circled information symbol
                clickableSymbol.classList.add('clickable');
                clickableSymbol.title = 'Click for more information';
                clickableSymbol.style.marginLeft = '10px'; // Space between value and symbol
                clickableSymbol.addEventListener('click', async (event) => {
                    event.preventDefault();

                    // Add txml rows to the existing table
                    const txmlItem = matchingTexts[0]; // Assume at least one item exists to use for the header
                    const txmlHeaderRow = document.createElement('tr');
                    const txmlHeaderCell = document.createElement('td');
                    txmlHeaderCell.textContent = `TEMPLATE FIELD INFORMATION`;
                    txmlHeaderCell.style.fontFamily = 'PT Serif Bold, Arial, sans-serif';
                    txmlHeaderCell.style.fontWeight = 'bold';
                    txmlHeaderCell.style.backgroundColor = 'lightyellow'; // Different background color
                    txmlHeaderCell.style.textAlign = 'left'; // Center align the header
                    txmlHeaderCell.colSpan = 1; // Span across one column
                    txmlHeaderRow.appendChild(txmlHeaderCell);
                    tbody.appendChild(txmlHeaderRow);

                    matchingTexts.forEach(text => {
                        const fields = [
                            { label: 'Name', value: text.name },
                            { label: 'URL', value: text.url ? `<a href="${text.url}" target="_blank">${text.url}</a>` : 'N/A' },
                            { label: 'Type', value: text.type },
                            { label: 'Inactive', value: text.inactive },
                            { label: 'Length', value: text.length },
                            { label: 'Default Text', value: text.defaultText },
                            { label: 'Default Index', value: text.defaultIndex },
                            { label: 'Required', value: text.required },
                            { label: 'Separate Lines', value: text.separateLines },
                            { label: 'Max Length', value: text.maxLength },
                            { label: 'Indent', value: text.indent },
                            { label: 'Pad', value: text.pad },
                            { label: 'Min Value', value: text.minValue },
                            { label: 'Max Value', value: text.maxValue },
                            { label: 'Increment', value: text.increment },
                            { label: 'Items', value: text.items }
                        ];

                        fields.forEach(field => {
                            if (field.value) {
                                const row = document.createElement('tr');
                                const cell = document.createElement('td');

                                cell.innerHTML = `<b>${field.label}:</b> ${field.value}`;
                                row.appendChild(cell);
                                tbody.appendChild(row);
                            }
                        });
                    });

                    // Adjust font size for the newly added rows
                    adjustFontSize();
                });

                cell.innerHTML = `<b>${key}:</b> ${value}`;
                cell.appendChild(clickableSymbol);
            } else {
                cell.innerHTML = `<b>${key}:</b> ${value}`;
            }

            row.appendChild(cell);
            tbody.appendChild(row);
        }
    }

    table.appendChild(tbody);
    const resultContainer = document.getElementById('resultContainer');
    resultContainer.innerHTML = '';
    if (selectedItem) {
        resultContainer.appendChild(table);
    }

    // Adjust font size after table is fully appended
    adjustFontSize();
    //checkMatchesAndSetButtonAppearance()
    forwardBackButtonActivate()
}

// ===========================================================================
// PAGE SELECTION AND BUTTON HANDLERS
// ===========================================================================

// Shows the page chosen in the dropdown (event.target.value). Used as the
// dropdown's change handler and called directly by the buttons below with
// { target: dropdown }. In combined mode a legacy page name is mapped to its
// Combined equivalent first. With sortByTerm the options are re-sorted A-Z.
function filterData(event, sortByTerm = false) {
  const selectedOption = event.target.value;
  const resolvedOption = resolveTargetForCurrentVersion(selectedOption);
  const matchingData = omData.find(item => item.Name === resolvedOption) || omData.find(item => item.Name === selectedOption);
  if (matchingData) {
    selectedData = matchingData;
    createOMTable(matchingData);
    pushHistory(matchingData.Name);
  }
  scrollToTop();
  adjustFontSize();
  if (sortByTerm) {
    sortDropdownByTerm();
  }
}

// Sorts the dropdown options alphabetically by their visible text.
function sortDropdownByTerm() {
  const dropdown = document.getElementById('filterDropdown');
  const sortedOptions = Array.from(dropdown.options).sort((a, b) => {
    return a.textContent.localeCompare(b.textContent, undefined, { sensitivity: 'base' });
  });
  dropdown.innerHTML = '';
  for (const option of sortedOptions) {
    dropdown.appendChild(option);
  }
}

// Records a newly visited page. `history` is the list of visited page names and
// `historyIndex` the current position in it: visiting a new page while back in
// the list discards the "forward" entries. Re-showing the current page is ignored.
function pushHistory(item) {
  if (item !== history[historyIndex]) {
    historyIndex++;
    history.splice(historyIndex, history.length - historyIndex, item);
  }
}

// Clears the search box and restores its magnifier placeholder.
function resetSearchBox() {
  const searchInput = document.getElementById('searchInput');
  searchInput.value = null;
  searchInput.placeholder = "\u{1F50D}";
}

// Re-displays a page from `history` (shared by back and forward). Pages come
// from OMJSON; anything else in history is a legacy order dialog name.
function showHistoryEntry(selectedItem) {
  const matchingData = omData.find(item => item.Name === selectedItem);
  if (matchingData) {
    const dropdown = document.getElementById('filterDropdown');
    resetSearchBox();
    populateDropdown(omData);
    dropdown.value = selectedItem;
    filterData({ target: dropdown });
    createOMTable(matchingData);
  } else {
    createODTable(selectedItem);
  }
}

function handleGoBack() {
  if (historyIndex > 0) {
    historyIndex--;
    showHistoryEntry(history[historyIndex]);
  }
  scrollToTop();
  adjustFontSize();
}

function handleGoForward() {
  if (historyIndex < history.length - 1) {
    historyIndex++;
    showHistoryEntry(history[historyIndex]);
  }
  scrollToTop();
  adjustFontSize();
}

// Main Menu button: opens the start page of the current tab.
function handleMainMenu() {
  const dropdown = document.getElementById('filterDropdown');
  resetSearchBox();
  populateDropdown(omData);
  if (currentVersion === 'inpt') {
    dropdown.value = MainMenu;
  } else if (currentVersion === 'outpt') {
    dropdown.value = outptMenu;
  } else if (currentVersion === 'eruc') {
    dropdown.value = erucMenu;
  } else if (currentVersion === 'combined') {
    dropdown.value = combinedMenu;
  }
  // If that page is not in the dropdown, fall back to the first visible option.
  if (!dropdown.querySelector(`option[value="${dropdown.value}"]`)) {
    const firstVisibleOption = Array.from(dropdown.options).find(opt => opt.style.display !== 'none' && !opt.disabled);
    if (firstVisibleOption) dropdown.value = firstVisibleOption.value;
  }
  filterData({ target: dropdown });
  scrollToTop();
  adjustFontSize();
}

// Index button: opens the index page of the current tab (ER/UC has none).
function handleIndex() {
  const dropdown = document.getElementById('filterDropdown');
  resetSearchBox();
  populateDropdown(omData);
  if (currentVersion === 'inpt') {
    dropdown.value = Index;
  } else if (currentVersion === 'outpt') {
    dropdown.value = outptIndex;
  } else if (currentVersion === 'combined') {
    dropdown.value = combinedIndex;
  }
  filterData({ target: dropdown });
  scrollToTop();
  adjustFontSize();
}

// ---------------------------------------------------------------------------
// Tab switching. The legacy tabs (Outpt / ER-UC / Inpt) are transitional and
// will be removed when the site is combined-only. Each handler switches
// currentVersion and shows the current page's counterpart on the new tab
// (names found by checkMatchesAndSetButtonAppearance).
// ---------------------------------------------------------------------------

function handleOutpt() {
  const dropdown = document.getElementById('filterDropdown');
  resetSearchBox();
  currentVersion = 'outpt';
  populateDropdown(omData);
  dropdown.value = matchedOutptName;
  filterData({ target: dropdown });
  scrollToTop();
  adjustFontSize();
  checkMatchesAndSetButtonAppearance();
}

// Note: unlike the other tab handlers, populateDropdown runs BEFORE
// currentVersion changes, so the dropdown is rebuilt with the previous tab's filtering.
function handleCombined() {
  const dropdown = document.getElementById('filterDropdown');
  resetSearchBox();
  populateDropdown(omData);
  currentVersion = 'combined';
  dropdown.value = matchedCombinedName || combinedMenu;
  filterData({ target: dropdown });
  scrollToTop();
  adjustFontSize();
  checkMatchesAndSetButtonAppearance();
}

function handleEruc() {
  const dropdown = document.getElementById('filterDropdown');
  resetSearchBox();
  currentVersion = 'eruc';
  populateDropdown(omData);
  dropdown.value = matchedErucName;
  filterData({ target: dropdown });
  scrollToTop();
  adjustFontSize();
  checkMatchesAndSetButtonAppearance();
}

// The Inpt counterpart is the current page's `Inpt` pointer, or else the first
// page whose Outpt/ERUC pointer names the current page.
function handleInpt() {
  const dropdown = document.getElementById('filterDropdown');
  resetSearchBox();
  currentVersion = 'inpt';
  populateDropdown(omData);
  const selectedDataName = selectedData.Name;
  let matchedItemName = null;

  if (selectedData.Inpt) {
    matchedItemName = selectedData.Inpt;
  }

  if (!matchedItemName) {
    for (const item of omData) {
      if (item.Outpt === selectedDataName || item.ERUC === selectedDataName) {
        matchedItemName = item.Name;
        break;
      }
    }
  }

  dropdown.value = matchedItemName || ''; // '' clears the dropdown when there is no counterpart
  filterData({ target: dropdown });
  scrollToTop();
  adjustFontSize();
  checkMatchesAndSetButtonAppearance();
}

// ===========================================================================
// EVENT WIRING
// ===========================================================================

// Search box click/typing: show the dropdown as an open list of all options.
function openDropdown() {
  const dropdown = document.getElementById('filterDropdown');
  dropdown.size = dropdown.options.length;
  dropdown.style.display = 'block';
}

// Station switcher buttons (test station only): open the same page on another
// station's site. NOTE (existing behavior, left unchanged): minneapolisButton
// has two listeners, so one click opens both the Black Hills and the
// Minneapolis pages, and blackHillsButton has no listener.
document.getElementById('desMoinesButton').addEventListener('click', function () {
  openPageInNewWindow("stations/636A6-DesMoines/DesMoinesCDSS.html", { " CI ": " ", " NE ": " ", "GMENU": "CI GMENU" });
});
document.getElementById('minneapolisButton').addEventListener('click', function () {
  openPageInNewWindow("stations/568-BlackHills/BlackHillsCDSS.html",{ " CI ": " ", " NE ": " " });
});
document.getElementById('fargoButton').addEventListener('click', function () {
  openPageInNewWindow("stations/437-Fargo/FargoCDSS.html",{ " CI ": " ", " NE ": " " });
});
document.getElementById('minneapolisButton').addEventListener('click', function () {
  openPageInNewWindow("stations/618-Minneapolis/MinneapolisCDSS.html",{ " CI ": " ", " NE ": " " });
});
document.getElementById('omahaButton').addEventListener('click', function () {
  openPageInNewWindow('stations/636-Omaha/OmahaCDSS.html', { " CI ": " ", " NE ": " ", "GMENU": "NE GMENU" });
});
document.getElementById('stCloudButton').addEventListener('click', function () {
  openPageInNewWindow('stations/656-StCloud/StCloudCDSS.html', { " CI ": " ", " NE ": " " });
});
document.getElementById('siouxFallsButton').addEventListener('click', function () {
  openPageInNewWindow('stations/438-SiouxFalls/SiouxFallsCDSS.html', { " CI ": " ", " NE ": " " });
});

// Navigation buttons (always present).
document.getElementById('goBackButton').addEventListener('click', handleGoBack);
document.getElementById('goForwardButton').addEventListener('click', handleGoForward);
document.getElementById('mainMenuButton').addEventListener('click', handleMainMenu);
document.getElementById('indexButton').addEventListener('click', handleIndex);

// Legacy tab buttons: only the test station has them; the combined-only
// production pages omit them, so a missing button is simply skipped.
function onClickIfPresent(buttonId, handler) {
  const button = document.getElementById(buttonId);
  if (button) button.addEventListener('click', handler);
}
onClickIfPresent('outptButton', handleOutpt);
onClickIfPresent('inptButton', handleInpt);
onClickIfPresent('erucButton', handleEruc);
onClickIfPresent('combinedButton', handleCombined);

document.getElementById('helpLegendButton').addEventListener('click', () => handleRowClick({ Item: helpLegendPageId }));

// Feedback form, pre-filled with the current page ID and station.
document.getElementById('feedbackButton').addEventListener('click', function () {
  const pageId = (selectedData && selectedData.Name) ? selectedData.Name : '';
  const feedbackUrl = 'https://forms.cloud.microsoft/Pages/ResponsePage.aspx?id=Ixtf6a-r7kWCHberJRqzv6NdTKT5lyFNnrhFJ-FjMgxURFYyUFlBWkkyMFhEWlFZMUdQRFg3M1RHRiQlQCN0PWcu'
    + '&r3cd582c08765477899cdd43f15e435b8=' + encodeURIComponent(pageId)
    + '&r7c21ccd08e3f47d889bb72f61fcd47c8=' + encodeURIComponent(CDSSlocation);
  window.open(feedbackUrl, '_blank', 'noopener,noreferrer');
});

// Page dropdown and search box. (Further search-box handlers are registered in
// searchAndOpenDropdown() and near the top of this script.)
document.getElementById('filterDropdown').addEventListener('change', filterData);
document.getElementById('searchInput').addEventListener('input', searchData);
document.getElementById('searchInput').addEventListener('click', openDropdown);
document.getElementById('searchInput').addEventListener('input', openDropdown);

document.getElementById('homeButton').addEventListener('click', function() {
    window.location.href = homeButtonUrl;
});

// Hide images that fail to load (e.g. not present in the repository).
document.addEventListener("DOMContentLoaded", function(event) {
  document.querySelectorAll('img').forEach(function(img){
  img.onerror = function(){this.style.display='none';};
  })
});

// Opens `pageURL` in a new window, passing the current page selection as
// ?dropdown=<name> (read by selectInitialPage on the other site). Each
// { find: replace } pair in `replacements` is applied to the name first, e.g. to
// translate between station naming conventions.
function openPageInNewWindow(pageURL, replacements) {
  const dropdown = document.getElementById('filterDropdown');
  let dropdownValue = dropdown.value;
  // Check if replacements are provided and modify the dropdownValue accordingly
  if (replacements) {
    for (const key in replacements) {
      if (replacements.hasOwnProperty(key)) {
        dropdownValue = dropdownValue.replace(key, replacements[key]);
      }
    }
  }
  const newURL = `${pageURL}?dropdown=${encodeURIComponent(dropdownValue)}`;
  // Open the new page in a new window
  window.open(newURL, '_blank');
  }
  
// ===========================================================================
// STARTUP
// ===========================================================================

// Chooses the page to show first: ?dropdown=<page> from the URL (set by
// openPageInNewWindow), else the combined main menu. If that page is not in the
// dropdown it falls back to the combined menu, then the legacy main menu, then
// the first visible option.
function selectInitialPage(dropdown) {
  const dropdownValue = new URLSearchParams(window.location.search).get('dropdown');
  dropdown.value = dropdownValue ? decodeURIComponent(dropdownValue) : combinedMenu;

  if (!dropdown.querySelector(`option[value="${dropdown.value}"]`)) {
    const combinedMenuOption = dropdown.querySelector(`option[value="${combinedMenu}"]`);
    const mainMenuOption = dropdown.querySelector(`option[value="${MainMenu}"]`);
    const firstVisibleOption = Array.from(dropdown.options).find(opt => opt.style.display !== 'none' && !opt.disabled);
    const fallbackOption = combinedMenuOption || mainMenuOption || firstVisibleOption || dropdown.options[0];
    if (fallbackOption) dropdown.value = fallbackOption.value;
  }

  // Final guard: if value is still empty, prefer combined menu directly.
  if (!dropdown.value) {
    dropdown.value = combinedMenu;
  }
}

// Load pages, order dialogs and drug links, then show the first page.
Promise.all([fetchOMData(), fetchODData(), fetchAbxLink()])
  .then(([omjsonData, odjsonData, abxlinkjsonData]) => {
    omData = omjsonData.menus || omjsonData;
    odData = odjsonData;
    abxLinkData = abxlinkjsonData;
    // Set combined as default before first render so drug links are active on initial load.
    if (!currentVersion) {
      currentVersion = 'combined';
    }
    populateDropdown(omData);

    const dropdown = document.getElementById('filterDropdown');
    selectInitialPage(dropdown);
    pushHistory(dropdown.value);
    filterData({ target: dropdown });
    scrollToTop();
    adjustFontSize();
  })
  .catch(error => {
    console.error('Error:', error);
    const resultContainer = document.getElementById('resultContainer');
    if (resultContainer) {
      resultContainer.innerHTML = '<div style="color:red">Data load failed. See browser console.</div>';
    }
  });

// Offline support: the service worker is registered site-wide (see service-worker.js).
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/service-worker.js', {
    scope: '/'
    });
  }
  
// "Install app" button: keep the browser's install prompt event and show it on click.
        let deferredInstallPrompt;
        window.addEventListener('beforeinstallprompt', (event) => {
            // Store the event to use it later when you want to show the install prompt.
            deferredInstallPrompt = event;
            // Show the install button
            const installButton = document.getElementById('install-button');
            installButton.style.display = 'block';
        });
        // Your existing click event listener for the install button
        const installButton = document.getElementById('install-button');
        installButton.addEventListener('click', () => {
            if (deferredInstallPrompt) {
                // Show the installation prompt to the user
                deferredInstallPrompt.prompt();

                // Wait for the user's choice
                deferredInstallPrompt.userChoice.then((choiceResult) => {
                    if (choiceResult.outcome === 'accepted') {
                        //console.log('User accepted the installation');
                    } else {
                        //console.log('User dismissed the installation');
                    }
                    // Reset the deferred event
                    deferredInstallPrompt = null;
                });
            }
        });

// ===========================================================================
// TAB / BUTTON APPEARANCE
// ===========================================================================

// First record matching `predicate`, read through `field` (null if none matches).
function counterpartFromFirstMatch(predicate, field) {
  const item = omData.find(predicate);
  return item ? item[field] : null;
}

// Runs after every render. Works out the current page's counterparts on the
// other tabs (matchedOutptName / matchedErucName / matchedCombinedName), greys
// out tab buttons that have no counterpart, and highlights the active tab.
function checkMatchesAndSetButtonAppearance() {
  const outptButton = document.getElementById('outptButton');
  const erucButton = document.getElementById('erucButton');
  const inptButton = document.getElementById('inptButton');
  const combinedButton = document.getElementById('combinedButton');
  const indexButton = document.getElementById('indexButton');
  matchedOutptName = null;
  matchedErucName = null;
  matchedCombinedName = null;

  if (!selectedData || !selectedData.Name) {
    selectedData = { Name: MainMenu }; // Set selectedData.Name to MainMenu if not defined
  }

  const selectedDataName = selectedData.Name;
  const isOutptOrEruc = item => item.Outpt === selectedDataName || item.ERUC === selectedDataName;

  // The page's own pointer wins; otherwise use the first page that points at this one.
  matchedOutptName = selectedData.Outpt || counterpartFromFirstMatch(isOutptOrEruc, 'Outpt');
  matchedErucName = selectedData.ERUC || counterpartFromFirstMatch(isOutptOrEruc, 'ERUC');
  matchedCombinedName = selectedData.Combined || counterpartFromFirstMatch(item => item.Combined === selectedDataName, 'Combined');

  setButtonAppearance(outptButton, Boolean(matchedOutptName));
  setButtonAppearance(erucButton, Boolean(matchedErucName));
  setButtonAppearance(combinedButton, Boolean(matchedCombinedName));

  // Highlight the active tab's button; ER/UC has no index page.
  const tabButtons = { inpt: inptButton, outpt: outptButton, eruc: erucButton, combined: combinedButton };
  if (currentVersion in tabButtons) {
    Object.entries(tabButtons).forEach(([version, button]) => {
      setButtonBackground(button, version === currentVersion);
    });
    setButtonAppearance(indexButton, currentVersion !== 'eruc');
  }
}

// Active: normal colour. Inactive: greyed out. (No-op when the button is not on the page.)
function setButtonAppearance(button, isActive) {
  if (!button) return;
  if (isActive) {
    button.classList.remove('inactive-button');
    button.style.color = '';
  } else {
    button.classList.add('inactive-button');
    button.style.color = 'grey';
  }
}

// Active tab: green background. (No-op when the button is not on the page.)
function setButtonBackground(button, isActive) {
  if (!button) return;
  if (isActive) {
    button.style.background = '#00b159';
  } else {
    button.style.background = '';
  }
}

// On page load, start in combined mode and set the tab button states.
window.onload = function() {
  currentVersion = 'combined';
  checkMatchesAndSetButtonAppearance();
};
