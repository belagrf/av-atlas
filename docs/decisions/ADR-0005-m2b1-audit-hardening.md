# ADR-0005: M2B.1 audit hardening contracts

- Status: proposed in `audit/m2b1-hardening`
- Date: 2026-07-14
- Milestone: M2B.1 source-audit hardening; no M2C implementation

## Decision

Persisted rights declarations use one schema, self-checksum, source, permission, expiry, retention,
and run-linkage validation path before resume or derivative processing. The self-hash is an
integrity checksum, not an authenticated signature or proof of who made a declaration.

Adapter-results 1.1 adds `partial_success` and balanced attempted, successful, failed, timed-out,
unsupported, and emitted counts. Successful observations from a partially failed adapter remain
valid evidence. Adapter-results 1.0 and OCR frame-results 1.0 remain validation-compatible.

Configuration remains JSON syntax in `.yaml` files but is validated against a complete strict
schema before construction. No scalar coercion is allowed. Raw-frame retention stays false-only
because retained media derivatives need a separately designed rights and deletion model.

Raw OCR observations remain immutable. A derived `ocr_text_tracks.json` groups repeated normalized
text only within a shot, within the configured gap, and with spatial compatibility while preserving
every member and frame reference. Event schema 1.1 records every generated chunk overlapping an
event; event schema 1.0 remains readable.

Ordinary OCR dependency exports use a hash identity, basename, and path class. Full paths require
an explicitly local/private diagnostic. Package-manager license claims are separated from metadata
actually read and files actually hashed.

## Consequences

New runs use additive 1.1 contracts and a derived OCR text-track artifact. Accepted M2B v1 inputs,
outputs, tag, and release are not rewritten. A later patch release may carry these changes after
review; this assignment creates no tag or release. No M2C capability is introduced.
