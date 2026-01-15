from decimal import Decimal, InvalidOperation
from .constants import SUBSCRIPTIONS as CFG
from .models import SubscriptionSetting

def _ents():
    return CFG.get("ENTITLEMENTS", {}) or {}

def _symbols():
    return CFG.get("CURRENCY_SYMBOLS", {}) or {}

def label_for_key(key: str) -> str:
    cfg = _ents().get(key) or {}
    return cfg.get("label") or key.replace("_", " ").title()

def value_label_for_key(key: str, value: str) -> str:
    cfg = _ents().get(key) or {}
    values = cfg.get("values") or {}
    if value is None:
        return ""
    return values.get(str(value).lower(), str(value).title())

def order_for_key(key: str) -> int:
    cfg = _ents().get(key) or {}
    return int(cfg.get("order", 9999))

def feature_keys_in_order(union_keys: set[str]) -> list[str]:
    cfg = _ents()
    configured = [k for k in cfg if k in union_keys]
    configured.sort(key=lambda k: (cfg[k].get("order", 9999)))
    unknown = sorted([k for k in union_keys if k not in cfg])
    return configured + unknown

def currency_symbol(code: str | None) -> str:
    if not code:
        return ""
    return _symbols().get(code.upper(), code.upper())

def format_money(amount, currency: str | None) -> str:
    if amount in (None, ""):
        return ""
    try:
        dec = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        return f"{amount}"
    s = f"{dec:,.2f}"
    if s.endswith(".00"):
        s = s[:-3]
    sym = currency_symbol(currency)
    return f"{sym}{s}" if sym else s

def build_comparison(plans: list[dict]) -> dict:
    """
    plans: serializer.data list from PlanSerializer (each has entitlements with label/value_display/order)
    Returns: {"monthly": {"columns":[...], "rows":[...]}, "yearly": {...}, ...}
    """
    from collections import defaultdict

    # group plans by interval (case-insensitive)
    by_interval = defaultdict(list)
    for p in plans:
        iv = (p.get("interval") or "").lower()
        by_interval[iv].append(p)

    comparison = {}
    for interval, iv_plans in by_interval.items():
        # columns in the same order as iv_plans
        columns = [{"slug": p["slug"], "name": p["name"]} for p in iv_plans]

        # union of entitlement keys with best label + lowest order
        key_meta = {}  # key -> {"label":..., "order": int}
        plan_ent_map = []  # for fast lookup per plan
        for p in iv_plans:
            ents = p.get("entitlements") or []
            m = {e["key"]: e for e in ents}
            plan_ent_map.append(m)
            for e in ents:
                k = e["key"]
                o = e.get("order") or 9999
                lbl = e.get("label") or k
                if k not in key_meta or o < key_meta[k]["order"]:
                    key_meta[k] = {"label": lbl, "order": o}

        # sort feature keys by configured order then key
        sorted_keys = sorted(key_meta.items(), key=lambda kv: (kv[1]["order"], kv[0]))

        rows = []
        for k, meta in sorted_keys:
            values = []
            for m in plan_ent_map:
                e = m.get(k)
                if not e:
                    values.append("—")
                else:
                    vd = e.get("value_display")
                    if vd not in (None, ""):
                        values.append(str(vd))
                    elif e.get("limit_int") is not None:
                        values.append(str(e["limit_int"]))
                    elif e.get("limit_str"):
                        values.append(str(e["limit_str"]))
                    else:
                        values.append("Yes" if e.get("enabled") else "No")
            rows.append({"key": k, "label": meta["label"], "values": values})

        comparison[interval] = {"columns": columns, "rows": rows}

    return comparison

def get_subscription_setting():
    """Safely return the single global SubscriptionSetting instance."""
    return SubscriptionSetting.objects.first()  # always one, enforced by validation
