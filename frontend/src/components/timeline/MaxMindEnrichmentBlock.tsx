import React from 'react';

import type { TimelineItem } from '@/types/timeline';
import { cn } from '@/utils/cn';

import { Badge } from '@/components/data-display/Badge';

import {
  Building2,
  Globe2,
  MapPin,
  Network,
  Radar,
  ServerCog,
  ShieldAlert,
} from 'lucide-react';

type MaxMindResultPayload = {
  results?: Record<string, MaxMindIpPayload> | null;
};

type MaxMindIpPayload = {
  ip?: string;
  databases?: Record<string, Record<string, unknown>> | null;
  queried_at?: string;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function getString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function getNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function getBoolean(value: unknown): boolean {
  return value === true;
}

function buildLocationSummary(databases: Record<string, Record<string, unknown>>) {
  const locationPayload =
    asRecord(databases['GeoLite2-City']) ||
    asRecord(databases['GeoIP2-City']) ||
    asRecord(databases['GeoLite2-Country']) ||
    asRecord(databases['GeoIP2-Country']);

  if (!locationPayload) {
    return null;
  }

  const city = getString(asRecord(locationPayload.city)?.name);
  const country = asRecord(locationPayload.country);
  const countryName = getString(country?.name);
  const countryCode = getString(country?.iso_code);
  const location = asRecord(locationPayload.location);
  const latitude = getNumber(location?.latitude);
  const longitude = getNumber(location?.longitude);

  const parts = [city, countryName || countryCode].filter(Boolean);

  return {
    label: parts.length > 0 ? parts.join(', ') : undefined,
    coordinates:
      latitude !== undefined && longitude !== undefined
        ? `${latitude.toFixed(4)}, ${longitude.toFixed(4)}`
        : undefined,
    countryCode,
  };
}

function buildAsnSummary(databases: Record<string, Record<string, unknown>>) {
  const asnPayload = asRecord(databases['GeoLite2-ASN']) || asRecord(databases['GeoIP2-ISP']);
  if (!asnPayload) {
    return null;
  }

  const organization =
    getString(asnPayload.autonomous_system_organization) ||
    getString(asnPayload.organization) ||
    getString(asnPayload.isp);
  const number = getNumber(asnPayload.autonomous_system_number);

  if (!organization && number === undefined) {
    return null;
  }

  return {
    organization,
    number,
  };
}

function buildNetworkSummary(databases: Record<string, Record<string, unknown>>) {
  for (const payload of Object.values(databases)) {
    const network = getString(asRecord(payload)?.network);
    if (network) {
      return network;
    }
    const traitsNetwork = getString(asRecord(asRecord(payload)?.traits)?.network);
    if (traitsNetwork) {
      return traitsNetwork;
    }
  }
  return undefined;
}

function buildAnonymousSignals(databases: Record<string, Record<string, unknown>>) {
  const anonymousPayload = asRecord(databases['GeoIP2-Anonymous-IP']);
  if (!anonymousPayload) {
    return [] as string[];
  }

  const signals: string[] = [];
  if (getBoolean(anonymousPayload.is_anonymous_vpn)) {
    signals.push('VPN');
  }
  if (getBoolean(anonymousPayload.is_public_proxy)) {
    signals.push('Public Proxy');
  }
  if (getBoolean(anonymousPayload.is_residential_proxy)) {
    signals.push('Residential Proxy');
  }
  if (getBoolean(anonymousPayload.is_tor_exit_node)) {
    signals.push('Tor Exit Node');
  }
  if (getBoolean(anonymousPayload.is_hosting_provider)) {
    signals.push('Hosting Provider');
  }
  if (signals.length === 0 && getBoolean(anonymousPayload.is_anonymous)) {
    signals.push('Anonymous Traffic');
  }
  return signals;
}

function buildConnectionType(databases: Record<string, Record<string, unknown>>) {
  return getString(asRecord(databases['GeoIP2-Connection-Type'])?.connection_type);
}

function buildDomain(databases: Record<string, Record<string, unknown>>) {
  return getString(asRecord(databases['GeoIP2-Domain'])?.domain);
}

function getMaxMindPayload(item: TimelineItem): MaxMindResultPayload | null {
  const enrichments = asRecord((item as TimelineItem & { enrichments?: unknown }).enrichments);
  const maxmind = asRecord(enrichments?.maxmind);
  if (!maxmind) {
    return null;
  }
  return maxmind as MaxMindResultPayload;
}

export function MaxMindEnrichmentBlock({ item }: { item: TimelineItem }) {
  const payload = getMaxMindPayload(item);
  const results = payload?.results;
  if (!results || Object.keys(results).length === 0) {
    return null;
  }

  return (
    <div className="flex w-full flex-col gap-3 rounded-md border border-neutral-border bg-neutral-50/60 p-3">
      <div className="flex items-center gap-2">
        <Globe2 className="h-4 w-4 text-subtext-color" />
        <span className="text-caption-bold font-caption-bold text-default-font">
          MaxMind Enrichment
        </span>
      </div>

      <div className="flex flex-col gap-3">
        {Object.entries(results).map(([ipAddress, rawResult]) => {
          const ipPayload = asRecord(rawResult) as MaxMindIpPayload | null;
          const databases = asRecord(ipPayload?.databases) as Record<string, Record<string, unknown>> | null;
          if (!databases || Object.keys(databases).length === 0) {
            return null;
          }

          const location = buildLocationSummary(databases);
          const asn = buildAsnSummary(databases);
          const network = buildNetworkSummary(databases);
          const connectionType = buildConnectionType(databases);
          const domain = buildDomain(databases);
          const anonymousSignals = buildAnonymousSignals(databases);

          return (
            <div
              key={ipAddress}
              className="flex flex-col gap-2 rounded-md border border-neutral-border bg-default-background p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="neutral" icon={<Radar className="h-3.5 w-3.5" />}>
                  {ipAddress}
                </Badge>
                {location?.countryCode && (
                  <Badge variant="neutral">{location.countryCode}</Badge>
                )}
                {Object.keys(databases).map((databaseName) => (
                  <Badge key={databaseName} variant="neutral">
                    {databaseName}
                  </Badge>
                ))}
              </div>

              <div className="grid gap-2 md:grid-cols-2">
                {location?.label && (
                  <InfoRow
                    icon={<MapPin className="h-3.5 w-3.5" />}
                    label="Location"
                    value={location.label}
                    secondary={location.coordinates}
                  />
                )}

                {(asn?.organization || asn?.number !== undefined) && (
                  <InfoRow
                    icon={<Building2 className="h-3.5 w-3.5" />}
                    label="ASN"
                    value={asn?.organization || `AS${asn?.number}`}
                    secondary={asn?.number !== undefined ? `AS${asn.number}` : undefined}
                  />
                )}

                {network && (
                  <InfoRow
                    icon={<Network className="h-3.5 w-3.5" />}
                    label="Network"
                    value={network}
                  />
                )}

                {connectionType && (
                  <InfoRow
                    icon={<ServerCog className="h-3.5 w-3.5" />}
                    label="Connection"
                    value={connectionType}
                  />
                )}

                {domain && (
                  <InfoRow
                    icon={<Globe2 className="h-3.5 w-3.5" />}
                    label="Domain"
                    value={domain}
                  />
                )}
              </div>

              {anonymousSignals.length > 0 && (
                <div className="flex flex-wrap items-center gap-2">
                  {anonymousSignals.map((signal) => (
                    <Badge key={signal} variant="neutral" icon={<ShieldAlert className="h-3.5 w-3.5" />}>
                      {signal}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function InfoRow({
  icon,
  label,
  value,
  secondary,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  secondary?: string;
}) {
  return (
    <div className="flex items-start gap-2 rounded-md bg-neutral-50 px-2.5 py-2">
      <span className="mt-0.5 text-subtext-color">{icon}</span>
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-[11px] font-medium uppercase tracking-wide text-subtext-color">
          {label}
        </span>
        <span className="break-all text-body font-body text-default-font">{value}</span>
        {secondary && (
          <span className="break-all text-caption font-caption text-subtext-color">{secondary}</span>
        )}
      </div>
    </div>
  );
}

export default MaxMindEnrichmentBlock;