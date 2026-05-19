# X9 Statistics Metric Contract

All dashboard numbers are split by domain. Do not add numbers across domains.

## business

Business metrics describe processed creator records, BD history aggregates, and
outreach state. They must not include raw extension observations.

- `total_creators`: unique creators from processed business tables plus BD
  history creator counts.
- `today_new_creators`: unique processed creators first seen today.
- `contacted`: processed creators whose current stage has reached contacted or later.
- `progressed`: business creators that reached confirmed or later, including
  BD history confirmed counts.
- `bd_history_*`: BD aggregate creator counts. They are part of business totals
  and are also exposed separately for attribution.

Primary endpoint: `/api/local/dashboard/department-summary`.
Primary pages: `/portal/business`, `/portal/dashboard`.

## collection_raw

Collection metrics describe plugin/import uploads before business normalization.
They must not be used as business totals.

- `sources.*.total`: raw observation rows by acquisition source.
- `sources.*.today`: raw observation rows collected today.
- `sources.tiktok_shop.funnel`: raw Shop list/detail observation counts.

Primary endpoint: `/api/local/collector/source-stats`.
Primary pages: `/portal/collection`, `/portal/collect-shop`,
`/portal/collect-leads`, `/portal/collect-import`.

## system_health

System health metrics describe service status, database connectivity, extension
sessions, and diagnostic row counts. They are operational only.

Primary endpoints: `/api/local/app/status`, `/api/local/db/status`,
`/api/local/db/stats`, `/api/local/extension/status`.

## recommendation

Recommendation metrics describe the recommendation list currently visible after
filters. They are UI-local list metrics unless explicitly returned by the
recommendation API.

Primary page: `/portal/recommendations`.
