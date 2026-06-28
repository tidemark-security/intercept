# Store Runbook Tasks as JSONB Documents

Case Runbooks have relational columns for runbook-level metadata such as title, description, lifecycle status, case tags, and audit ownership, while their Runbook Tasks are stored as a JSONB document. This matches the existing Intercept pattern of storing alert, case, and task timelines as JSONB documents, keeps runbook authoring simple, and avoids premature per-task identity/versioning until the product needs it.
