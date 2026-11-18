# Attachment lifecycle

Alerts, cases and tasks share the upload and download handlers in
`backend/app/api/route_utils.py`. The timeline item stores the final object key,
the staging key and the analyst's metadata.

1. Requesting a presigned upload URL creates an `UPLOADING` attachment with the
   filename, MIME type, size, uploader, description, timestamp and tags. The
   browser uploads the bytes to the staging key.
2. The uploader requests completion. The handler checks the object key prefixes,
   size, checksum and MIME type, copies the object to the final key and prepares
   any companion case email. The service checks the expected status and staging
   key under the entity row lock. It commits the hash, `COMPLETE` status,
   explicit null staging key and companion item together. Staging cleanup runs
   after commit. Marking an upload `FAILED` retains the staging key.
3. Analysts can edit the description, timestamp, tags and display flags.
   The frontend omits `created_at` and nested replies from edit requests.
   The API allowlist excludes file properties, and the update service serializes
   only explicitly set attachment fields. At the shared merge point,
   `ATTACHMENT_STORAGE_FIELDS` preserves the stored file properties for all
   ordinary edits. Only the upload-status transition can write those fields on
   an in-progress item. Completed, failed and legacy items with no status keep
   their existing storage metadata.
4. Downloading requires a completed attachment and an existing object under the
   item's expected prefix. The signed URL uses the stored filename.
5. Removing the timeline item commits the database change before attempting to
   delete the final object. Deleting an unfinished item can leave a staged object.

The cross-entity lifecycle tests in
`backend/tests/integration/test_attachment_lifecycle_api.py` read the stored
item after each transition. The tests in
`backend/tests/integration/test_timeline_mutation_locking.py` cover concurrent
mutations, rollback and the timing of object cleanup.
