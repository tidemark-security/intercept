import { describe, expect, it } from "vitest";

import {
  FALLBACK_LINK_TEMPLATE_ICON,
  getAvailableIconNames,
  normalizeLinkTemplateIconName,
} from "./iconMapping";

describe("iconMapping", () => {
  it("pins BoxSelect as the default icon and includes custom plus lucide icon names", () => {
    const iconNames = getAvailableIconNames();

    expect(iconNames[0]).toBe(FALLBACK_LINK_TEMPLATE_ICON);
    expect(iconNames).toContain("Search");
    expect(iconNames).toContain("ShieldCheck");
    expect(iconNames).toContain("VirusTotalIcon");
  });

  it("normalizes unavailable icon names to BoxSelect while preserving custom and lucide names", () => {
    expect(normalizeLinkTemplateIconName("DefinitelyNotALucideIcon")).toBe(
      FALLBACK_LINK_TEMPLATE_ICON,
    );
    expect(normalizeLinkTemplateIconName("Search")).toBe("Search");
    expect(normalizeLinkTemplateIconName("VirusTotalIcon")).toBe("VirusTotalIcon");
  });
});
