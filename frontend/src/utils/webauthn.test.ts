import { describe, expect, it } from "vitest";

import { classifyPasskeyPromptError } from "./webauthn";

describe("classifyPasskeyPromptError", () => {
  it("distinguishes cancellation, credential unavailability, and unexpected failures", () => {
    expect(classifyPasskeyPromptError(new DOMException("cancelled", "AbortError"))).toBe(
      "cancelled",
    );
    expect(classifyPasskeyPromptError(new Error("Passkey request was cancelled"))).toBe(
      "cancelled",
    );
    expect(classifyPasskeyPromptError(new DOMException("unavailable", "NotAllowedError"))).toBe(
      "unavailable",
    );
    expect(classifyPasskeyPromptError(new Error("transport failure"))).toBe("failed");
  });
});
