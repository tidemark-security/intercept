/**
 * Add Actor Form Component
 *
 * Functional form for creating actor timeline items.
 * Based on AddActorDialog from UI library, enhanced with form state and submission.
 */

import React from "react";
import { useEnrichmentAliases } from "@/hooks";
import { useSearchCore } from "@/hooks/useSearchCore";

import { cn } from "@/utils/cn";
import { Slider } from "@/components/forms/Slider";
import { TextArea } from "@/components/forms/TextArea";
import { TextField } from "@/components/forms/TextField";
import { ToggleGroup } from "@/components/buttons/ToggleGroup";
import { RadioCardGroup } from "@/components/forms/RadioCardGroup";
import { TagsManager } from "@/components/forms/TagsManager";
import { DateTimeManager } from "@/components/forms/DateTimeManager";
import { useTimelineForm } from "@/hooks/useTimelineForm";
import { useTimelineFormContext } from "@/contexts/TimelineFormContext";
import { TimelineFormLayout } from "@/components/timeline/TimelineFormLayout";
import type { EnrichmentAliasRead } from "@/types/generated/models/EnrichmentAliasRead";
import type { InternalActorItem } from "@/types/generated/models/InternalActorItem";
import type { ThreatActorItem } from "@/types/generated/models/ThreatActorItem";
import type { ExternalActorItem } from "@/types/generated/models/ExternalActorItem";

import {
  Biohazard,
  Bot,
  Briefcase,
  Building,
  Crown,
  Key,
  Mail,
  Phone,
  User,
  Wrench,
} from "lucide-react";

interface AliasSuggestionGroup {
  key: string;
  canonicalValue: string;
  canonicalDisplay?: string | null;
  aliases: EnrichmentAliasRead[];
}

function groupAliasSuggestions(
  aliasResults: EnrichmentAliasRead[],
): AliasSuggestionGroup[] {
  const groups = new Map<string, AliasSuggestionGroup>();

  aliasResults.forEach((alias) => {
    const groupKey = `${alias.provider_id}:${alias.canonical_value}`;
    const existingGroup = groups.get(groupKey);

    if (existingGroup) {
      existingGroup.aliases.push(alias);
      if (!existingGroup.canonicalDisplay && alias.canonical_display) {
        existingGroup.canonicalDisplay = alias.canonical_display;
      }
      return;
    }

    groups.set(groupKey, {
      key: groupKey,
      canonicalValue: alias.canonical_value,
      canonicalDisplay: alias.canonical_display,
      aliases: [alias],
    });
  });

  return Array.from(groups.values());
}

export interface AddActorFormProps {
  initialData?: InternalActorItem | ThreatActorItem | ExternalActorItem;
}

