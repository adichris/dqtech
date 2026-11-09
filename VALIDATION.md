# Validation â€” 7 November 2026

Passed on Python 3.12, Django 5.2.16 and Oscar 4.2.1:

- Django system check: no issues.
- Migration consistency: no changes detected; all migrations applied successfully to the local SQLite database.
- 128 Django integration tests passed. Coverage includes tenant boundaries, staff finance permissions/revocation, seller-only gateway settings, callback ownership, signed webhooks, exact payment amount/currency matching, duplicate payment confirmation, post-cancellation payment review, split orders, trial commissions, Oscar order creation, stock reservations/cancellation/dispatch, receipts/journals/refunds, verified reviews, favourites, search filters, pagination, basket quantities, delivery/collection and listing reports.
- 29 focused unit tests passed for commission dates/rounding, balanced journal validation, credential encryption, HMAC verification and provider redirect/payment matching.
- Static asset collection completed successfully.
- Python source compiled and browser JavaScript passed node --check.
- Chrome browser checks at 1440px and 390px confirmed autocomplete, quick view, inline add-to-bag, HTMX search filtering, grid/list switching, product tabs, purchase quantities, basket quantity updates and collection choices. Search, product and basket pages had no horizontal overflow at mobile width. No JavaScript errors were reported; Font Awesome loaded from the local font files.
- New delivery/messaging tests cover default COD provisioning, immutable payment/delivery snapshots, cash collection before delivery, unpaid returns, regional rates, address validation, collection-only contact details, private tracking, location validation, tenant-scoped settings, encrypted secrets, durable outbox deduplication, SMTP backend integration, Arkesel V2 request construction, WhatsApp templates/opt-in/STOP, signed callbacks, service windows, delivery-report ordering and unknown-send handling.
- Chrome checks at 1440px and 390px passed for device-location autofill using a mocked provider, permission-denial fallback, address preservation across HTMX quantity changes, country-dependent region fields, collection requirements, default COD, tracking progress/location display, seller tracking updates and messaging settings. No JavaScript errors or horizontal overflow were reported. Real device GPS/provider accuracy was not exercised.
- Eight address-book tests passed for owner-only access, deduplication, default/replacement behavior, valid full addresses, checkout saving, immutable order snapshots, saved selection after errors and initial regional pricing. Browser checks confirmed saved-address selection, editable prefill, preservation after HTMX updates, light/dark persistence across navigation/reload, and mobile layout on basket/product/search/address pages. No JavaScript errors or horizontal overflow were reported.
- Supplied logo displayed from the local original PNG; changing SYSTEM_NAME through Django settings was tested.

Limits:

- SQLite tests do not verify PostgreSQL concurrent transaction behavior. PostgreSQL load/concurrency tests and a production security review remain necessary.
- Provider responses were mocked in tests. No real Paystack account, live charge, refund transfer, courier API, SMTP server, Arkesel account or WhatsApp Cloud API send was exercised. Email used a controlled Django memory backend; SMS/WhatsApp HTTP responses and callbacks were mocked/signed in tests. Docker and public deployment were not exercised.
- Oscar's simple Haystack backend emits an update-not-implemented warning during tests. Public search uses tenant-scoped Django ORM queries; a production Oscar search backend should be selected if its staff search needs expand.

Reproduce from the project directory with DEBUG=1:

    python manage.py check
    python manage.py makemigrations --check --dry-run
    python manage.py test mall
    python -m unittest discover -p 'test_*.py'
    python manage.py collectstatic --noinput

Total: 147 passing automated tests (118 Django integration + 29 focused unit tests). Local migrations 0001â€“0010 applied successfully. See DELIVERY_AND_MESSAGING.md for account activation and worker requirements.

See STATUS.md for remaining production requirements.

## Oscar consolidation and typography verification

- 128 Django tests and 29 unit tests passed after consolidation. New integration checks exercise native model identity, catalogue authority, native basket checkout, address usage, allocations, history, payment transactions and immutable order totals.
- A populated legacy SQLite database migrated successfully with addresses, listings, orders/lines, stock allocations, receipts, reviews, wishlist, notifications and tracking preserved. Read-only Oscar audit reported no issues in the migration probe and local catalogue.
- Chrome checks on home, search, product and bag pages at 1440px, 390px and 320px found no horizontal page overflow. Computed body and product description sizes were 16px; card titles were 18px desktop and 17px mobile. Mobile search layout was visually inspected.
- PostgreSQL migration execution and live provider sends remain unverified. Earlier browser workflow checks listed above preceded the Oscar consolidation; the current browser pass checks typography and page rendering.
