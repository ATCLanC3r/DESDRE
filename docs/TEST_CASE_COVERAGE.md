# Official Test-Case Coverage

This map is based on the supplied `Test Cases.pdf`. “Implemented” means the relevant model, view, template, or API path exists in this repository. The group must rehearse each test manually and record pass/fail evidence before submission.

| ID | Requirement | Implementation evidence | Status |
|---|---|---|---|
| TC-001 | Producer registration | `/p/producer/register/`, producer form/profile and farm address | Implemented |
| TC-002 | Customer registration | `/c/customer/register/`, role-aware customer form/profile | Implemented |
| TC-003 | Producer lists products | `/p/producer/products/add/`, `ProductForm`, `POST /api/products/` | Implemented |
| TC-004 | Browse by category | `/pt/products/`, `ProductCategory`, API category filter | Implemented |
| TC-005 | Product search | Product list search and `GET /api/products/?search=` | Implemented |
| TC-006 | Shopping cart | `Cart`, `CartItem`, add/update/remove cart views | Implemented |
| TC-007 | Single-vendor checkout | `/orders/checkout/`, order/payment models | Implemented |
| TC-008 | Multi-vendor checkout | Cart grouping and `OrderProducer` supplier splits | Implemented |
| TC-009 | Producer incoming orders | `/p/producer/orders/`, scoped producer-order API | Implemented |
| TC-010 | Update order status | Producer status update view and controlled status choices | Implemented |
| TC-011 | Inventory management | Product edit, atomic stock deduction, availability handling | Implemented |
| TC-012 | Weekly settlements | `/payments/settlements/history`, CSV/PDF exports, Celery tasks | Implemented |
| TC-013 | Food miles | Geocoded addresses and Haversine distance calculation | Implemented |
| TC-014 | Organic filter | `is_organic` field and catalogue/API filters | Implemented |
| TC-015 | Allergen warnings | Allergen models, product warnings, product detail display | Implemented |
| TC-016 | Seasonal availability | Start/end months, wrap-around season logic, display | Implemented |
| TC-017 | Community bulk orders | Community profile, special instructions, bulk flag | Implemented |
| TC-018 | Restaurant recurring orders | Recurring templates, instances, pause/resume/cancel/edit | Implemented |
| TC-019 | Surplus discounts | 10-50% validation, expiry, discounted cart pricing, analytics | Implemented |
| TC-020 | Recipes and farm stories | Producer content dashboard and customer-facing pages | Implemented |
| TC-021 | Order history and reorder | `/orders/order-history/`, reorder and receipt actions | Implemented |
| TC-022 | Secure authentication | Django hashing/validators, role checks, audit log, login limiting | Implemented |
| TC-023 | Low-stock notifications | Threshold, atomic deduction, producer notification | Implemented |
| TC-024 | Ratings and reviews | Verified-purchase review flow and producer responses | Implemented |
| TC-025 | 5% commission reporting | 5/95 split, settlements, admin reporting and exports | Implemented |

## Automated verification

Run:

```bash
docker compose run --rm -e RUN_MIGRATIONS=false -e SEED_DEMO_DATA=false -e USE_SQLITE=true -e USE_REDIS_CACHE=false web python manage.py test
```

The current automated suite verifies 17 focused behaviours. The official 25 test cases remain demonstration scenarios and should each be rehearsed with screenshots or a screen recording where permitted.

