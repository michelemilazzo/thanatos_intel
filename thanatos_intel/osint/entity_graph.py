"""API grafo Entity Relationship — costruisce nodes+edges partendo da un'entità.
Ricorsione limitata (default depth=2) per evitare esplosioni combinatorie.
"""
import frappe


MAX_NODES = 200
DEFAULT_DEPTH = 2

TYPE_COLORS = {
    "Company": "#61cfc9",
    "Person": "#f2a541",
    "Domain": "#8ab6f9",
    "IP": "#c084fc",
    "Email": "#e879f9",
    "Wallet": "#facc15",
    "Phone": "#34d399",
    "Vehicle": "#fb7185",
    "Vessel": "#94a3b8",
    "Aircraft": "#94a3b8",
    "default": "#cfcfcf",
}


@frappe.whitelist()
def entity_graph(entity, depth=None, max_nodes=None):
    """Ritorna {nodes, edges, stats} per l'entità e il suo vicinato."""
    if not entity:
        return {"nodes": [], "edges": [], "stats": {}}
    d = int(depth or DEFAULT_DEPTH)
    mn = int(max_nodes or MAX_NODES)

    seen = set()
    nodes = {}
    edges = []
    frontier = {entity}
    for level in range(d + 1):
        if not frontier or len(seen) >= mn:
            break
        next_frontier = set()
        for name in frontier:
            if name in seen or len(seen) >= mn:
                continue
            seen.add(name)
            info = frappe.db.get_value(
                "Investigation Entity", name,
                ["name", "entity_type", "primary_identifier", "full_name"],
                as_dict=True,
            )
            if not info:
                continue
            nodes[name] = {
                "id": name,
                "label": (info.full_name or info.primary_identifier or name)[:60],
                "group": info.entity_type or "default",
                "color": TYPE_COLORS.get(info.entity_type or "default", TYPE_COLORS["default"]),
                "level": level,
                "shape": "dot" if info.entity_type != "Person" else "diamond",
            }
            if level < d:
                rels = frappe.db.sql("""
                    SELECT related_entity, rel_type, confidence
                    FROM `tabEntity Relationship`
                    WHERE parent=%s AND parenttype='Investigation Entity'
                """, (name,), as_dict=True)
                for r in rels:
                    if r.related_entity:
                        edges.append({
                            "from": name, "to": r.related_entity,
                            "label": (r.rel_type or "").replace("_", " "),
                            "arrows": "to",
                            "value": float(r.confidence or 50) / 100,
                        })
                        if r.related_entity not in seen:
                            next_frontier.add(r.related_entity)
        frontier = next_frontier

    # aggiungi nodi mancanti (i related_entity che non erano in seen)
    for e in edges:
        if e["to"] not in nodes:
            info = frappe.db.get_value(
                "Investigation Entity", e["to"],
                ["name", "entity_type", "primary_identifier", "full_name"],
                as_dict=True,
            )
            if info:
                nodes[e["to"]] = {
                    "id": info.name,
                    "label": (info.full_name or info.primary_identifier or info.name)[:60],
                    "group": info.entity_type or "default",
                    "color": TYPE_COLORS.get(info.entity_type or "default", TYPE_COLORS["default"]),
                    "level": d,
                    "shape": "dot" if info.entity_type != "Person" else "diamond",
                }

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "stats": {
            "nodes": len(nodes),
            "edges": len(edges),
            "depth": d,
            "truncated": len(seen) >= mn,
            "root": entity,
        },
    }
