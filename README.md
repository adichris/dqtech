# DQTech Digital Shopping Mall

A running Django + Django Oscar marketplace with custom merchant dashboards, independent seller payments, classifieds, campus filters, inventory, split orders, finance records and staff access controls.

## Run locally

Use Python 3.12. In PowerShell:

```powershell
./start.ps1 -Install
```

The script installs dependencies in .venv, creates persistent local development secrets, applies migrations and starts http://127.0.0.1:8008/. It binds to localhost and enables DEBUG for development only.

To add the illustrative catalogue, set DEMO_PASSWORD and run ./start.ps1 -SeedDemo. Demo seller accounts are ama, kojo, akua and kofi; their passwords come from your DEMO_PASSWORD. Register a buyer through the site. Create a technical administrator with .venv/Scripts/python manage.py createsuperuser while DEBUG=1 is set.

For an existing environment, install requirements.txt, set DEBUG=1, run python manage.py migrate, and then python manage.py runserver 127.0.0.1:8008.

## Branding from Python settings

Edit config/settings.py:

```python
SYSTEM_NAME = 'DQTech Digital Shopping Mall'
SYSTEM_TAGLINE = 'Your Business. Your Store. Connected to the World.'
SYSTEM_COMPANY = 'Digital Quotient Technologies Ltd'
SYSTEM_LOGO = 'brand/dqtech-logo.png'
```

The supplied original logo is preserved in static/brand/dqtech-logo.png. Public page titles, the header/footer and technical administration use these settings. Restart Django after changing settings.

## Storefront and discovery

- Dedicated /search/ page with debounced header autocomplete for products and stores.
- Keyword, category, market, currency, price, customer-rating, availability, verified-seller, listing-type and campus filters.
- Server-side validation, filter chips, preserved query parameters and 12-product pagination. Price comparisons require a single currency.
- Grid/list layouts, quick view, saved favourites, stock-aware inline add-to-bag, product galleries, image enlargement, sharing and recommendations.
- Verified-purchase reviews after delivery, one review per buyer/product, rating summaries and distributions, and listing reports for staff review. No demo ratings are invented.
- Font Awesome Free 6.7.2, original SVG illustrations, Bootstrap 5.3.8, HTMX 4.0.1 and Alpine.js. Core scripts, icon fonts and CSS are bundled locally. Font Awesome licensing is in static/vendor/fontawesome/LICENSE.txt.

## Basket and orders

The basket groups items by seller, updates quantities with HTML fragments, supports saved-for-later items, and calculates delivery versus collection separately for each store. Mixed currencies are displayed separately and never added into one misleading total.

Checkout locks buyer/inventory records, checks product and seller availability, validates seller-owned payment methods, and creates a separate order for every store. Oscar creates the underlying baskets, orders and stock reservations. Tenant models provide store boundaries, workflow fields and public projections. Cancellation releases allocations, dispatch consumes them, and confirmed returned goods can be restocked. Receipt records and order statements are printable.

The custom seller workspace controls products, orders, delivery settings, payment methods, verification submissions, customer enquiries and return/refund records. New shops require administrator activation. Oscar's own interface is platform-staff-only at /engine/dashboard/. Django Unfold technical administration is at /admin/.

## Abuse protection and stock holds

- Login locks for 15 minutes after 10 failures per username or 50 per client address (campus networks share addresses). Signup, password reset (also 3 emails per address per hour, without revealing whether the account exists), checkout, enquiries, reviews, listing reports, add-to-bag and search suggestions are rate limited. Limits use the Django cache: set REDIS_URL in production so all workers share counters, and set TRUSTED_PROXY_COUNT to the number of reverse proxies in front of Django so the real client address is used.
- Unpaid online/manual-payment orders are cancelled after UNPAID_ORDER_HOLD_HOURS (48) and their stock released, unless the buyer has submitted a payment reference for the seller to verify. Cash on Delivery orders are never auto-cancelled. The notification worker runs this every five minutes; `python manage.py expire_unpaid_orders` runs it once.
- A buyer may hold at most 10 unpaid orders in total and 3 per seller. Sellers can cancel any unpaid, unprepared order from their dashboard with a reason shown to the customer.
- Product image links must use HTTPS. Set PRODUCT_IMAGE_HOSTS to restrict them to approved image hosts; existing non-HTTPS links are no longer displayed.
- Responses carry a Content-Security-Policy (no third-party scripts, plugins, framing or off-site form posts) and Permissions-Policy. HSTS defaults to one hour in production; raise SECURE_HSTS_SECONDS once HTTPS is stable. Errors are logged to the console and, with ADMINS set, emailed.
- After sign-in, store owners land in the seller centre, shop staff in their workspaces and buyers back in the mall.

## Display preferences

The header moon/sun button switches between light and dark mode throughout the storefront, buyer pages and merchant workspace. The first visit follows the device preference; a manual choice is stored in that browser, survives navigation/reloads and synchronises across tabs. The accessible toggle announces the available action. Theme selection does not change product imagery or the supplied logo.

## Reusable buyer addresses

