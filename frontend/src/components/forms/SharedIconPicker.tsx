import { useEffect, useMemo, useRef, useState } from "react";
import { TextField } from "@/components/forms/TextField";
import { cn } from "@/utils/cn";
import { getAvailableIconNames, getIconComponent } from "@/utils/iconMapping";

export function SharedIconPicker({ value, onChange, className }: {
  value: string;
  onChange: (icon: string) => void;
  className?: string;
}) {
  const iconDropdownRef = useRef<HTMLDivElement>(null);
  const [iconSearchTerm, setIconSearchTerm] = useState("");
  const [showIconDropdown, setShowIconDropdown] = useState(false);
  const allIconNames = useMemo(() => getAvailableIconNames(), []);
  const filteredIcons = useMemo(
    () => allIconNames.filter((name) => name.toLowerCase().includes(iconSearchTerm.toLowerCase())),
    [allIconNames, iconSearchTerm],
  );

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (iconDropdownRef.current && !iconDropdownRef.current.contains(event.target as Node)) {
        setShowIconDropdown(false);
        setIconSearchTerm("");
      }
    };

    if (showIconDropdown) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showIconDropdown]);

  return (
    <div className={cn("flex w-full flex-col gap-2", className)}>
      <span className="text-body-bold font-body-bold text-default-font">Icon</span>
      <div className="relative" ref={iconDropdownRef}>
        <button
          type="button"
          className="flex w-full items-center gap-2 rounded-md border border-solid border-neutral-border bg-default-background px-3 py-2 text-left hover:border-neutral-400"
          aria-label={`Icon ${value}`}
          aria-expanded={showIconDropdown}
          onClick={() => setShowIconDropdown((open) => !open)}
        >
          <span className="text-[20px] text-neutral-700">{getIconComponent(value)}</span>
          <span className="flex-1 text-body font-body text-default-font">{value}</span>
        </button>

        {showIconDropdown ? (
          <div className="absolute z-10 mt-1 w-full rounded-md border border-solid border-neutral-border bg-default-background shadow-lg">
            <div className="p-2">
              <TextField className="h-auto w-full">
                <TextField.Input
                  placeholder="Search icons..."
                  value={iconSearchTerm}
                  onChange={(event) => setIconSearchTerm(event.target.value)}
                  onClick={(event) => event.stopPropagation()}
                />
              </TextField>
            </div>
            <div className="max-h-64 overflow-y-auto">
              {filteredIcons.map((iconName) => (
                <button
                  key={iconName}
                  type="button"
                  className="flex w-full items-center gap-3 px-4 py-2 text-left hover:bg-neutral-100"
                  onClick={() => {
                    onChange(iconName);
                    setShowIconDropdown(false);
                    setIconSearchTerm("");
                  }}
                >
                  <span className="text-[20px] text-neutral-700">{getIconComponent(iconName)}</span>
                  <span className="text-body font-body text-default-font">{iconName}</span>
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
