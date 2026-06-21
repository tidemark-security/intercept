# Store Template Tasks as JSONB Documents

Case Templates have relational columns for template-level metadata such as title, description, lifecycle status, case tags, and audit ownership, while their Template Tasks are stored as a JSONB document. This matches the existing Intercept pattern of storing alert, case, and task timelines as JSONB documents, keeps template authoring simple, and avoids premature per-task identity/versioning until the product needs it.
