/*
 * Oracle Health (Cerner Millennium) EHR adapter — Tier 1 stub
 * -----------------------------------------------------------
 * Oracle Health sites do not have VistA `ORZID... GMENU` names or CPRS .txml
 * templates, so this adapter drives classification and launching from the
 * *neutral content model* instead of VistA prefix strings.
 *
 * Neutral fields this adapter reads (authored via the CMS or exported from the
 * Oracle order catalog):
 *   item.Kind     -> 'menu' | 'order' | 'text'   (falls back to 'text')
 *   item.Binding  -> { orderName, synonymId, powerPlan, url }  (optional)
 *
 * Tier 1 behavior (deployable today, zero integration): the app is guidance +
 * reference links. "Launching" an order shows the exact order name/synonym to
 * search for in PowerChart as copyable text. Tiers 2-3 (SMART on FHIR launch,
 * PowerPlan deep-links) can extend launchOrder() later without touching the
 * renderer or the content.
 *
 * Implements the adapter interface documented in ehr-adapter.js.
 */
(function () {
  window.EHRAdapters = window.EHRAdapters || {};

  window.EHRAdapters.oracle = function createOracleAdapter(config) {
    config = config || {};

    function kindOf(item) {
      if (!item) return 'text';
      var k = item.Kind || item.kind;
      return k ? String(k).toLowerCase() : 'text';
    }

    function isMenu(item) {
      return kindOf(item) === 'menu';
    }

    function isOrderLink(item) {
      return kindOf(item) === 'order';
    }

    function bindingOf(item) {
      return (item && (item.Binding || item.binding)) || {};
    }

    // Tier 1: present the orderable's name/synonym for the clinician to place
    // manually in PowerChart. Reference URLs open directly.
    async function launchOrder(matchingItem, host) {
      host = host || {};
      var binding = bindingOf(matchingItem);

      if (binding.url) {
        window.open(binding.url, '_blank');
        return [];
      }

      var orderName = binding.orderName || matchingItem.DisplayText || matchingItem.Name || '';
      var synonym = binding.synonymId ? ('\nSynonym ID: ' + binding.synonymId) : '';
      var powerPlan = binding.powerPlan ? ('\nPowerPlan: ' + binding.powerPlan) : '';

      var body =
        '<html><head><title>Place Order in PowerChart</title></head>' +
        '<body style="font-family:Arial,sans-serif;padding:16px;">' +
        '<p>Search for and place the following order in PowerChart:</p>' +
        '<p><strong style="font-size:1.1em;">' + orderName + '</strong></p>' +
        (synonym ? '<p>' + synonym.trim() + '</p>' : '') +
        (powerPlan ? '<p>' + powerPlan.trim() + '</p>' : '') +
        '</body></html>';

      var newTab = window.open('', '_blank');
      if (newTab) {
        newTab.document.write(body);
      }

      // Keep the guidance context visible in-app as well.
      if (host.createODTable) host.createODTable(matchingItem);
      if (host.pushHistory && matchingItem && matchingItem.Name) host.pushHistory(matchingItem.Name);
      return [];
    }

    // Oracle content has no VistA-style .txml template fields.
    async function getTemplateFields() {
      return [];
    }

    return {
      name: 'Oracle Health',
      sourceMenuLabel: 'Order Set: ',
      isMenu: isMenu,
      isOrderLink: isOrderLink,
      isNavigable: function (item) { return isMenu(item) || isOrderLink(item); },
      getTemplateFields: getTemplateFields,
      launchOrder: launchOrder
    };
  };
})();