export function AddActorForm({ initialData }: AddActorFormProps) {
  const { editMode, onCancel } = useTimelineFormContext();
  const {
    query: aliasQuery,
    setQuery: setAliasQuery,
    debouncedQuery: debouncedAliasQuery,
  } = useSearchCore();

  // Determine actor type from initialData
  const getActorType = () => {
    if (!initialData) return "internal";
    if (initialData.type === "internal_actor") return "internal";
    if (initialData.type === "threat_actor") return "threat";
    if (initialData.type === "external_actor") return "external";
    return "internal";
  };

  // Extract form state from initialData based on actor type
  const getInitialFormState = () => {
    if (!initialData) {
      return {
        actorType: "internal",
        timestamp: "",
        tags: [] as string[],
        userId: "",
        characteristics: [] as string[],
        internalDescription: "",
        threatActorName: "",
        confidence: 50,
        threatDescription: "",
        name: "",
        title: "",
        organisation: "",
        phone: "",
        email: "",
        externalDescription: "",
      };
    }

    const actorType = getActorType();
    const baseState = {
      actorType,
      timestamp: initialData.timestamp || "",
      tags: initialData.tags || [],
      userId: "",
      characteristics: [] as string[],
      internalDescription: "",
      threatActorName: "",
      confidence: 50,
      threatDescription: "",
      name: "",
      title: "",
      organisation: "",
      phone: "",
      email: "",
      externalDescription: "",
    };

    if (actorType === "internal" && "user_id" in initialData) {
      const characteristics: string[] = [];
      if (initialData.is_vip) characteristics.push("vip");
      if (initialData.is_privileged) characteristics.push("privileged");
      if (initialData.is_high_risk) characteristics.push("high-risk");
      if (initialData.is_contractor) characteristics.push("contractor");
      if (initialData.is_service_account)
        characteristics.push("service-account");

      return {
        ...baseState,
        userId: initialData.user_id || "",
        characteristics,
        internalDescription: initialData.description || "",
      };
    } else if (actorType === "threat" && "confidence" in initialData) {
      return {
        ...baseState,
        threatActorName: initialData.name || "",
        confidence: initialData.confidence || 50,
        threatDescription: initialData.description || "",
      };
    } else if (actorType === "external") {
      return {
        ...baseState,
        name: initialData.name || "",
        title: initialData.title || "",
        organisation: initialData.org || "",
        phone: initialData.contact_phone || "",
        email: initialData.contact_email || "",
        externalDescription: initialData.description || "",
      };
    }

    return baseState;
  };

  const {
    formState,
    setFormState,
    handleSubmit: handleFormSubmit,
    handleClear,
    isSubmitting,
    itemType,
    initialFlagHighlight,
  } = useTimelineForm<
    any,
    InternalActorItem | ThreatActorItem | ExternalActorItem
  >({
    initialData,
    defaultState: getInitialFormState(),
    transformInitialData: () => getInitialFormState(),
    buildPayload: (state) => {
      // Map form actor type to backend type
      const getBackendType = (actorType: string) => {
        if (actorType === "internal") return "internal_actor";
        if (actorType === "threat") return "threat_actor";
        if (actorType === "external") return "external_actor";
        return "internal_actor"; // fallback
      };

      // Build actor-specific data based on type
      const actorData: any = {};

      if (state.actorType === "internal") {
        actorData.user_id = state.userId;
        actorData.is_vip = state.characteristics.includes("vip");
        actorData.is_privileged = state.characteristics.includes("privileged");
        actorData.is_high_risk = state.characteristics.includes("high-risk");
        actorData.is_contractor = state.characteristics.includes("contractor");
        actorData.is_service_account =
          state.characteristics.includes("service-account");
        actorData.description = state.internalDescription;
      } else if (state.actorType === "threat") {
        actorData.name = state.threatActorName;
        actorData.confidence = state.confidence;
        actorData.description = state.threatDescription;
      } else if (state.actorType === "external") {
        actorData.name = state.name;
        actorData.title = state.title;
        actorData.org = state.organisation;
        actorData.contact_phone = state.phone;
        actorData.contact_email = state.email;
        actorData.description = state.externalDescription;
      }

      return {
        type: getBackendType(state.actorType),
        timestamp: state.timestamp || undefined,
        tags: state.tags.length > 0 ? state.tags : undefined,
        ...actorData,
      };
    },
  });

  const aliasSearchEnabled =
    !editMode &&
    formState.actorType === "internal" &&
    debouncedAliasQuery.trim().length > 0;

  const { data: aliasResults = [], isFetching: aliasResultsLoading } =
    useEnrichmentAliases({
      query: debouncedAliasQuery,
      entityType: "user",
      limit: 6,
      enabled: aliasSearchEnabled,
    });

  const groupedAliasResults = groupAliasSuggestions(aliasResults);

  const handleSubmit = (flagHighlightState?: {
    flagged: boolean;
    highlighted: boolean;
  }) => {
    handleFormSubmit(flagHighlightState);
  };

  const showAliasSuggestions =
    formState.actorType === "internal" &&
    aliasQuery.trim().length > 0 &&
    (aliasResultsLoading || groupedAliasResults.length > 0);

  const applyAliasSuggestion = (canonicalValue: string) => {
    setFormState({
      ...formState,
      userId: canonicalValue,
    });
    setAliasQuery(canonicalValue);
  };

  return (
    <TimelineFormLayout
      icon={<User className="text-neutral-600" />}
      title={editMode ? "Edit Actor" : "Add Actor"}
      editMode={editMode}
      formAutoComplete="off"
      onSubmit={handleSubmit}
      onCancel={onCancel}
      onClear={editMode ? undefined : handleClear}
      submitLabel={editMode ? "Update Actor" : "Add Actor"}
      submitDisabled={false}
      isSubmitting={isSubmitting}
      useWell={false}
      initialFlagHighlight={initialFlagHighlight}
    >
      <div className="flex w-full grow flex-col items-start rounded-md border border-solid border-neutral-border bg-default-background px-1 py-1">
        <div className="w-full grow flex flex-col items-start gap-6 px-4 py-4 overflow-auto">
          <div className="flex flex-col items-start gap-6 w-full flex-none">
            <div className="flex w-full flex-col items-start gap-1">
              <span className="text-caption-bold font-caption-bold text-default-font">
                Actor Type
              </span>
              <RadioCardGroup
                className="h-auto w-full flex-none"
                value={formState.actorType}
                onValueChange={(actorType) =>
                  !editMode && setFormState({ ...formState, actorType })
                }
              >
                <div className="flex grow shrink-0 basis-0 flex-col flex-wrap items-start gap-2">
                  <RadioCardGroup.RadioCard
                    disabled={editMode}
                    hideRadio={false}
                    value="internal"
                  >
                    <div className="flex flex-col items-start pr-2">
                      <span className="w-full text-body-bold font-body-bold text-default-font">
                        Internal
                      </span>
                      <span className="w-full text-caption font-caption text-subtext-color">
                        Users within our organisation / directory
                      </span>
                    </div>
                  </RadioCardGroup.RadioCard>
                  <RadioCardGroup.RadioCard
                    disabled={editMode}
                    hideRadio={false}
                    value="threat"
                  >
                    <div className="flex flex-col items-start pr-2">
                      <span className="w-full text-body-bold font-body-bold text-default-font">
                        External - Threat
                      </span>
                      <span className="w-full text-caption font-caption text-subtext-color">
                        Known threat actor groups
                      </span>
                    </div>
                  </RadioCardGroup.RadioCard>
                  <RadioCardGroup.RadioCard
                    disabled={editMode}
                    hideRadio={false}
                    value="external"
                  >
                    <div className="flex flex-col items-start pr-2">
                      <span className="w-full text-body-bold font-body-bold text-default-font">
                        External - Other
                      </span>
                      <span className="w-full text-caption font-caption text-subtext-color">
                        Actors from outside, including third-party support and
                        government agencies
                      </span>
                    </div>
                  </RadioCardGroup.RadioCard>
                </div>
              </RadioCardGroup>
            </div>

            <DateTimeManager
              value={formState.timestamp}
              onChange={(timestamp) =>
                setFormState({ ...formState, timestamp })
              }
              label="Timestamp"
              helpText="When was this actor first identified"
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
          {/* Actor Form Columns - Inline */}
          <div className={cn("flex w-full grow items-stretch gap-6")}>
            <div
              className={cn(
                "flex grow shrink-0 basis-0 flex-col items-start gap-6 rounded-md border border-solid border-neutral-border bg-neutral-50 px-4 py-4",
                {
                  hidden:
                    formState.actorType === "external" ||
                    formState.actorType === "threat",
                },
              )}
            >
              <TextField
                className="h-auto w-full flex-none"
                label="User ID"
                helpText="UPN, samaccountname, or other stable identity"
                icon={<User />}
              >
                <TextField.Input
                  placeholder="user@example.com"
                  autoComplete="off"
                  value={formState.userId}
                  onChange={(e) =>
                    {
                      const nextValue = (e.target as HTMLInputElement).value;
                      setFormState({
                        ...formState,
                        userId: nextValue,
                      });
                      setAliasQuery(nextValue);
                    }
                  }
                />
              </TextField>
              {showAliasSuggestions ? (
                <div className="-mt-4 flex w-full flex-col overflow-hidden rounded-md border border-neutral-border bg-default-background shadow-sm">
                  {aliasResultsLoading ? (
                    <div className="px-3 py-2 text-caption font-caption text-subtext-color">
                      Searching directory aliases...
                    </div>
                  ) : (
                    <>

                      {groupedAliasResults.map((group) => {
                        const primaryLabel =
                          group.canonicalDisplay || group.canonicalValue;
                        const showCanonicalValue =
                          primaryLabel !== group.canonicalValue;
                        const visibleAliases = group.aliases.slice(0, 3);
                        const hiddenAliasCount =
                          group.aliases.length - visibleAliases.length;

                        return (
                      <button
                        key={group.key}
                        type="button"
                        className="flex w-full items-start gap-3 border-b border-neutral-border px-3 py-3 text-left last:border-b-0 hover:bg-neutral-50"
                        onClick={() => applyAliasSuggestion(group.canonicalValue)}
                      >
                        <div className="flex min-w-0 flex-1 flex-col gap-2">
                          <div className="flex min-w-0 items-start justify-between gap-3">
                            <div className="flex min-w-0 flex-col">
                              <span className="truncate text-body font-body text-default-font">
                                {primaryLabel}
                              </span>
                              {showCanonicalValue ? (
                                <span className="truncate text-caption font-caption text-subtext-color">
                                  Primary ID: {group.canonicalValue}
                                </span>
                              ) : null}
                            </div>
                            <span className="shrink-0 text-caption font-caption text-subtext-color">
                              {group.aliases.length} {group.aliases.length === 1 ? "match" : "matches"}
                            </span>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {visibleAliases.map((alias) => (
                              <span
                                key={alias.id}
                                className="inline-flex max-w-full items-center gap-1 border border-neutral-border bg-default-background px-2 py-1 text-caption font-caption text-subtext-color"
                              >
                                <span className="truncate">{alias.alias_value}</span>
                                <span className="shrink-0 text-subtext-color/80">
                                  {alias.alias_type}
                                </span>
                              </span>
                            ))}
                            {hiddenAliasCount > 0 ? (
                              <span className="inline-flex items-center border border-dashed border-neutral-border px-2 py-1 text-caption font-caption text-subtext-color">
                                +{hiddenAliasCount} more aliases
                              </span>
                            ) : null}
                          </div>
                        </div>
                      </button>
                        );
                      })}
                    </>
                  )}
                </div>
              ) : null}
              <div className="flex w-full flex-col items-start gap-1">
                <span className="text-caption-bold font-caption-bold text-default-font">
                  User Characteristics
                </span>
                <ToggleGroup
                  type="multiple"
                  value={formState.characteristics}
                  onValueChange={(characteristics) =>
                    setFormState({ ...formState, characteristics })
                  }
                  className="w-full"
                >
                  <ToggleGroup.Item
                    value="vip"
                    icon={<Crown />}
                    className="w-auto"
                  >
                    VIP
                  </ToggleGroup.Item>
                  <ToggleGroup.Item
                    value="privileged"
                    icon={<Key />}
                    className="w-auto"
                  >
                    Privileged
                  </ToggleGroup.Item>
                  <ToggleGroup.Item
                    value="high-risk"
                    icon={<Biohazard />}
                    className="w-auto"
                  >
                    At Risk
                  </ToggleGroup.Item>
                  <ToggleGroup.Item
                    value="contractor"
                    icon={<Wrench />}
                    className="w-auto"
                  >
                    Contractor
                  </ToggleGroup.Item>
                  <ToggleGroup.Item
                    value="service-account"
                    icon={<Bot />}
                    className="w-auto"
                  >
                    Service Account
                  </ToggleGroup.Item>
                </ToggleGroup>
              </div>
              <TextArea
                className="w-full grow flex flex-col"
                label="Description"
                helpText=""
              >
                <TextArea.Input
                  className="min-h-[64px] w-full grow resize-none"
                  placeholder="Add context about this actor..."
                  value={formState.internalDescription}
                  onChange={(e) =>
                    setFormState({
                      ...formState,
                      internalDescription: (e.target as HTMLTextAreaElement)
                        .value,
                    })
                  }
                />
              </TextArea>
            </div>
            <div
              className={cn(
                "hidden grow shrink-0 basis-0 flex-col items-start gap-6 rounded-md border border-solid border-neutral-border bg-neutral-50 px-4 py-4",
                { flex: formState.actorType === "threat" },
              )}
            >
              <TextField
                className="h-auto w-full flex-none"
                label="Threat Actor Name"
                helpText="This will autocomplete if you've provided a threat actor library."
                icon={<Biohazard />}
              >
                <TextField.Input
                  placeholder="APT-999, Virulent Vespa"
                  value={formState.threatActorName}
                  onChange={(e) =>
                    setFormState({
                      ...formState,
                      threatActorName: (e.target as HTMLInputElement).value,
                    })
                  }
                />
              </TextField>
              <div className="flex w-full flex-col items-start gap-1">
                <span className="w-full text-caption-bold font-caption-bold text-default-font">
                  Confidence
                </span>
                <div className="flex w-full flex-col items-start gap-4 border border-solid border-neutral-border bg-default-background px-4 py-4">
                  <div className="flex w-full flex-col items-start gap-1">
                    <span className="text-caption font-caption text-subtext-color">
                      Use the slider to set attribution confidence.
                    </span>
                  </div>
                  <div className="flex w-full flex-col items-start gap-2">
                    <Slider
                      value={[formState.confidence]}
                      onValueChange={(value) =>
                        setFormState({ ...formState, confidence: value[0] })
                      }
                    />
                    <div className="flex w-full items-center justify-between">
                      <span className="text-caption font-caption text-subtext-color">
                        0%
                      </span>
                      <span className="text-caption font-caption text-brand-primary">
                        {formState.confidence}%
                      </span>
                      <span className="text-caption font-caption text-subtext-color">
                        100%
                      </span>
                    </div>
                  </div>
                </div>
              </div>
              <TextArea
                className="w-full grow flex flex-col"
                label="Description"
                helpText=""
              >
                <TextArea.Input
                  className="min-h-[64px] w-full grow resize-none"
                  placeholder="Add context about this actor..."
                  value={formState.threatDescription}
                  onChange={(e) =>
                    setFormState({
                      ...formState,
                      threatDescription: (e.target as HTMLTextAreaElement)
                        .value,
                    })
                  }
                />
              </TextArea>
            </div>
            <div
              className={cn(
                "hidden grow shrink-0 basis-0 flex-col items-start gap-4 rounded-md border border-solid border-neutral-border bg-neutral-50 px-4 py-4",
                { flex: formState.actorType === "external" },
              )}
            >
              <TextField
                className="h-auto w-full flex-none"
                label="Name"
                helpText=""
                icon={<User />}
              >
                <TextField.Input
                  placeholder="Actor name"
                  value={formState.name}
                  onChange={(e) =>
                    setFormState({
                      ...formState,
                      name: (e.target as HTMLInputElement).value,
                    })
                  }
                />
              </TextField>
              <TextField
                className="h-auto w-full flex-none"
                label="Title"
                helpText=""
                icon={<Briefcase />}
              >
                <TextField.Input
                  placeholder="Job title"
                  value={formState.title}
                  onChange={(e) =>
                    setFormState({
                      ...formState,
                      title: (e.target as HTMLInputElement).value,
                    })
                  }
                />
              </TextField>
              <TextField
                className="h-auto w-full flex-none"
                label="Organisation"
                helpText=""
                icon={<Building />}
              >
                <TextField.Input
                  placeholder="Where the actor is from"
                  value={formState.organisation}
                  onChange={(e) =>
                    setFormState({
                      ...formState,
                      organisation: (e.target as HTMLInputElement).value,
                    })
                  }
                />
              </TextField>
              <TextField
                className="h-auto w-full flex-none"
                label="Phone"
                helpText=""
                icon={<Phone />}
              >
                <TextField.Input
                  placeholder="+61 400 000 000"
                  value={formState.phone}
                  onChange={(e) =>
                    setFormState({
                      ...formState,
                      phone: (e.target as HTMLInputElement).value,
                    })
                  }
                />
              </TextField>
              <TextField
                className="h-auto w-full flex-none"
                label="Email"
                helpText=""
                icon={<Mail />}
              >
                <TextField.Input
                  placeholder="actor@example.com"
                  value={formState.email}
                  onChange={(e) =>
                    setFormState({
                      ...formState,
                      email: (e.target as HTMLInputElement).value,
                    })
                  }
                />
              </TextField>
              <TextArea
                className="w-full grow flex flex-col"
                label="Description"
                helpText=""
              >
                <TextArea.Input
                  className="min-h-[64px] w-full grow resize-none"
                  placeholder="Add context about this actor..."
                  value={formState.externalDescription}
                  onChange={(e) =>
                    setFormState({
                      ...formState,
                      externalDescription: (e.target as HTMLTextAreaElement)
                        .value,
                    })
                  }
                />
              </TextArea>
            </div>
          </div>
        </div>
      </div>
    </TimelineFormLayout>
  );
}
