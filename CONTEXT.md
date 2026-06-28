# Intercept Case Management

Intercept helps analysts triage security alerts, escalate investigations into cases, and track investigation work through timelines and tasks.

## Language

**Case Template**:
A reusable incident-response structure that can be attached to a **Case** to guide expected investigation and response work for a class of incidents.
_Avoid_: Template, link template, playbook, response template

**Case Template Identifier**:
A durable reference to a **Case Template** used when analysts, integrations, or Triage Recommendations need to point at a specific template.
_Avoid_: Slug, catalog key, display name

**Case Template Library**:
The shared catalog where analysts, auditors, and admins can inspect **Case Templates** and their Template Tasks.
_Avoid_: Admin template settings, template manager

**Published Case Template**:
A **Case Template** that is available to apply to a **Case** or recommend from a **Triage Recommendation**.
_Avoid_: Active template, applicable template, enabled template

**Template Task**:
A real **Task** created from a **Case Template** and attached to a **Case** timeline after analyst confirmation or accepted recommendation.
_Avoid_: Ghost task, inline recommendation task, checklist item

**PICERL Stage**:
The single fixed incident-response stage associated with a **Template Task** or manually created **Task**: Preparation, Identification, Containment, Eradication, Recovery, or Lessons Learned.
_Avoid_: PICERL phase, stage band

**Relative Due Date Offset**:
An optional number of seconds on a **Template Task** that determines the created task's due date relative to when the **Case Template** is applied.
_Avoid_: SLA date, due date template, absolute due date

**Template Tag**:
A tag explicitly defined by a **Case Template** for the parent **Case** or by a **Template Task** for the created **Task**.
_Avoid_: Inherited tag, dynamic tag

**Triage Recommendation**:
An AI-generated assessment of an **Alert** that can suggest disposition, priority, ownership, follow-up actions, case escalation, or a **Case Template**.
_Avoid_: AI recommendation, recommendation

**Recommended Action**:
A specific follow-up action suggested by a **Triage Recommendation** as an alternative to recommending a **Case Template** when no suitable template applies to the alert.
_Avoid_: Specific action, suggested task, AI task

## Example Dialogue

Analyst: "This DLP alert should become a case. Which Case Template should I attach?"

Lead: "The Triage Recommendation suggests the DLP Case Template. Accept it if the alert should become a case with that response structure."

Analyst: "What if no Case Template fits?"

Lead: "Then the Triage Recommendation can include Recommended Actions instead."

Analyst: "Can I skip template work that does not apply?"

Lead: "Yes. Review the Template Tasks before applying the Case Template, uncheck anything irrelevant, and the accepted tasks become real case tasks."
