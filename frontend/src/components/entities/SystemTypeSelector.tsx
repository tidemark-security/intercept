/**
 * System Type Selector Component
 * 
 * A searchable system type selection component with filtering.
 * Based on SystemTypeSelectionDialog from UI library but with functional search.
 */

import React from "react";

import { SYSTEM_TYPE_ICONS, SYSTEM_TYPE_LABELS } from "@/utils/systemTypeIcons";
import { Accordion } from "@/components/misc/Accordion";
import { Badge } from "@/components/data-display/Badge";
import { IconButton } from "@/components/buttons/IconButton";
import { IconWithBackground } from "@/components/misc/IconWithBackground";
import { RadioCardGroup } from "@/components/forms/RadioCardGroup";
import { TextField } from "@/components/forms/TextField";
import { cn } from "@/utils/cn";
import type { SystemType } from "@/types/generated/models/SystemType";

import { BarChart, Cpu, Eraser, Factory, HelpCircle, Laptop, Search, Server } from 'lucide-react';
// Define system type data structure
interface SystemTypeOption {
  value: SystemType | "OTHER";
  label: string;
  icon: React.ReactNode;
}

interface SystemCategory {
  id: string;
  label: string;
  icon: React.ReactNode;
  types: SystemTypeOption[];
}

// Helper to get icon element from SYSTEM_TYPE_ICONS
function getIconElement(type: SystemType): React.ReactNode {
  const IconComponent = SYSTEM_TYPE_ICONS[type];
  return IconComponent ? <IconComponent /> : <Cpu />;
}

// Helper to get label from SYSTEM_TYPE_LABELS  
function getLabel(type: SystemType): string {
  return SYSTEM_TYPE_LABELS[type] ?? type;
}

