/**
 * Add Network Form Component
 * 
 * Functional form for creating network traffic timeline items.
 * Allows documenting network connections with source/dest IPs, ports, and protocol.
 */

import React from "react";

import { Select } from "@/components/forms/Select";
import { TextArea } from "@/components/forms/TextArea";
import { TextField } from "@/components/forms/TextField";
import { TagsManager } from "@/components/forms/TagsManager";
import { DateTimeManager } from "@/components/forms/DateTimeManager";
import { useTimelineForm } from "@/hooks/useTimelineForm";
import { useTimelineFormContext } from "@/contexts/TimelineFormContext";
import { TimelineFormLayout } from "@/components/timeline/TimelineFormLayout";
import { useValidation } from "@/hooks/useValidation";
import type { NetworkTrafficItem } from '@/types/generated/models/NetworkTrafficItem';
import type { Protocol } from '@/types/generated/models/Protocol';

import { Activity } from 'lucide-react';
export interface AddNetworkFormProps {
  initialData?: NetworkTrafficItem;
}

// Valid protocol values that match backend enum
const VALID_PROTOCOLS = new Set([
  'TCP', 'UDP', 'ICMP', 'GRE', 'ESP', 'AH', 'SCTP', 'IPV6', 'IGMP', 'OTHER',
  // Full list from Protocol enum - include commonly used ones
  'HOPOPT', 'IGMP', 'GGP', 'IPV4', 'ST', 'CBT', 'EGP', 'IGP', 'RSVP', 'DCCP'
]);

/**
 * Normalize protocol value to ensure it matches valid backend enum values.
 * Legacy values like 'HTTP', 'HTTPS', 'DNS', or lowercase 'other' are mapped to 'OTHER'.
 */
function normalizeProtocol(protocol: string | undefined | null): string {
  if (!protocol) return '';
  const upper = protocol.toUpperCase();
  return VALID_PROTOCOLS.has(upper) ? upper : 'OTHER';
}

