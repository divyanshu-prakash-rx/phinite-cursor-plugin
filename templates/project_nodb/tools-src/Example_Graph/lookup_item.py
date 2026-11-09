"""lookup_item — Example Assistant (Phinite tool, no params: reads capture variables from inputs).

Finds an item in a small built-in catalogue. Replace CATALOGUE with your API call (use _http) or data source.

inputs (captures): item_query (or item_id from an earlier call)
returns: item
capture: item_id
"""

CATALOGUE = {
    "SKU-100": {"name": "Desk lamp", "price": 39.0, "in_stock": True},
    "SKU-200": {"name": "Office chair", "price": 189.0, "in_stock": False},
}


def _run(inputs, env):
    query = _str(inputs, "item_query", "item_id")
    if not query:
        return _fail("No item named yet", "Ask the user which item they mean (name or SKU).")
    match = next((sku for sku, item in CATALOGUE.items()
                  if query.upper() == sku or query.lower() in item["name"].lower()), None)
    if not match:
        available = ", ".join(f"{item['name']} ({sku})" for sku, item in CATALOGUE.items())
        return _fail(f"No item matches '{query}'", f"Tell the user, and offer what is available: {available}")
    return _ok({"item": {"sku": match, **CATALOGUE[match]}}, {"item_id": match})