// All system types organized by category - using actual SystemType enum values
const SYSTEM_CATEGORIES: SystemCategory[] = [
  {
    id: "end-user",
    label: "Enterprise Systems: End User",
    icon: <Laptop />,
    types: [
      { value: "ENT_WORKSTATION", label: getLabel("ENT_WORKSTATION"), icon: getIconElement("ENT_WORKSTATION") },
      { value: "ENT_LAPTOP", label: getLabel("ENT_LAPTOP"), icon: getIconElement("ENT_LAPTOP") },
      { value: "MOBILE_IOS", label: getLabel("MOBILE_IOS"), icon: getIconElement("MOBILE_IOS") },
      { value: "MOBILE_ANDROID", label: getLabel("MOBILE_ANDROID"), icon: getIconElement("MOBILE_ANDROID") },
      { value: "MOBILE_OTHER", label: getLabel("MOBILE_OTHER"), icon: getIconElement("MOBILE_OTHER") },
    ],
  },
  {
    id: "server",
    label: "Enterprise Systems: Server",
    icon: <Server />,
    types: [
      { value: "ENT_WEB_SERVER", label: getLabel("ENT_WEB_SERVER"), icon: getIconElement("ENT_WEB_SERVER") },
      { value: "ENT_DATABASE_SERVER", label: getLabel("ENT_DATABASE_SERVER"), icon: getIconElement("ENT_DATABASE_SERVER") },
      { value: "ENT_APPLICATION_SERVER", label: getLabel("ENT_APPLICATION_SERVER"), icon: getIconElement("ENT_APPLICATION_SERVER") },
      { value: "ENT_FILE_SERVER", label: getLabel("ENT_FILE_SERVER"), icon: getIconElement("ENT_FILE_SERVER") },
      { value: "ENT_MAIL_SERVER", label: getLabel("ENT_MAIL_SERVER"), icon: getIconElement("ENT_MAIL_SERVER") },
      { value: "ENT_DNS_SERVER", label: getLabel("ENT_DNS_SERVER"), icon: getIconElement("ENT_DNS_SERVER") },
      { value: "ENT_DOMAIN_CONTROLLER", label: getLabel("ENT_DOMAIN_CONTROLLER"), icon: getIconElement("ENT_DOMAIN_CONTROLLER") },
      { value: "ENT_ROUTER", label: getLabel("ENT_ROUTER"), icon: getIconElement("ENT_ROUTER") },
      { value: "ENT_SWITCH", label: getLabel("ENT_SWITCH"), icon: getIconElement("ENT_SWITCH") },
      { value: "ENT_FIREWALL", label: getLabel("ENT_FIREWALL"), icon: getIconElement("ENT_FIREWALL") },
      { value: "ENT_LOAD_BALANCER", label: getLabel("ENT_LOAD_BALANCER"), icon: getIconElement("ENT_LOAD_BALANCER") },
      { value: "ENT_PROXY_SERVER", label: getLabel("ENT_PROXY_SERVER"), icon: getIconElement("ENT_PROXY_SERVER") },
      { value: "ENT_JUMP_HOST", label: getLabel("ENT_JUMP_HOST"), icon: getIconElement("ENT_JUMP_HOST") },
      { value: "ENT_VPN_SERVER", label: getLabel("ENT_VPN_SERVER"), icon: getIconElement("ENT_VPN_SERVER") },
      { value: "ENT_MAINFRAME", label: getLabel("ENT_MAINFRAME"), icon: getIconElement("ENT_MAINFRAME") },
      { value: "ENT_PRINTER", label: getLabel("ENT_PRINTER"), icon: getIconElement("ENT_PRINTER") },
    ],
  },
  {
    id: "ics",
    label: "ICS: Industrial Control Systems",
    icon: <Factory />,
    types: [
      { value: "ICS_CONTROL_SERVER", label: getLabel("ICS_CONTROL_SERVER"), icon: getIconElement("ICS_CONTROL_SERVER") },
      { value: "ICS_HMI", label: getLabel("ICS_HMI"), icon: getIconElement("ICS_HMI") },
      { value: "ICS_PLC", label: getLabel("ICS_PLC"), icon: getIconElement("ICS_PLC") },
      { value: "ICS_RTU", label: getLabel("ICS_RTU"), icon: getIconElement("ICS_RTU") },
      { value: "ICS_IED", label: getLabel("ICS_IED"), icon: getIconElement("ICS_IED") },
      { value: "ICS_DATA_HISTORIAN", label: getLabel("ICS_DATA_HISTORIAN"), icon: getIconElement("ICS_DATA_HISTORIAN") },
      { value: "ICS_DATA_GATEWAY", label: getLabel("ICS_DATA_GATEWAY"), icon: getIconElement("ICS_DATA_GATEWAY") },
      { value: "ICS_SAFETY_CONTROLLER", label: getLabel("ICS_SAFETY_CONTROLLER"), icon: getIconElement("ICS_SAFETY_CONTROLLER") },
      { value: "ICS_FIELD_IO", label: getLabel("ICS_FIELD_IO"), icon: getIconElement("ICS_FIELD_IO") },
    ],
  },
  {
    id: "iot",
    label: "IOT: Internet of Things",
    icon: <BarChart />,
    types: [
      { value: "IOT_SENSOR", label: getLabel("IOT_SENSOR"), icon: getIconElement("IOT_SENSOR") },
      { value: "IOT_CAMERA", label: getLabel("IOT_CAMERA"), icon: getIconElement("IOT_CAMERA") },
      { value: "IOT_SMART_HOME", label: getLabel("IOT_SMART_HOME"), icon: getIconElement("IOT_SMART_HOME") },
      { value: "IOT_WEARABLE", label: getLabel("IOT_WEARABLE"), icon: getIconElement("IOT_WEARABLE") },
      { value: "IOT_VEHICLE", label: getLabel("IOT_VEHICLE"), icon: getIconElement("IOT_VEHICLE") },
      { value: "IOT_MEDICAL", label: getLabel("IOT_MEDICAL"), icon: getIconElement("IOT_MEDICAL") },
      { value: "IOT_APPLIANCE", label: getLabel("IOT_APPLIANCE"), icon: getIconElement("IOT_APPLIANCE") },
      { value: "IOT_GATEWAY", label: getLabel("IOT_GATEWAY"), icon: getIconElement("IOT_GATEWAY") },
      { value: "IOT_OTHER", label: getLabel("IOT_OTHER"), icon: getIconElement("IOT_OTHER") },
    ],
  },
];

const OTHER_UNKNOWN_TYPE: SystemTypeOption = {
  value: "OTHER",
  label: "Other/Unknown",
  icon: <HelpCircle />,
};

interface SystemTypeSelectorProps {
  title?: React.ReactNode;
  compact?: boolean;
  className?: string;
  value?: string;
  onChange?: (value: string) => void;
}

