# Dependency and model bill of materials

The machine-readable inventory is [`dependency-bom.json`](dependency-bom.json), validated against
`schemas/dependency-bom.schema.json` and copied into every run.

M2A/M2B use the locally installed FFmpeg/ffprobe 6.1.1-3ubuntu5 build, jsonschema 4.26.0, and DejaVu Sans
2.37-8. Exact observed executable/font hashes and locally reported licenses are recorded. The
FFmpeg binary reports GPL-2.0-or-later because this Ubuntu build enables GPL components. License
descriptions are inventory facts, not legal advice.

No checkpoint or model weight is installed, approved, downloaded, or used. The checkpoint list is
therefore empty. Future learned dependencies must be optional, separately licensed, checksum-bound,
and added before installation.

Compatibility actually exercised in this repository:

- Core and M2A: CPython 3.14.3 on Linux x86-64.
- Declared core range: Python 3.11 or newer.
- Optional ML/model matrix: untested and empty; no compatibility claim is made.

The uv lock records Python package transitives. A later release audit must enumerate those
transitives separately if the release policy requires a full software SBOM rather than the current
perception/model BOM.

The operator-approved local M2B path uses Ubuntu `tesseract-ocr` and `libtesseract5` 5.3.4-1build5
with Leptonica 1.82.0 and `tesseract-ocr-eng` 1:4.1.0-2. Exact executable, shared-library,
English-data, installed OSD-data, and local license-file hashes are recorded in the machine-readable
BOM and each fresh run's OCR dependency report. `TESSDATA_PREFIX` was unset, so the distribution
default `/usr/share/tesseract-ocr/5/tessdata` was used. OSD data is inventoried but not selected by
the frozen eng-only configuration. The checkpoint inventory remains empty; Tesseract language data
is third-party pretrained data, not AV-Atlas training output.

The M2B controlled-baseline release reverified these identities without installing anything. Pilot
preparation adds no package, model, language data, or checkpoint. The M2C decision memo is research
planning only; its candidate classes are not approved BOM components. The checkpoint inventory
remains empty.

M2B.1 separates declared project metadata, measured current-host inventory, package-manager claims,
and hashes computed directly over installed files. Ordinary run exports use a hash-derived OCR
identity plus sanitized path classes and basenames. A package license is not hardcoded when its
installed metadata cannot be read or does not identify it; uncertainty is reported instead.