Signed-in buyers manage their private address book at /account/addresses/ (also linked from My orders). Save Home, Work or Campus addresses, edit/delete them and choose a default. The first saved entry becomes the default; deleting it promotes another saved address. Checkout pre-fills the default, offers a saved-address picker and lets customers save a new complete address after successful checkout. Selected addresses also work without JavaScript via the Use address button. Addresses are scoped to the buyer, deduplicated and never shared with other accounts. Existing order snapshots stay unchanged when an address is edited/deleted. WhatsApp consent is not stored in the address book or carried forward to future orders.

## Ghana delivery and addresses

Ghana is the default delivery country, with all 16 regions and a starter catalogue of towns for each region. Town suggestions are not an exhaustive gazetteer: customers can type any town or village. Structured recipient, phone, country, region, city, street, landmark, optional GhanaPost GPS/postcode and delivery notes are validated and snapshotted on each order. Collection-only baskets require contact details but not a home street address.

The Use my location button requests browser permission, then calls BigDataCloud directly from that device to suggest country, region, city and locality. The customer reviews these and enters the exact street and GhanaPost address. Coordinates are not stored or sent to the mall server by this lookup. It is not a GhanaPost GPS lookup. HTTPS is required outside localhost; permission refusal, unsupported countries and provider failure preserve manual entry. GEO_LOOKUP_URL in settings controls the browser endpoint; set it empty to disable. The default free endpoint must only receive the current device coordinates obtained through the browser, never server-side or bulk requests. See the BigDataCloud references in DELIVERY_AND_MESSAGING.md.

Sellers set their default delivery fee, optional regional overrides, collection availability/address and policies at /seller/settings/. Regional rate lines use exact names, for example Greater Accra=20.00. Checkout recomputes the fee from seller settings; browser totals cannot override it. Collection has no delivery fee. These are merchant-defined charges, not carrier quotes.

## Cash on Delivery by default

Every existing and new seller receives an always-active Cash on Delivery option, selected by default at checkout. Other seller payment methods remain available. COD orders start Confirmed without a receipt: Confirmed â†’ Preparing â†’ Dispatched (or ready for collection) â†’ cash actually collected â†’ Delivered. Only the seller/finance-authorised action records cash, using a unique receipt reference. Cash confirmation preserves the delivery stage. Delivery completion requires a receipt and triggers commission billing; no commission invoice is created for uncollected cash. An unpaid, unprepared COD order can be cancelled, and returned unpaid goods can be restored through the return workflow without inventing a refund.

## Tracking and order notifications

Customers use /orders/ â†’ Track order to see progress, order history, destination and seller-reported parcel locations. Sellers publish location, optional coordinates and customer-facing notes from the tracking page. The map link uses the reported coordinates. This is not live courier GPS; no ETA or location is fabricated. The authenticated tracking page refreshes every 30 seconds and enforces buyer/store permissions.

Order placement, payment, preparation, dispatch/collection, delivery, cancellation and return events create in-app notifications and durable email/SMS/WhatsApp outbox entries when each channel is available. Email uses global Django EMAIL_* and DEFAULT_FROM_EMAIL settings. Local DEBUG defaults to console previews; production defaults to Django SMTP. Seller new-order email alerts use the owner's account email.

Each seller configures Arkesel V2 credentials and approved sender ID at /seller/sms/, and their Meta WhatsApp Cloud API connection at /seller/whatsapp/. Keys/tokens/app secrets use the platform encryption key and are never displayed again. Sellers see message outcomes at /seller/messages/.

WhatsApp customers explicitly opt in at checkout. Automated purchase and delivery updates use approved utility templates, with three positional body parameters: order number, update and full tracking URL. Seller new-order alerts use a separate approved template and an opted-in recipient number. Signed, tenant-bound webhooks record inbound customer messages, STOP/START and delivery reports. Free-form seller replies require a verified customer message within 24 hours; queued replies are checked again before sending. A WhatsApp Business mobile app alone is not a Cloud API connection.

The worker drains the committed outbox:

```powershell
python manage.py dispatch_notifications --watch
```

start.ps1 starts/stops a hidden worker with the local web server. Compose includes a notifications service. Without a worker, messages remain queued. Provider acceptance is not confirmed delivery; WhatsApp delivered/read states come from verified webhooks. Ambiguous network outcomes are held for provider review rather than automatically resent. SMTP/Arkesel/Meta accounts, credits, approved senders/templates and public HTTPS webhook configuration must be supplied before real delivery. See DELIVERY_AND_MESSAGING.md for setup and recovery.

## Mall Pay (platform-managed online payments)

