# Project status â€” 7 November 2026

## Working locally

Django 5.2.16 and Oscar 4.2.1 run together. Migrations apply successfully. The live local application replaces the original static prototype. Seller-scoped catalogue, split checkout, Oscar order/stock records, seller payment methods, encrypted Paystack connection settings, signed webhook verification, receipts, cancellation, returns, refund records, balanced journals, expenses, commission invoices, role-gated finance, CSV exports, verification review and in-app notifications are implemented.

The storefront uses the supplied logo and a Python-configured system name. It includes a dedicated faceted search page, autocomplete, pagination, grid/list browsing, quick-view cards, favourites, gallery/zoom/sharing, verified-purchase reviews, rating distributions and related products. The redesigned basket includes quantities, per-store delivery/collection choices, separate currency totals and seller-specific payments. Font Awesome assets and original SVG artwork are included locally.

Ghana delivery now includes all regions, town suggestions with manual entry, location-assisted autofill, structured address snapshots, regional seller rates and default Cash on Delivery. Customer tracking provides private progress/history and seller-reported locations. Email, seller-owned Arkesel SMS and seller-owned WhatsApp Cloud API adapters have a durable outbox and worker, encrypted credentials and seller message logs. WhatsApp includes explicit checkout consent, signed webhooks, STOP/START handling, approved-template notifications, 24-hour-window replies and delivered/read reports.

Buyer-owned reusable address books now include labels, default selection, editing/deletion, checkout reuse and optional saving at checkout. Address changes preserve historical order snapshots. The public and custom merchant interfaces include a persistent light/dark toggle with device-preference fallback.

## 8 November 2026 update

Mall Pay split payments (marketplace Paystack account with seller subaccounts and commission deducted at source), an eligibility threshold for seller-owned Paystack accounts, login lockout and rate limits, automatic expiry of unpaid orders with per-buyer caps and seller cancellation, HTTPS-only product images, Content-Security-Policy/HSTS/logging/Redis cache, role-aware sign-in redirects, staff access to workspaces from the seller centre, paginated dashboards and a currency column in finance exports. Mall Pay has been tested only with mocked Paystack responses; a real marketplace Paystack account, subaccount creation and a test-mode split payment must be exercised before launch. Email verification, MFA and platform-mediated disputes remain to be built.

## External activation and production work

- Seller-owned Paystack accounts and credentials must be configured and exercised in test mode. Live provider transactions, provider refunds, chargebacks and settlement reconciliation have not been executed. Other automatic providers are not implemented.
- Refund records require the seller to complete the actual refund externally. Commission records do not automatically deduct or collect funds from sellers.
- A full audited double-entry accounting product, statutory tax invoices, country-specific tax rules, accounting period closure and automated subscription/setup fee billing remain outside the current implementation.
- Fixed staff-role bundles are implemented; custom action-level role designers, invitation acceptance, branch assignment, staff editing workflows, MFA, recovery codes and comprehensive email verification remain to be added.
- Market/currency support covers GH/GHS, NG/NGN, US/USD and GB/GBP. Price comparison is scoped to one currency; foreign exchange and country-specific tax/shipping engines are not implemented.
- CASMET, GradVenture and STUDSMALL are represented by store programme metadata and campus discovery. Full associate commissions, mentoring, programme applications and hostel-delivery workflows are not implemented.
- Delivery/collection fees and seller tracking references are supported. Courier GPS/API integration, carrier delivery quotes, shipping labels, advanced variants, media uploads/storage, stock reservation expiry and full customer messaging threads remain to be developed.
- Add production authentication hardening, monitoring, backups/restore rehearsals, load/security review and PostgreSQL concurrency testing before launch.
- Docker and public hosting were not available for execution testing. Live SMTP, Arkesel and Meta WhatsApp accounts, approved senders/templates, an HTTPS domain and a deployment account must be configured for production.

## References inspected

- https://centipidbilling.com/ghana
- https://centipidbilling.com/features
- https://docs.centipidbilling.com/analytics/dashboard-and-analytics
- https://docs.centipidbilling.com/billing/expenses
- https://centipidbilling.com/features/staff-roles-permissions
- https://django-oscar.readthedocs.io/en/latest/_modules/oscar/apps/order/utils.html
- https://paystack.com/docs/payments/webhooks/
- https://four.htmx.org/docs/

CentipidBilling's public workflows informed the design; no proprietary code or private data schema was available. The user's supplied HTMX guidance was applied using the verified HTMX 4.0.1 distribution.

## Oscar consolidation and readability

Native Oscar records now own addresses, catalogue/stock, baskets, orders/lines/status history, payment transactions, reviews, favourites and notifications. Custom tables retain tenant policies and integration metadata. See OSCAR_ARCHITECTURE.md before applying the forward-only data migrations. Larger shared typography and mobile spacing are implemented across the storefront and merchant interface.
