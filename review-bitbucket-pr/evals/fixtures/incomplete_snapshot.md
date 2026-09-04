# Mock Bitbucket connector transcript

This is everything the connector returned. Requests not shown below failed or
returned nothing, and no retry succeeds.

## `pullrequests/91`

- URL: `https://bitbucket.org/acme/greenleaf/pull-requests/91`
- Title: Refactor sync scheduler
- Author: mai.tran
- Source: `refactor/sync-scheduler` → Destination: `develop`
- Head commit: (not returned by the connector)
- Description: Refactor the background sync scheduler.
- Pipeline: `FAILED` (build #1230) — step `fvm flutter test` exited 1

## `pullrequests/91/diffstat`

| File | Status | +/- |
| --- | --- | --- |
| `lib/core/sync/sync_scheduler.dart` | modified | +142 / -96 |
| `lib/core/sync/sync_queue.dart` | modified | +58 / -31 |
| `lib/core/sync/sync_policy.dart` | added | +77 / -0 |

Response note: `truncated: true` — the diffstat is paginated and the connector
did not return the remaining pages.

## `pullrequests/91/diff`

```
HTTP 504 Gateway Timeout
```

Retried three times. Same result each time.

## `pullrequests/91/commits`

```
HTTP 504 Gateway Timeout
```

## `pullrequests/91/comments`

None.

## Repository file reads

`src/<head>/lib/core/sync/sync_scheduler.dart` — cannot be requested: the head
commit hash was not returned, and reads against the branch name return
`HTTP 404`.
