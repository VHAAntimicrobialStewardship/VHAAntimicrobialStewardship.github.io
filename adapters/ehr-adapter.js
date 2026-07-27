/*
 * EHR adapter contract + registry
 * --------------------------------
 * The CDSS renderer is EHR-agnostic: it works against a *neutral content model*
 * and delegates every EHR-specific decision (how an item is classified, how an
 * order is launched, what the "source menu" footer says) to an adapter.
 *
 * This lets a single codebase serve VistA sites today and Oracle Health sites
 * later, with per-station selection via the `EHR` config variable.
 *
 * -----------------------------------------------------------------------------
 * Neutral content model
 * -----------------------------------------------------------------------------
 * The renderer only needs to know, for each cell of an order-menu (OM) page,
 * which of three neutral "kinds" it is:
 *
 *   'menu'  -> navigates to another OM page (a sub-menu)
 *   'order' -> a launchable / orderable item (opens an order dialog or a link)
 *   'text'  -> plain clinical guidance text (no navigation)
 *
 * The clinical guidance itself (drug, dose, route, duration, headers, etc.) is
 * already EHR-neutral and is never interpreted here.
 *
 * -----------------------------------------------------------------------------
 * Adapter interface
 * -----------------------------------------------------------------------------
 * An adapter factory has the shape `function (config) -> adapter`, where
 * `config` carries the station-specific settings from the CDSS page, e.g.
 *   { EHR, MenuPrefix, LinkPrefix, txmlFile }
 *
 * The returned adapter object must implement:
 *
 *   name              {string}  Human label for the source EHR (e.g. 'VistA').
 *   sourceMenuLabel   {string}  Footer label for a page's source id
 *                               (e.g. 'VistA Menu Name: ').
 *
 *   isMenu(item)      -> boolean  Is this a sub-menu navigation item?
 *   isOrderLink(item) -> boolean  Is this a launchable order/link item?
 *   isNavigable(item) -> boolean  isMenu(item) || isOrderLink(item).
 *       `item` may be an OM content cell ({ Item, ... }) or an OD record
 *       ({ Name, ... }); adapters should accept either shape.
 *
 *   launchOrder(odItem, host) -> Promise<void>
 *       Launch / resolve an order-dialog record. `host` provides callbacks the
 *       adapter may need from the renderer:
 *         host.fetchODData()          -> Promise<Array>  all OD records
 *         host.createODTable(record)  -> void            render an OD table
 *         host.pushHistory(name)      -> void            record navigation
 *
 *   getTemplateFields(value) -> Promise<Array>
 *       Return any EHR "template field" metadata associated with a free-text
 *       order-dialog value (VistA: matching .txml fields). Return [] when the
 *       EHR has no such concept.
 * -----------------------------------------------------------------------------
 */
(function () {
  window.EHRAdapters = window.EHRAdapters || {};

  /**
   * Select and instantiate the adapter for the given station config.
   * Falls back to the VistA adapter when `EHR` is missing/unknown so existing
   * VistA stations keep working unchanged.
   */
  window.selectEHRAdapter = function selectEHRAdapter(config) {
    config = config || {};
    var key = String(config.EHR || 'vista').trim().toLowerCase();
    var factory = window.EHRAdapters[key] || window.EHRAdapters.vista;
    if (!factory) {
      throw new Error('No EHR adapter available for "' + key + '"');
    }
    return factory(config);
  };
})();
