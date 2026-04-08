(() => {
  const PAGE_SIZE = 100;
  let allData = [];
  let filtered = [];
  let displayed = 0;

  const $ = (id) => document.getElementById(id);
  const tbody = $("table-body");
  const searchInput = $("search");
  const filterSet = $("filter-set");
  const filterCondition = $("filter-condition");
  const filterStock = $("filter-stock");
  const sortBy = $("sort-by");
  const resetBtn = $("reset-btn");
  const loadMoreBtn = $("load-more");
  const statsEl = $("stats");
  const updatedEl = $("updated-at");

  // Show loading state
  tbody.innerHTML = '<tr><td colspan="7" class="loading">Loading card data</td></tr>';

  Papa.parse("data.csv", {
    download: true,
    header: true,
    skipEmptyLines: true,
    complete(results) {
      allData = results.data.filter((r) => r["Card Name"]);
      buildFilterOptions();
      applyFilters();

      // Show last updated from file mod or fallback
      updatedEl.textContent = `${allData.length.toLocaleString()} cards loaded. Data refreshes daily via GitHub Actions.`;
    },
    error(err) {
      tbody.innerHTML = `<tr><td colspan="7" style="padding:2rem;text-align:center;color:#e05555">Failed to load data: ${err.message}</td></tr>`;
    },
  });

  function buildFilterOptions() {
    const sets = new Set();
    const conditions = new Set();
    allData.forEach((r) => {
      if (r["Set"]) sets.add(r["Set"]);
      if (r["Condition"]) conditions.add(r["Condition"]);
    });

    [...sets]
      .sort()
      .forEach((s) => {
        const opt = document.createElement("option");
        opt.value = s;
        opt.textContent = s;
        filterSet.appendChild(opt);
      });

    [...conditions]
      .sort()
      .forEach((c) => {
        const opt = document.createElement("option");
        opt.value = c;
        opt.textContent = c;
        filterCondition.appendChild(opt);
      });
  }

  function parsePrice(p) {
    if (!p) return 0;
    return parseFloat(p.replace(/[^0-9.]/g, "")) || 0;
  }

  function applyFilters() {
    const query = searchInput.value.trim().toLowerCase();
    const setVal = filterSet.value;
    const condVal = filterCondition.value;
    const stockVal = filterStock.value;
    const sort = sortBy.value;

    filtered = allData.filter((r) => {
      if (query && !r["Card Name"].toLowerCase().includes(query)) return false;
      if (setVal && r["Set"] !== setVal) return false;
      if (condVal && r["Condition"] !== condVal) return false;
      if (stockVal && r["In Stock"] !== stockVal) return false;
      return true;
    });

    // Sort
    filtered.sort((a, b) => {
      switch (sort) {
        case "name-asc":
          return a["Card Name"].localeCompare(b["Card Name"]);
        case "name-desc":
          return b["Card Name"].localeCompare(a["Card Name"]);
        case "price-asc":
          return parsePrice(a["Price (AUD)"]) - parsePrice(b["Price (AUD)"]);
        case "price-desc":
          return parsePrice(b["Price (AUD)"]) - parsePrice(a["Price (AUD)"]);
        case "set-asc":
          return (a["Set"] || "").localeCompare(b["Set"] || "");
        default:
          return 0;
      }
    });

    displayed = 0;
    tbody.innerHTML = "";
    renderPage();

    statsEl.textContent = `${filtered.length.toLocaleString()} of ${allData.length.toLocaleString()} cards`;
  }

  function renderPage() {
    const end = Math.min(displayed + PAGE_SIZE, filtered.length);
    const fragment = document.createDocumentFragment();

    for (let i = displayed; i < end; i++) {
      const r = filtered[i];
      const tr = document.createElement("tr");
      const inStock = r["In Stock"] === "Yes";

      tr.innerHTML =
        `<td class="col-name">${esc(r["Card Name"])}</td>` +
        `<td class="col-set">${esc(r["Set"])}</td>` +
        `<td class="col-condition">${esc(r["Condition"])}</td>` +
        `<td class="col-price">${esc(r["Price (AUD)"])}</td>` +
        `<td class="col-stock"><span class="${inStock ? "stock-yes" : "stock-no"}">${inStock ? "Yes" : "No"}</span></td>` +
        `<td class="col-qty">${esc(r["Qty In Stock"] || r["Inventory Qty"] || "")}</td>` +
        `<td class="col-sku">${esc(r["SKU"] || "")}</td>`;

      fragment.appendChild(tr);
    }

    tbody.appendChild(fragment);
    displayed = end;

    loadMoreBtn.style.display = displayed < filtered.length ? "inline-block" : "none";
  }

  function esc(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // Debounce search
  let timer;
  searchInput.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(applyFilters, 250);
  });

  filterSet.addEventListener("change", applyFilters);
  filterCondition.addEventListener("change", applyFilters);
  filterStock.addEventListener("change", applyFilters);
  sortBy.addEventListener("change", applyFilters);
  loadMoreBtn.addEventListener("click", renderPage);

  resetBtn.addEventListener("click", () => {
    searchInput.value = "";
    filterSet.value = "";
    filterCondition.value = "";
    filterStock.value = "Yes";
    sortBy.value = "name-asc";
    applyFilters();
  });
})();
