# PixelLedger

**[Explore the interactive project presentation](docs/overview.html)** — open locally in your browser; works offline.

Run a fictional game shop: buy stock, set prices, take orders, and handle returns. Advance the simulation to see how those decisions affect demand and cash. The shop uses SQLite; all customers and payments are simulated.

**All customers, orders and payments are simulated. No real payment processor or external database is contacted.**

## Try it first

Review the starting cash and stock, then place a small order through the sales desk. Advance one day and inspect the changes in orders and inventory. Use the SQL examples to explore the same records without changing them.

<details>
<summary>Using the existing managed Windows workspace</summary>

Assigned environment: **base**. From this repository folder in PowerShell:

```powershell
.\run.cmd --check
.\run.cmd
```

The repo-local launcher selects `G:\AnaConda\install`
and imports required startup modules. It installs nothing and downloads
no models. On a standalone clone where that interpreter is absent, it uses your
active `python`; activate a compatible environment first. `--check` reports the
actual interpreter; it does not validate optional models or every workflow.

</details>

## What you can do

- **Run the shop:** Overview with cash, net sales, estimated operating profit, inventory value, demand history and market events.
- **Manage inventory:** Search categories, identify low stock, change prices and receive affordable stock with a recorded purchase cost.
- **Handle orders:** Create multi-product orders, apply discounts, retry simulated payments, ship, deliver, cancel and process partial returns.
- **Know your customers:** Add players, inspect order counts and net spending, and see loyalty tiers improve with purchases. Earned tiers are retained after returns; net spending still reflects refunds.
- **Explore the database:** Live schema browser and a bounded read-only SQL lab with reporting examples.
- **Play the world:** Advance one or seven days, enable visible-page auto-play, or reset to a reproducible seeded starting world.

## Run

Use an existing compatible environment. The current offline tests pass in Conda `base` with Python **3.13.5**. SQLite is included with Python; no PostgreSQL server, Node build, or external API key is needed.

```powershell
git clone https://github.com/mkamalpour/PixelLedger.git
cd PixelLedger
conda activate base  # Or use your existing compatible environment.
# Install dependencies if they are not already available in your environment.
python -m pip install -r requirements.txt
python main.py
```

On macOS/Linux, activate an existing compatible environment before using the same Python commands.

Open **http://127.0.0.1:8000**. The first run creates an isolated shop database with 26 products, 16 fictional customers, suppliers, staff and eight starter orders. Subsequent launches keep your decisions.

Use `python main.py --port 8001` for another port, or `--reload` for development. `/docs` provides the API reference. Serve the app through Python; opening the HTML directly does not start the simulator.

## Business rules

- **Money:** Integer USD cents throughout. Line discounts are capped at 25%; an illustrative 8% sales tax is rounded per discounted line. Net sales and profit exclude tax, while cash receipts and refunds include it. These are simulation rules, not jurisdiction-specific accounting guidance.
- **Inventory:** Creating an order reserves its units immediately. Available stock cannot go below zero. Shipping does not deduct the same stock twice. Canceling an unshipped order releases its reservation.
- **Payments:** Failed attempts collect nothing. A successful capture is recorded once; repeated payment requests do not charge twice. Fulfillment requires payment.
- **Returns:** Only delivered orders can be returned. Quantities cannot exceed the remaining purchased units. Cumulative proportional refunds recover the exact original amount when all units are returned, including rounding. Damaged returns can be written off without recreating stock or reversing their cost.
- **History:** Order prices and unit costs are snapshots; repricing a product never changes an old order. Payments, refunds, stock movements and cash changes retain an audit trail.
- **Transactions:** Business mutations use SQLite write transactions. Concurrent checkouts cannot oversell the same last unit. Checkout and day-advance requests support retry IDs to prevent duplicate changes after uncertain network responses.

Restocking spends cash at the product's unit cost. Daily overhead is $180. Overhead or customer refunds can move the cash balance into an overdraft; new stock purchases require available funds. Estimated operating profit is net sales minus consumed inventory costs and overhead. It is separate from cash flow and inventory asset value.

## How the world adapts

A deterministic simulation day creates demand from product popularity, price relative to its baseline, customer reputation, weekends and changing category events. Customers may arrive, purchase, miss out on stock, or fail payment. Missed purchases reduce reputation; prompt deliveries improve it.

Paid processing orders ship on a subsequent day, and shipments arrive after their simulated lead time. Carrier congestion can add a day. Unpaid reservations expire after two days. Stock shortages and higher prices can reduce completed sales, making repricing and replenishment meaningful decisions.

Time moves only when requested. Auto-play advances one day every ten seconds while its page is visible and no operation or modal blocks it. It starts paused and does not run as a hidden server job. The same seed and sequence of decisions reproduce the same world; advancing seven days at once matches seven single-day steps.

## SQL playground and PostgreSQL reference

The SQL lab runs against a read-only SQLite connection with an authorization policy that blocks writes, attachment, pragmas, extension loading and access to retry internals. Results are capped at 200 rows and query work has a two-second budget. Start with the examples in [sql/queries.sql](sql/queries.sql).

[sql/postgresql_reference.sql](sql/postgresql_reference.sql) preserves a PostgreSQL version of the schema in a dedicated `pixelledger` namespace. It does **not** delete unrelated public tables. It is a reference schema, not a PostgreSQL runtime adapter; application behavior is implemented in the Python engine and verified with SQLite.

## Local data and optional access key

Simulation saves live in `data/shop.db` and are excluded from Git, alongside credentials, caches, environments and local editor metadata. You can set an optional root `.env`:

```dotenv
PIXELLEDGER_DB=data/shop.db
PIXELLEDGER_HOST=127.0.0.1
PIXELLEDGER_PORT=8000
PIXELLEDGER_API_KEY=
```

The default database path is anchored to the project. A custom relative `PIXELLEDGER_DB` path is resolved from the working directory. Use a dedicated simulator database. Reset requires typing **RESET SHOP** and affects this shop's records, never your old PostgreSQL database.

The launcher requires a shared API key before binding beyond loopback. Use a specific interface address when configuring a shared workspace; trusted hosts remain restricted. Remote operators can unlock the interface with that key; local operators receive it automatically. This is a shared simulation workspace, not a hosted storefront with individual user accounts or real payment processing. Protect network deployments with appropriate transport security.

## Verification

```powershell
python -m pytest tests -q -p no:cacheprovider
```

The isolated suite covers exact discounts/tax/refunds, failed and duplicate payments, valid transitions, damaged returns, atomic rollback, concurrent stock reservation, deterministic simulation, request deduplication, spending and stock reconciliation, reset isolation, API protection and read-only SQL restrictions. Tests use temporary synthetic databases and never run the legacy PostgreSQL reset or seed scripts.

## Project layout

```text
shop/        Transactional engine, schema, API and SQL explorer
web/         Local dashboard HTML, JavaScript and CSS
sql/         Reporting examples and PostgreSQL reference schema
tests/       Isolated business-rule and API regressions
main.py      Local launcher
```

Checked on Windows with Python 3.13.5 (Conda base): **44 tests passed**.

No license file is included.

Engine calls reject nonfinite or overprecise discounts and boolean stock quantities before any transaction can persist. API identifiers require integers.

See the [engineering audit](docs/ENGINEERING_AUDIT.md) for the dated test baseline,
project assessment, environment assignment and remaining work.
