# ServiceNow Enrichment

ServiceNow enrichment uses the Table API against a configured user table, usually `sys_user`.

Required settings:

- `enrichment.servicenow.enabled`
- `enrichment.servicenow.instance_url`
- `enrichment.servicenow.username`
- `enrichment.servicenow.password`
- `enrichment.servicenow.auth_type`: `basic` or `oauth_password`. Defaults to `basic`.

For OAuth password-grant authentication, also configure:

- `enrichment.servicenow.oauth_client_id`
- `enrichment.servicenow.oauth_client_secret`

The OAuth path uses `pysnow.OAuthClient` to generate an access token, then calls the same Table API endpoints with a bearer token. The basic path continues to use username/password HTTP auth.

The API user needs read access to the configured table and fields. For the default `sys_user` mapping, grant read access to `sys_id`, `user_name`, `email`, `name`, `first_name`, `last_name`, `title`, `department`, `company`, `phone`, `mobile_phone`, and `active`.

Mapping settings:

- `enrichment.servicenow.table`: defaults to `sys_user`.
- `enrichment.servicenow.user_query_field`: simplified setup field used to build `lookup_query_template`.
- `enrichment.servicenow.active_only`: simplified setup toggle that appends `active=true` when the configure API saves the lookup template.
- `enrichment.servicenow.fields`: comma-separated fields returned by the Table API.
- `enrichment.servicenow.lookup_query_template`: encoded query template for single-item lookups. Use `{value}` for the escaped actor identifier.
- `enrichment.servicenow.bulk_sync_query`: encoded query for scheduled sync/backfill. Defaults to `active=true`.

Bulk sync is bounded by `enrichment.servicenow.max_records` and `enrichment.servicenow.page_size`. The backend clamps page size to 1-1000 and max records to 1-50000, so a scheduled run cannot walk an unbounded table.

Recommended preview workflow:

1. Configure the instance URL and credentials with `enabled=false`.
2. Set `table`, `fields`, and `lookup_query_template` for a known test user.
3. Enable the provider and enrich one timeline internal actor.
4. Check provider status for cache and alias counts.
5. Enable daily bulk sync only after the lookup mapping returns the expected user fields.

Troubleshooting:

- `ServiceNow provider is not fully configured`: instance URL, username, password, or table is missing.
- `User not found`: the lookup query did not match the actor identifier. Check `lookup_query_template` and the timeline actor's `user_id`, `contact_email`, or `name`.
- Empty aliases after sync: ensure `fields` includes at least one of `email`, `user_name`, or `sys_id`.
- Sync stops early: the run reached `max_records`, or ServiceNow returned fewer rows than the requested page size.
