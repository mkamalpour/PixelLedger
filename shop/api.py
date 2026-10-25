"""Local operator API for PixelLedger; no payment gateway or external database calls."""

from contextlib import asynccontextmanager
from decimal import Decimal
from hmac import compare_digest
import json
import os
import sqlite3
from typing import Literal
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from shop.database import ROOT
from shop.engine import Shop, RuleError

shop = Shop()
API_KEY = os.getenv("PIXELLEDGER_API_KEY", "")


@asynccontextmanager
async def lifespan(app):
    shop.initialize()
    yield


app = FastAPI(
    title="PixelLedger",
    version="1.0.0",
    description="A transactional game shop simulator and read-only SQL playground.",
    lifespan=lifespan,
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=list(
        {
            "127.0.0.1",
            "localhost",
            "::1",
            "testserver",
            os.getenv("PIXELLEDGER_HOST", "127.0.0.1"),
        }
    ),
)


@app.middleware("http")
async def protect(request, call_next):
    if (
        request.url.path.startswith("/api/")
        and request.url.path != "/api/health"
        and API_KEY
        and not compare_digest(
            request.headers.get("x-api-key", "").encode(), API_KEY.encode()
        )
    ):
        return JSONResponse({"detail": "Invalid API key"}, status_code=401)
    origin = request.headers.get("origin")
    if (
        request.method in {"POST", "PATCH", "PUT", "DELETE"}
        and origin
        and urlsplit(origin).netloc != request.url.netloc
    ):
        return JSONResponse(
            {"detail": "Cross-origin writes are disabled"}, status_code=403
        )
    return await call_next(request)


@app.exception_handler(RuleError)
async def rule_error(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=409)


@app.exception_handler(sqlite3.IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse(
        {
            "detail": "That change conflicts with an existing record or a database constraint."
        },
        status_code=409,
    )


class Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class OrderItem(Input):
    product_id: int = Field(gt=0, strict=True)
    quantity: int = Field(ge=1, le=100, strict=True)


class OrderRequest(Input):
    customer_id: int = Field(gt=0, strict=True)
    items: list[OrderItem] = Field(min_length=1, max_length=20)
    discount_percent: Decimal = Field(
        default=Decimal("0"), ge=0, le=25, max_digits=4, decimal_places=2
    )
    request_id: str | None = Field(default=None, min_length=1, max_length=100)


class PaymentRequest(Input):
    success: bool = True


class StatusRequest(Input):
    status: Literal["Processing", "Shipped", "Delivered", "Cancelled"]


class ReturnRequest(Input):
    line_id: int = Field(gt=0, strict=True)
    quantity: int = Field(ge=1, le=100, strict=True)
    restock: bool = True
    reason: str = Field(default="Changed mind", min_length=1, max_length=300)


class PriceRequest(Input):
    price_cents: int = Field(ge=100, le=5000000, strict=True)


class RestockRequest(Input):
    quantity: int = Field(ge=1, le=1000, strict=True)


class CustomerRequest(Input):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(
        min_length=3, max_length=200, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    )


class SimulationRequest(Input):
    days: int = Field(default=1, ge=1, le=30, strict=True)
    request_id: str | None = Field(default=None, min_length=1, max_length=100)


class ResetRequest(Input):
    confirmation: Literal["RESET SHOP"]
    seed: int = Field(default=42, ge=0, le=2147483647, strict=True)


class QueryRequest(Input):
    sql: str = Field(min_length=1, max_length=10000)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    local = (
        request.client
        and request.url.hostname in {"127.0.0.1", "localhost", "::1", "testserver"}
        and request.client.host in {"127.0.0.1", "::1", "testclient"}
    )
    runtime = (
        json.dumps({"apiKey": API_KEY if local else ""})
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    content = (
        (ROOT / "web/index.html")
        .read_text(encoding="utf-8")
        .replace("__PIXELLEDGER_RUNTIME_CONFIG__", runtime)
    )
    return HTMLResponse(
        content,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
        },
    )


@app.get("/app.js", include_in_schema=False)
def javascript():
    return FileResponse(ROOT / "web/app.js", media_type="text/javascript")


@app.get("/styles.css", include_in_schema=False)
def styles():
    return FileResponse(ROOT / "web/styles.css", media_type="text/css")


@app.get("/api/health")
def health():
    return {"status": "ok", "simulation": "local", "currency": "USD"}


@app.get("/api/state")
def state():
    return shop.state()


@app.post("/api/orders")
def create_order(req: OrderRequest):
    return shop.create_order(
        req.customer_id,
        [item.model_dump() for item in req.items],
        req.discount_percent,
        req.request_id,
    )


@app.post("/api/orders/{order_id}/pay")
def pay(order_id: int, req: PaymentRequest):
    return shop.pay(order_id, req.success)


@app.post("/api/orders/{order_id}/status")
def status(order_id: int, req: StatusRequest):
    return shop.transition(order_id, req.status)


@app.post("/api/orders/{order_id}/returns")
def returns(order_id: int, req: ReturnRequest):
    return shop.return_items(
        order_id, req.line_id, req.quantity, req.restock, req.reason
    )


@app.patch("/api/products/{product_id}")
def price(product_id: int, req: PriceRequest):
    return shop.set_price(product_id, req.price_cents)


@app.post("/api/products/{product_id}/restock")
def restock(product_id: int, req: RestockRequest):
    return shop.restock(product_id, req.quantity)


@app.post("/api/customers")
def customer(req: CustomerRequest):
    return shop.add_customer(req.name, req.email)


@app.post("/api/simulate")
def simulate(req: SimulationRequest):
    return shop.advance(req.days, req.request_id)


@app.post("/api/reset")
def reset(req: ResetRequest):
    return shop.reset(req.seed)


@app.get("/api/schema")
def schema():
    return shop.db.schema()


@app.post("/api/query")
def query(req: QueryRequest):
    try:
        return shop.db.query(req.sql)
    except (sqlite3.Error, ValueError) as exc:
        raise HTTPException(
            status_code=422, detail="Query rejected: " + str(exc)
        ) from exc
