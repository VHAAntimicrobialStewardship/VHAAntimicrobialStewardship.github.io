// Shared marked configuration for node tooling: the same module the site loads (shared/cdss-markdown.js),
// so render checks see exactly what the browser renders, including DOMPurify.
const { JSDOM } = require('jsdom');
const createDOMPurify = require('dompurify');
const { Marked } = require('marked');
const site = require('../../shared/cdss-markdown.js');

const purify = createDOMPurify(new JSDOM('').window);
const instance = site.createMarked(Marked);

module.exports = {
  // Returns the sanitized HTML for markdown source.
  renderHtml: (text) => site.toSafeHtml(instance, purify, text)
};
