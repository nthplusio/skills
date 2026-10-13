# Pull request 2984 — Move hierarchy level tables into a shared LEVEL schema

> Synthetic fixture. The platform, tenants, numbers, and ticket IDs are
> invented. The shape of the change is typical of a multi-tenant analytics
> platform that stores each tenant's data in its own Snowflake database.

## Description

Every tenant database has one hierarchy per dimension, and each hierarchy
has its own level table:

- `DIMENSION.ACCOUNT_HIERARCHY_LEVEL`
- `DIMENSION.PRODUCT_HIERARCHY_LEVEL`
- `DIMENSION.REGION_HIERARCHY_LEVEL`

Each row is `(LEVEL_ID, HIERARCHY_ID, ORDINAL, NAME)`. The placement tables
(`DIMENSION.ACCOUNT_HIERARCHY` and so on) record which node sits at which
`ORDINAL`, not which `LEVEL_ID`. The grid views `DIMENSION.V_ACCOUNT_MAP`,
`V_PRODUCT_MAP`, and `V_REGION_MAP` expose positional columns `LEVEL1` to
`LEVEL4` by joining on `ORDINAL`.

Two problems follow. When a tenant renumbers levels, placements silently
point at a different level. And the grid shows generic headers (`Level4`)
while the hierarchy editor shows the authored name (`Cost centre`), because
the views never read `NAME`.

This PR:

1. Creates schema `LEVEL` with one table `LEVEL.HIERARCHY_LEVEL`
   `(LEVEL_ID, DIMENSION, HIERARCHY_ID, ORDINAL, NAME, DISPLAY_NAME)`.
2. Copies rows from the three per-dimension level tables into it.
3. Adds a `LEVEL_ID` column to each placement table, backfills it by joining
   on `(HIERARCHY_ID, ORDINAL)`, then sets it `NOT NULL`.
4. Replaces the three old level tables with views over
   `LEVEL.HIERARCHY_LEVEL`, kept for two releases so existing readers keep
   working.
5. Rewrites the `V_*_MAP` views to join on `LEVEL_ID`. The `LEVEL1` to
   `LEVEL4` columns keep their names and values. Four new columns
   `LEVEL1_NAME` to `LEVEL4_NAME` carry the authored names.

## Files

```
db/migrations/0417_create_level_schema.sql        new
db/migrations/0418_backfill_placement_level_id.sql new
db/migrations/0419_level_tables_to_views.sql      new
db/views/v_account_map.sql                        changed
db/views/v_product_map.sql                        changed
db/views/v_region_map.sql                         changed
api/readers/dimension_map.py                      changed  (reads LEVELn_NAME for headers)
api/tests/test_dimension_map.py                   changed
docs/data/hierarchy-levels.md                     new
```

## How it runs

The deploy job applies `db/migrations/*.sql` to every tenant database in
order, one tenant at a time. The backfill in 0418 runs in batches of 50,000
rows. On the larger of the two cloned tenants, which is also the largest of
the 212 tenants in production, the three migrations took 4 minutes 10
seconds. Each migration is idempotent: rerunning it on a migrated tenant
changes nothing.

## Consumers of the changed objects

| Consumer | Reads | Effect |
| --- | --- | --- |
| Grid readers (`api/readers/dimension_map.py`) | `V_*_MAP` | Headers switch to authored names; values unchanged |
| CSV and XLSX export | `V_*_MAP` | Four extra columns at the end; existing columns byte-identical |
| Reporting marts (`REPORTING.*`) | `DIMENSION.*_HIERARCHY_LEVEL` joined on `ORDINAL` | Keep working through the compatibility views until release N+2; ticket DATA-412 moves them to `LEVEL_ID` |
| Nightly refresh job (`dbt` project `marts`) | the same level tables | Same as reporting marts |
| Hierarchy editor | `LEVEL.HIERARCHY_LEVEL` after this PR | Unchanged behaviour |

## Risk found during a read-only scan

A read-only scan of all 212 production tenants found three with two rows
that share the same `ORDINAL` inside one hierarchy, so
the backfill join is ambiguous for them. Migration 0418 stops with an error
that lists the tenant and the duplicate rows, and leaves the tenant
unmigrated. Those three need a manual fix before the deploy; the fix is a
one-row update per tenant and is already written up in the ticket.

## Rollback

Until release N+2 the old tables are reconstructable: drop the compatibility
views, recreate the three tables from `LEVEL.HIERARCHY_LEVEL`, make
`LEVEL_ID` nullable again, and restore the previous `V_*_MAP` definitions
from git. Rollback script: `db/rollback/0417_0419.sql`. It takes about one
minute per tenant.

## Verification

- Ran all three migrations against a disposable clone of two tenants, one
  large and one small. Row counts in the new table equal the sum of the
  three old tables.
- Restored twelve saved grid presets on the clone; every preset opened with
  the same rows and the same column order.
- Exported the same view before and after; the files are identical except
  for the four appended columns.
- Did not test the reporting marts beyond confirming they still query
  without error through the compatibility views.

## Review discussion

**Reviewer (data platform):** Will the finance reports break when the
compatibility views go away?

**Author:** Not in this release. They join on `ORDINAL` through the views,
which still exist. DATA-412 switches them to `LEVEL_ID` before N+2.

**Reviewer:** The three ambiguous tenants. Does the deploy stop for every
tenant or only those three?

**Author:** Only those three. Each tenant migrates on its own; a failure
leaves that tenant on the old shape and moves on. The deploy summary lists
the failures.

**Reviewer (API):** Approved. Please add the header change to the release
notes; users will notice it.
