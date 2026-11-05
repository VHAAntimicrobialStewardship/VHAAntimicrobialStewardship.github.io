// Markdown renderer for guidance pages: marked (same library Sveltia previews with) + DOMPurify.
// Opt-in per station page: set  var Renderer = 'markdown';  and load vendor/marked.umd.js,
// vendor/purify.min.js and this file before cdss-app.js. ?renderer=classic restores the old
// line-per-row renderer for that visit. Also loadable from node (scripts/render-check.js).
//
// breaks:true matches Sveltia's editor (a single newline is a visible line break).
// Raw HTML is never parsed, so dosing text such as <AND> and <OR> stays literal.
(function (global) {
  'use strict';

  const ALLOWED_TAGS = [
    'p', 'br', 'hr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'em', 'del', 's', 'code', 'pre',
    'blockquote', 'ul', 'ol', 'li', 'a', 'img', 'table', 'thead', 'tbody', 'tr', 'th', 'td'
  ];
  const ALLOWED_ATTR = ['href', 'src', 'alt', 'title', 'start', 'align', 'colspan', 'rowspan', 'data-cdss-target'];
  const EXTERNAL_URL = /^(?:https?:|mailto:)/i;

  function escapeAttr(value) {
    return String(value).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // `MarkedClass` is marked.Marked. Internal links ([label](page-id)) are emitted as
  // data-cdss-target so the sanitizer cannot strip them; decorate() wires them up.
  function createMarked(MarkedClass) {
    return new MarkedClass({
      gfm: true,
      breaks: true,
      tokenizer: {
        html() {
          return undefined;
        },
        tag() {
          return undefined;
        }
      },
      renderer: {
        link({ href, title, tokens }) {
          const label = this.parser.parseInline(tokens);
          const titleAttr = title ? ` title="${escapeAttr(title)}"` : '';
          if (EXTERNAL_URL.test(href)) {
            let safeHref = href;
            try {
              safeHref = encodeURI(decodeURI(href));
            } catch (e) {
              safeHref = href;
            }
            return `<a href="${escapeAttr(safeHref)}"${titleAttr}>${label}</a>`;
          }
          return `<a data-cdss-target="${escapeAttr(href)}"${titleAttr}>${label}</a>`;
        }
      }
    });
  }

  function toSafeHtml(markedInstance, purify, text) {
    const html = markedInstance.parse(String(text || ''), { async: false });
    return purify.sanitize(html, { ALLOWED_TAGS, ALLOWED_ATTR, ALLOW_DATA_ATTR: false });
  }

  function safeDecode(value) {
    try {
      return decodeURIComponent(value);
    } catch (e) {
      return value;
    }
  }

  // Applies site behaviour to sanitized HTML. hooks:
  //   resolveLink(target, label) -> page name or null   internal link lookup
  //   openItem(item, label)                             navigate to a resolved link
  //   imageUrl(src) -> url or ''                        normalizes upload paths ('' shows the alt text)
  //   appendAbxText(container, text)                    optional; adds drug-name links
  function decorate(root, hooks) {
    const doc = root.ownerDocument;

    root.querySelectorAll('a[data-cdss-target]').forEach((anchor) => {
      const target = safeDecode(anchor.getAttribute('data-cdss-target') || '').trim();
      const label = anchor.textContent;
      const item = hooks.resolveLink(target, label);
      if (!item) {
        anchor.replaceWith(...anchor.childNodes); // unresolved: show the label as plain text
        return;
      }
      anchor.removeAttribute('data-cdss-target');
      anchor.classList.add('clickable');
      anchor.addEventListener('click', () => hooks.openItem(item, label));
    });

    root.querySelectorAll('a[href]').forEach((anchor) => {
      anchor.classList.add('AbxLink');
      anchor.target = '_blank';
      anchor.rel = 'noopener noreferrer';
    });

    root.querySelectorAll('img').forEach((image) => {
      const url = hooks.imageUrl(image.getAttribute('src') || '');
      if (!url) {
        image.replaceWith(doc.createTextNode(image.getAttribute('alt') || ''));
        return;
      }
      image.setAttribute('src', url);
      image.classList.add('markdown-image');
    });

    root.querySelectorAll('hr').forEach((rule) => rule.classList.add('markdown-rule'));

    root.querySelectorAll('table').forEach((table) => {
      const wrap = doc.createElement('div');
      wrap.className = 'markdown-table-wrap';
      table.replaceWith(wrap);
      wrap.appendChild(table);
    });

    if (typeof hooks.appendAbxText === 'function') {
      const walker = doc.createTreeWalker(root, 4 /* NodeFilter.SHOW_TEXT */);
      const textNodes = [];
      while (walker.nextNode()) {
        const node = walker.currentNode;
        if (node.nodeValue.trim() && !node.parentElement.closest('a, code, pre')) {
          textNodes.push(node);
        }
      }
      textNodes.forEach((node) => {
        const fragment = doc.createDocumentFragment();
        hooks.appendAbxText(fragment, node.nodeValue);
        node.replaceWith(fragment);
      });
    }
  }

  // A leading H1 is shown as the page banner row; returns its text and removes it from root.
  function takeBanner(root) {
    const first = root.firstElementChild;
    if (first && first.tagName === 'H1') {
      const text = first.textContent.trim();
      first.remove();
      return text;
    }
    return null;
  }

  const api = { createMarked, toSafeHtml, decorate, takeBanner, enabled: false, render: null };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
    return;
  }

  const params = new URLSearchParams(global.location.search);
  const requested = typeof Renderer !== 'undefined' && Renderer === 'markdown' && params.get('renderer') !== 'classic';
  if (requested && global.marked && global.DOMPurify) {
    const instance = createMarked(global.marked.Marked);
    api.enabled = true;
    api.render = function (text, hooks) {
      const root = global.document.createElement('div');
      root.className = 'markdown-body';
      root.innerHTML = toSafeHtml(instance, global.DOMPurify, text);
      decorate(root, hooks);
      return root;
    };
  }
  global.CDSSMarkdown = api;
})(typeof window !== 'undefined' ? window : globalThis);
