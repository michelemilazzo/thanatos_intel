# Payment Hook Runtime Blueprint

Event:
- Payment Entry on_submit

Runtime flow:
1. Receive payment event
2. Validate Payment Entry status
3. Match Sales Invoice
4. Match Visa Case Order
5. Update payment_status=Paid
6. Enable portal access
7. Queue workflow engine
8. Create audit log