export function SystemTypeSelector({
  title = "System Type",
  compact = false,
  className,
  value,
  onChange,
}: SystemTypeSelectorProps) {
  const [searchQuery, setSearchQuery] = React.useState("");

  // Filter categories and types based on search query
  const filteredCategories = React.useMemo(() => {
    if (!searchQuery.trim()) {
      return SYSTEM_CATEGORIES;
    }

    const query = searchQuery.toLowerCase().trim();
    
    return SYSTEM_CATEGORIES.map((category) => ({
      ...category,
      types: category.types.filter((type) =>
        type.label.toLowerCase().includes(query)
      ),
    })).filter((category) => category.types.length > 0);
  }, [searchQuery]);

  // Check if Other/Unknown matches
  const showOtherUnknown = React.useMemo(() => {
    if (!searchQuery.trim()) return true;
    return OTHER_UNKNOWN_TYPE.label.toLowerCase().includes(searchQuery.toLowerCase().trim());
  }, [searchQuery]);

  const handleClear = () => {
    setSearchQuery("");
  };

  return (
    <div
      className={cn(
        "flex h-full w-full flex-col items-start",
        { "flex-col flex-nowrap gap-4": compact },
        className
      )}
    >
      <div
        className={cn(
          "flex w-full flex-col items-start gap-4 border-b border-solid border-neutral-border px-6 py-6",
          { "px-0 py-0": compact }
        )}
      >
        <div className="flex w-full items-center gap-4">
          {title ? (
            <span
              className={cn(
                "grow shrink-0 basis-0 text-heading-3 font-heading-3 text-default-font",
                { "text-caption-bold font-caption-bold": compact }
              )}
            >
              {title}
            </span>
          ) : null}
        </div>
        <div className="flex w-full items-center gap-2">
          <TextField
            className="h-auto grow shrink-0 basis-0"
            variant="filled"
            label=""
            helpText=""
            icon={<Search />}
          >
            <TextField.Input
              placeholder="Search system types..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </TextField>
          <IconButton icon={<Eraser />} onClick={handleClear} />
        </div>
      </div>
      <div
        className={cn(
          "flex w-full flex-col items-start px-6 py-6 overflow-auto",
          { "px-0 py-0": compact }
        )}
      >
        <RadioCardGroup
          className="h-auto w-full flex-none"
          value={value}
          onValueChange={onChange}
        >
          <div className="flex grow shrink-0 basis-0 flex-col items-start gap-4">
            {/* Other/Unknown option */}
            {showOtherUnknown && (
              <div className="flex w-full items-start gap-2">
                <RadioCardGroup.RadioCard
                  className="h-16 w-40 flex-none"
                  hideRadio={true}
                  value={OTHER_UNKNOWN_TYPE.value}
                >
                  <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                    <HelpCircle className="text-body font-body text-default-font" />
                    <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                      {OTHER_UNKNOWN_TYPE.label}
                    </span>
                  </div>
                </RadioCardGroup.RadioCard>
              </div>
            )}

            {/* Category accordions */}
            {filteredCategories.map((category) => (
              <div
                key={category.id}
                className="flex w-full flex-col items-start rounded-md bg-neutral-50"
              >
                <Accordion
                  trigger={
                    <div className="flex w-full items-center gap-4 px-2 py-2">
                      <IconWithBackground
                        size={compact ? "small" : "medium"}
                        icon={category.icon}
                        bevel={false}
                      />
                      <span
                        className={cn(
                          "grow shrink-0 basis-0 text-heading-3 font-heading-3 text-default-font",
                          { "text-caption-bold font-caption-bold": compact }
                        )}
                      >
                        {category.label}
                      </span>
                      <Badge variant="neutral">{category.types.length}</Badge>
                      <Accordion.Chevron />
                    </div>
                  }
                  defaultOpen={searchQuery.trim() !== "" || !compact}
                >
                  <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2 px-2 py-2">
                    <div className="flex grow shrink-0 basis-0 flex-wrap items-center gap-2">
                      {category.types.map((type) => (
                        <RadioCardGroup.RadioCard
                          key={type.value}
                          className="h-16 w-40 flex-none"
                          hideRadio={true}
                          value={type.value}
                        >
                          <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                            <span className="text-body font-body text-default-font">
                              {type.icon}
                            </span>
                            <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                              {type.label}
                            </span>
                          </div>
                        </RadioCardGroup.RadioCard>
                      ))}
                    </div>
                  </div>
                </Accordion>
              </div>
            ))}

            {/* No results message */}
            {!showOtherUnknown && filteredCategories.length === 0 && (
              <div className="flex w-full items-center justify-center py-8">
                <span className="text-body font-body text-subtext-color">
                  No system types match "{searchQuery}"
                </span>
              </div>
            )}
          </div>
        </RadioCardGroup>
      </div>
    </div>
  );
}
