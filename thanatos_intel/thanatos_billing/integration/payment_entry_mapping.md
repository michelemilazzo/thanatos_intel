# ERPNext Payment Integration

Trigger source:
- Payment Entry submitted
- Sales Invoice paid

Flow:
1. Read Payment Entry
2. Find Visa Case Order
3. Update payment_status = Paid
4. Enable portal
5. Queue workflow engine

Entities:
- Payment Entry
- Sales Invoice
- Visa Case Order
- Visa Study Case
