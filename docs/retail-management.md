# Retail Management: architecture and implementation

## Audit and scope

The platform already supplies Company, organization selection, authentication,
module installation, permission/role catalogs, provisioning and AuditLog. The
`retail-management` template is an empty placeholder. Engineering project payments
and clients do not represent retail stock, suppliers, customers or receipts.

This implementation adds a Django domain module inside the same application and
database. New additive migrations activate only the Retail template and add its
domain tables. Other template definitions and customer records are preserved.

First-version modules: Dashboard, Products (including categories), Locations,
Inventory, Suppliers, Customers, Purchases, Sales and returns, Reports, Roles and
permissions, Audit activity. Reports is optional; disabling a module retains data.

## Models and rules

- Category, Product: tenant-unique SKU and non-empty barcode, category, unit,
  selling price, cost price, configurable tax percentage and reorder level.
- Location: tenant-unique code, name, address and active state.
- Supplier and Customer: separate tenant-scoped contact registers.
- StockBalance: unique organization/location/product and nonnegative quantity.
- StockMovement: append-only receipt/sale/return/adjustment ledger with actor,
  reason, quantity and resulting balance. Opening stock is an audited adjustment.
- RetailDocument and RetailLine: draft/posted/cancelled purchases and sales,
  immutable posted product/price/tax snapshots, totals, currency, creator and poster.
  A posted sale can have one full return, with recorded reason and restock choice.

Stock changes lock the organization and affected balances within one transaction;
the same lock serializes first-balance creation and posting. A second post has no
additional effect. All quantity and money values use Decimal and DB constraints.
Sales cannot make stock negative. Returns preserve the original sale and create
a separate refund record; duplicate refunds are rejected. The entire sale is
refunded in this version. Original receipt totals remain unchanged.

Tax is an exclusive, organization-configurable product percentage, not a global
legal default. Payments record funds already received; no payment gateway or card
details are stored. Cash may exceed the amount due and records change; card/bank
amounts must equal the total. Full accounting, payroll, credit sales, partial
returns, stock transfers, loyalty and online commerce are future work.

## Access, pages and endpoints

Pages under `/retail/`: dashboard, product/category/location/supplier/customer
lists and forms, inventory and adjustment form, purchase/sale lists, draft editor,
receipt/detail, post/cancel/refund actions, reports/CSV, roles and audit activity.
Tenant scope comes from a validated session membership, never body/query IDs.
An active organization role and enabled module are required for each action.
Platform administrator/superuser flags give no implicit access to retail records.

Roles: Organization Administrator, Store Manager, Cashier, Inventory Controller,
Purchasing Officer and Read-only Auditor. Cashiers see their own sales; broader
sales access, price overrides, cost visibility, refunds, adjustments, report exports
and role assignment require distinct permissions. Role management uses existing
organization memberships. Audit entries include the server-derived tenant.

Session-authenticated JSON GET endpoints: `/retail/api/dashboard/`,
`/retail/api/products/`, `/retail/api/inventory/`, `/retail/api/sales/` and sale
detail. Mutations use CSRF-protected forms and the same checked transaction
services. No destructive document/delete endpoints are provided. CSV downloads
are audited and escape spreadsheet formula prefixes in text fields.

## Verification

Test catalog/provisioning, template isolation, tenant/role/module checks, scoped
foreign keys, unique SKU/barcode, Decimal totals, stock receipts/adjustments,
negative-stock rollback, duplicate posting, posted-record immutability, refunds,
cashier ownership/cost privacy, report exports, HTML/JSON pages and CSRF.
Migrations are additive and can be applied with `python manage.py migrate`.