Mall Pay is the default way for sellers to accept card and mobile-money payments. The marketplace's own Paystack account (PLATFORM_PAYSTACK_SECRET) runs checkout; each seller enters their settlement bank or mobile-money number at /seller/mall-pay/, which creates a Paystack subaccount. Every payment is split by Paystack: the seller's subaccount receives the sale (and bears Paystack's fees), and the marketplace commission is deducted at source as a flat transaction charge. Commission on Mall Pay sales is recorded as Collected, so no commission bill is raised on delivery. If a Mall Pay order is refunded, the commission invoice becomes Credit due and platform superusers are notified to refund the buyer in Paystack and return the commission.

Configure the marketplace webhook as https://<your domain>/webhooks/paystack/platform/. PLATFORM_PAYSTACK_CURRENCIES lists the currencies your Paystack account settles (default GHS). Each payment attempt remembers which account it was started on, so switching between Mall Pay and a seller-owned account never breaks verification of payments already in progress.

### When sellers may use their own Paystack account

A seller-owned account means the marketplace can no longer deduct commission at source, so /seller/gateway/ unlocks only after a track record (all configurable in settings or environment):

- business verified by the marketplace
- 90 days since the store opened (past the three commission-free months)
- 25 delivered orders
- refunds at most 10% of completed orders
- no commission invoice overdue by more than 30 days

The page shows each requirement and the seller's progress. Platform staff can approve a store early by ticking Shop.own_gateway_approved in /admin/. Seller-owned connections saved before this rule are grandfathered.

## Independent seller payments

Sellers can publish their own mobile-money, bank-transfer or collection instructions. Buyer-submitted references do not confirm payment. A merchant must verify actual receipt before confirming a manual payment.

The Paystack adapter supports Ghana/GHS and Nigeria/NGN seller accounts. Configure a persistent GATEWAY_ENCRYPTION_KEY and an HTTPS PUBLIC_BASE_URL, then sellers save their own test/live secret in /seller/gateway/. Secrets are encrypted using Fernet and never rendered back into HTML. Configure each connection's webhook URL in that seller's Paystack account.

Hosted checkout initialization, API verification and signed webhooks are implemented. A successful payment must match the exact seller connection, reference, minor-unit amount and currency. Duplicate callbacks/webhooks do not create another receipt. Payments arriving after cancellation are held for reconciliation. Tests use mocked provider responses; no real seller account or live payment was supplied or processed.

Refund decisions record a refund completed through the seller's payment provider. Recording a reference here does not send funds. Automated provider refunds, dispute handling and automated settlement reconciliation are not implemented. Commission is collected automatically only for Mall Pay sales; seller-owned and manual/COD sales still raise commission invoices.

## Finance and teams

- Three calendar months commission-free from store creation; 3% thereafter, configurable through effective-dated CommissionPolicy records. No historical subscription/setup fees are automatically imposed.
- Delivery creates a commission invoice and balanced journal entries. Verified receipts, operating expenses and confirmed refunds also produce balanced entries.
- Merchant finance overview, expense ledger, CSV export, commission records, audit events and in-app notifications.
- Owner-managed fixed staff roles: manager, finance, support and catalogue assistant. Active membership and finance access are checked on the server for every protected area; revoked staff lose access immediately. Some staff workspaces provide read access while owner-only screens perform catalogue edits and fulfilment.
- Account registration/login and Django password-reset flow. Production SMTP must be configured; the development email backend writes to the console.

CentipidBilling was used only as a public reference for finance summaries, payment review, expenses, exports, dashboard organization and permission separation. Its proprietary source/data models were not available or reused. References: https://centipidbilling.com/ghana, https://centipidbilling.com/features and official documentation linked in STATUS.md.

## Deployment

Docker Compose provides PostgreSQL, Redis, Django/Gunicorn, a notification outbox worker and a Celery worker. Copy .env.example to .env and set unique secrets, DB_PASSWORD, GATEWAY_ENCRYPTION_KEY, PUBLIC_BASE_URL, ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS. Gateway encryption keys must remain stable and be backed up securely.

Build the image, run docker compose run --rm web python manage.py migrate, create an administrator, then start the services. Static assets are collected into the image during the build. The published web port binds to 127.0.0.1:8000; use an HTTPS reverse proxy. Set TRUST_PROXY_HTTPS=1 only when the trusted proxy overwrites X-Forwarded-Proto. DEBUG must be 0 in production. PostgreSQL is required for concurrent inventory row locking; SQLite is for local development.

Celery/Redis infrastructure is configured; no automatic payment collection, subscriptions or recurring billing jobs are enabled. Docker/PostgreSQL execution and public deployment have not been verified in this environment.

## Tests

```powershell
$env:DEBUG='1'
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test mall
python -m unittest discover -p 'test_*.py'
```

See VALIDATION.md for actual results. STATUS.md records the remaining production requirements. This is a tested local application, not a claim that all compliance, accounting, payment-provider and production operations are complete.

## Canonical Django Oscar commerce

Addresses, catalogue, inventory, baskets, orders, reviews, wishlists and notifications now use native Oscar models and workflows. See [OSCAR_ARCHITECTURE.md](OSCAR_ARCHITECTURE.md) for the model map, extension boundaries and required backup guidance before migrating an existing installation. Run python manage.py audit_oscar after migration.

Shared typography uses a 16px body, 17–18px product titles and 18–19px card prices. Supporting text has a 14px minimum, with 16px form fields and responsive card spacing.
