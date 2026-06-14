"""API ingest posizioni — tracking lecito di asset autorizzati.

L'ingest accetta posizioni SOLO per Tracked Asset attivi, entro la finestra
autorizzata, con token valido. Nessuna geolocalizzazione occulta di terzi:
ogni asset deve avere base giuridica e documento di consenso/mandato.
"""
import json
import frappe
from frappe import _
from frappe.utils import now_datetime


@frappe.whitelist(allow_guest=True, methods=["POST"])
def ingest(token: str, lat: float, lng: float, ts: str = None,
           accuracy: float = None, speed: float = None,
           heading: float = None, raw: str = None):
	"""Riceve una posizione da hardware tracker o app consensuale.

	Autenticazione: ingest_token dell'asset (non sessione utente).
	"""
	asset_name = frappe.db.get_value("Tracked Asset", {"ingest_token": token}, "name")
	if not asset_name:
		frappe.local.response["http_status_code"] = 403
		return {"ok": False, "error": "invalid token"}

	asset = frappe.get_doc("Tracked Asset", asset_name)
	if not asset.active:
		frappe.local.response["http_status_code"] = 409
		return {"ok": False, "error": "asset not active"}
	if not asset.is_within_window():
		frappe.local.response["http_status_code"] = 409
		return {"ok": False, "error": "outside authorized window"}

	pos = frappe.get_doc({
		"doctype": "Asset Position",
		"tracked_asset": asset_name,
		"reported_at": ts or now_datetime(),
		"geo_lat": float(lat),
		"geo_lng": float(lng),
		"accuracy": float(accuracy) if accuracy is not None else None,
		"speed": float(speed) if speed is not None else None,
		"heading": float(heading) if heading is not None else None,
		"source": "ingest",
		"raw_payload": raw if isinstance(raw, str) else (json.dumps(raw) if raw else None),
	})
	pos.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True, "position": pos.name}


@frappe.whitelist(methods=["POST"])
def track_point(field_activity: str = None, lat: float = None, lng: float = None,
                accuracy: float = None, speed: float = None):
	"""Breadcrumb GPS dell'investigatore loggato (dalla pagina di cattura)."""
	investigator = frappe.db.get_value("Investigator", {"platform_user": frappe.session.user}, "name")
	pt = frappe.get_doc({
		"doctype": "Geo Track Point",
		"investigator": investigator,
		"field_activity": field_activity,
		"captured_at": now_datetime(),
		"geo_lat": float(lat) if lat is not None else None,
		"geo_lng": float(lng) if lng is not None else None,
		"accuracy": float(accuracy) if accuracy is not None else None,
		"speed": float(speed) if speed is not None else None,
		"source": "browser",
	})
	pt.insert(ignore_permissions=True)
	return {"ok": True, "point": pt.name}


@frappe.whitelist()
def asset_track(tracked_asset: str, hours: int = 24):
	"""Ritorna la polyline delle posizioni recenti di un asset (per mappa)."""
	from frappe.utils import add_to_date, now_datetime as _now
	since = add_to_date(_now(), hours=-int(hours))
	rows = frappe.get_all("Asset Position",
		filters={"tracked_asset": tracked_asset, "reported_at": [">=", since]},
		fields=["reported_at", "geo_lat", "geo_lng", "speed", "accuracy"],
		order_by="reported_at asc")
	return {"asset": tracked_asset, "points": rows}
