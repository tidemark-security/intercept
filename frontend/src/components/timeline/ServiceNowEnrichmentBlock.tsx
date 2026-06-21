import React from 'react';

import { Badge } from '@/components/data-display/Badge';
import { toSafeHref } from '@/utils/safeUrl';
import type { TimelineItem } from '@/types/timeline';
import {
  asRecord,
  EnrichmentBlockSection,
  EnrichmentInfoRow,
  getString,
} from './EnrichmentBlockShared';

import {
  AlertTriangle,
  Binary,
  BriefcaseBusiness,
  Building2,
  Database,
  ExternalLink,
  Fingerprint,
  HardDrive,
  IdCard,
  Mail,
  MapPin,
  Network,
  Phone,
  ServerCog,
  UserRound,
  Wrench,
} from 'lucide-react';

type ServiceNowMappedField = {
  field?: string;
  value?: unknown;
  mapped?: boolean;
};

type ServiceNowPayload = {
  status?: string;
  source_table?: string;
  record_id?: string;
  record_link?: string;
  matched_identifier?: unknown;
  lookup_identifiers?: unknown;
  error?: string;
  sys_id?: string;
  user_name?: string;
  email?: string;
  display_name?: string;
  first_name?: string;
  last_name?: string;
  job_title?: string;
  department?: string;
  company?: string;
  phone?: string;
  mobile_phone?: string;
  active?: string;
  mapped_fields?: Record<string, ServiceNowMappedField>;
  name?: string;
  fqdn?: string;
  ip_address?: string;
  asset_tag?: string;
  ci_class?: string;
  ci_type?: string;
  classification?: string;
  criticality?: string;
  install_status?: string;
  privilege_fields?: Record<string, unknown>;
};

function getServiceNowPayload(item: TimelineItem): ServiceNowPayload | null {
  const enrichments = asRecord((item as TimelineItem & { enrichments?: unknown }).enrichments);
  const payload = asRecord(enrichments?.servicenow);
  if (!payload) {
    return null;
  }
  return payload as ServiceNowPayload;
}

