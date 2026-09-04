# Mock Bitbucket connector transcript

Everything the connector returns for this pull request is below. Treat it as the
complete, authoritative snapshot: no other data is retrievable. Repository search
results shown here are the complete match set for the queries listed.

## `pullrequests/57`

- URL: `https://bitbucket.org/acme/orders-api/pull-requests/57`
- Title: Add PARTIALLY_REFUNDED order status
- Author: hoang.le
- Source: `feature/partial-refund` → Destination: `main`
- Head commit: `d41f57`
- Description: Support partial refunds. Adds a new order status and emits it from the refund handler.
- Acceptance criteria: A partially refunded order shows a distinct status in the customer portal and in the ops dashboard.
- Pipeline: `SUCCESSFUL` (build #3390) — `npm run build`, `npm test`

## `pullrequests/57/diffstat`

| File | Status | +/- |
| --- | --- | --- |
| `src/domain/order-status.ts` | modified | +1 / -0 |
| `src/handlers/refund-handler.ts` | modified | +6 / -1 |

## `pullrequests/57/diff`

```diff
diff --git a/src/domain/order-status.ts b/src/domain/order-status.ts
--- a/src/domain/order-status.ts
+++ b/src/domain/order-status.ts
@@ -1,6 +1,7 @@
 export const ORDER_STATUS = {
   PENDING: 'PENDING',
   PAID: 'PAID',
   REFUNDED: 'REFUNDED',
+  PARTIALLY_REFUNDED: 'PARTIALLY_REFUNDED',
   CANCELLED: 'CANCELLED',
 } as const;

diff --git a/src/handlers/refund-handler.ts b/src/handlers/refund-handler.ts
--- a/src/handlers/refund-handler.ts
+++ b/src/handlers/refund-handler.ts
@@ -14,7 +14,12 @@ export async function handleRefund(req: RefundRequest): Promise<void> {
-  await orders.setStatus(req.orderId, ORDER_STATUS.REFUNDED);
+  const order = await orders.get(req.orderId);
+  const isPartial = req.amount < order.total;
+  await orders.setStatus(
+    req.orderId,
+    isPartial ? ORDER_STATUS.PARTIALLY_REFUNDED : ORDER_STATUS.REFUNDED,
+  );
+  await analytics.track('refund_completed', { orderId: req.orderId });
 }
```

Added-line numbers on the new side:

- `src/domain/order-status.ts` line 5: `PARTIALLY_REFUNDED: 'PARTIALLY_REFUNDED',`
- `src/handlers/refund-handler.ts` lines 15-20: the block above

## `pullrequests/57/comments`

None.

## `src/d41f57/package.json` (excerpt)

```json
{
  "dependencies": { "express": "^4.19.2", "i18next": "^23.11.5" },
  "devDependencies": { "typescript": "^5.4.5", "jest": "^29.7.0", "eslint": "^8.57.0" }
}
```

## `src/d41f57/src/domain/order-status.ts` (full file, post-change)

```ts
export const ORDER_STATUS = {
  PENDING: 'PENDING',
  PAID: 'PAID',
  REFUNDED: 'REFUNDED',
  PARTIALLY_REFUNDED: 'PARTIALLY_REFUNDED',
  CANCELLED: 'CANCELLED',
} as const;

export type OrderStatus = (typeof ORDER_STATUS)[keyof typeof ORDER_STATUS];
```

## Repository search: `ORDER_STATUS` (complete match set)

- `src/domain/order-status.ts` — definition
- `src/handlers/refund-handler.ts:19` — changed by this PR
- `src/handlers/checkout-handler.ts:44` — `orders.setStatus(id, ORDER_STATUS.PAID)`
- `src/portal/status-label.ts:6` — see below
- `src/ops/dashboard-filters.ts:11` — see below

## `src/d41f57/src/portal/status-label.ts` (full file, unchanged by this PR)

```ts
import { ORDER_STATUS, type OrderStatus } from '../domain/order-status';
import { t } from '../i18n';

export function statusLabel(status: OrderStatus): string {
  switch (status) {
    case ORDER_STATUS.PENDING:
      return t('order.status.pending');
    case ORDER_STATUS.PAID:
      return t('order.status.paid');
    case ORDER_STATUS.REFUNDED:
      return t('order.status.refunded');
    case ORDER_STATUS.CANCELLED:
      return t('order.status.cancelled');
    default:
      return 'Unknown status';
  }
}
```

## `src/d41f57/src/ops/dashboard-filters.ts` (full file, unchanged by this PR)

```ts
import { ORDER_STATUS } from '../domain/order-status';

export const DASHBOARD_FILTERS = [
  { key: ORDER_STATUS.PENDING, order: 1 },
  { key: ORDER_STATUS.PAID, order: 2 },
  { key: ORDER_STATUS.REFUNDED, order: 3 },
  { key: ORDER_STATUS.CANCELLED, order: 4 },
];
```

## `src/d41f57/src/i18n/en.json` (excerpt)

```json
{
  "order.status.pending": "Pending",
  "order.status.paid": "Paid",
  "order.status.refunded": "Refunded",
  "order.status.cancelled": "Cancelled"
}
```

## Repository search: `analytics.track(` (complete match set)

- `src/handlers/checkout-handler.ts:51` — `analytics.track('checkout_completed', { orderId, total })`
- `src/handlers/refund-handler.ts:20` — added by this PR

## `src/d41f57/eslint.config.js` (excerpt)

```js
rules: {
  'complexity': ['warn', 12],
  '@typescript-eslint/switch-exhaustiveness-check': 'off',
}
```
