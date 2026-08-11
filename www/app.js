/* Sacramento budget shell behavior. View state remains server-owned by Shiny. */
(function () {
  "use strict";

  var VALID_VIEWS = ["overview", "changed", "explorer", "lab", "budget101", "methods"];
  var VALID_VIEW_SET = VALID_VIEWS.reduce(function (set, value) {
    set[value] = true;
    return set;
  }, {});
  var DATA_FRAME_LABELS = {
    "overview-workspace_table": "Overview exact supporting records",
    "changed-table": "Department comparison exact values",
    "explorer-table": "Explorer exact supporting records",
    "lab-scenario_table": "Hypothetical scenario results",
  };
  var DETAIL_OUTPUT_IDS = {
    "overview-workspace_table": true,
    "overview-trend_chart": true,
    "overview-workspace_chart": true,
    "changed-table": true,
    "changed-chart": true,
    "changed-scatter": true,
    "explorer-table": true,
    "explorer-chart": true,
  };
  var FOCUSABLE = [
    "a[href]",
    "area[href]",
    "button:not([disabled])",
    "input:not([disabled]):not([type='hidden'])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    "iframe",
    "object",
    "embed",
    "[contenteditable]",
    "[tabindex]:not([tabindex='-1'])",
  ].join(",");
  var state = {
    pendingUserView: null,
    legacyPending: false,
    legacySent: false,
    lastSelectionTrigger: null,
    lastSelectionDescriptor: null,
    lastSelectionFallbackId: null,
    lastLocationSynced: null,
    handlingLocation: false,
    header: {
      lastScrollY: 0,
      ticking: false,
    },
    overviewYearFocus: null,
    overviewChartObserver: null,
    overviewChartResizeObserver: null,
    overviewMeasureFocus: null,
    overviewKpiObserver: null,
    detail: {
      element: null,
      drawer: null,
      lifecycle: "closed",
      lifecycleGeneration: -1,
      contentKey: null,
      inertNodes: [],
      trigger: null,
      descriptor: null,
      fallbackId: null,
      restoreFocus: true,
      closeRequested: false,
      transitionToken: 0,
      cleanupTimer: null,
      pendingFocusId: null,
      summaryObserver: null,
      expectedTitle: null,
      focusRestore: null,
      focusRestoreObserver: null,
      focusRestoreRoot: null,
      focusRestoreFrame: null,
    },
    dataFrameObservers: new WeakMap(),
  };

  function isValidView(value) {
    return !!(value && VALID_VIEW_SET[value]);
  }

  function normalizeView(value) {
    if (value === "drilldown") {
      state.legacyPending = true;
      return "overview";
    }
    return isValidView(value) ? value : null;
  }

  function viewFromLocation() {
    return normalizeView(window.location.hash.replace(/^#/, "").toLowerCase());
  }

  function locationForView(value) {
    return window.location.pathname + window.location.search + "#" + value;
  }

  function scrollViewTop() {
    window.setTimeout(function () {
      window.scrollTo(0, 0);
    }, 0);
  }

  function revealHeader() {
    var header = document.querySelector(".city-header");
    if (header) header.classList.remove("is-scroll-hidden");
  }

  function syncHeaderToScroll() {
    var header = document.querySelector(".city-header");
    var currentY = Math.max(0, window.scrollY || window.pageYOffset || 0);
    var delta = currentY - state.header.lastScrollY;
    var keepsHeaderVisible = header && (
      header.matches(":focus-within") || !!header.querySelector("details[open]")
    );

    if (header) {
      if (currentY <= 16 || delta < 0 || keepsHeaderVisible) {
        header.classList.remove("is-scroll-hidden");
      } else if (currentY > 96 && delta > 0) {
        header.classList.add("is-scroll-hidden");
      }
    }

    state.header.lastScrollY = currentY;
    state.header.ticking = false;
  }

  function queueHeaderScrollUpdate() {
    if (state.header.ticking) return;
    state.header.ticking = true;
    window.requestAnimationFrame(syncHeaderToScroll);
  }

  function initializeHeaderScroll() {
    state.header.lastScrollY = Math.max(0, window.scrollY || window.pageYOffset || 0);
    revealHeader();
  }

  function setActiveView(value) {
    if (!isValidView(value)) return;
    document.querySelectorAll(
      ".city-nav__link, .city-resources__link, .city-mobile-nav__link"
    ).forEach(function (link) {
      var active = link.getAttribute("data-nav-value") === value;
      link.classList.toggle("is-active", active);
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    document.querySelectorAll(".city-resources").forEach(function (resources) {
      var summary = resources.querySelector(".city-resources__summary");
      if (summary) summary.classList.toggle("is-active", !!resources.querySelector(".city-resources__link.is-active"));
    });
  }

  function closeMobileMenu(event) {
    var link = event.target.closest && event.target.closest("[data-menu-link], [data-nav-value]");
    if (!link) return;
    var details = link.closest("details");
    if (details) details.removeAttribute("open");
  }

  function findShinyTarget(inputId, value) {
    var tabset = document.getElementById(inputId);
    if (!tabset) return null;
    return Array.prototype.slice.call(tabset.querySelectorAll("[data-value]")).find(function (target) {
      return target.getAttribute("data-value") === value;
    }) || null;
  }

  function activateShinyTab(inputId, value) {
    var target = findShinyTarget(inputId, value);
    if (!target) return false;
    if (!target.classList.contains("active")) target.click();
    return true;
  }

  function restoreShinyView(value) {
    if (!isValidView(value)) return;
    if (activateShinyTab("app_view", value)) return;
    if (window.Shiny && window.Shiny.setInputValue) {
      window.Shiny.setInputValue("app_view", value, { priority: "event" });
    }
  }

  function navigateToView(value, mode) {
    if (!isValidView(value)) return;
    if (detailIsActive()) {
      state.detail.restoreFocus = false;
      requestDetailClose();
    }
    setActiveView(value);
    if (mode === "push" && window.location.hash !== "#" + value) {
      state.pendingUserView = value;
      window.history.pushState({}, "", locationForView(value));
    } else if (mode === "replace" && window.location.hash !== "#" + value) {
      window.history.replaceState({}, "", locationForView(value));
    }
    restoreShinyView(value);
    state.lastLocationSynced = locationForView(value);
    scrollViewTop();
  }

  function selectNav(event) {
    var link = event.target.closest && event.target.closest("[data-nav-value]");
    if (!link) return;
    var rawValue = link.getAttribute("data-nav-value");
    if (rawValue === "drilldown") {
      state.legacyPending = true;
      state.legacySent = false;
    }
    var value = normalizeView(rawValue);
    if (!value) return;
    event.preventDefault();
    closeMobileMenu(event);
    navigateToView(value, "push");
    if (rawValue === "drilldown") sendLegacyWorkspaceEvent();
  }

  function documentAnchor(rawHash) {
    if (!rawHash) return null;
    var id;
    try { id = decodeURIComponent(rawHash); }
    catch (_error) { id = rawHash; }
    return document.getElementById(id);
  }

  function selectHashView() {
    if (state.handlingLocation) return;
    var rawHash = window.location.hash.replace(/^#/, "");
    var raw = rawHash.toLowerCase();
    if (raw && raw !== "drilldown" && !isValidView(raw)) {
      if (documentAnchor(rawHash)) return;
      window.history.replaceState({}, "", locationForView("overview"));
      raw = "overview";
    }
    var value = normalizeView(raw) || "overview";
    var canonical = locationForView(value);
    if (state.lastLocationSynced === canonical && window.Shiny && window.Shiny.setInputValue) {
      setActiveView(value);
      return;
    }
    state.pendingUserView = null;
    state.handlingLocation = true;
    if (raw === "drilldown") {
      state.legacyPending = true;
      state.legacySent = false;
      window.history.replaceState({}, "", canonical);
    }
    if (detailIsActive()) {
      state.detail.restoreFocus = false;
      requestDetailClose();
    }
    setActiveView(value);
    restoreShinyView(value);
    state.lastLocationSynced = canonical;
    state.handlingLocation = false;
    scrollViewTop();
    sendLegacyWorkspaceEvent();
  }

  function sendLegacyWorkspaceEvent() {
    if (!state.legacyPending || state.legacySent) return;
    if (!window.Shiny || !window.Shiny.setInputValue) return;
    state.legacySent = true;
    window.Shiny.setInputValue("overview-legacy_drilldown", true, { priority: "event" });
  }

  function rememberSelectionTrigger(trigger, fallbackId) {
    state.lastSelectionTrigger = trigger || null;
    state.lastSelectionFallbackId = fallbackId || null;
    state.lastSelectionDescriptor = trigger ? Array.prototype.reduce.call(
      trigger.attributes,
      function (descriptor, attribute) {
        if (attribute.name.indexOf("data-selection-") === 0) {
          descriptor[attribute.name] = attribute.value;
        }
        return descriptor;
      },
      {}
    ) : null;
  }

  function clearClientSelectionPresentation() {
    document.querySelectorAll("[data-overview-select].is-client-selected").forEach(function (node) {
      node.classList.remove("is-client-selected");
      node.classList.toggle("is-selected", node.dataset.citySelectionWasSelected === "true");
      if (node.dataset.citySelectionPressed === "__missing__") node.removeAttribute("aria-pressed");
      else node.setAttribute("aria-pressed", node.dataset.citySelectionPressed);
      delete node.dataset.citySelectionWasSelected;
      delete node.dataset.citySelectionPressed;
    });
  }

  function showClientSelectionPresentation(trigger) {
    clearClientSelectionPresentation();
    if (!trigger) return;
    trigger.dataset.citySelectionWasSelected = trigger.classList.contains("is-selected") ? "true" : "false";
    trigger.dataset.citySelectionPressed = trigger.hasAttribute("aria-pressed")
      ? trigger.getAttribute("aria-pressed")
      : "__missing__";
    trigger.classList.add("is-selected", "is-client-selected");
    trigger.setAttribute("aria-pressed", "true");
  }

  function sendOverviewSelection(event) {
    var trigger = event.target.closest && event.target.closest("[data-overview-select]");
    if (!trigger) {
      if (event.target.closest && event.target.closest("#overview-reset")) {
        state.overviewYearFocus = null;
        setOverviewYearPressed("2027");
        clearClientSelectionPresentation();
      }
      return;
    }
    if (!window.Shiny || !window.Shiny.setInputValue) return;
    var fields = {
      year: "data-selection-year",
      flow: "data-selection-flow",
      scope: "data-selection-scope",
      department: "data-selection-department",
      fund: "data-selection-fund",
      category: "data-selection-category",
      record: "data-selection-record",
      lens: "data-selection-lens",
    };
    var selection = {};
    Object.keys(fields).forEach(function (key) {
      var value = trigger.getAttribute(fields[key]);
      if (value !== null) selection[key] = value;
    });
    rememberSelectionTrigger(trigger, null);
    showClientSelectionPresentation(trigger);
    primeDetailShell();
    var inputName = trigger.getAttribute("data-selection-input") || "overview-selection_request";
    window.Shiny.setInputValue(inputName, selection, { priority: "event" });
  }

  function setOverviewPressed(root, selector, active) {
    root.querySelectorAll(selector).forEach(function (control) {
      control.setAttribute("aria-pressed", control === active ? "true" : "false");
    });
  }

  function setOverviewYearPressed(year) {
    document.querySelectorAll(".city-overview-year-control[data-overview-year]").forEach(function (control) {
      control.setAttribute(
        "aria-pressed",
        control.getAttribute("data-overview-year") === year ? "true" : "false"
      );
    });
  }

  function activeOverviewYear() {
    return ((document.getElementById("overview-context_year") || {}).textContent || "").trim();
  }

  function sendOverviewMeasure(event) {
    var trigger = event.target.closest && event.target.closest("[data-overview-measure]");
    if (!trigger || !window.Shiny || !window.Shiny.setInputValue) return;
    var measure = trigger.getAttribute("data-overview-measure");
    if (document.activeElement === trigger) state.overviewMeasureFocus = measure;
    var group = trigger.closest(".city-story-studio__live-kpis") || document;
    setOverviewPressed(group, "[data-overview-measure]", trigger);
    window.Shiny.setInputValue("overview-measure_request", measure, {
      priority: "event"
    });
  }

  function restoreOverviewMeasureFocus() {
    if (!state.overviewMeasureFocus) return;
    var measure = state.overviewMeasureFocus;
    var target = document.querySelector('[data-overview-measure="' + measure + '"]');
    if (!target) return;
    window.requestAnimationFrame(function () {
      if (!target.isConnected) return;
      target.focus({ preventScroll: true });
      state.overviewMeasureFocus = null;
    });
  }

  function observeOverviewKpis() {
    var root = document.getElementById("overview-kpis");
    if (!root || state.overviewKpiObserver) return;
    state.overviewKpiObserver = new MutationObserver(restoreOverviewMeasureFocus);
    state.overviewKpiObserver.observe(root, { childList: true, subtree: true });
  }

  function sendOverviewYear(event) {
    var trigger = event.target.closest && event.target.closest(
      ".city-overview-year-control[data-overview-year]"
    );
    if (!trigger || !window.Shiny || !window.Shiny.setInputValue) return;
    var year = trigger.getAttribute("data-overview-year");
    if (!year) return;
    state.overviewYearFocus = document.activeElement === trigger ? { year: year } : null;
    setOverviewYearPressed(year);
    window.Shiny.setInputValue("overview-year_request", { year: year }, { priority: "event" });
  }

  function handleOverviewControlKeydown(event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    var trigger = event.target.closest && event.target.closest(
      "[data-overview-measure]"
    );
    if (!trigger) return;
    if (trigger.matches("button")) return;
    event.preventDefault();
    if (trigger.hasAttribute("data-overview-measure")) sendOverviewMeasure(event);
    else sendOverviewYear(event);
  }

  function decorateOverviewYearControls() {
    var root = document.getElementById("overview-trend_chart");
    if (!root) return;
    var plot = root.matches(".js-plotly-plot") ? root : root.querySelector(".js-plotly-plot");
    var values = plot && plot.data && plot.data[0] && plot.data[0].x;
    if (!plot || !values) return;
    var activeYear = activeOverviewYear();
    Array.prototype.forEach.call(plot.querySelectorAll(".points .point"), function (point, index) {
      var year = String(values[index] || "").replace(/^FY/, "");
      if (!/^\d{4}$/.test(year)) return;
      point.setAttribute("data-overview-year", year);
      point.setAttribute("title", "View FY" + year + " details");
      point.toggleAttribute("data-overview-selected", activeYear === "FY" + year);
    });
  }

  function renderOverviewYearControls() {
    var root = document.getElementById("overview-trend_chart");
    if (!root) return;
    var plot = root.matches(".js-plotly-plot") ? root : root.querySelector(".js-plotly-plot");
    var values = plot && plot.data && plot.data[0] && plot.data[0].x;
    if (!values) return;
    var years = values.map(function (value) { return String(value); }).filter(function (label, index, all) {
      return /^FY\d{4}$/.test(label) && all.indexOf(label) === index;
    });
    if (!years.length) return;
    var group = root.parentNode.querySelector(".city-overview-year-controls");
    if (!group) {
      group = document.createElement("div");
      group.className = "city-overview-year-controls";
      group.setAttribute("aria-label", "Select fiscal year from chart");
      root.insertAdjacentElement("afterend", group);
    }
    group.setAttribute("role", "group");
    var activeYear = activeOverviewYear();
    var retained = {};
    years.forEach(function (label, index) {
      var year = label.slice(2);
      var button = group.querySelector('.city-overview-year-control[data-overview-year="' + year + '"]');
      if (!button) {
        button = document.createElement("button");
        button.type = "button";
        button.className = "city-overview-year-control";
      }
      button.textContent = label;
      button.setAttribute("data-overview-year", year);
      button.setAttribute("aria-pressed", activeYear === label ? "true" : "false");
      button.setAttribute("aria-label", "View " + label + " details");
      button.setAttribute("title", "View " + label + " details");
      var expectedPosition = group.children[index];
      if (expectedPosition !== button) group.insertBefore(button, expectedPosition || null);
      retained[year] = true;
    });
    group.querySelectorAll(".city-overview-year-control").forEach(function (button) {
      if (!retained[button.getAttribute("data-overview-year")]) button.remove();
    });
    var plotArea = plot.querySelector(".nsewdrag");
    var barPaths = plot.querySelectorAll(".points .point path");
    if (plotArea && window.innerWidth > 600) {
      var rootBox = root.getBoundingClientRect();
      var plotBox = plotArea.getBoundingClientRect();
      group.style.marginLeft = Math.max(0, plotBox.left - rootBox.left) + "px";
      group.style.width = plotBox.width + "px";
      group.style.gridTemplateColumns = "repeat(" + years.length + ", minmax(0, 1fr))";
      group.querySelectorAll(".city-overview-year-control").forEach(function (button, index) {
        if (barPaths[index]) button.style.width = barPaths[index].getBoundingClientRect().width + "px";
      });
    } else {
      group.style.removeProperty("margin-left");
      group.style.removeProperty("width");
      group.style.removeProperty("grid-template-columns");
      group.querySelectorAll(".city-overview-year-control").forEach(function (button) {
        button.style.removeProperty("width");
      });
    }
    if (state.overviewYearFocus) {
      var focusYear = state.overviewYearFocus.year;
      var focusTarget = group.querySelector(
        '.city-overview-year-control[data-overview-year="' + focusYear + '"]'
      );
      if (focusTarget) {
        window.requestAnimationFrame(function () {
          if (!focusTarget.isConnected) return;
          focusTarget.focus({ preventScroll: true });
          state.overviewYearFocus = null;
        });
      }
    }
  }

  function observeOverviewChart() {
    var root = document.getElementById("overview-trend_chart");
    if (!root || state.overviewChartObserver) return;
    state.overviewChartObserver = new MutationObserver(function () {
      window.requestAnimationFrame(function () {
        decorateOverviewYearControls();
        renderOverviewYearControls();
      });
    });
    state.overviewChartObserver.observe(root, { childList: true, subtree: true });
    if ("ResizeObserver" in window && !state.overviewChartResizeObserver) {
      state.overviewChartResizeObserver = new ResizeObserver(function () {
        window.requestAnimationFrame(renderOverviewYearControls);
      });
      state.overviewChartResizeObserver.observe(root);
    }
  }

  function rememberIntegratedDetailTrigger(event) {
    if (detailIsActive() || !event.target.closest) return;
    if (event.target.closest("[data-overview-measure], [data-overview-year], #overview-trend_chart")) return;
    if (event.type === "keydown" && event.key !== "Enter" && event.key !== " ") return;
    if (event.target.closest(".city-detail-overlay")) return;
    var output = event.target.closest(
      "shiny-data-frame, .shiny-data-frame-output, .shiny-ipywidget-output, " +
      ".city-client-plot-output"
    );
    var overviewTrigger = event.target.closest("[data-overview-select]");
    if (!output && !overviewTrigger) return;
    var focusCandidate = event.target.closest(FOCUSABLE);
    rememberSelectionTrigger(overviewTrigger || focusCandidate || null, output && output.id ? output.id : null);
    var interactiveOutputTarget = output && event.target.closest(
      "tbody tr, .js-plotly-plot path, .js-plotly-plot rect, .js-plotly-plot circle, " +
      ".js-plotly-plot .point, .js-plotly-plot .slice"
    );
    if (
      interactiveOutputTarget &&
      DETAIL_OUTPUT_IDS[output.id] &&
      !event.target.closest("a, button, input, select, summary, textarea")
    ) {
      primeDetailShell();
      window.Shiny.setInputValue("detail_reopen_request", output.id + ":" + window.performance.now(), {
        priority: "event",
      });
    }
  }

  function isVisible(element) {
    if (!element || element.hidden || element.getAttribute("aria-hidden") === "true") return false;
    if (element.closest("[hidden], [inert], [aria-hidden='true']")) return false;
    var style = window.getComputedStyle(element);
    if (style.display === "none" || style.visibility === "hidden") return false;
    var rect = element.getBoundingClientRect();
    return element.getClientRects().length > 0 && (rect.width > 0 || rect.height > 0);
  }

  function labelDataFrameControls(frame) {
    if (!frame || !document.contains(frame)) return;
    var label = DATA_FRAME_LABELS[frame.id] || "Exact data table";
    var table = frame.querySelector("table");
    if (table && !table.getAttribute("aria-label")) table.setAttribute("aria-label", label);
    var headerCells = frame.querySelectorAll("thead tr:not(.filters) th");
    var filterRow = frame.querySelector("thead tr.filters");
    if (!filterRow) return;
    Array.prototype.slice.call(filterRow.cells).forEach(function (cell, index) {
      var header = headerCells[index];
      var headerText = header ? header.textContent.trim() : "column";
      var controls = cell.querySelectorAll("input, select");
      Array.prototype.slice.call(controls).forEach(function (control, controlIndex) {
        if (control.getAttribute("aria-label")) return;
        var suffix = "";
        if (controls.length === 2) suffix = controlIndex === 0 ? " minimum" : " maximum";
        else if (controls.length > 2) suffix = " " + (controlIndex + 1);
        control.setAttribute("aria-label", "Filter " + headerText + suffix);
      });
    });
  }

  function registerDataFrame(frame) {
    if (!frame || frame.tagName !== "SHINY-DATA-FRAME") return;
    labelDataFrameControls(frame);
    if (state.dataFrameObservers.has(frame)) return;
    var observer = new MutationObserver(function () {
      labelDataFrameControls(frame);
    });
    observer.observe(frame, { childList: true, subtree: true });
    state.dataFrameObservers.set(frame, observer);
  }

  function discoverDataFrames(root) {
    if (!root) return;
    if (root.matches && root.matches("shiny-data-frame")) registerDataFrame(root);
    if (!root.querySelectorAll) return;
    root.querySelectorAll("shiny-data-frame").forEach(registerDataFrame);
  }

  function setBackgroundInert(overlay) {
    var affected = [];
    var node = overlay;
    while (node && node.parentElement) {
      var parent = node.parentElement;
      Array.prototype.slice.call(parent.children).forEach(function (child) {
        if (child === node) return;
        if (!child.hasAttribute("data-city-inert-before")) {
          child.setAttribute("data-city-inert-before", child.inert ? "true" : "false");
        }
        child.inert = true;
        affected.push(child);
      });
      if (parent === document.body) break;
      node = parent;
    }
    return affected;
  }

  function restoreBackgroundInert(nodes) {
    (nodes || []).forEach(function (node) {
      if (!node || !node.hasAttribute("data-city-inert-before")) return;
      node.inert = node.getAttribute("data-city-inert-before") === "true";
      node.removeAttribute("data-city-inert-before");
    });
  }

  function detailShell() {
    var overlay = document.querySelector("[data-detail-overlay]");
    if (!overlay) return null;
    state.detail.element = overlay;
    state.detail.drawer = overlay.querySelector("[data-detail-drawer]") || overlay;
    return overlay;
  }

  function detailIsActive() {
    return state.detail.lifecycle !== "closed";
  }

  function resetDetailScroll() {
    var drawer = state.detail.drawer;
    if (!drawer) return;
    var body = drawer.querySelector(".city-detail-drawer__body");
    drawer.scrollTop = 0;
    if (body) body.scrollTop = 0;
  }

  function focusDetail() {
    var drawer = state.detail.drawer;
    if (!drawer) return;
    var target = drawer.querySelector("[autofocus], [data-detail-close], input, select, button, a[href], [tabindex]");
    if (target && typeof target.focus === "function") target.focus({ preventScroll: true });
  }

  function locateDetailRestoreTarget(detail) {
    var trigger = detail.trigger;
    if ((!trigger || !document.contains(trigger)) && detail.descriptor) {
      trigger = Array.prototype.slice.call(document.querySelectorAll("[data-overview-select]")).find(function (candidate) {
        return isVisible(candidate) && !candidate.closest("[data-detail-overlay]") &&
          Object.keys(detail.descriptor).every(function (name) {
            return candidate.getAttribute(name) === detail.descriptor[name];
          });
      }) || null;
    }
    if (
      trigger && document.contains(trigger) && isVisible(trigger) &&
      !trigger.closest("[data-detail-overlay]") && typeof trigger.focus === "function" &&
      (trigger.matches(FOCUSABLE) || trigger.tabIndex >= 0)
    ) {
      return trigger;
    }
    var fallback = [
      detail.fallbackId && document.getElementById(detail.fallbackId),
      document.getElementById("overview-analysis-workspace"),
      document.getElementById("main"),
    ].find(function (candidate) {
      return candidate && isVisible(candidate) && !candidate.closest("[data-detail-overlay]");
    }) || null;
    if (fallback && typeof fallback.focus === "function") {
      if (!fallback.matches(FOCUSABLE)) fallback.setAttribute("tabindex", "-1");
      return fallback;
    }
    return null;
  }

  function attemptDetailFocusRestore(force) {
    var request = state.detail.focusRestore;
    if (!request || detailIsActive()) {
      state.detail.focusRestore = null;
      return;
    }
    if (window.performance.now() > request.expiresAt) {
      state.detail.focusRestore = null;
      return;
    }
    var target = locateDetailRestoreTarget(request);
    var active = document.activeElement;
    var pageHasNoFocus = !active || active === document.body || active === document.documentElement;
    if (request.restored && !pageHasNoFocus && active !== target) {
      state.detail.focusRestore = null;
      return;
    }
    if (!target || (!force && !pageHasNoFocus && active !== target)) return;
    target.focus({ preventScroll: true });
    if (document.activeElement === target) request.restored = true;
  }

  function restoreDetailTrigger(detail) {
    state.detail.focusRestore = {
      trigger: detail.trigger,
      descriptor: detail.descriptor,
      fallbackId: detail.fallbackId,
      restored: false,
      expiresAt: window.performance.now() + 4000,
    };
    attemptDetailFocusRestore(true);
    window.setTimeout(function () {
      attemptDetailFocusRestore(true);
    }, 0);
  }

  function cancelPendingDetailFocusRestore(event) {
    if (!event.isTrusted || state.detail.lifecycle !== "closed") return;
    state.detail.focusRestore = null;
  }

  function registerDetailFocusRestoreObserver() {
    var detail = state.detail;
    var root = document.querySelector("[data-view-section='overview']");
    if (!root || detail.focusRestoreRoot === root) return;
    if (detail.focusRestoreObserver) detail.focusRestoreObserver.disconnect();
    detail.focusRestoreRoot = root;
    detail.focusRestoreObserver = new MutationObserver(function () {
      if (!detail.focusRestore || detail.focusRestoreFrame !== null) return;
      detail.focusRestoreFrame = window.requestAnimationFrame(function () {
        detail.focusRestoreFrame = null;
        attemptDetailFocusRestore(false);
      });
    });
    detail.focusRestoreObserver.observe(root, { childList: true, subtree: true });
  }

  function setDetailLifecycle(value) {
    var overlay = state.detail.element;
    var drawer = state.detail.drawer;
    state.detail.lifecycle = value;
    if (!overlay) return;
    overlay.setAttribute("data-detail-lifecycle", value);
    if (value === "closed" || value === "closing") {
      overlay.setAttribute("aria-hidden", "true");
      if (drawer) drawer.setAttribute("aria-hidden", "true");
    } else {
      overlay.setAttribute("aria-hidden", "false");
      if (drawer) drawer.setAttribute("aria-hidden", "false");
    }
    document.dispatchEvent(new CustomEvent("budget:detail-lifecycle", { detail: { lifecycle: value } }));
    if (window.performance && window.performance.mark) {
      window.performance.mark("budget-detail-" + value);
    }
  }

  function setDetailContentState(value, status) {
    var overlay = state.detail.element;
    if (!overlay) return;
    overlay.setAttribute("data-detail-content-state", value);
    var liveStatus = overlay.querySelector("[data-detail-client-status]");
    if (liveStatus) liveStatus.textContent = status || "";
  }

  function clearDetailSummaryValues() {
    var drawer = state.detail.drawer;
    if (!drawer) return;
    drawer.querySelectorAll(
      ".city-detail-metrics .shiny-text-output"
    ).forEach(function (output) {
      output.textContent = "";
    });
  }

  function stopDetailSummaryObserver() {
    if (state.detail.summaryObserver) {
      state.detail.summaryObserver.disconnect();
      state.detail.summaryObserver = null;
    }
  }

  function markDetailSummaryReady() {
    var detail = state.detail;
    var drawer = detail.drawer;
    if (!drawer || !detailIsActive() || detail.lifecycle === "closing") return;
    var title = drawer.querySelector(".city-detail-drawer__title");
    var total = drawer.querySelector(".city-detail-metrics .city-stat-card__value .shiny-text-output");
    if (!title || !total || !title.textContent.trim() || !total.textContent.trim()) return;
    if (detail.expectedTitle && title.textContent.trim() !== detail.expectedTitle) return;
    stopDetailSummaryObserver();
    setDetailContentState("ready", "Budget detail ready.");
  }

  function watchDetailSummaryReady() {
    var drawer = state.detail.drawer;
    stopDetailSummaryObserver();
    if (!drawer) return;
    markDetailSummaryReady();
    if (drawer.closest("[data-detail-overlay]").getAttribute("data-detail-content-state") === "ready") return;
    state.detail.summaryObserver = new MutationObserver(markDetailSummaryReady);
    state.detail.summaryObserver.observe(drawer, {
      childList: true,
      characterData: true,
      subtree: true,
    });
  }

  function clearCloseTimer() {
    if (state.detail.cleanupTimer !== null) {
      window.clearTimeout(state.detail.cleanupTimer);
      state.detail.cleanupTimer = null;
    }
  }

  function reducedMotion() {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function beginDetailOpen(options) {
    var overlay = detailShell();
    if (!overlay) return;
    var detail = state.detail;
    var shouldTransition = detail.lifecycle === "closed" || detail.lifecycle === "closing";
    detail.focusRestore = null;
    clearCloseTimer();
    if (shouldTransition) detail.transitionToken += 1;
    var token = detail.transitionToken;
    detail.closeRequested = false;
    if (detail.lifecycle === "closed") {
      detail.trigger = state.lastSelectionTrigger || document.activeElement;
      detail.descriptor = state.lastSelectionDescriptor;
      detail.fallbackId = state.lastSelectionFallbackId;
      detail.restoreFocus = true;
      detail.inertNodes = setBackgroundInert(overlay);
      document.body.classList.add("city-detail-open");
      document.body.setAttribute("data-city-scroll-lock", "true");
      document.body.dataset.cityOverflowBefore = document.body.style.overflow || "";
      document.body.style.overflow = "hidden";
    }
    overlay.classList.remove("is-closing");
    overlay.classList.add("is-open");
    setDetailContentState(
      (options && options.loading) ? "loading" : "ready",
      (options && options.loading) ? "Loading budget detail." : "Budget detail ready."
    );
    if (options && options.loading) {
      clearDetailSummaryValues();
      watchDetailSummaryReady();
    } else {
      stopDetailSummaryObserver();
    }
    if (!shouldTransition) return;
    setDetailLifecycle("opening");
    resetDetailScroll();
    window.requestAnimationFrame(function () {
      if (state.detail.lifecycle !== "opening" && state.detail.lifecycle !== "open") return;
      var drawer = state.detail.drawer;
      var animations = drawer && typeof drawer.getAnimations === "function"
        ? drawer.getAnimations().filter(function (animation) {
          return animation.playState === "running" || animation.playState === "pending";
        })
        : [];
      var completeOpen = function () {
        if (state.detail.lifecycle !== "opening" || token !== state.detail.transitionToken) return;
        setDetailLifecycle("open");
        resetDetailScroll();
        focusDetail();
      };
      if (!animations.length) {
        completeOpen();
        return;
      }
      Promise.allSettled(animations.map(function (animation) { return animation.finished; }))
        .then(completeOpen);
    });
  }

  function completeDetailClose(token) {
    var detail = state.detail;
    if (detail.lifecycle !== "closing" || token !== detail.transitionToken) return;
    var overlay = detail.element;
    clearCloseTimer();
    stopDetailSummaryObserver();
    if (overlay) {
      overlay.classList.remove("is-open", "is-closing");
      setDetailContentState("idle", "");
    }
    restoreBackgroundInert(detail.inertNodes);
    detail.inertNodes = [];
    document.body.classList.remove("city-detail-open");
    if (document.body.hasAttribute("data-city-scroll-lock")) {
      document.body.style.overflow = document.body.dataset.cityOverflowBefore || "";
      delete document.body.dataset.cityOverflowBefore;
      document.body.removeAttribute("data-city-scroll-lock");
    }
    var destination = detail.pendingFocusId;
    detail.pendingFocusId = null;
    var closingDetail = {
      trigger: detail.trigger,
      descriptor: detail.descriptor,
      fallbackId: detail.fallbackId,
    };
    var shouldRestoreFocus = detail.restoreFocus;
    detail.trigger = null;
    detail.descriptor = null;
    detail.fallbackId = null;
    detail.restoreFocus = true;
    detail.closeRequested = false;
    setDetailLifecycle("closed");
    if (destination) {
      focusWorkspace({ id: destination });
    } else if (shouldRestoreFocus) {
      restoreDetailTrigger(closingDetail);
    }
  }

  function beginDetailClose(options) {
    var overlay = detailShell();
    if (!overlay || state.detail.lifecycle === "closed") return;
    var detail = state.detail;
    if (options && options.restoreFocus === false) detail.restoreFocus = false;
    if (options && options.focusId) {
      detail.restoreFocus = false;
      detail.pendingFocusId = options.focusId;
    }
    if (detail.lifecycle === "closing") return;
    detail.transitionToken += 1;
    var token = detail.transitionToken;
    setDetailLifecycle("closing");
    overlay.classList.add("is-closing");
    overlay.classList.remove("is-open");
    if (reducedMotion()) {
      completeDetailClose(token);
      return;
    }
    detail.cleanupTimer = window.setTimeout(function () {
      completeDetailClose(token);
    }, 700);
  }

  function primeDetailShell() {
    beginDetailOpen({ loading: true });
  }

  function requestDetailClose() {
    if (!detailIsActive()) return;
    beginDetailClose();
    if (state.detail.closeRequested) return;
    state.detail.closeRequested = true;
    var close = state.detail.drawer && state.detail.drawer.querySelector("[data-detail-close]");
    if (close) close.click();
  }

  function handleDetailClick(event) {
    var overlay = event.target.closest && event.target.closest("[data-detail-overlay]");
    if (!overlay) return;
    if (event.target.closest("[data-detail-back], [data-detail-clear]")) {
      clearClientSelectionPresentation();
    }
    if (event.target.closest("[data-detail-backdrop]")) {
      state.detail.closeRequested = true;
      beginDetailClose();
    } else if (event.target.closest("[data-detail-expand], [data-detail-inspect]")) {
      var target = event.target.closest("[data-detail-inspect]")
        ? "overview-records"
        : "overview-analysis-workspace";
      state.detail.closeRequested = true;
      beginDetailClose({ restoreFocus: false, focusId: target });
    } else if (event.target.closest("[data-detail-close]")) {
      state.detail.closeRequested = true;
      beginDetailClose();
    }
  }

  function trapDetailFocus(event) {
    if (!detailIsActive() || state.detail.lifecycle === "closing") return;
    var drawer = state.detail.drawer;
    if (!drawer) return;
    if (event.key === "Escape") {
      event.preventDefault();
      requestDetailClose();
      return;
    }
    if (event.key !== "Tab") return;
    var focusable = Array.prototype.slice.call(drawer.querySelectorAll(FOCUSABLE)).filter(isVisible);
    if (!focusable.length) {
      event.preventDefault();
      drawer.setAttribute("tabindex", "-1");
      drawer.focus();
      return;
    }
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function keepFocusInsideDetail(event) {
    if (!detailIsActive() || state.detail.lifecycle === "closing") return;
    var drawer = state.detail.drawer;
    if (drawer && !drawer.contains(event.target)) focusDetail();
  }

  function syncDetailLifecycle(message) {
    var detail = state.detail;
    var overlay = detailShell();
    if (!message || !overlay) return;
    var generation = Number(message.generation);
    var hasGeneration = Number.isFinite(generation);
    if (hasGeneration && generation < detail.lifecycleGeneration) return;
    if (hasGeneration) detail.lifecycleGeneration = generation;
    if (message.open) {
      if (!hasGeneration && detail.lifecycle === "closing" && detail.closeRequested) return;
      var changed = detail.contentKey !== null && detail.contentKey !== message.content_key;
      detail.contentKey = message.content_key || detail.contentKey;
      detail.expectedTitle = message.title || null;
      if (message.lens) overlay.setAttribute("data-detail-lens", message.lens);
      if (message.accent) overlay.setAttribute("data-detail-accent", message.accent);
      beginDetailOpen({ loading: message.content_state !== "ready" });
      if (message.content_state) {
        setDetailContentState(
          message.content_state,
          message.content_state === "ready" ? "Budget detail ready." : "Loading budget detail."
        );
      }
      if (changed) {
        resetDetailScroll();
        window.requestAnimationFrame(function () {
          if (detailIsActive()) {
            resetDetailScroll();
            focusDetail();
          }
        });
      }
      return;
    }
    beginDetailClose();
  }

  function copyBookmarkedUrl(message) {
    if (!message || !message.url) return;
    var url;
    try { url = new URL(message.url, window.location.href); }
    catch (_error) { return; }
    var current = viewFromLocation();
    var candidate = normalizeView(url.hash.replace(/^#/, "").toLowerCase());
    url.hash = "#" + (current || candidate || "overview");
    window.history.replaceState({}, "", url.pathname + url.search + url.hash);
    var status = document.querySelector("[data-copy-status]");
    var copied = window.location.href;
    if (!navigator.clipboard) {
      if (status) status.textContent = "Shareable URL is ready in the address bar";
      return;
    }
    navigator.clipboard.writeText(copied).then(function () {
      if (!status) return;
      var original = status.textContent;
      status.textContent = "Link copied";
      window.setTimeout(function () { status.textContent = original; }, 1800);
    }).catch(function () {
      if (status) status.textContent = "Shareable URL is ready in the address bar";
    });
  }

  function focusWorkspace(message) {
    var id = message && (message.id || message.target || message.element);
    if (!id) return;
    if (detailIsActive()) {
      state.detail.restoreFocus = false;
      state.detail.pendingFocusId = id;
      return;
    }
    var attempts = 0;
    var maxAttempts = 60;
    function attemptFocus() {
      var target = document.getElementById(id);
      if (!target || !isVisible(target) || target.closest("[inert]")) {
        attempts += 1;
        if (attempts < maxAttempts) window.setTimeout(attemptFocus, 50);
        return;
      }
      var noMotion = reducedMotion();
      try { target.scrollIntoView({ behavior: noMotion ? "auto" : "smooth", block: "start" }); }
      catch (_error) { target.scrollIntoView(); }
      if (typeof target.focus === "function") {
        if (!target.matches(FOCUSABLE)) target.setAttribute("tabindex", "-1");
        target.focus({ preventScroll: true });
        if (document.activeElement !== target) {
          attempts += 1;
          if (attempts < maxAttempts) window.setTimeout(attemptFocus, 50);
        }
      }
    }
    attemptFocus();
  }

  function syncSourceStatus(message) {
    var shell = document.getElementById("source_status_shell");
    if (!shell || !message) return;
    var state = String(message.state || "loading");
    var statusClass = String(message.status_class || "loading");
    var classes = ["city-source-status", "city-source-status--" + statusClass];
    shell.className = classes.join(" ");
    shell.setAttribute("role", "status");
    shell.setAttribute("aria-live", "polite");
    shell.setAttribute("aria-busy", message.aria_busy ? "true" : "false");
    shell.setAttribute("data-source-state", state);
    var icon = shell.querySelector("[data-source-status-icon]");
    var messageNode = shell.querySelector("[data-source-status-message]");
    var detailNode = shell.querySelector("[data-source-status-detail]");
    var timestampNode = shell.querySelector("[data-source-status-timestamp]");
    if (icon) {
      icon.className = "city-status__icon city-status__dot city-status__icon--" + statusClass;
      icon.textContent = message.icon || "";
      icon.setAttribute("aria-hidden", "true");
    }
    if (messageNode) messageNode.textContent = message.message || "";
    if (detailNode) detailNode.textContent = message.detail || "";
    if (timestampNode) timestampNode.textContent = message.timestamp || "";
    var retry = document.getElementById("retry_source");
    if (retry) {
      retry.disabled = !!message.button_disabled;
      retry.setAttribute("aria-busy", message.button_disabled ? "true" : "false");
      retry.textContent = message.button_label || "Refresh source";
    }
  }

  function registerShinyHandlers() {
    if (!window.Shiny || !window.Shiny.addCustomMessageHandler || window.__budgetHandlersReady) return;
    window.__budgetHandlersReady = true;
    window.Shiny.addCustomMessageHandler("budget-view-selected", function (message) {
      if (message && message.view === "drilldown") state.legacySent = false;
      var value = normalizeView(message && message.view);
      if (!value) return;
      var renderedTarget = findShinyTarget("app_view", value);
      if (renderedTarget && !renderedTarget.classList.contains("active")) return;
      if (state.pendingUserView && state.pendingUserView !== value) return;
      setActiveView(value);
      if (state.pendingUserView === value) {
        state.pendingUserView = null;
        return;
      }
      if (!state.pendingUserView) {
        window.history.replaceState({}, "", locationForView(value));
        state.lastLocationSynced = locationForView(value);
        scrollViewTop();
      }
      sendLegacyWorkspaceEvent();
    });
    window.Shiny.addCustomMessageHandler("budget-bookmarked", copyBookmarkedUrl);
    window.Shiny.addCustomMessageHandler("budget-workspace-focus", focusWorkspace);
    window.Shiny.addCustomMessageHandler("budget-detail-lifecycle", syncDetailLifecycle);
    window.Shiny.addCustomMessageHandler("budget-source-status", syncSourceStatus);
    window.Shiny.addCustomMessageHandler("budget-plotly-react", function renderPlot(message) {
      var host = message && document.getElementById(message.id);
      if (!host) return;
      if (!window.Plotly || !window.Plotly.react) {
        window.setTimeout(function () { renderPlot(message); }, 25);
        return;
      }
      window.Plotly.react(
        host,
        message.data || [],
        message.layout || {},
        message.config || { displaylogo: false, responsive: true }
      ).then(function () {
        host.__budgetPlotMessage = message;
        Array.from(host.querySelectorAll("g.trace.bars")).forEach(function (group, curveNumber) {
          Array.from(group.querySelectorAll("path")).forEach(function (mark, pointIndex) {
            mark.addEventListener("click", function () {
              var trace = (message.data || [])[curveNumber] || {};
              var customdata = (trace.customdata || [])[pointIndex];
              if (message.inputId) {
                window.Shiny.setInputValue(
                  message.inputId,
                  {
                    customdata: customdata,
                    pointIndex: pointIndex,
                    curveNumber: curveNumber
                  },
                  { priority: "event" }
                );
              }
              if (message.selectionInputId && customdata) {
                var selection = Object.assign({}, message.selection || {}, {
                  department: customdata,
                  fund: null,
                  category: null
                });
                window.Shiny.setInputValue(
                  message.selectionInputId,
                  selection,
                  { priority: "event" }
                );
              }
            }, true);
          });
        });
        if (host.removeAllListeners && host.on) {
          host.removeAllListeners("plotly_click");
          host.on("plotly_click", function (plotEvent) {
            var point = plotEvent && plotEvent.points && plotEvent.points[0];
            if (!point) return;
            if (message.inputId) {
              window.Shiny.setInputValue(
                message.inputId,
                {
                  customdata: point.customdata,
                  pointIndex: point.pointIndex,
                  curveNumber: point.curveNumber
                },
                { priority: "event" }
              );
            }
            if (message.selectionInputId && point.customdata) {
              var selection = Object.assign({}, message.selection || {}, {
                department: point.customdata,
                fund: null,
                category: null
              });
              window.Shiny.setInputValue(
                message.selectionInputId,
                selection,
                { priority: "event" }
              );
            }
          });
        }
        if (host.__budgetClickHandler) {
          host.removeEventListener("click", host.__budgetClickHandler, true);
        }
        host.__budgetClickHandler = function (event) {
          var mark = event.target && event.target.closest &&
            event.target.closest(".barlayer path, .scatterlayer path, .point");
          if (!mark || !message.inputId) return;
          var marks = Array.from(host.querySelectorAll(".barlayer path, .scatterlayer path, .point"));
          var flatIndex = marks.indexOf(mark);
          if (flatIndex < 0) return;
          var pointIndex = flatIndex;
          var curveNumber = 0;
          for (var index = 0; index < (message.data || []).length; index += 1) {
            var values = message.data[index].customdata || [];
            if (pointIndex < values.length) {
              curveNumber = index;
              break;
            }
            pointIndex -= values.length;
          }
          var trace = (message.data || [])[curveNumber] || {};
          var customdata = (trace.customdata || [])[pointIndex];
          window.Shiny.setInputValue(
            message.inputId,
            {
              customdata: customdata,
              pointIndex: pointIndex,
              curveNumber: curveNumber
            },
            { priority: "event" }
          );
        };
        host.addEventListener("click", host.__budgetClickHandler, true);
      });
    });
    sendLegacyWorkspaceEvent();
  }

  document.addEventListener("click", closeMobileMenu);
  document.addEventListener("click", function (event) {
    var host = event.target && event.target.closest &&
      event.target.closest(".city-client-plot");
    var message = host && host.__budgetPlotMessage;
    if (!host || !message || !message.inputId) return;
    var marks = Array.from(host.querySelectorAll(".barlayer path"));
    var mark = event.target.closest && event.target.closest(".barlayer path");
    if (!mark && marks.length) {
      mark = marks.reduce(function (nearest, candidate) {
        var rect = candidate.getBoundingClientRect();
        var dx = event.clientX - Math.max(rect.left, Math.min(event.clientX, rect.right));
        var dy = event.clientY - Math.max(rect.top, Math.min(event.clientY, rect.bottom));
        var distance = dx * dx + dy * dy;
        return !nearest || distance < nearest.distance ? { mark: candidate, distance: distance } : nearest;
      }, null).mark;
    }
    var flatIndex = marks.indexOf(mark);
    if (flatIndex < 0) return;
    var pointIndex = flatIndex;
    var curveNumber = 0;
    for (var index = 0; index < (message.data || []).length; index += 1) {
      var values = message.data[index].customdata || [];
      if (pointIndex < values.length) {
        curveNumber = index;
        break;
      }
      pointIndex -= values.length;
    }
    var trace = (message.data || [])[curveNumber] || {};
    var customdata = (trace.customdata || [])[pointIndex];
    window.Shiny.setInputValue(
      message.inputId,
      {
        customdata: customdata,
        pointIndex: pointIndex,
        curveNumber: curveNumber
      },
      { priority: "event" }
    );
    if (message.selectionInputId && customdata) {
      var selection = Object.assign({}, message.selection || {}, {
        department: customdata,
        fund: null,
        category: null
      });
      window.Shiny.setInputValue(message.selectionInputId, selection, { priority: "event" });
    }
  }, true);
  document.addEventListener("click", selectNav);
  document.addEventListener("click", sendOverviewMeasure);
  document.addEventListener("click", sendOverviewYear);
  document.addEventListener("click", sendOverviewSelection);
  document.addEventListener("click", handleDetailClick);
  document.addEventListener("pointerdown", rememberIntegratedDetailTrigger, true);
  document.addEventListener("keydown", rememberIntegratedDetailTrigger, true);
  document.addEventListener("keydown", handleOverviewControlKeydown);
  document.addEventListener("pointerdown", cancelPendingDetailFocusRestore, true);
  document.addEventListener("keydown", cancelPendingDetailFocusRestore, true);
  document.addEventListener("keydown", trapDetailFocus);
  document.addEventListener("focusin", keepFocusInsideDetail);
  document.addEventListener("focusin", function (event) {
    if (event.target && event.target.closest && event.target.closest(".city-header")) revealHeader();
  });
  document.addEventListener("toggle", function (event) {
    if (event.target && event.target.open && event.target.closest(".city-header")) revealHeader();
  }, true);
  document.addEventListener("shiny:bound", function (event) { discoverDataFrames(event.target); });
  document.addEventListener("shiny:recalculated", function (event) {
    discoverDataFrames(event.target);
    observeOverviewChart();
    observeOverviewKpis();
    restoreOverviewMeasureFocus();
    window.requestAnimationFrame(decorateOverviewYearControls);
    window.requestAnimationFrame(renderOverviewYearControls);
    window.setTimeout(decorateOverviewYearControls, 250);
    window.setTimeout(renderOverviewYearControls, 250);
    window.setTimeout(decorateOverviewYearControls, 1000);
    window.setTimeout(renderOverviewYearControls, 1000);
    registerDetailFocusRestoreObserver();
    window.requestAnimationFrame(function () {
      attemptDetailFocusRestore(false);
    });
  });
  window.addEventListener("popstate", selectHashView);
  window.addEventListener("hashchange", selectHashView);
  window.addEventListener("scroll", queueHeaderScrollUpdate, { passive: true });
  document.addEventListener("DOMContentLoaded", function () {
    initializeHeaderScroll();
    registerShinyHandlers();
    detailShell();
    registerDetailFocusRestoreObserver();
    discoverDataFrames(document);
    selectHashView();
    observeOverviewChart();
    observeOverviewKpis();
    [500, 1500, 3000, 5000].forEach(function (delay) {
      window.setTimeout(function () {
        decorateOverviewYearControls();
        renderOverviewYearControls();
      }, delay);
    });
    var overlay = detailShell();
    if (overlay) {
      overlay.addEventListener("transitionend", function (event) {
        if (event.target !== overlay || event.propertyName !== "opacity") return;
        if (state.detail.lifecycle === "closing") completeDetailClose(state.detail.transitionToken);
      });
    }
  });
  document.addEventListener("shiny:connected", function () {
    registerShinyHandlers();
    selectHashView();
    registerDetailFocusRestoreObserver();
    discoverDataFrames(document);
  });
})();