function displayValue(value: unknown): string | undefined {
  if (typeof value === 'string') {
    return value.trim() || undefined;
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return undefined;
}

function formatIdentifier(value: unknown): string | undefined {
  const direct = displayValue(value);
  if (direct) {
    return direct;
  }

  const record = asRecord(value);
  if (record) {
    const source = displayValue(record.source);
    const field = displayValue(record.field);
    const identifier = displayValue(record.value);
    const prefix = [source, field].filter(Boolean).join(' / ');
    if (identifier) {
      return prefix ? `${prefix}: ${identifier}` : identifier;
    }
  }

  if (Array.isArray(value)) {
    return value
      .map(formatIdentifier)
      .filter(Boolean)
      .join(', ') || undefined;
  }

  return undefined;
}

function buildMappedFieldRows(payload: ServiceNowPayload) {
  const mappedRows = Object.entries(payload.mapped_fields || {})
    .map(([key, rawValue]) => {
      const value = asRecord(rawValue);
      const field = displayValue(value?.field) || key;
      const mappedValue = displayValue(value?.value);
      return field && mappedValue ? { key: `mapped-${key}`, label: field, value: mappedValue } : null;
    })
    .filter((row): row is { key: string; label: string; value: string } => Boolean(row));

  const privilegeRows = Object.entries(payload.privilege_fields || {})
    .map(([field, rawValue]) => {
      const value = displayValue(rawValue);
      return value ? { key: `privilege-${field}`, label: field, value } : null;
    })
    .filter((row): row is { key: string; label: string; value: string } => Boolean(row));

  return [...mappedRows, ...privilegeRows];
}

export function ServiceNowEnrichmentBlock({ item }: { item: TimelineItem }) {
  const payload = getServiceNowPayload(item);
  if (!payload) {
    return null;
  }

  const sourceTable = getString(payload.source_table);
  const recordId = getString(payload.record_id) || getString(payload.sys_id);
  const recordHref = toSafeHref(getString(payload.record_link));
  const matchedIdentifier = formatIdentifier(payload.matched_identifier);
  const lookupIdentifiers = formatIdentifier(payload.lookup_identifiers);
  const error = getString(payload.error);
  const displayName = getString(payload.display_name) || getString(payload.name);
  const username = getString(payload.user_name);
  const email = getString(payload.email);
  const jobTitle = getString(payload.job_title);
  const department = getString(payload.department);
  const company = getString(payload.company);
  const phone = getString(payload.phone);
  const mobilePhone = getString(payload.mobile_phone);
  const active = getString(payload.active);
  const fqdn = getString(payload.fqdn);
  const ipAddress = getString(payload.ip_address);
  const assetTag = getString(payload.asset_tag);
  const ciType = getString(payload.ci_type) || getString(payload.ci_class) || getString(payload.classification);
  const criticality = getString(payload.criticality);
  const installStatus = getString(payload.install_status);
  const mappedRows = buildMappedFieldRows(payload);

  const hasContent = Boolean(
    sourceTable ||
      recordId ||
      recordHref ||
      matchedIdentifier ||
      lookupIdentifiers ||
      error ||
      displayName ||
      username ||
      email ||
      jobTitle ||
      department ||
      company ||
      phone ||
      mobilePhone ||
      active ||
      fqdn ||
      ipAddress ||
      assetTag ||
      ciType ||
      criticality ||
      installStatus ||
      mappedRows.length > 0
  );

  if (!hasContent) {
    return null;
  }

  return (
    <EnrichmentBlockSection icon={<Database className="h-4 w-4" />} title="ServiceNow Enrichment">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {sourceTable && (
            <Badge variant="neutral" icon={<Database className="h-3.5 w-3.5" />}>
              {sourceTable}
            </Badge>
          )}
          {payload.status && <Badge variant="neutral">{payload.status}</Badge>}
          {recordHref && (
            <a
              className="inline-flex items-center gap-1 rounded-md border border-neutral-border bg-neutral-200 px-2 py-1 text-caption-bold font-caption-bold text-default-font transition-colors hover:border-brand-primary hover:text-brand-primary"
              href={recordHref}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Open record
            </a>
          )}
        </div>

        {error && (
          <div className="flex items-start gap-2 rounded-md border border-warning-600 bg-warning-primary-blush px-3 py-2 text-body font-body text-default-font">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning-600" />
            <span className="min-w-0 break-words">{error}</span>
          </div>
        )}

        <div className="grid gap-2 md:grid-cols-2">
          {recordId && (
            <EnrichmentInfoRow
              icon={<Fingerprint className="h-3.5 w-3.5" />}
              label="Record ID"
              value={recordId}
            />
          )}
          {matchedIdentifier && (
            <EnrichmentInfoRow
              icon={<IdCard className="h-3.5 w-3.5" />}
              label="Matched Identifier"
              value={matchedIdentifier}
            />
          )}
          {!matchedIdentifier && lookupIdentifiers && (
            <EnrichmentInfoRow
              icon={<IdCard className="h-3.5 w-3.5" />}
              label="Lookup Identifiers"
              value={lookupIdentifiers}
            />
          )}
          {displayName && (
            <EnrichmentInfoRow
              icon={<UserRound className="h-3.5 w-3.5" />}
              label="Name"
              value={displayName}
            />
          )}
          {username && (
            <EnrichmentInfoRow
              icon={<IdCard className="h-3.5 w-3.5" />}
              label="Username"
              value={username}
            />
          )}
          {email && (
            <EnrichmentInfoRow
              icon={<Mail className="h-3.5 w-3.5" />}
              label="Email"
              value={email}
            />
          )}
          {jobTitle && (
            <EnrichmentInfoRow
              icon={<BriefcaseBusiness className="h-3.5 w-3.5" />}
              label="Job Title"
              value={jobTitle}
            />
          )}
          {(company || department) && (
            <EnrichmentInfoRow
              icon={<Building2 className="h-3.5 w-3.5" />}
              label="Organization"
              value={company || department || ''}
              secondary={company && department ? department : undefined}
            />
          )}
          {phone && (
            <EnrichmentInfoRow
              icon={<Phone className="h-3.5 w-3.5" />}
              label="Phone"
              value={phone}
              secondary={mobilePhone}
            />
          )}
          {!phone && mobilePhone && (
            <EnrichmentInfoRow
              icon={<Phone className="h-3.5 w-3.5" />}
              label="Mobile"
              value={mobilePhone}
            />
          )}
          {active && (
            <EnrichmentInfoRow
              icon={<Binary className="h-3.5 w-3.5" />}
              label="Active"
              value={active}
            />
          )}
          {fqdn && (
            <EnrichmentInfoRow
              icon={<ServerCog className="h-3.5 w-3.5" />}
              label="FQDN"
              value={fqdn}
            />
          )}
          {ipAddress && (
            <EnrichmentInfoRow
              icon={<Network className="h-3.5 w-3.5" />}
              label="IP Address"
              value={ipAddress}
            />
          )}
          {assetTag && (
            <EnrichmentInfoRow
              icon={<HardDrive className="h-3.5 w-3.5" />}
              label="Asset Tag"
              value={assetTag}
            />
          )}
          {ciType && (
            <EnrichmentInfoRow
              icon={<ServerCog className="h-3.5 w-3.5" />}
              label="CI Type"
              value={ciType}
            />
          )}
          {criticality && (
            <EnrichmentInfoRow
              icon={<AlertTriangle className="h-3.5 w-3.5" />}
              label="Criticality"
              value={criticality}
            />
          )}
          {installStatus && (
            <EnrichmentInfoRow
              icon={<Wrench className="h-3.5 w-3.5" />}
              label="Install Status"
              value={installStatus}
            />
          )}
        </div>

        {mappedRows.length > 0 && (
          <div className="grid gap-2 md:grid-cols-2">
            {mappedRows.map((row) => (
              <EnrichmentInfoRow
                key={row.key}
                icon={<Binary className="h-3.5 w-3.5" />}
                label={row.label}
                value={row.value}
              />
            ))}
          </div>
        )}
      </div>
    </EnrichmentBlockSection>
  );
}

export default ServiceNowEnrichmentBlock;
