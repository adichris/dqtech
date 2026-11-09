# Oscar architecture and migration guide

Django Oscar 4.2.1 supplies the canonical commerce records. The merchant interface adapts these records while keeping tenant permissions in the mall application.

| Area | Authoritative implementation |
| --- | --- |
| Buyer addresses | Oscar address.UserAddress, extended with a label; native hash, defaults and usage counters |
| Countries and order addresses | Oscar Country and immutable order.ShippingAddress snapshots |
| Catalogue and inventory | Oscar Product, ProductClass, Category, ProductCategory and partner.StockRecord |
| Seller ownership and prices | Oscar Partner and a tenant/currency scoped purchase strategy |
| Shopping bag | Oscar Basket and Line, split by seller and currency |
| Checkout | Oscar OrderCreator, TotalCalculator, Order and Line |
| Fulfilment | Oscar status history, line allocations and shipping events |
| Confirmed money movements | Oscar payment Source, Transaction and PaymentEvent |
| Reviews and favourites | Oscar ProductReview, WishList and wishlist Line |
| Notifications and email | Oscar Notification, CommunicationEvent, Email and Dispatcher with global Django SMTP |

Tenant listing and order records retain their public identifiers and add marketplace policy metadata. They do not store duplicate product names, prices, stock, order totals, order status or order lines. Addresses, reviews, wishlists and in-app notifications use native models directly. The custom UI reads native records through adapters.

Custom models remain for shop onboarding, tenant staff roles, seller credentials, commissions, journal/expense records, receipt evidence, returns, geographic tracking details and durable SMS/WhatsApp delivery attempts. These represent marketplace policies or integrations beyond Oscar's core. Tracking events link to native communication history. Cash on Delivery remains available to every seller; only verified receipts create native payment transactions.

The commerce/address, commerce/partner and commerce/order packages follow Oscar application extension conventions. Address migrations include Oscar's upstream history and its license. Partner and order reuse upstream migration modules. Platform administrators use Oscar's dashboard; merchants use the tenant workspace.

## Existing installations

Back up the database before applying migrations. Mall migrations 0011–0014 migrate existing addresses, catalogue, orders, stock reservations, receipts, reviews, wishlists, notifications and tracking into native records before removing duplicated tables/columns. Migration 0015 links seller memberships to native partners. Data migrations 0011–0014 are forward-only: rollback requires restoring the pre-migration database backup and matching source. Do not fake these migrations.

Run python manage.py migrate, then python manage.py audit_oscar. The audit is read-only and checks native identities, required links, stock records, receipt sources and tracking history. A populated legacy SQLite migration probe passed. PostgreSQL migration execution still requires deployment testing.

Native placed-order totals are immutable snapshots. Seller edits to current catalogue prices do not rewrite historical orders. Native payment entries record confirmed external transactions; they do not themselves transfer or refund money. Tax configuration, live provider credentials and production infrastructure require deployment configuration and validation.
