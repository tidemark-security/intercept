import React from 'react';

import { Badge } from '@/components/data-display/Badge';
import {
  asRecord,
  EnrichmentBlockSection,
  EnrichmentInfoRow,
  getBoolean,
  getString,
} from './EnrichmentBlockShared';
import type { TimelineItem } from '@/types/timeline';

import { BadgeCheck, Briefcase, Building2, IdCard, Mail, Phone, ShieldAlert, Users } from 'lucide-react';

type GoogleWorkspacePayload = {
  google_id?: string;
  primary_email?: string;
  display_name?: string;
  given_name?: string;
  family_name?: string;
  job_title?: string;
  department?: string;
  organization?: string;
  org_unit_path?: string;
  phone?: string;
  suspended?: boolean;
};

function getGoogleWorkspacePayload(item: TimelineItem): GoogleWorkspacePayload | null {
  const enrichments = asRecord((item as TimelineItem & { enrichments?: unknown }).enrichments);
  const payload = asRecord(enrichments?.google_workspace);
  if (!payload) {
    return null;
  }
  return payload as GoogleWorkspacePayload;
}

export function GoogleWorkspaceEnrichmentBlock({ item }: { item: TimelineItem }) {
  const payload = getGoogleWorkspacePayload(item);
  if (!payload) {
    return null;
  }

  const displayName = getString(payload.display_name);
  const primaryEmail = getString(payload.primary_email);
  const givenName = getString(payload.given_name);
  const familyName = getString(payload.family_name);
  const jobTitle = getString(payload.job_title);
  const department = getString(payload.department);
  const organization = getString(payload.organization);
  const orgUnitPath = getString(payload.org_unit_path);
  const phone = getString(payload.phone);
  const googleId = getString(payload.google_id);
  const suspended = getBoolean(payload.suspended);

  const fullNameSecondary = [givenName, familyName].filter(Boolean).join(' ');
  const hasContent = Boolean(
    displayName ||
      primaryEmail ||
      jobTitle ||
      department ||
      organization ||
      orgUnitPath ||
      phone ||
      googleId ||
      suspended !== undefined
  );

  if (!hasContent) {
    return null;
  }

  return (
    <EnrichmentBlockSection icon={<Users className="h-4 w-4" />} title="Google Workspace Enrichment">
      <div className="grid gap-2 md:grid-cols-2">
        {displayName && (
          <EnrichmentInfoRow
            icon={<BadgeCheck className="h-3.5 w-3.5" />}
            label="Name"
            value={displayName}
            secondary={fullNameSecondary && fullNameSecondary !== displayName ? fullNameSecondary : undefined}
          />
        )}

        {primaryEmail && (
          <EnrichmentInfoRow
            icon={<Mail className="h-3.5 w-3.5" />}
            label="Primary Email"
            value={primaryEmail}
          />
        )}

        {jobTitle && (
          <EnrichmentInfoRow
            icon={<Briefcase className="h-3.5 w-3.5" />}
            label="Job Title"
            value={jobTitle}
          />
        )}

        {(organization || department) && (
          <EnrichmentInfoRow
            icon={<Building2 className="h-3.5 w-3.5" />}
            label="Organization"
            value={organization || department || ''}
            secondary={organization && department ? department : undefined}
          />
        )}

        {orgUnitPath && (
          <EnrichmentInfoRow
            icon={<Users className="h-3.5 w-3.5" />}
            label="Org Unit"
            value={orgUnitPath}
          />
        )}

        {phone && (
          <EnrichmentInfoRow
            icon={<Phone className="h-3.5 w-3.5" />}
            label="Phone"
            value={phone}
          />
        )}

        {googleId && (
          <EnrichmentInfoRow
            icon={<IdCard className="h-3.5 w-3.5" />}
            label="Google ID"
            value={googleId}
          />
        )}
      </div>

      {suspended !== undefined && (
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="neutral" icon={<ShieldAlert className="h-3.5 w-3.5" />}>
            {suspended ? 'Suspended' : 'Active'}
          </Badge>
        </div>
      )}
    </EnrichmentBlockSection>
  );
}

export default GoogleWorkspaceEnrichmentBlock;