/**
 * Add System Form Component
 * 
 * Functional form for creating system timeline items.
 * Based on AddSystemDialog from UI library, enhanced with form state and submission.
 */

import React from "react";

import { SystemTypeSelector } from "@/components/entities/SystemTypeSelector";
import { TextArea } from "@/components/forms/TextArea";
import { TextField } from "@/components/forms/TextField";
import { ToggleGroup } from "@/components/buttons/ToggleGroup";
import { TagsManager } from "@/components/forms/TagsManager";
import { DateTimeManager } from "@/components/forms/DateTimeManager";
import { useTimelineForm } from "@/hooks/useTimelineForm";
import { useTimelineFormContext } from "@/contexts/TimelineFormContext";
import { TimelineFormLayout } from "@/components/timeline/TimelineFormLayout";
import type { SystemItem } from '@/types/generated/models/SystemItem';
import type { SystemType } from '@/types/generated/models/SystemType';

import { Biohazard, ChevronsUp, Cpu, Factory, Globe, Key } from 'lucide-react';
export interface AddSystemFormProps {
  initialData?: SystemItem;
}

export function AddSystemForm({ initialData }: AddSystemFormProps) {
  const { editMode, onCancel } = useTimelineFormContext();
  const hostnameInputRef = React.useRef<HTMLInputElement>(null);

  const {
    formState,
    setFormState,
    handleSubmit,
    handleClear,
    isSubmitting,
    initialFlagHighlight,
  } = useTimelineForm<{
    hostname: string;
    description: string;
    timestamp: string;
    tags: string[];
    ipAddress: string;
    cmdbId: string;
    systemType: SystemType | '';
    isCritical: boolean;
    isPrivileged: boolean;
    isHighRisk: boolean;
    isInternetFacing: boolean;
    isLegacy: boolean;
  }, SystemItem>({
    initialData,
    defaultState: {
      hostname: '',
      description: '',
      timestamp: '',
      tags: [],
      ipAddress: '',
      cmdbId: '',
      systemType: '',
      isCritical: false,
      isPrivileged: false,
      isHighRisk: false,
      isInternetFacing: false,
      isLegacy: false,
    },
    transformInitialData: (data) => ({
      hostname: data.hostname || '',
      description: data.description || '',
      timestamp: data.timestamp || '',
      tags: data.tags || [],
      ipAddress: data.ip_address || '',
      cmdbId: data.cmdb_id || '',
      systemType: data.system_type || '',
      isCritical: data.is_critical || false,
      isPrivileged: data.is_privileged || false,
      isHighRisk: data.is_high_risk || false,
      isInternetFacing: data.is_internet_facing || false,
      isLegacy: data.is_legacy || false,
    }),
    buildPayload: (state) => ({
      hostname: state.hostname,
      description: state.description || undefined,
      timestamp: state.timestamp || undefined,
      tags: state.tags.length > 0 ? state.tags : undefined,
      ip_address: state.ipAddress || undefined,
      cmdb_id: state.cmdbId || undefined,
      system_type: state.systemType || undefined,
      is_critical: state.isCritical,
      is_privileged: state.isPrivileged,
      is_high_risk: state.isHighRisk,
      is_internet_facing: state.isInternetFacing,
      is_legacy: state.isLegacy,
    }),
    validate: (state) => {
      if (!state.hostname.trim()) {
        return { valid: false, error: "Hostname is required" };
      }
      return { valid: true };
    },
  });

  // Auto-focus the hostname input when form appears (but not in edit mode)
  React.useEffect(() => {
    if (!editMode) {
      const timer = setTimeout(() => {
        hostnameInputRef.current?.focus();
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [editMode]);

  const selectedCharacteristics = [
    formState.isCritical ? 'critical' : null,
    formState.isPrivileged ? 'privileged' : null,
    formState.isHighRisk ? 'high_risk' : null,
    formState.isInternetFacing ? 'internet_facing' : null,
    formState.isLegacy ? 'legacy' : null,
  ].filter((value): value is string => value !== null);

  return (
    <TimelineFormLayout
      icon={<Cpu className="text-neutral-600" />}
      title={editMode ? "Edit System" : "Add System"}
      onSubmit={handleSubmit}
      onCancel={onCancel}
      onClear={editMode ? undefined : handleClear}
      submitLabel={editMode ? "Update System" : "Add System"}
      submitDisabled={!formState.hostname.trim()}
      isSubmitting={isSubmitting}
      useWell={false}
      editMode={editMode}
      initialFlagHighlight={initialFlagHighlight}
    >
      <div className="flex w-full flex-col items-start gap-6 rounded-md border border-solid border-neutral-border bg-default-background px-4 py-4">
        <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-4">
          <TextField
            className="h-auto w-full flex-none"
            label="Hostname"
            helpText="System hostname or computer name"
          >
            <TextField.Input
              ref={hostnameInputRef}
              placeholder="web-server-01.domain.com"
              value={formState.hostname}
              onChange={(e) => setFormState({ ...formState, hostname: e.target.value })}
            />
          </TextField>

          <TextArea
            className="h-auto w-full flex-none"
            label="Description"
            helpText="Additional context about this system"
          >
            <TextArea.Input
              placeholder="Describe the system's role and any relevant details..."
              value={formState.description}
              onChange={(e) => setFormState({ ...formState, description: e.target.value })}
            />
          </TextArea>

          <DateTimeManager
            value={formState.timestamp}
            onChange={(timestamp) => setFormState({ ...formState, timestamp })}
            label="Timestamp"
            helpText="When was this system first observed in the incident"
            placeholder="YYYY-MM-DD HH:MM"
            showNowButton={true}
          />

          <TagsManager
            tags={formState.tags}
            onTagsChange={(tags) => setFormState({ ...formState, tags })}
            label="Tags"
            placeholder="Enter tags and press Enter"
          />
        </div>

        <div className="flex grow shrink-0 basis-0 flex-col items-start gap-4 self-stretch rounded-md border border-solid border-neutral-border bg-neutral-50 px-4 py-4">
          <div className="flex w-full flex-col items-start gap-1">
            <span className="text-caption-bold font-caption-bold text-default-font">
              System Characteristics
            </span>
            <div className="flex w-full flex-wrap items-center gap-2 border border-solid border-neutral-border">
              <div className="flex flex-wrap items-center gap-2">
                <ToggleGroup
                  type="multiple"
                  value={selectedCharacteristics}
                  onValueChange={(characteristics) =>
                    setFormState({
                      ...formState,
                      isCritical: characteristics.includes('critical'),
                      isPrivileged: characteristics.includes('privileged'),
                      isHighRisk: characteristics.includes('high_risk'),
                      isInternetFacing: characteristics.includes('internet_facing'),
                      isLegacy: characteristics.includes('legacy'),
                    })
                  }
                >
                  <ToggleGroup.Item
                    icon={<ChevronsUp />}
                    value="critical"
                    className="w-auto"
                  >
                    Critical
                  </ToggleGroup.Item>
                  <ToggleGroup.Item icon={<Key />} value="privileged" className="w-auto">
                    Privileged
                  </ToggleGroup.Item>
                  <ToggleGroup.Item
                    icon={<Biohazard />}
                    value="high_risk"
                    className="w-auto"
                  >
                    High Risk
                  </ToggleGroup.Item>
                  <ToggleGroup.Item icon={<Globe />} value="internet_facing" className="w-auto">
                    Internet Facing
                  </ToggleGroup.Item>
                  <ToggleGroup.Item icon={<Factory />} value="legacy" className="w-auto">
                    Legacy
                  </ToggleGroup.Item>
                </ToggleGroup>
              </div>
            </div>
          </div>

          <TextField
            className="h-auto w-full flex-none"
            label="IP Address"
            helpText="Primary IP address of the system"
          >
            <TextField.Input
              placeholder="192.168.1.100"
              value={formState.ipAddress}
              onChange={(e) => setFormState({ ...formState, ipAddress: e.target.value })}
            />
          </TextField>

          <TextField
            className="h-auto w-full flex-none"
            label="CMDB ID"
            helpText="Reference ID in configuration management database"
          >
            <TextField.Input
              placeholder="SYS-12345"
              value={formState.cmdbId}
              onChange={(e) => setFormState({ ...formState, cmdbId: e.target.value })}
            />
          </TextField>
        </div>

        <div className="flex max-h-[768px] grow shrink-0 basis-0 items-start gap-4 self-stretch rounded-md border border-solid border-neutral-border bg-neutral-50 px-4 py-4">
          <SystemTypeSelector
            title="System Type"
            compact={true}
            value={formState.systemType}
            onChange={(value) => setFormState({ ...formState, systemType: value as SystemType })}
          />
        </div>
      </div>
    </TimelineFormLayout>
  );
}