export function AddNetworkForm({ initialData }: AddNetworkFormProps) {
  const { editMode, onCancel } = useTimelineFormContext();
  
  const sourceIpInputRef = React.useRef<HTMLInputElement>(null);
  const { validate, rules } = useValidation();
  
  // Field-level validation errors
  const [fieldErrors, setFieldErrors] = React.useState<{
    sourceIp: string | null;
    destIp: string | null;
    sourcePort: string | null;
    destPort: string | null;
  }>({
    sourceIp: null,
    destIp: null,
    sourcePort: null,
    destPort: null,
  });
  
  // Helper to update a single field error
  const setFieldError = React.useCallback((field: keyof typeof fieldErrors, error: string | null) => {
    setFieldErrors(prev => ({ ...prev, [field]: error }));
  }, []);
  
  // Helper to validate a field and update its error state
  const validateField = React.useCallback((field: keyof typeof fieldErrors, ruleKey: string, value: string) => {
    if (value.trim()) {
      const result = validate(ruleKey, value.trim());
      setFieldError(field, result.valid ? null : result.error || "Invalid value");
    } else {
      setFieldError(field, null);
    }
  }, [setFieldError, validate]);
  
  // Check if any field has an error
  const hasFieldErrors = Object.values(fieldErrors).some(e => e !== null);
  
  const {
    formState,
    setFormState,
    handleSubmit,
    handleClear,
    isSubmitting,
    initialFlagHighlight,
  } = useTimelineForm<{
    sourceIp: string;
    sourcePort: string;
    destIp: string;
    destPort: string;
    protocol: string;
    description: string;
    timestamp: string;
    tags: string[];
  }, NetworkTrafficItem>({
    initialData,
    defaultState: {
      sourceIp: '',
      sourcePort: '',
      destIp: '',
      destPort: '',
      protocol: '',
      description: '',
      timestamp: '',
      tags: [],
    },
    transformInitialData: (data) => ({
      sourceIp: data.source_ip || '',
      sourcePort: data.source_port?.toString() || '',
      destIp: data.destination_ip || '',
      destPort: data.destination_port?.toString() || '',
      protocol: normalizeProtocol(data.protocol),
      description: data.description || '',
      timestamp: data.timestamp || '',
      tags: data.tags || [],
    }),
    buildPayload: (state) => ({
      source_ip: state.sourceIp,
      source_port: state.sourcePort ? parseInt(state.sourcePort, 10) : undefined,
      destination_ip: state.destIp,
      destination_port: state.destPort ? parseInt(state.destPort, 10) : undefined,
      protocol: state.protocol as Protocol | undefined,
      description: state.description || undefined,
      timestamp: state.timestamp || undefined,
      tags: state.tags.length > 0 ? state.tags : undefined,
    }),
    validate: (state) => {
      if (!state.sourceIp.trim()) {
        return { valid: false, error: "Source IP is required" };
      }
      if (!state.destIp.trim()) {
        return { valid: false, error: "Destination IP is required" };
      }
      // Validate IP formats
      const srcIpResult = validate('network.src_ip', state.sourceIp.trim());
      if (!srcIpResult.valid) {
        return { valid: false, error: srcIpResult.error || "Invalid source IP" };
      }
      const dstIpResult = validate('network.dst_ip', state.destIp.trim());
      if (!dstIpResult.valid) {
        return { valid: false, error: dstIpResult.error || "Invalid destination IP" };
      }
      // Validate ports if provided
      if (state.sourcePort) {
        const srcPortResult = validate('network.src_port', state.sourcePort);
        if (!srcPortResult.valid) {
          return { valid: false, error: srcPortResult.error || "Invalid source port" };
        }
      }
      if (state.destPort) {
        const dstPortResult = validate('network.dst_port', state.destPort);
        if (!dstPortResult.valid) {
          return { valid: false, error: dstPortResult.error || "Invalid destination port" };
        }
      }
      return { valid: true };
    },
  });

  // Auto-focus the source IP input when form appears (but not in edit mode)
  React.useEffect(() => {
    if (!editMode) {
      const timer = setTimeout(() => {
        sourceIpInputRef.current?.focus();
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [editMode]);

  // Run initial validation when form loads in edit mode (once rules are available)
  const hasRunInitialValidation = React.useRef(false);
  React.useEffect(() => {
    if (editMode && rules && !hasRunInitialValidation.current) {
      hasRunInitialValidation.current = true;
      if (formState.sourceIp.trim()) {
        validateField('sourceIp', 'network.src_ip', formState.sourceIp);
      }
      if (formState.destIp.trim()) {
        validateField('destIp', 'network.dst_ip', formState.destIp);
      }
      if (formState.sourcePort) {
        validateField('sourcePort', 'network.src_port', formState.sourcePort);
      }
      if (formState.destPort) {
        validateField('destPort', 'network.dst_port', formState.destPort);
      }
    }
  }, [editMode, rules, formState.sourceIp, formState.destIp, formState.sourcePort, formState.destPort, validateField]);

  return (
    <TimelineFormLayout
      icon={<Activity className="text-neutral-600" />}
      title={editMode ? "Edit Network Traffic" : "Add Network Traffic"}
      onSubmit={handleSubmit}
      onCancel={onCancel}
      onClear={editMode ? undefined : handleClear}
      submitLabel={editMode ? "Update Network Traffic" : "Add Network Traffic"}
      submitDisabled={!formState.sourceIp.trim() || !formState.destIp.trim() || hasFieldErrors}
      isSubmitting={isSubmitting}
      useWell={true}
      editMode={editMode}
      initialFlagHighlight={initialFlagHighlight}
    >
      <div className="flex w-full gap-4">
        <TextField
          className="h-auto w-full"
          label="Source IP"
          helpText={fieldErrors.sourceIp || "Originating IP address"}
          error={fieldErrors.sourceIp !== null}
        >
          <TextField.Input
            ref={sourceIpInputRef}
            placeholder="e.g., 10.0.1.50"
            value={formState.sourceIp}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
              const newValue = e.target.value;
              setFormState({ ...formState, sourceIp: newValue });
              validateField('sourceIp', 'network.src_ip', newValue);
            }}
            onBlur={() => {
              validateField('sourceIp', 'network.src_ip', formState.sourceIp);
            }}
          />
        </TextField>

        <TextField
          className="h-auto w-32 flex-none"
          label="Port (optional)"
          helpText={fieldErrors.sourcePort || "Source port"}
          error={fieldErrors.sourcePort !== null}
        >
          <TextField.Input
            type="number"
            placeholder="e.g., 54321"
            value={formState.sourcePort}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
              const newValue = e.target.value;
              setFormState({ ...formState, sourcePort: newValue });
              validateField('sourcePort', 'network.src_port', newValue);
            }}
            onBlur={() => {
              validateField('sourcePort', 'network.src_port', formState.sourcePort);
            }}
          />
        </TextField>
      </div>

      <div className="flex w-full gap-4">
        <TextField
          className="h-auto w-full"
          label="Destination IP"
          helpText={fieldErrors.destIp || "Target IP address"}
          error={fieldErrors.destIp !== null}
        >
          <TextField.Input
            placeholder="e.g., 203.0.113.42"
            value={formState.destIp}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
              const newValue = e.target.value;
              setFormState({ ...formState, destIp: newValue });
              validateField('destIp', 'network.dst_ip', newValue);
            }}
            onBlur={() => {
              validateField('destIp', 'network.dst_ip', formState.destIp);
            }}
          />
        </TextField>

        <TextField
          className="h-auto w-32 flex-none"
          label="Port (optional)"
          helpText={fieldErrors.destPort || "Dest port"}
          error={fieldErrors.destPort !== null}
        >
          <TextField.Input
            type="number"
            placeholder="e.g., 443"
            value={formState.destPort}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
              const newValue = e.target.value;
              setFormState({ ...formState, destPort: newValue });
              validateField('destPort', 'network.dst_port', newValue);
            }}
            onBlur={() => {
              validateField('destPort', 'network.dst_port', formState.destPort);
            }}
          />
        </TextField>
      </div>

      <Select
        className="h-auto w-full flex-none"
        label="Protocol (optional)"
        helpText="Network protocol"
        placeholder="Select protocol..."
        value={formState.protocol}
        onValueChange={(protocol) => setFormState({ ...formState, protocol })}
      >
        <Select.Item value="TCP">TCP</Select.Item>
        <Select.Item value="UDP">UDP</Select.Item>
        <Select.Item value="ICMP">ICMP</Select.Item>
        <Select.Item value="GRE">GRE</Select.Item>
        <Select.Item value="ESP">ESP (IPsec)</Select.Item>
        <Select.Item value="AH">AH (IPsec)</Select.Item>
        <Select.Item value="SCTP">SCTP</Select.Item>
        <Select.Item value="IPV6">IPv6</Select.Item>
        <Select.Item value="IGMP">IGMP</Select.Item>
        <Select.Item value="OTHER">Other</Select.Item>
      </Select>

      <TextArea
        className="h-auto w-full flex-none"
        label="Description (optional)"
        helpText="Additional context about this network activity"
      >
        <TextArea.Input
          className="h-24 w-full flex-none"
          placeholder="Enter description..."
          value={formState.description}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => 
            setFormState({ ...formState, description: e.target.value })
          }
        />
      </TextArea>

      <DateTimeManager
        value={formState.timestamp}
        onChange={(timestamp) => setFormState({ ...formState, timestamp })}
        label="Timestamp"
        helpText="When this network traffic occurred"
        showNowButton={true}
      />
      
      <TagsManager
        tags={formState.tags}
        onTagsChange={(tags) => setFormState({ ...formState, tags })}
        label="Tags"
        placeholder="Enter tags and press Enter"
      />
    </TimelineFormLayout>
  );
}
