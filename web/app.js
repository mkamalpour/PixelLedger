"use strict";
const $ = (s, r = document) => r.querySelector(s);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};
const money = (n) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    (Number(n) || 0) / 100,
  );
const number = (n) => new Intl.NumberFormat("en-US").format(Number(n) || 0);
const runtime = (() => {
  try {
    return JSON.parse($("#pixelledger-runtime").textContent);
  } catch {
    return {};
  }
})();
let state = null,
  view = "overview",
  busy = false,
  auto = false,
  timer = null,
  schema = null,
  lastFocus = null;
const filters = {
  inventory: "",
  category: "All categories",
  low: false,
  orders: "All statuses",
  customers: "",
};
const titles = {
  overview: [
    "THE BIG PICTURE",
    "Your shop, in play.",
    "Keep the shelves stocked and the next move yours.",
  ],
  inventory: [
    "ON THE SHELVES",
    "Stock the next big thing.",
    "Price with intention. Replenish before demand moves on.",
  ],
  orders: [
    "THE SALES DESK",
    "Every order has a story.",
    "From the first click to the final delivery, you are in control.",
  ],
  customers: [
    "YOUR COMMUNITY",
    "Know your regulars.",
    "A good game shop is built on returning players.",
  ],
  sql: [
    "UNDER THE HOOD",
    "Ask your shop anything.",
    "Explore the live database with safe, read-only SQL.",
  ],
  activity: [
    "THE SHOP JOURNAL",
    "Watch the world respond.",
    "Market shifts, purchases, and the consequences of your decisions.",
  ],
  settings: [
    "SHOP SETTINGS",
    "Make a fresh start.",
    "A reproducible world, safely separate from real money.",
  ],
};
const navItems = [
  ["overview", "Overview", "\u25a6"],
  ["inventory", "Inventory", "\u25a4"],
  ["orders", "Orders", "\u25a7"],
  ["customers", "Customers", "\u2637"],
  ["sql", "SQL lab", ">_"],
  ["activity", "Activity", "\u25f4"],
];
for (const [id, label, icon] of navItems) {
  const b = el("button", "nav-button");
  b.dataset.view = id;
  const glyph = el("span", "nav-icon", icon);
  glyph.setAttribute("aria-hidden", "true");
  b.append(glyph, el("span", "", label));
  $("#nav").append(b);
}
const mobileSettings = el("button", "nav-button mobile-settings", "Settings");
mobileSettings.dataset.view = "settings";
$("#nav").append(mobileSettings);
function button(text, fn, cls = "button small") {
  const b = el("button", cls, text);
  b.type = "button";
  b.addEventListener("click", fn);
  return b;
}
function tag(text, kind = "") {
  return el("span", "tag " + kind, text);
}
function toast(text) {
  const n = $("#toast");
  n.textContent = text;
  n.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (n.hidden = true), 4500);
}
function banner(text) {
  $("#error-banner").textContent = text;
  $("#error-banner").hidden = !text;
}
async function request(path, method = "GET", body) {
  const c = new AbortController(),
    t = setTimeout(() => c.abort(), 30000);
  try {
    const r = await fetch("/api" + path, {
      method,
      signal: c.signal,
      headers: {
        "Content-Type": "application/json",
        ...(runtime.apiKey ? { "X-API-Key": runtime.apiKey } : {}),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    let data;
    try {
      data = await r.json();
    } catch {
      throw Error("The shop returned an unreadable response. Try again.");
    }
    if (!r.ok) {
      const detail =
        data.detail || data.error || "Request could not be completed.";
      throw Error(
        Array.isArray(detail)
          ? detail.map((x) => x.msg).join("; ")
          : typeof detail === "string"
            ? detail
            : JSON.stringify(detail),
      );
    }
    $("#connection").textContent = "Shop connected";
    return data;
  } catch (e) {
    if (e.name === "AbortError")
      throw Error(
        "The request timed out. Check the shop connection before trying again.",
      );
    throw e;
  } finally {
    clearTimeout(t);
  }
}
function setBusy(value) {
  busy = value;
  document
    .querySelectorAll("button[data-mutate],#advance,#new-order")
    .forEach((b) => (b.disabled = value || !state));
  $("#advance").textContent = value
    ? "Updating shop..."
    : "Advance a day \u2192";
}
async function mutate(path, body = {}, method = "POST", close = true) {
  if (busy) return false;
  setBusy(true);
  try {
    const data = await request(path, method, body);
    state = data.state || data;
    banner("");
    if (close && $("#dialog").open) $("#dialog").close();
    render();
    toast("Shop updated.");
    return true;
  } catch (e) {
    const form = $("#dialog-content .form-error");
    if ($("#dialog").open && form) {
      form.textContent = e.message;
      form.hidden = false;
    } else banner(e.message);
    return false;
  } finally {
    setBusy(false);
  }
}
const id = () =>
  crypto.randomUUID
    ? crypto.randomUUID()
    : Date.now().toString(36) + "-" + Math.random().toString(36).slice(2);
function changeView(next) {
  if (!titles[next]) next = "overview";
  view = next;
  location.hash = next;
  render();
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-view]");
  if (b) changeView(b.dataset.view);
});
window.addEventListener("hashchange", () => {
  const next = location.hash.slice(1);
  if (titles[next] && next !== view) {
    view = next;
    render();
  }
});
$("#advance").addEventListener("click", () => advance(1));
$("#new-order").addEventListener("click", createOrder);
$("#close-dialog").addEventListener("click", () => $("#dialog").close());
$("#dialog").addEventListener("close", () => lastFocus?.focus());
function showDialog(title) {
  lastFocus = document.activeElement;
  $("#dialog-title").textContent = title;
  $("#dialog-content").replaceChildren();
  $("#dialog").showModal();
  return $("#dialog-content");
}
function formBase(title) {
  const container = showDialog(title),
    form = el("form");
  form.append(el("div", "form-error"));
  $(".form-error", form).hidden = true;
  container.append(form);
  return form;
}
function field(label, type = "text", value = "", attrs = {}) {
  const l = el("label", "field", label),
    i = el(type === "select" ? "select" : "input");
  if (type !== "select") i.type = type;
  i.value = value;
  Object.assign(i, attrs);
  l.append(i);
  return [l, i];
}
function formFooter(form, text = "Save changes") {
  const f = el("div", "form-footer"),
    save = el("button", "button primary", text);
  save.type = "submit";
  save.dataset.mutate = "true";
  f.append(
    button("Cancel", () => $("#dialog").close(), "button"),
    save,
  );
  form.append(f);
}
function panel(title, subtitle, action) {
  const p = el("section", "panel"),
    h = el("div", "panel-head"),
    left = el("div");
  left.append(el("h2", "", title));
  if (subtitle) left.append(el("p", "panel-subtitle", subtitle));
  h.append(left);
  if (action) h.append(action);
  p.append(h);
  return p;
}
function empty(target, title, text) {
  const e = el("div", "empty");
  e.append(el("strong", "", title), el("span", "", text));
  target.append(e);
}
function table(headers, rows) {
  const wrap = el("div", "table-wrap"),
    t = el("table"),
    head = el("thead"),
    tr = el("tr");
  headers.forEach((h) => tr.append(el("th", "", h)));
  head.append(tr);
  const body = el("tbody");
  for (const cells of rows) {
    const r = el("tr");
    for (const c of cells) {
      const td = el("td");
      td.append(
        c instanceof Node ? c : document.createTextNode(String(c ?? "")),
      );
      r.append(td);
    }
    body.append(r);
  }
  t.append(head, body);
  wrap.append(t);
  return wrap;
}
function render() {
  if (!state) return;
  const [over, title, sub] = titles[view];
  $("#eyebrow").textContent = over;
  $("#title").textContent = title;
  $("#subtitle").textContent = sub;
  $("#crumb").textContent =
    navItems.find((x) => x[0] === view)?.[1] || "Settings";
  $("#day").textContent = "DAY " + state.day;
  document.querySelectorAll(".nav-button").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === view);
    if (b.dataset.view === view) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
  const c = $("#content");
  c.replaceChildren();
  ({
    overview: overview,
    inventory: inventory,
    orders: orders,
    customers: customers,
    sql: sqlView,
    activity: activity,
    settings: settings,
  })[view](c);
  setBusy(busy);
}
function metric(label, value, note, kind = "") {
  const n = el("article", "metric");
  n.append(
    el("div", "label", label),
    el("div", "metric-value " + kind, value),
    el("div", "metric-note", note),
  );
  return n;
}
function overview(c) {
  c.append(button('Download financial report', async () => {
    try {
      const report = await request('/report');
      const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], {type: 'application/json'}));
      const link = el('a');
      link.href = url;
      link.download = 'pixelledger-day-' + report.day + '.json';
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { toast(error.message); }
  }));
  const m = state.metrics,
    metrics = el("div", "metrics");
  metrics.append(
    metric(
      "AVAILABLE CASH",
      money(state.cash_cents),
      "Restock budget after shop expenses",
      state.cash_cents < 0 ? "negative" : "",
    ),
    metric(
      "NET SALES",
      money(m.net_sales_cents),
      "Paid revenue, less refunds; tax excluded",
    ),
    metric(
      "ESTIMATED PROFIT",
      money(m.profit_cents),
      "Net sales less goods and operating costs",
      m.profit_cents < 0 ? "negative" : "positive",
    ),
    metric(
      "INVENTORY VALUE",
      money(m.inventory_value_cents),
      number(m.low_stock_count) + " products need a stock check",
    ),
  );
  c.append(metrics);
  const grid = el("div", "overview-grid");
  const chart = panel(
    "Sales, day by day",
    "Paid revenue less refunds, excluding sales tax",
    tag("USD / NET SALES"),
  );
  const history = state.history.slice(-14),
    bars = el("div", "chart");
  const max = Math.max(
    1,
    ...history.map((x) => Math.max(0, x.net_sales_cents)),
  );
  history
    .filter((h) => history.some((x) => x.net_sales_cents !== 0))
    .forEach((h) => {
      const w = el("div", "bar-wrap"),
        bar = el("div", "bar");
      bar.style.height =
        Math.max(1, (Math.max(0, h.net_sales_cents) / max) * 95) + "%";
      w.title = "Day " + h.day + ": " + money(h.net_sales_cents);
      w.setAttribute("role", "img");
      w.setAttribute("aria-label", w.title);
      w.append(bar);
      bars.append(w);
    });
  if (!history.some((x) => x.net_sales_cents !== 0))
    bars.append(
      el("div", "chart-empty", "Advance a day to see your first sales."),
    );
  const labels = el("div", "chart-labels");
  labels.append(
    el("span", "", "DAY " + (history[0]?.day ?? state.day)),
    el(
      "span",
      "",
      history.length < 2
        ? "OPENING DAY"
        : "DAY " + (history.at(-1)?.day ?? state.day),
    ),
  );
  chart.append(bars, labels);
  grid.append(chart);
  const market = panel("The market today", "", tag("LIVE CONDITIONS"));
  market.classList.add("market");
  const mc = el("div", "market-content");
  mc.append(
    el(
      "p",
      "label",
      "DAY " + state.day + " / " + (state.date || "YOUR SHOP WORLD"),
    ),
    el("h3", "", state.market.title),
    el("p", "", state.market.description),
  );
  const stats = el("div", "market-stats");
  stats.append(
    el("span", "", state.market.category || "All categories"),
    el(
      "strong",
      "",
      Number(state.market.multiplier || 1).toFixed(2) + "x demand",
    ),
  );
  mc.append(stats);
  const controls = el("div", "sim-controls");
  const a = button("Advance 7 days", () => advance(7), "button lime");
  a.dataset.mutate = "true";
  controls.append(
    a,
    button(
      auto ? "Pause auto-play" : "Auto-play: off",
      () => {
        auto = !auto;
        configureAuto();
        render();
      },
      "button",
    ),
  );
  mc.append(
    controls,
    el(
      "p",
      "hint",
      auto
        ? "Auto-play advances one day every 10 seconds while this page is visible."
        : "Time is paused. Advance a day to bring in customers and move paid orders forward.",
    ),
  );
  market.append(mc);
  grid.append(market);
  c.append(grid);
  const bottom = el("div", "bottom-grid");
  const stock = panel(
    "Shelf watch",
    "Low stock first. Your next restock starts here.",
    button("View inventory", () => changeView("inventory"), "link-button"),
  );
  const products = [...state.products]
    .sort(
      (a, b) =>
        (a.stock > a.reorder_point) - (b.stock > b.reorder_point) ||
        a.stock - b.stock,
    )
    .slice(0, 4);
  stock.append(
    table(
      ["PRODUCT", "STOCK", "PRICE", "ACTIONS"],
      products.map((p) => [
        productCell(p),
        stockCell(p),
        money(p.price_cents),
        button("Restock", () => restock(p)),
      ]),
    ),
  );
  bottom.append(stock);
  const journal = panel(
    "Shop signals",
    "The latest from your shop floor",
    button("View all", () => changeView("activity"), "link-button"),
  );
  journal.append(eventList(state.events.slice(0, 4)));
  bottom.append(journal);
  c.append(bottom);
}
function productCell(p) {
  const n = el("div", "product-name"),
    icon = el(
      "span",
      "product-icon",
      (p.category || "GM").slice(0, 2).toUpperCase(),
    ),
    text = el("div", "", p.name);
  text.append(el("span", "secondary", p.category + " / " + p.sku));
  n.append(icon, text);
  return n;
}
function stockCell(p) {
  const n = el(
    "span",
    p.stock <= p.reorder_point ? "stock-low" : "",
    number(p.stock) + " units",
  );
  if (p.stock <= p.reorder_point)
    n.append(
      el(
        "span",
        "secondary",
        p.stock === 0 ? "Out of stock" : "Reorder at " + p.reorder_point,
      ),
    );
  return n;
}
function searchInput(placeholder, value, fn) {
  const i = el("input");
  i.type = "search";
  i.placeholder = placeholder;
  i.setAttribute("aria-label", placeholder);
  i.value = value;
  i.addEventListener("input", fn);
  return i;
}
function inventory(c) {
  const p = panel(
      "Product catalog",
      state.products.length + " games, gear, and collectibles",
    ),
    toolbar = el("div", "toolbar");
  const results = el("div");
  const search = searchInput(
    "Search products or SKU",
    filters.inventory,
    (e) => {
      filters.inventory = e.target.value;
      draw();
    },
  );
  const cat = el("select");
  cat.setAttribute("aria-label", "Filter category");
  ["All categories", ...new Set(state.products.map((x) => x.category))].forEach(
    (x) => cat.add(new Option(x, x)),
  );
  cat.value = filters.category;
  cat.onchange = () => {
    filters.category = cat.value;
    draw();
  };
  const low = el("label", "checkbox"),
    check = el("input");
  check.type = "checkbox";
  check.checked = filters.low;
  check.onchange = () => {
    filters.low = check.checked;
    draw();
  };
  low.append(check, document.createTextNode("Low stock only"));
  const count = el("span", "count spacer");
  toolbar.append(search, cat, low, count);
  p.append(toolbar, results);
  c.append(p);
  function draw() {
    let rows = state.products.filter(
      (x) =>
        (x.name + " " + x.sku)
          .toLowerCase()
          .includes(filters.inventory.toLowerCase()) &&
        (filters.category === "All categories" ||
          x.category === filters.category) &&
        (!filters.low || x.stock <= x.reorder_point),
    );
    count.textContent = rows.length + " PRODUCTS";
    results.replaceChildren();
    if (!rows.length)
      return empty(
        results,
        "No products match",
        "Try another search or clear the low-stock filter.",
      );
    results.append(
      table(
        ["PRODUCT", "PRICE / COST", "STOCK", "DEMAND", "MANAGE"],
        rows.map((x) => {
          const price = el("div", "", money(x.price_cents));
          price.append(el("span", "secondary", "Cost " + money(x.cost_cents)));
          const demand = el("span", "demand"),
            track = el("i"),
            bar = el("b");
          bar.style.width =
            Math.min(100, Math.max(0, Number(x.demand || 0) * 30)) + "%";
          track.append(bar);
          demand.append(
            track,
            document.createTextNode(Number(x.demand || 0).toFixed(1) + "x"),
          );
          demand.title =
            "Relative demand signal; price, reputation, and market conditions affect demand.";
          const actions = el("div", "actions");
          actions.append(
            button("Price", () => editPrice(x)),
            button("Restock", () => restock(x)),
          );
          return [productCell(x), price, stockCell(x), demand, actions];
        }),
      ),
    );
  }
  draw();
}
function cents(text) {
  if (!/^\d+(\.\d{1,2})?$/.test(text.trim()))
    throw Error("Enter a valid price with at most two decimal places.");
  const [a, b = ""] = text.trim().split(".");
  const n = Number(a) * 100 + Number(b.padEnd(2, "0"));
  if (!Number.isSafeInteger(n)) throw Error("That price is too large.");
  return n;
}
function editPrice(p) {
  const f = formBase("Set product price");
  f.append(
    el(
      "p",
      "detail-note",
      p.name +
        ". Price changes apply to future orders. Higher prices may reduce customer demand.",
    ),
  );
  const [l, i] = field(
    "Selling price (USD)",
    "text",
    (p.price_cents / 100).toFixed(2),
    { required: true, inputMode: "decimal", maxLength: 12 },
  );
  f.append(
    l,
    el(
      "p",
      "hint",
      "Unit cost: " +
        money(p.cost_cents) +
        " / Original price: " +
        money(p.base_price_cents),
    ),
  );
  formFooter(f);
  f.onsubmit = (e) => {
    e.preventDefault();
    try {
      mutate("/products/" + p.id, { price_cents: cents(i.value) }, "PATCH");
    } catch (err) {
      $(".form-error", f).textContent = err.message;
      $(".form-error", f).hidden = false;
    }
  };
}
function restock(p) {
  const f = formBase("Receive new stock");
  f.append(el("p", "detail-note", p.name + " / " + p.supplier));
  const [l, q] = field("Units to receive", "number", "10", {
    required: true,
    min: 1,
    max: 10000,
    step: 1,
  });
  const cost = el("div", "order-summary");
  f.append(
    l,
    cost,
    el(
      "p",
      "hint",
      "Stock arrives immediately. The purchase cost is deducted from available cash.",
    ),
  );
  function update() {
    cost.textContent =
      "Purchase cost: " +
      money(Number(q.value) * p.cost_cents) +
      " / Available: " +
      money(state.cash_cents);
  }
  q.oninput = update;
  update();
  formFooter(f, "Receive stock");
  f.onsubmit = (e) => {
    e.preventDefault();
    mutate("/products/" + p.id + "/restock", { quantity: Number(q.value) });
  };
}
function orders(c) {
  const p = panel("Order ledger", "Only captured payments count toward sales."),
    toolbar = el("div", "toolbar"),
    select = el("select"),
    result = el("div");
  select.setAttribute("aria-label", "Filter order status");
  [
    "All statuses",
    "Pending",
    "Processing",
    "Shipped",
    "Delivered",
    "Cancelled",
  ].forEach((x) => select.add(new Option(x, x)));
  select.value = filters.orders;
  select.onchange = () => {
    filters.orders = select.value;
    draw();
  };
  toolbar.append(
    select,
    el(
      "span",
      "hint",
      "Select an order to manage payment, fulfillment, or returns.",
    ),
  );
  p.append(toolbar, result);
  c.append(p);
  function draw() {
    result.replaceChildren();
    const rows = state.orders.filter(
      (x) => filters.orders === "All statuses" || x.status === filters.orders,
    );
    if (!rows.length)
      return empty(
        result,
        "No orders here yet",
        "Create an order yourself, or advance the simulation to bring in customers.",
      );
    result.append(
      table(
        ["ORDER", "CUSTOMER", "STATUS", "PAYMENT", "TOTAL", "ACTIONS"],
        rows.map((o) => [
          "#" + String(o.id).padStart(4, "0"),
          o.customer_name,
          tag(
            o.status,
            o.status === "Delivered"
              ? "good"
              : o.status === "Cancelled"
                ? "bad"
                : "warn",
          ),
          tag(
            o.payment_status,
            /paid|captured/i.test(o.payment_status) ? "good" : "",
          ),
          money(o.total_cents),
          button("Manage", () => orderDetail(o.id)),
        ]),
      ),
    );
  }
  draw();
}
function orderDetail(orderId) {
  const o = state.orders.find((x) => x.id === orderId);
  if (!o) return;
  const d = showDialog("Order #" + String(o.id).padStart(4, "0"));
  d.append(el("div", "form-error"));
  $(".form-error", d).hidden = true;
  const meta = el("div", "detail-meta");
  meta.append(
    tag(o.status),
    tag(o.payment_status),
    tag("DAY " + o.created_day),
  );
  d.append(meta, el("p", "detail-note", o.customer_name));
  d.append(
    table(
      ["ITEM", "QTY", "UNIT PRICE", "TOTAL"],
      o.items.map((x) => [
        x.product_name,
        x.quantity,
        money(x.unit_price_cents),
        money(x.total_cents),
      ]),
    ),
  );
  const total = el("div", "detail-total");
  total.append(
    el("span", "", "Order total"),
    el("span", "", money(o.total_cents)),
  );
  d.append(total);
  const actions = el("div", "detail-actions");
  async function action(path, body) {
    if (await mutate("/orders/" + o.id + path, body, "POST", false))
      orderDetail(o.id);
  }
  const paid =
    /paid|captured|partial|refunded/i.test(o.payment_status) &&
    !/unpaid|failed/i.test(o.payment_status);
  if (["Pending", "Processing"].includes(o.status)) {
    if (!paid) {
      actions.append(
        button(
          "Capture payment",
          () => action("/pay", { success: true }),
          "button primary",
        ),
        button(
          "Simulate failed payment",
          () => action("/pay", { success: false }),
          "button",
        ),
      );
    }
    if (paid && o.status === "Pending")
      actions.append(
        button(
          "Start processing",
          () => action("/status", { status: "Processing" }),
          "button primary",
        ),
      );
    if (paid)
      actions.append(
        button(
          "Ship order",
          () => action("/status", { status: "Shipped" }),
          "button primary",
        ),
      );
    actions.append(
      button(
        "Cancel order",
        () => {
          if (
            confirm(
              "Cancel this order? Stock will be released and any captured payment refunded.",
            )
          )
            action("/status", { status: "Cancelled" });
        },
        "button danger",
      ),
    );
  }
  if (o.status === "Shipped")
    actions.append(
      button(
        "Mark delivered",
        () => action("/status", { status: "Delivered" }),
        "button primary",
      ),
    );
  for (const b of actions.children) b.dataset.mutate = "true";
  d.append(actions);
  if (o.status === "Delivered") {
    d.append(
      el(
        "p",
        "detail-note",
        "Return delivered items below. Refunds include the original discount and tax; the server calculates the exact amount.",
      ),
    );
    for (const line of o.items) {
      const remaining = line.quantity - (line.returned_qty || 0);
      if (remaining > 0)
        d.append(
          button(
            "Return " + line.product_name + " (" + remaining + " available)",
            () => returnItem(o, line),
            "button",
          ),
        );
    }
  }
  if (o.status === "Pending" && !paid)
    d.append(
      el(
        "p",
        "detail-note",
        "Unpaid orders reserve stock and expire after two simulation days. Shipping requires a successful payment.",
      ),
    );
  if (o.status === "Cancelled")
    d.append(
      el(
        "p",
        "detail-note",
        "This order is closed. Stock and refunds have already been handled.",
      ),
    );
  setBusy(busy);
}
function returnItem(o, line) {
  const f = formBase("Return an item");
  f.append(el("p", "detail-note", line.product_name));
  const [ql, q] = field("Quantity to return", "number", "1", {
      required: true,
      min: 1,
      max: line.quantity - (line.returned_qty || 0),
      step: 1,
    }),
    [rl, r] = field("Reason", "text", "Customer return", {
      required: true,
      maxLength: 200,
    });
  const label = el("label", "checkbox"),
    check = el("input");
  check.type = "checkbox";
  check.checked = true;
  label.append(check, document.createTextNode("Restock the returned items"));
  f.append(ql, rl, label);
  formFooter(f, "Process return");
  f.onsubmit = (e) => {
    e.preventDefault();
    mutate("/orders/" + o.id + "/returns", {
      line_id: line.id,
      quantity: Number(q.value),
      restock: check.checked,
      reason: r.value,
    });
  };
}
function createOrder() {
  if (!state || busy) return;
  const requestId = id();
  const f = formBase("Create a shop order"),
    [cl, customer] = field("Customer", "select");
  customer.add(new Option("Choose a customer", ""));
  state.customers.forEach((x) => customer.add(new Option(x.name, x.id)));
  customer.required = true;
  f.append(cl);
  const lines = el("div", "order-lines");
  f.append(lines);
  function addLine() {
    const row = el("div", "order-line"),
      select = el("select"),
      qty = el("input");
    select.setAttribute("aria-label", "Product");
    select.add(new Option("Choose a product", ""));
    state.products.forEach((x) =>
      select.add(
        new Option(
          x.name + " / " + money(x.price_cents) + " / " + x.stock + " in stock",
          x.id,
        ),
      ),
    );
    select.required = true;
    qty.type = "number";
    qty.min = "1";
    qty.max = "1000";
    qty.step = "1";
    qty.value = "1";
    qty.required = true;
    qty.setAttribute("aria-label", "Quantity");
    row.append(
      select,
      qty,
      button(
        "\u00d7",
        () => {
          row.remove();
          preview();
        },
        "icon-button",
      ),
    );
    select.onchange = preview;
    qty.oninput = preview;
    lines.append(row);
    preview();
  }
  const add = button("+ Add product", addLine, "link-button");
  const [dl, discount] = field("Discount (%)", "number", "0", {
      required: true,
      min: 0,
      max: 25,
      step: "0.01",
    }),
    summary = el("div", "order-summary");
  discount.oninput = preview;
  f.append(
    add,
    dl,
    summary,
    el(
      "p",
      "hint",
      "Tax: 8%. Total is an estimate; the shop calculates authoritative totals. Orders reserve stock until paid or cancelled.",
    ),
  );
  function preview() {
    let subtotal = 0;
    for (const row of lines.children) {
      const p = state.products.find(
        (x) => String(x.id) === $("select", row).value,
      );
      subtotal += (p?.price_cents || 0) * Number($("input", row).value || 0);
    }
    summary.textContent =
      "Estimated total: " +
      money(
        Math.round(subtotal * (1 - Number(discount.value || 0) / 100) * 1.08),
      );
  }
  addLine();
  formFooter(f, "Create pending order");
  f.onsubmit = (e) => {
    e.preventDefault();
    if (!lines.children.length) {
      $(".form-error", f).textContent = "Add at least one product.";
      $(".form-error", f).hidden = false;
      return;
    }
    mutate("/orders", {
      customer_id: Number(customer.value),
      items: [...lines.children].map((row) => ({
        product_id: Number($("select", row).value),
        quantity: Number($("input", row).value),
      })),
      discount_percent: Number(discount.value),
      request_id: requestId,
    });
  };
}
function customers(c) {
  const p = panel(
      "Player community",
      "Customer tiers reflect captured, non-refunded purchases.",
      button("+ Add customer", addCustomer, "button"),
    ),
    toolbar = el("div", "toolbar"),
    results = el("div");
  toolbar.append(
    searchInput("Search name or email", filters.customers, (e) => {
      filters.customers = e.target.value;
      draw();
    }),
  );
  p.append(toolbar, results);
  c.append(p);
  function draw() {
    results.replaceChildren();
    const rows = state.customers.filter((x) =>
      (x.name + " " + (x.email || ""))
        .toLowerCase()
        .includes(filters.customers.toLowerCase()),
    );
    if (!rows.length)
      return empty(
        results,
        "No customers match",
        "Add a customer or try another search.",
      );
    results.append(
      table(
        ["CUSTOMER", "TIER", "ORDERS", "NET SPEND"],
        rows.map((x) => {
          const n = el("div", "", x.name);
          n.append(el("span", "secondary", x.email || "No email supplied"));
          return [n, tag(x.tier), number(x.order_count), money(x.spent_cents)];
        }),
      ),
    );
  }
  draw();
}
function addCustomer() {
  const f = formBase("Welcome a new customer"),
    [nl, n] = field("Full name", "text", "", {
      required: true,
      maxLength: 100,
    }),
    [ml, m] = field("Email (optional)", "email", "", { maxLength: 254 });
  f.append(nl, ml);
  formFooter(f, "Add customer");
  f.onsubmit = (e) => {
    e.preventDefault();
    mutate("/customers", { name: n.value, email: m.value || null });
  };
}
const sampleQueries = [
  [
    "Product stock",
    "SELECT name, category, stock, price_cents FROM products ORDER BY stock ASC LIMIT 30;",
  ],
  [
    "Order ledger",
    "SELECT id, status, payment_status, total_cents FROM orders ORDER BY id DESC LIMIT 30;",
  ],
  ["Customer community", "SELECT * FROM customers LIMIT 20;"],
  ["Cash movements", "SELECT * FROM ledger ORDER BY id DESC LIMIT 30;"],
];
function sqlView(c) {
  const layout = el("div", "sql-layout"),
    side = el("aside", "panel schema");
  side.append(el("h3", "", "DATABASE SCHEMA"));
  const schemaBody = el("div");
  side.append(schemaBody);
  const p = panel(
    "SQL workbench",
    "Read-only access. Up to 200 result rows per query.",
    tag("SELECT ONLY"),
  );
  const editor = el("div", "sql-editor"),
    textarea = el("textarea");
  textarea.setAttribute("aria-label", "Read-only SQL query");
  textarea.spellcheck = false;
  textarea.value =
    sessionStorage.getItem("pixelledger-query") || sampleQueries[0][1];
  const actions = el("div", "sql-actions"),
    select = el("select");
  select.setAttribute("aria-label", "Sample SQL queries");
  select.add(new Option("Sample queries", ""));
  sampleQueries.forEach((s, i) => select.add(new Option(s[0], i)));
  select.onchange = () => {
    if (select.value !== "")
      textarea.value = sampleQueries[Number(select.value)][1];
  };
  const run = button("Run query \u2192", execute, "button primary");
  actions.append(select, run);
  const output = el("div", "query-result");
  editor.append(
    textarea,
    actions,
    el(
      "p",
      "hint",
      "Ctrl / Cmd + Enter to run. Writes, attachments, and unsafe functions are blocked.",
    ),
    output,
  );
  p.append(editor);
  layout.append(side, p);
  c.append(layout);
  async function execute() {
    if (!textarea.value.trim()) return;
    run.disabled = true;
    sessionStorage.setItem("pixelledger-query", textarea.value);
    try {
      const r = await request("/query", "POST", { sql: textarea.value });
      output.replaceChildren(
        el(
          "p",
          "hint",
          r.rows.length +
            " rows" +
            (r.truncated ? " / results capped at 200 rows" : ""),
        ),
      );
      if (!r.rows.length)
        empty(output, "Query complete", "No rows matched your query.");
      else
        output.append(
          table(
            r.columns,
            r.rows.map((row) =>
              Array.isArray(row) ? row : r.columns.map((k) => row[k]),
            ),
          ),
        );
    } catch (e) {
      output.replaceChildren(el("p", "form-error", e.message));
    } finally {
      run.disabled = false;
    }
  }
  textarea.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      execute();
    }
  });
  function drawSchema() {
    schemaBody.replaceChildren();
    for (const t of schema.tables) {
      const d = el("details"),
        sum = el("summary", "", t.name);
      d.append(sum);
      t.columns.forEach((col) =>
        d.append(el("small", "", col.name + " / " + col.type)),
      );
      schemaBody.append(d);
    }
  }
  if (schema) drawSchema();
  else
    request("/schema")
      .then((s) => {
        schema = s;
        drawSchema();
      })
      .catch((e) => schemaBody.append(el("p", "hint", e.message)));
}
function eventList(events) {
  const list = el("div", "events");
  if (!events.length) {
    empty(
      list,
      "A quiet start",
      "Your shop journal will fill as the simulation progresses.",
    );
    return list;
  }
  for (const e of events) {
    const row = el("article", "event"),
      text = el("div");
    text.append(
      el("p", "", e.message),
      el("small", "", "DAY " + e.day + " / " + e.kind),
    );
    row.append(el("span", "event-dot"), text);
    list.append(row);
  }
  return list;
}
function activity(c) {
  const metrics = el("div", "metrics");
  metrics.append(
    metric(
      "ORDERS",
      number(state.metrics.orders_count),
      "Across the entire shop timeline",
    ),
    metric(
      "CUSTOMERS",
      number(state.metrics.customers_count),
      "Players in your community",
    ),
    metric(
      "LOST SALES",
      number(state.metrics.lost_sales),
      "Demand your available stock could not meet",
    ),
    metric(
      "REPUTATION",
      Number(state.metrics.reputation || 0).toFixed(0) + " / 100",
      "Customer experience affects future demand",
    ),
  );
  c.append(metrics);
  const p = panel(
    "Shop journal",
    "Decisions and world events, most recent first.",
  );
  p.append(eventList(state.events));
  c.append(p);
  const ledger = panel(
    "Cash ledger",
    "Every movement, including stock purchases, refunds, and operating costs.",
  );
  ledger.style.marginTop = "24px";
  ledger.append(
    table(
      ["DAY", "TYPE", "DESCRIPTION", "CASH MOVEMENT"],
      state.ledger
        .slice(0, 100)
        .map((x) => [x.day, x.kind, x.description, money(x.amount_cents)]),
    ),
  );
  c.append(ledger);
}
function settings(c) {
  const p = el("section", "panel settings");
  p.append(
    el("h3", "", "A world that runs on your terms"),
    el(
      "p",
      "",
      "Time advances only when you ask it to, or while auto-play is enabled on a visible page. Prices, availability, reputation, and market events shape customer demand. Payments and money are simulated.",
    ),
    el("p", "", "Current seed: " + state.seed + " / Current day: " + state.day),
    el("hr"),
  );
  const h = el("h3", "", "Reset the demo shop");
  p.append(
    h,
    el(
      "p",
      "",
      "This permanently replaces the current simulation, including orders, customers, and your decisions. Use the same seed to reproduce the starting world.",
    ),
  );
  const f = el("form"),
    [sl, s] = field("Simulation seed", "number", String(state.seed), {
      required: true,
      min: 0,
      max: 2147483647,
      step: 1,
    }),
    [cl, confirmation] = field("Type RESET SHOP to confirm", "text", "", {
      required: true,
      autoComplete: "off",
    }),
    err = el("div", "form-error");
  err.hidden = true;
  f.append(sl, cl, err);
  const submit = el("button", "button danger", "Reset shop");
  submit.type = "submit";
  submit.dataset.mutate = "true";
  f.append(submit);
  f.onsubmit = async (e) => {
    e.preventDefault();
    if (confirmation.value !== "RESET SHOP") {
      err.textContent = "Type RESET SHOP exactly to confirm.";
      err.hidden = false;
      return;
    }
    auto = false;
    configureAuto();
    if (
      await mutate("/reset", {
        confirmation: confirmation.value,
        seed: Number(s.value),
      })
    ) {
      changeView("overview");
      toast("A fresh shop is ready.");
    }
  };
  p.append(f);
  c.append(p);
}
const pendingAdvances = new Map();
async function advance(days) {
  if (busy) return;
  const requestId = pendingAdvances.get(days) || id();
  pendingAdvances.set(days, requestId);
  if (await mutate("/simulate", { days, request_id: requestId }))
    pendingAdvances.delete(days);
}
function configureAuto() {
  clearInterval(timer);
  timer = null;
  if (auto)
    timer = setInterval(() => {
      if (!document.hidden && !busy && !$("#dialog").open) advance(1);
    }, 10000);
}
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && auto) configureAuto();
});
async function loadState() {
  try {
    state = await request("/state");
    banner("");
    render();
  } catch (e) {
    $("#connection").textContent = "Shop disconnected";
    banner(e.message);
    const c = $("#content");
    c.replaceChildren();
    const box = el("section", "panel settings");
    empty(
      box,
      "Connect to your shop",
      "Start the local server with python main.py. If this server requires an access key, enter it below. The key stays only in this page memory.",
    );
    const f = el("form"),
      [label, key] = field("Shop access key (if required)", "password", "", {
        autoComplete: "off",
        maxLength: 512,
      });
    const submit = el("button", "button primary", "Connect / retry");
    submit.type = "submit";
    f.append(label, submit);
    f.onsubmit = async (event) => {
      event.preventDefault();
      runtime.apiKey = key.value.trim();
      submit.disabled = true;
      await loadState();
    };
    box.append(f);
    c.append(box);
  }
}
view = titles[location.hash.slice(1)] ? location.hash.slice(1) : "overview";
setBusy(false);
loadState();
