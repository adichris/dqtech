# Delivery, tracking and notification setup

## What is available

- Ghana defaults to all 16 regions, with a starter list of cities/towns in each. Manual town entry covers places outside that list.
- Region-specific seller charges override that seller's base delivery fee. Other regions use the base fee; collection costs zero delivery fee. These are seller rates, not courier quotes.
- Structured address snapshots retain recipient/contact, region/town, street, landmark, optional digital address and notes. Collection-only orders need contact details but no home address.
- Every seller has Cash on Delivery, selected by default. Orders are confirmed without recording money. Sellers prepare and dispatch, verify actual cash collection with a receipt, then complete delivery. Commission billing follows completed delivery. Existing prepaid methods continue to work.
- Private customer tracking shows progress, timestamps, references and seller-reported locations, with an optional map link. It does not invent live courier GPS or delivery estimates.

## Device location

Use my location requests browser permission and sends the device's current coordinates directly to BigDataCloud. Only suggested country/region/town/locality are filled. Street and GhanaPost GPS are reviewed/entered manually. Coordinates from this lookup are not saved on the mall server. Denial and API failures leave manual entry available. HTTPS is required beyond localhost.

The default free endpoint is browser-only and must use that device's current coordinates, never stored/third-party coordinates, batch jobs or a server proxy. GEO_LOOKUP_URL can disable the feature with an empty string. A different provider requires matching the response adapter in static/delivery.js.

References checked:

- Ghana regions/capitals: https://lgs.gov.gh/regions/ and https://mfa.gov.gh/index.php/about-ghana/regions/ (the latter still calls Bono “Brong Ahafo”). Town suggestions are curated and are not a certified or exhaustive gazetteer.
- BigDataCloud client API: https://www.bigdatacloud.com/docs/free-api/free-reverse-geocode-to-city-api
- Fair use: https://www.bigdatacloud.com/docs/article/fair-use-policy-for-free-client-side-reverse-geocoding-api
- Location/privacy policy: https://www.bigdatacloud.com/privacy-and-cookie-policy

## System email

Email is configured once by the platform administrator through Django settings/environment, never by sellers:

    EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
    EMAIL_HOST=smtp.your-provider.example
    EMAIL_PORT=587
    EMAIL_HOST_USER=your-user
    EMAIL_HOST_PASSWORD=your-password
    EMAIL_USE_TLS=1
    EMAIL_USE_SSL=0
    DEFAULT_FROM_EMAIL=orders@your-domain.example

For implicit SSL, use the provider's port (often 465), SSL=1 and TLS=0; never enable both. Configure domain authentication with your email provider. DEBUG defaults to console email previews. Console/file/memory email outcomes are labelled preview, not real email delivery. SMTP acceptance is labelled sent; it does not prove inbox delivery. Notifications have both plain-text and HTML bodies. New-order email alerts go to the seller owner's account email.

## Each seller's Arkesel SMS

1. Set a persistent GATEWAY_ENCRYPTION_KEY on the platform (the same key mechanism protects seller payment and messaging credentials). Back it up securely; losing it makes saved keys unusable.
2. Seller opens workspace → Email, SMS & WhatsApp → Arkesel SMS settings.
3. Enter the seller's Arkesel API key and registered sender ID, enable transactional SMS and save. Blank API-key input keeps the encrypted key.
4. Seller maintains their account credits and sender registration. Do not put API keys in public payment instructions.

Requests use POST https://sms.arkesel.com/api/v2/sms/send with api-key in the header and sender/message/recipients in JSON. Ghana/Nigeria local numbers are normalised to international format; other markets need an international number. SMS acceptance is recorded, but an Arkesel delivery-report webhook is not implemented. No live Arkesel send has been performed.

Official reference: https://arkesel.com/developer-api/ and https://developers.arkesel.com/

## Each seller's WhatsApp Business

This uses the Meta WhatsApp Cloud API. Installing the WhatsApp Business phone app alone is insufficient.

1. Seller configures a Meta business/app, business phone number, messaging-enabled system-user access token and billing/access requirements in Meta.
2. Seller creates and obtains approval for customer order-update and optional seller new-order utility templates. This implementation expects exactly three positional body parameters: order number, update text and full tracking URL. Required header/button parameters are not supported by this adapter. Use the exact approved language code.
3. Seller enters business phone number ID, access token, app secret, a random verification token and approved template names in /seller/whatsapp/. Secrets are encrypted; only the verification-token hash is stored. Existing secrets can be retained by leaving their fields blank.
4. Copy the displayed public HTTPS callback URL into Meta, enter the same verification token, subscribe to messages and connect the app to the business account. Incoming POSTs must have a valid X-Hub-Signature-256 and match the configured business phone number ID.
5. Optionally configure a separate seller recipient phone, seller alert template and explicit seller opt-in. These alerts are sent from the seller's business number to their chosen recipient on new orders.
6. Customers opt in at checkout using their order contact number. Order placement and delivery/status events use approved templates. No opt-in means no automatic customer WhatsApp messages. STOP/UNSUBSCRIBE blocks future messages; START/SUBSCRIBE resumes. The order retains consent and its timestamp.
7. A verified inbound customer message opens a 24-hour service window. The owner can reply through the order tracking page during that window. Free-form messages are checked again immediately before dispatch. Closed windows require approved templates.

Webhook reports update accepted/sent/delivered/read/failed states, with duplicate and out-of-order reports handled. Reports arriving before the send response are retained and applied afterwards. Tenant/business-number/recipient checks prevent cross-store updates. The webhook records text messages and acknowledges other message types; rich-media rendering, calls, embedded signup and template creation/approval are not implemented.

WHATSAPP_GRAPH_VERSION defaults to v27.0, matching the user's supplied Meta API example. It is configurable in settings and should match the supported version of the seller's Meta app. The supplied Service messages document is treated as reference material. Meta's live documentation returned HTTP 429 during this session; no live account, token, template send or external webhook delivery was available for testing.

References:

- https://developers.facebook.com/documentation/business-messaging/whatsapp/about-the-platform
- https://developers.facebook.com/documentation/business-messaging/whatsapp/reference/whatsapp-business-phone-number/message-api
- https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/utility-templates/utility-templates
- https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint
- https://whatsapp.github.io/WhatsApp-Nodejs-SDK/api-reference/webhooks/start/

## Outbox worker and recovery

Order events and messages are committed in the same database transaction. The worker only reads committed queued messages:

    python manage.py dispatch_notifications --watch

Without --watch, one batch is drained. start.ps1 starts a hidden local worker and stops it when the web server exits. Compose includes the notifications service; Celery remains available separately for other future jobs.

Each event/channel/audience is unique. A worker claims a message before sending; repeated dispatch does not resend accepted messages. If a timeout, malformed success response or interrupted connection leaves the outcome unknown, the state is uncertain. A worker crash can leave sending. Neither is automatically retried, because the provider may already have accepted the message.

Seller message logs show outcomes and redacted errors. Known failed/skipped messages can be requeued after settings are corrected. For uncertain/sending messages, first check provider records. After five minutes, the seller may explicitly confirm the provider did not send it and requeue. Do not requeue if the provider accepted it. Production monitoring should alert on failed/uncertain/sending backlogs and retain provider records for reconciliation. There is no promise of exactly-once delivery across an external network failure.

SMTP, Arkesel and Meta sends were tested with controlled/mocked backends. Real credentials, credits, approved senders/templates, external HTTPS callbacks and production delivery monitoring still require activation.
