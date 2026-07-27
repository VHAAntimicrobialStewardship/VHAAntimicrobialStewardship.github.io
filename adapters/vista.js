/*
 * VistA EHR adapter
 * -----------------
 * Interprets the VistA-sourced order-menu (OM) / order-dialog (OD) JSON and
 * resolves order launches through CPRS .txml template fields.
 *
 * All VistA-specific coupling that used to live inline in each *CDSS.html page
 * is centralized here:
 *   - prefix-based item classification (MenuPrefix / LinkPrefix)
 *   - the "VistA Menu Name: " source footer label
 *   - .txml parsing and order-link resolution (formerly findMatches / fetchAndParseXML)
 *
 * Implements the adapter interface documented in ehr-adapter.js.
 */
(function () {
  window.EHRAdapters = window.EHRAdapters || {};

  window.EHRAdapters.vista = function createVistaAdapter(config) {
    config = config || {};
    var menuPrefix = config.MenuPrefix || '';
    var linkPrefix = config.LinkPrefix || '';
    var txmlFile = config.txmlFile;

    // Cache the parsed .txml so repeated launches/template lookups reuse it.
    var txmlPromise = null;

    // Read the EHR "name" of an item, accepting either an OM content cell
    // ({ Item }) or an OD record ({ Name }).
    function nameOf(item) {
      if (!item) return '';
      if (item.Item != null) return item.Item;
      if (item.Name != null) return item.Name;
      return '';
    }

    function isMenu(item) {
      var n = nameOf(item);
      return !!(n && menuPrefix && n.startsWith(menuPrefix));
    }

    function isOrderLink(item) {
      var n = nameOf(item);
      return !!(n && linkPrefix && n.startsWith(linkPrefix));
    }

    // Fetch + parse the station's .txml (CPRS template) file once.
    function fetchAndParseXML() {
      if (txmlPromise) return txmlPromise;
      txmlPromise = (async function () {
        try {
          const response = await fetch(txmlFile);
          if (!response.ok) {
            throw new Error('Network response was not ok ' + response.statusText);
          }
          const xmlText = await response.text();
          const parser = new DOMParser();
          const xmlDoc = parser.parseFromString(xmlText, 'text/xml');

          const boilerplateTexts = Array.from(
            xmlDoc.querySelectorAll('BOILERPLATE_TEXT p'),
            p => p.textContent
          );

          const fields = Array.from(xmlDoc.querySelectorAll('TEMPLATE_FIELDS FIELD')).map(field => {
            const q = sel => (field.querySelector(sel) ? field.querySelector(sel).textContent : null);
            return {
              name: field.getAttribute('NAME'),
              type: q('TYPE'),
              inactive: q('INACTIVE'),
              length: q('LENGTH'),
              defaultText: q('DEFAULT_TEXT'),
              defaultIndex: q('DEFAULT_INDEX'),
              required: q('REQUIRED'),
              separateLines: q('SEPARATE_LINES'),
              maxLength: q('MAX_LENGTH'),
              indent: q('INDENT'),
              pad: q('PAD'),
              minValue: q('MIN_VALUE'),
              maxValue: q('MAX_VALUE'),
              increment: q('INCREMENT'),
              url: q('URL'),
              items: q('ITEMS')
            };
          });

          return { boilerplateTexts, fields };
        } catch (error) {
          console.error('Error parsing .txml:', error);
          txmlPromise = null; // allow a later retry
          return { boilerplateTexts: [], fields: [] };
        }
      })();
      return txmlPromise;
    }

    // Return matching .txml template fields for a free-text OD value.
    async function getTemplateFields(value) {
      const txmlData = await fetchAndParseXML();
      return txmlData.fields.filter(field =>
        new RegExp(field.name.replace(/\*/g, '.*'), 'i').test(value)
      );
    }

    // Resolve/launch an order-dialog record via its .txml matches.
    // Ports the former inline findMatches() behavior.
    async function launchOrder(matchingItem, host) {
      host = host || {};
      try {
        const txmlData = await fetchAndParseXML();
        const odData = await host.fetchODData();

        const matches = [];

        const filteredODData = odData.filter(odItem =>
          odItem.Name.trim().toLowerCase() === matchingItem.Name.trim().toLowerCase()
        );

        for (const item of filteredODData) {
          const itemMatches = [];
          const urls = [];

          for (let i = 1; i <= 20; i++) {
            const wordProcessingField = item['WordProcessing' + i];
            if (wordProcessingField && wordProcessingField.trim() !== '') {
              const matchesInTxml = txmlData.fields.filter(field =>
                new RegExp(field.name.replace(/\*/g, '.*'), 'i').test(wordProcessingField)
              );
              if (matchesInTxml.length > 0) {
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
          }

          matches.push(...itemMatches);

          if (urls.length > 0) {
            if (urls.length === 1) {
              window.open(urls[0], '_blank');
            } else {
              const popupContent = itemMatches
                .filter(match => match.txmlURL)
                .map(match => `<a href="${match.txmlURL}" target="_self">${match.txmlDefaultText || match.txmlName}</a>`)
                .join('<br>');

              const newTab = window.open('', '_blank');
              newTab.document.write(
                `<html><head><title>Select CDSS Link</title></head><body>Multiple links in CDSS order dialog. Select one below to open.<br>${popupContent}</body></html>`
              );
            }
          } else {
            if (host.createODTable) host.createODTable(item);
            if (host.pushHistory) host.pushHistory(item.Name);
          }
        }

        return matches;
      } catch (error) {
        console.error('Error finding matches:', error);
        return [];
      }
    }

    return {
      name: 'VistA',
      sourceMenuLabel: 'VistA Menu Name: ',
      isMenu: isMenu,
      isOrderLink: isOrderLink,
      isNavigable: function (item) { return isMenu(item) || isOrderLink(item); },
      getTemplateFields: getTemplateFields,
      launchOrder: launchOrder
    };
  };
})();
