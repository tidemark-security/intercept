import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TimelineFormProvider } from "@/contexts/TimelineFormContext";

const {
  aliasResults,
  setAliasQuery,
  setFormState,
  handleFormSubmit,
  handleClear,
} = vi.hoisted(() => ({
  aliasResults: [
    {
      id: 1,
      provider_id: "google",
      entity_type: "user",
      canonical_value: "john@example.com",
      canonical_display: "John Doe",
      alias_value: "jdoe",
      alias_type: "samaccountname",
      attributes: {},
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
    {
      id: 2,
      provider_id: "google",
      entity_type: "user",
      canonical_value: "john@example.com",
      canonical_display: "John Doe",
      alias_value: "john.doe@example.com",
      alias_type: "email_alias",
      attributes: {},
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
    {
      id: 3,
      provider_id: "google",
      entity_type: "user",
      canonical_value: "john@example.com",
      canonical_display: "John Doe",
      alias_value: "johnny",
      alias_type: "display_name",
      attributes: {},
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
    {
      id: 4,
      provider_id: "google",
      entity_type: "user",
      canonical_value: "john@example.com",
      canonical_display: "John Doe",
      alias_value: "john-doe-legacy",
      alias_type: "directory_id",
      attributes: {},
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
    {
      id: 5,
      provider_id: "google",
      entity_type: "user",
      canonical_value: "jane@example.com",
      canonical_display: "Jane Smith",
      alias_value: "jsmith",
      alias_type: "samaccountname",
      attributes: {},
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  ],
  setAliasQuery: vi.fn(),
  setFormState: vi.fn(),
  handleFormSubmit: vi.fn(),
  handleClear: vi.fn(),
}));

vi.mock("@/hooks", () => ({
  useEnrichmentAliases: vi.fn(() => ({
    data: aliasResults,
    isFetching: false,
  })),
}));

vi.mock("@/hooks/useSearchCore", () => ({
  useSearchCore: vi.fn(() => ({
    query: "john",
    setQuery: setAliasQuery,
    debouncedQuery: "john",
  })),
}));

vi.mock("@/hooks/useTimelineForm", () => ({
  useTimelineForm: vi.fn(() => ({
    formState: {
      actorType: "internal",
      timestamp: "",
      tags: [],
      userId: "",
      characteristics: [],
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
    },
    setFormState,
    handleSubmit: handleFormSubmit,
    handleClear,
    isSubmitting: false,
    itemType: "actor",
    initialFlagHighlight: undefined,
  })),
}));

vi.mock("@/components/timeline/TimelineFormLayout", () => ({
  TimelineFormLayout: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

vi.mock("@/components/forms/TextField", () => {
  const TextField = ({ label, children }: { label?: string; children: React.ReactNode }) => (
    <label>
      {label ? <span>{label}</span> : null}
      {children}
    </label>
  );

  TextField.Input = (props: React.InputHTMLAttributes<HTMLInputElement>) => (
    <input {...props} />
  );

  return { TextField };
});

vi.mock("@/components/forms/TextArea", () => {
  const TextArea = ({ label, children }: { label?: string; children: React.ReactNode }) => (
    <label>
      {label ? <span>{label}</span> : null}
      {children}
    </label>
  );

  TextArea.Input = (
    props: React.TextareaHTMLAttributes<HTMLTextAreaElement>,
  ) => <textarea {...props} />;

  return { TextArea };
});

vi.mock("@/components/buttons/ToggleGroup", () => {
  const ToggleGroup = ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  );

  ToggleGroup.Item = ({ children }: { children: React.ReactNode }) => (
    <button type="button">{children}</button>
  );

  return { ToggleGroup };
});

vi.mock("@/components/forms/RadioCardGroup", () => {
  const RadioCardGroup = ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  );

  RadioCardGroup.RadioCard = ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  );

  return { RadioCardGroup };
});

vi.mock("@/components/forms/TagsManager", () => ({
  TagsManager: () => null,
}));

vi.mock("@/components/forms/DateTimeManager", () => ({
  DateTimeManager: () => null,
}));

vi.mock("@/components/forms/Slider", () => ({
  Slider: () => null,
}));

import { AddActorForm } from "./ActorForm";

describe("AddActorForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("merges aliases by primary user and selects the canonical user id", async () => {
    const user = userEvent.setup();

    render(
      <TimelineFormProvider
        alertId={1}
        itemType="actor"
        editMode={false}
        onSuccess={vi.fn()}
        onCancel={vi.fn()}
      >
        <AddActorForm />
      </TimelineFormProvider>,
    );

    expect(screen.getByText("Primary users")).toBeInTheDocument();
    expect(screen.getAllByText("John Doe")).toHaveLength(1);
    expect(screen.getByText("Primary ID: john@example.com")).toBeInTheDocument();
    expect(screen.getByText("4 matches")).toBeInTheDocument();
    expect(screen.getByText("jdoe")).toBeInTheDocument();
    expect(screen.getByText("john.doe@example.com")).toBeInTheDocument();
    expect(screen.getByText("johnny")).toBeInTheDocument();
    expect(screen.getByText("+1 more aliases")).toBeInTheDocument();
    expect(screen.getByText("Jane Smith")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /John Doe/i }));

    expect(setFormState).toHaveBeenCalledWith(
      expect.objectContaining({ userId: "john@example.com" }),
    );
    expect(setAliasQuery).toHaveBeenCalledWith("john@example.com");
  });
});