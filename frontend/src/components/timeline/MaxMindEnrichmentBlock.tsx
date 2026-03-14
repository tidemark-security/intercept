import React from 'react';

import type { TimelineItem } from '@/types/timeline';
import { Badge } from '@/components/data-display/Badge';
import {
  asRecord,
  EnrichmentBlockSection,
  EnrichmentInfoRow,
  getNumber,
  getString,
  isTrue,
} from './EnrichmentBlockShared';

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
  if (isTrue(anonymousPayload.is_anonymous_vpn)) {
    signals.push('VPN');
  }
  if (isTrue(anonymousPayload.is_public_proxy)) {
    signals.push('Public Proxy');
  }
  if (isTrue(anonymousPayload.is_residential_proxy)) {
    signals.push('Residential Proxy');
  }
  if (isTrue(anonymousPayload.is_tor_exit_node)) {
    signals.push('Tor Exit Node');
  }
  if (isTrue(anonymousPayload.is_hosting_provider)) {
    signals.push('Hosting Provider');
  }
  if (signals.length === 0 && isTrue(anonymousPayload.is_anonymous)) {
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
    <EnrichmentBlockSection icon={<Globe2 className="h-4 w-4" />} title="MaxMind Enrichment">
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
                  <EnrichmentInfoRow
                    icon={<MapPin className="h-3.5 w-3.5" />}
                    label="Location"
                    value={location.label}
                    secondary={location.coordinates}
                  />
                )}

                {(asn?.organization || asn?.number !== undefined) && (
                  <EnrichmentInfoRow
                    icon={<Building2 className="h-3.5 w-3.5" />}
                    label="ASN"
                    value={asn?.organization || `AS${asn?.number}`}
                    secondary={asn?.number !== undefined ? `AS${asn.number}` : undefined}
                  />
                )}

                {network && (
                  <EnrichmentInfoRow
                    icon={<Network className="h-3.5 w-3.5" />}
                    label="Network"
                    value={network}
                  />
                )}

                {connectionType && (
                  <EnrichmentInfoRow
                    icon={<ServerCog className="h-3.5 w-3.5" />}
                    label="Connection"
                    value={connectionType}
                  />
                )}

                {domain && (
                  <EnrichmentInfoRow
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
    </EnrichmentBlockSection>
  );
}

export default MaxMindEnrichmentBlock;