import frappe


@frappe.whitelist()
def sync_contacts_to_mail(user: str | None = None) -> dict:
	"""Sync Frappe/CRM contacts to the Mail webmail address book."""

	if not user:
		user = frappe.session.user

	from mail.client.doctype.contact_card.contact_card import bulk_add_contact_cards
	from mail.jmap import get_default_address_book_id

	default_ab = get_default_address_book_id(user)

	contacts_raw = frappe.db.sql(
		"""
        SELECT c.name, c.first_name, c.last_name, c.company_name,
            GROUP_CONCAT(DISTINCT ce.email_id SEPARATOR '|||') as emails,
            GROUP_CONCAT(DISTINCT cp.phone SEPARATOR '|||') as phones
        FROM `tabContact` c
        LEFT JOIN `tabContact Email` ce ON ce.parent=c.name AND ce.email_id != ''
        LEFT JOIN `tabContact Phone` cp ON cp.parent=c.name
        WHERE ce.email_id IS NOT NULL AND ce.email_id != ''
        GROUP BY c.name
        LIMIT 1000
		""",
		as_dict=True,
	)

	seen, cards = set(), []
	for c in contacts_raw:
		full_name = " ".join(filter(None, [c.first_name, c.last_name])) or c.company_name or c.name
		emails_list = []
		for e in (c.emails or "").split("|||"):
			e = e.strip()
			if e and e not in seen:
				emails_list.append({"address": e, "type": "Personal"})
				seen.add(e)
		if not emails_list:
			continue
		phones_list = (
			[{"number": p.strip(), "type": "Personal"} for p in (c.phones or "").split("|||") if p.strip()]
			or None
		)
		cards.append(
			{
				"user": user,
				"address_book_ids": [default_ab],
				"full_name": full_name,
				"kind": "Individual",
				"emails": emails_list,
				"phones": phones_list,
			}
		)

	imported = 0
	for i in range(0, len(cards), 50):
		bulk_add_contact_cards(user, cards[i : i + 50], raise_exception=False)
		imported += len(cards[i : i + 50])

	return {"imported": imported, "total_frappe_contacts": len(contacts_raw)}
