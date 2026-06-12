"""
Fat Loss Coach Action API
Custom GPT Action -> FastAPI -> Google Sheets

Env vars required:
- API_KEY: shared secret used by ChatGPT Action as custom header X-API-Key
- SPREADSHEET_ID: Google Sheet ID
- GOOGLE_SERVICE_ACCOUNT_JSON: raw service account JSON string
  OR GOOGLE_SERVICE_ACCOUNT_JSON_BASE64: base64-encoded service account JSON
- TIMEZONE: optional, default America/Los_Angeles
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from pydantic import BaseModel, Field

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TIMEZONE = os.getenv("TIMEZONE", "America/Los_Angeles")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
API_KEY = os.getenv("API_KEY", "")

SHEET_NAMES = {
    "settings": "Settings",
    "inventory": "Inventory",
    "weight": "WeightLog",
    "meal": "MealLog",
    "usage": "UsageLog",
    "catalog": "FoodCatalog",
}

HEADERS = {
    "Settings": ["key", "value"],
    "Inventory": [
        "id", "item_en", "item_zh", "category", "quantity", "unit", "storage",
        "purchase_date", "opened_date", "use_by", "calories_per_100g",
        "protein_per_100g", "carbs_per_100g", "fat_per_100g", "status",
        "priority", "min_quantity", "target_quantity", "notes", "last_updated",
    ],
    "WeightLog": [
        "date", "weight_lb", "sleep_hours", "hunger_1_10", "training_perf_1_10",
        "training", "calories", "protein_g", "fast_food", "alcohol", "night_snack", "notes",
    ],
    "MealLog": [
        "date", "meal_type", "planned_or_actual", "calories", "protein_g",
        "carbs_g", "fat_g", "food_summary", "inventory_used", "notes",
    ],
    "UsageLog": [
        "timestamp", "date", "item_id", "item_en", "item_zh", "quantity_used",
        "unit", "meal", "reason", "notes",
    ],
    "FoodCatalog": [
        "item_en", "item_zh", "category", "unit_basis", "calories_per_100g",
        "protein_per_100g", "carbs_per_100g", "fat_per_100g", "notes",
    ],
}

WEIGHT_TO_G = {"g": 1.0, "gram": 1.0, "grams": 1.0, "kg": 1000.0, "oz": 28.3495, "lb": 453.592, "lbs": 453.592}
COUNT_UNITS = {"each", "ea", "unit", "units", "piece", "pieces", "pack", "packs", "bag", "bags", "bunch", "bunches", "carton", "cartons", "tub", "tubs"}
VOLUME_UNITS = {"tsp", "tbsp", "cup", "cups", "ml", "l"}

app = FastAPI(
    title="Fat Loss Coach Inventory API",
    version="1.0.0",
    description="API for a Custom GPT fat-loss coach to read/write Google Sheets inventory, weight logs, meal logs, and usage logs.",
)
@app.get("/", include_in_schema=False)
def root() -> Dict[str, Any]:
    return {
        "ok": True,
        "service": "Fat Loss Coach Inventory API",
        "health_endpoint": "/health",
        "docs": "/docs"
    }


def today_iso() -> str:
    # Date is supplied by the client/GPT in most cases; this fallback uses server date.
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def require_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> None:
    if not API_KEY:
        raise HTTPException(status_code=500, detail="Server API_KEY is not configured")
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@lru_cache(maxsize=1)
def sheets_service():
    if not SPREADSHEET_ID:
        raise RuntimeError("SPREADSHEET_ID env var is required")

    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    b64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64")
    if b64:
        raw = base64.b64decode(b64).decode("utf-8")
    if not raw:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 is required")

    info = json.loads(raw)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def get_values(sheet_name: str, range_suffix: str = "A:ZZ") -> List[List[Any]]:
    rng = f"{sheet_name}!{range_suffix}"
    result = sheets_service().spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=rng,
        valueRenderOption="UNFORMATTED_VALUE",
        dateTimeRenderOption="FORMATTED_STRING",
    ).execute()
    return result.get("values", [])


def append_values(sheet_name: str, rows: List[List[Any]]) -> Dict[str, Any]:
    if not rows:
        return {"updatedRows": 0}
    body = {"values": rows}
    return sheets_service().spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{sheet_name}!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()


def clear_values(sheet_name: str, range_suffix: str = "A2:ZZ") -> None:
    sheets_service().spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{sheet_name}!{range_suffix}",
        body={},
    ).execute()


def update_values(sheet_name: str, start_cell: str, rows: List[List[Any]]) -> Dict[str, Any]:
    body = {"values": rows}
    return sheets_service().spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{sheet_name}!{start_cell}",
        valueInputOption="USER_ENTERED",
        body=body,
    ).execute()


def rows_as_dicts(sheet_name: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    values = get_values(sheet_name)
    if not values:
        return HEADERS.get(sheet_name, []), []
    headers = [str(h).strip() for h in values[0]]
    out: List[Dict[str, Any]] = []
    for row in values[1:]:
        padded = row + [""] * max(0, len(headers) - len(row))
        obj = {headers[i]: padded[i] if i < len(padded) else "" for i in range(len(headers))}
        if any(str(v).strip() for v in obj.values()):
            out.append(obj)
    return headers, out


def write_dict_rows(sheet_name: str, headers: List[str], rows: List[Dict[str, Any]]) -> None:
    clear_values(sheet_name)
    if not rows:
        return
    values = [[row.get(h, "") for h in headers] for row in rows]
    update_values(sheet_name, "A2", values)


def as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_unit(unit: str) -> str:
    return (unit or "").strip().lower()


def convert_qty(qty: float, from_unit: str, to_unit: str) -> float:
    fu = normalize_unit(from_unit)
    tu = normalize_unit(to_unit)
    if fu == tu:
        return qty
    if fu in WEIGHT_TO_G and tu in WEIGHT_TO_G:
        return qty * WEIGHT_TO_G[fu] / WEIGHT_TO_G[tu]
    if fu in COUNT_UNITS and tu in COUNT_UNITS:
        # Treat count-like units as equivalent only when explicitly used; this is approximate.
        return qty
    raise HTTPException(status_code=400, detail=f"Cannot convert unit '{from_unit}' to '{to_unit}'. Update manually or use same unit.")


def parse_date_maybe(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        # Google Sheets serial date fallback; day 0 = 1899-12-30.
        return date(1899, 12, 30) + timedelta(days=int(value))
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def active_inventory(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        status = str(r.get("status", "active")).lower() or "active"
        qty = as_float(r.get("quantity"), 0) or 0
        if status == "active" and qty > 0:
            out.append(r)
    return out


def find_inventory_index(rows: List[Dict[str, Any]], item_id: Optional[str], item_en: Optional[str], item_zh: Optional[str]) -> int:
    def norm(x: Any) -> str:
        return str(x or "").strip().lower()
    if item_id:
        for i, r in enumerate(rows):
            if norm(r.get("id")) == norm(item_id):
                return i
    if item_en:
        for i, r in enumerate(rows):
            if norm(r.get("item_en")) == norm(item_en):
                return i
    if item_zh:
        for i, r in enumerate(rows):
            if norm(r.get("item_zh")) == norm(item_zh):
                return i
    raise HTTPException(status_code=404, detail=f"Inventory item not found: id={item_id}, item_en={item_en}, item_zh={item_zh}")


class InventoryItemIn(BaseModel):
    item_en: str
    item_zh: Optional[str] = ""
    category: str = Field(default="other", description="protein, carb, veg, fruit, condiment, staple, snack, drink, other")
    quantity: float
    unit: str
    storage: str = Field(default="fridge", description="fridge, freezer, pantry, counter")
    purchase_date: Optional[str] = None
    opened_date: Optional[str] = ""
    use_by: Optional[str] = ""
    calories_per_100g: Optional[float] = ""
    protein_per_100g: Optional[float] = ""
    carbs_per_100g: Optional[float] = ""
    fat_per_100g: Optional[float] = ""
    status: str = "active"
    priority: str = "medium"
    min_quantity: Optional[float] = ""
    target_quantity: Optional[float] = ""
    notes: Optional[str] = ""


class AddInventoryPayload(BaseModel):
    items: List[InventoryItemIn]


class InventoryUpdate(BaseModel):
    id: str
    fields: Dict[str, Any]


class UpdateInventoryPayload(BaseModel):
    updates: List[InventoryUpdate]


class ConsumeItem(BaseModel):
    item_id: Optional[str] = None
    item_en: Optional[str] = None
    item_zh: Optional[str] = None
    quantity_used: float
    unit: str
    meal: Optional[str] = ""
    reason: Optional[str] = "actual_consumed"
    notes: Optional[str] = ""


class ConsumePayload(BaseModel):
    date: Optional[str] = None
    items: List[ConsumeItem]
    dry_run: bool = Field(default=False, description="If true, validate and return projected inventory without writing")


class WeightEntry(BaseModel):
    date: Optional[str] = None
    weight_lb: float
    sleep_hours: Optional[float] = ""
    hunger_1_10: Optional[float] = ""
    training_perf_1_10: Optional[float] = ""
    training: Optional[str] = ""
    calories: Optional[float] = ""
    protein_g: Optional[float] = ""
    fast_food: Optional[str] = "no"
    alcohol: Optional[str] = "no"
    night_snack: Optional[str] = "no"
    notes: Optional[str] = ""


class MealEntry(BaseModel):
    date: Optional[str] = None
    meal_type: str
    planned_or_actual: str = Field(default="planned", description="planned or actual")
    calories: Optional[float] = ""
    protein_g: Optional[float] = ""
    carbs_g: Optional[float] = ""
    fat_g: Optional[float] = ""
    food_summary: Optional[str] = ""
    inventory_used: Optional[str] = ""
    notes: Optional[str] = ""


class MealLogPayload(BaseModel):
    meals: List[MealEntry]


@app.get("/health", dependencies=[Depends(require_api_key)])
def health() -> Dict[str, Any]:
    return {"ok": True, "spreadsheet_id_configured": bool(SPREADSHEET_ID), "timezone": TIMEZONE}


@app.post("/setup/headers", dependencies=[Depends(require_api_key)])
def setup_headers() -> Dict[str, Any]:
    """Writes standard headers to row 1 of all expected sheets. Does not delete data rows."""
    updated = []
    for sheet_name, headers in HEADERS.items():
        update_values(sheet_name, "A1", [headers])
        updated.append(sheet_name)
    return {"updated_sheets": updated}


@app.get("/inventory", dependencies=[Depends(require_api_key)])
def get_inventory(include_archived: bool = False) -> Dict[str, Any]:
    headers, rows = rows_as_dicts(SHEET_NAMES["inventory"])
    result = rows if include_archived else active_inventory(rows)
    return {"count": len(result), "items": result}


@app.post("/inventory/add", dependencies=[Depends(require_api_key)])
def add_inventory(payload: AddInventoryPayload) -> Dict[str, Any]:
    headers = HEADERS["Inventory"]
    rows_to_append = []
    created = []
    for item in payload.items:
        inv_id = f"inv-{uuid.uuid4().hex[:8]}"
        d = item.model_dump()
        d["id"] = inv_id
        d["purchase_date"] = d.get("purchase_date") or today_iso()
        d["last_updated"] = now_iso()
        row = [d.get(h, "") for h in headers]
        rows_to_append.append(row)
        created.append({"id": inv_id, "item_en": d.get("item_en"), "item_zh": d.get("item_zh"), "quantity": d.get("quantity"), "unit": d.get("unit")})
    append_values(SHEET_NAMES["inventory"], rows_to_append)
    return {"created_count": len(created), "created": created}


@app.post("/inventory/update", dependencies=[Depends(require_api_key)])
def update_inventory(payload: UpdateInventoryPayload) -> Dict[str, Any]:
    sheet_name = SHEET_NAMES["inventory"]
    headers, rows = rows_as_dicts(sheet_name)
    valid_fields = set(headers)
    updated = []
    for upd in payload.updates:
        idx = find_inventory_index(rows, upd.id, None, None)
        for k, v in upd.fields.items():
            if k not in valid_fields:
                raise HTTPException(status_code=400, detail=f"Invalid inventory field: {k}")
            rows[idx][k] = v
        rows[idx]["last_updated"] = now_iso()
        updated.append(rows[idx])
    write_dict_rows(sheet_name, headers, rows)
    return {"updated_count": len(updated), "updated": updated}


@app.post("/inventory/consume", dependencies=[Depends(require_api_key)])
def consume_inventory(payload: ConsumePayload) -> Dict[str, Any]:
    sheet_name = SHEET_NAMES["inventory"]
    headers, rows = rows_as_dicts(sheet_name)
    usage_rows = []
    projected_changes = []
    consumption_date = payload.date or today_iso()

    # Work on a mutable copy; do not write until all validations pass.
    new_rows = [dict(r) for r in rows]
    for item in payload.items:
        idx = find_inventory_index(new_rows, item.item_id, item.item_en, item.item_zh)
        r = new_rows[idx]
        current_qty = as_float(r.get("quantity"), 0) or 0
        current_unit = str(r.get("unit", "")).strip()
        used_in_current_unit = convert_qty(item.quantity_used, item.unit, current_unit)
        remaining = current_qty - used_in_current_unit
        if remaining < -1e-6:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Insufficient inventory",
                    "item": r,
                    "requested": item.quantity_used,
                    "requested_unit": item.unit,
                    "available": current_qty,
                    "available_unit": current_unit,
                },
            )
        r["quantity"] = round(max(0, remaining), 3)
        if r["quantity"] <= 0:
            r["status"] = "finished"
        r["last_updated"] = now_iso()
        projected_changes.append({
            "id": r.get("id"),
            "item_en": r.get("item_en"),
            "item_zh": r.get("item_zh"),
            "before": current_qty,
            "used": round(used_in_current_unit, 3),
            "after": r["quantity"],
            "unit": current_unit,
        })
        usage_rows.append([
            now_iso(), consumption_date, r.get("id"), r.get("item_en"), r.get("item_zh"),
            item.quantity_used, item.unit, item.meal or "", item.reason or "", item.notes or "",
        ])

    if payload.dry_run:
        return {"dry_run": True, "changes": projected_changes}

    write_dict_rows(sheet_name, headers, new_rows)
    append_values(SHEET_NAMES["usage"], usage_rows)
    return {"dry_run": False, "consumed_count": len(payload.items), "changes": projected_changes}


@app.get("/inventory/expiring", dependencies=[Depends(require_api_key)])
def expiring_inventory(days: int = Query(default=3, ge=0, le=30)) -> Dict[str, Any]:
    _, rows = rows_as_dicts(SHEET_NAMES["inventory"])
    today = date.today()
    cutoff = today + timedelta(days=days)
    items = []
    for r in active_inventory(rows):
        d = parse_date_maybe(r.get("use_by"))
        if d and d <= cutoff:
            x = dict(r)
            x["days_until_use_by"] = (d - today).days
            items.append(x)
    items.sort(key=lambda r: (as_float(r.get("days_until_use_by"), 999) or 999, str(r.get("priority", "medium"))))
    return {"count": len(items), "days": days, "items": items}


@app.post("/weight-log", dependencies=[Depends(require_api_key)])
def log_weight(entry: WeightEntry) -> Dict[str, Any]:
    d = entry.model_dump()
    d["date"] = d.get("date") or today_iso()
    headers = HEADERS["WeightLog"]
    append_values(SHEET_NAMES["weight"], [[d.get(h, "") for h in headers]])
    return {"logged": d}


@app.get("/weight-log", dependencies=[Depends(require_api_key)])
def get_weight_log(days: int = Query(default=30, ge=1, le=365)) -> Dict[str, Any]:
    _, rows = rows_as_dicts(SHEET_NAMES["weight"])
    parsed = []
    cutoff = date.today() - timedelta(days=days)
    for r in rows:
        d = parse_date_maybe(r.get("date"))
        wt = as_float(r.get("weight_lb"))
        if d and wt is not None and d >= cutoff:
            x = dict(r)
            x["date"] = d.isoformat()
            x["weight_lb"] = wt
            parsed.append(x)
    parsed.sort(key=lambda r: r["date"])
    return {"count": len(parsed), "items": parsed}


def compute_trend(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    entries = []
    for r in rows:
        d = parse_date_maybe(r.get("date"))
        wt = as_float(r.get("weight_lb"))
        if d and wt is not None:
            entries.append({"date": d, "weight_lb": wt})
    entries.sort(key=lambda x: x["date"])
    last_14 = entries[-14:]
    recent_7 = entries[-7:]
    previous_7 = entries[-14:-7]

    def avg(xs: List[Dict[str, Any]]) -> Optional[float]:
        if not xs:
            return None
        return round(sum(x["weight_lb"] for x in xs) / len(xs), 2)

    recent_avg = avg(recent_7) if len(recent_7) >= 7 else None
    prev_avg = avg(previous_7) if len(previous_7) >= 7 else None
    trend_delta = None
    weekly_loss = None
    status = "need_more_data"
    adjustment = "Do not change calories based on weight trend yet. Collect at least 7-14 days."
    if recent_avg is not None and prev_avg is not None:
        trend_delta = round(recent_avg - prev_avg, 2)  # negative = weight loss
        weekly_loss = round(prev_avg - recent_avg, 2)
        if weekly_loss < 1.0:
            status = "slow"
            adjustment = "If tracking is accurate, reduce daily calories by about 150 kcal, prioritizing oil, sweet sauces, snacks, fast food."
        elif 1.25 <= weekly_loss <= 1.75:
            status = "on_target"
            adjustment = "Maintain calories and macros."
        elif weekly_loss > 2.0:
            status = "too_fast"
            adjustment = "If hunger, sleep, or training performance is poor, add 100-200 kcal/day, mostly around training carbohydrates. If week 1 and feeling fine, observe."
        else:
            status = "acceptable_but_adjust_watchfully"
            adjustment = "Small adjustment only if hunger or performance is off; otherwise observe another week."

    return {
        "entries_count": len(entries),
        "latest_weight_lb": entries[-1]["weight_lb"] if entries else None,
        "latest_date": entries[-1]["date"].isoformat() if entries else None,
        "recent_7_day_avg_lb": recent_avg,
        "previous_7_day_avg_lb": prev_avg,
        "trend_delta_lb_per_week": trend_delta,
        "weekly_loss_lb": weekly_loss,
        "status": status,
        "adjustment_guidance": adjustment,
    }


@app.get("/trend-summary", dependencies=[Depends(require_api_key)])
def trend_summary() -> Dict[str, Any]:
    _, rows = rows_as_dicts(SHEET_NAMES["weight"])
    return compute_trend(rows)


@app.post("/meal-log", dependencies=[Depends(require_api_key)])
def log_meals(payload: MealLogPayload) -> Dict[str, Any]:
    headers = HEADERS["MealLog"]
    rows = []
    for meal in payload.meals:
        d = meal.model_dump()
        d["date"] = d.get("date") or today_iso()
        rows.append([d.get(h, "") for h in headers])
    append_values(SHEET_NAMES["meal"], rows)
    return {"logged_count": len(rows)}


@app.get("/shopping-list/suggested", dependencies=[Depends(require_api_key)])
def suggested_shopping_list() -> Dict[str, Any]:
    _, rows = rows_as_dicts(SHEET_NAMES["inventory"])
    suggestions = []
    for r in active_inventory(rows):
        qty = as_float(r.get("quantity"), 0) or 0
        min_qty = as_float(r.get("min_quantity"))
        target_qty = as_float(r.get("target_quantity"))
        if min_qty is not None and target_qty is not None and qty <= min_qty:
            suggestions.append({
                "item_en": r.get("item_en"),
                "item_zh": r.get("item_zh"),
                "category": r.get("category"),
                "current_quantity": qty,
                "unit": r.get("unit"),
                "suggested_buy_quantity": max(0, round(target_qty - qty, 2)),
                "reason": "below_min_quantity",
            })
    return {"count": len(suggestions), "items": suggestions}


@app.get("/coach-context", dependencies=[Depends(require_api_key)])
def coach_context(expiring_days: int = Query(default=3, ge=0, le=14)) -> Dict[str, Any]:
    _, inv_rows = rows_as_dicts(SHEET_NAMES["inventory"])
    _, weight_rows = rows_as_dicts(SHEET_NAMES["weight"])
    _, settings_rows = rows_as_dicts(SHEET_NAMES["settings"])
    settings = {str(r.get("key", "")): r.get("value", "") for r in settings_rows if r.get("key")}
    active = active_inventory(inv_rows)
    expiring = expiring_inventory(days=expiring_days)["items"]
    trend = compute_trend(weight_rows)
    shopping = suggested_shopping_list()["items"]
    return {
        "settings": settings,
        "inventory_active_count": len(active),
        "inventory_active": active,
        "expiring_items": expiring,
        "trend_summary": trend,
        "suggested_shopping_list": shopping,
        "timezone": TIMEZONE,
    }
