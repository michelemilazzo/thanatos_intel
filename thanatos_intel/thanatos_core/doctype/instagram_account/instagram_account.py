import frappe


class InstagramAccount(frappe.model.document.Document):

    def validate(self):
        self.username = (self.username or "").strip().lstrip("@")
        self.ig_user_id = (self.ig_user_id or "").strip()

    @frappe.whitelist()
    def test_connection(self) -> dict:
        """Verifica che token + ig_user_id siano validi interrogando il Graph."""
        from thanatos_intel.ingest.instagram import account_token, GRAPH
        import requests
        token = account_token(self.name)
        if not token:
            return {"ok": False, "error": "Access token mancante"}
        try:
            r = requests.get(f"{GRAPH}/{self.ig_user_id}",
                             params={"fields": "username,name,followers_count",
                                     "access_token": token}, timeout=15)
            data = r.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}
        if r.status_code != 200:
            return {"ok": False, "error": (data.get("error") or {}).get("message", str(data))}
        return {"ok": True, "profile": data}
