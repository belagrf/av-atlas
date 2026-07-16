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

M2B.2 adds no third-party dependency, checkpoint, or language data. Its copy, hashing, file-mode,
descriptor, synchronization, and advisory-lock controls use the Python standard library and local
operating-system interfaces. The private descriptor-relative recovery path was exercised on Linux;
platforms without POSIX-style directory descriptors or `flock` fail closed before acquisition. The
machine-readable dependency inventory and empty checkpoint list are
therefore unchanged.

The M2B.2 source-review correction uses reviewed controls already provided by the inventoried local
FFmpeg/libavformat build: an explicit `file` protocol whitelist, a forced and whitelisted
`matroska` demuxer for authorized source snapshots, and a forced `png_pipe` demuxer for generated
OCR frames. The supported-format narrowing is AV-Atlas policy, not a new dependency or a claim that
native parsing is sandboxed. No network component, model, checkpoint, language data, or package was
added.

M2B.3 inventories the already installed, system-class Bubblewrap dependency without installing or
downloading it. The measured executable basename is `bwrap`, version `bubblewrap 0.9.0`, size
72,160 bytes, SHA-256
`52231e1caf55bcbc667b269f49c63599a6f7db4767ae6a039580d0ff853db712`. Ubuntu package metadata
reports `bubblewrap` `0.9.0-1ubuntu0.1` for `amd64`, source package/version
`bubblewrap 0.9.0-1ubuntu0.1`, and license `LGPL-2+` from installed copyright metadata with SHA-256
`229a402fddba5c81005950f28de162359383cba731f5b859b8f82a03c338bf01`. The sanitized dependency
identity is `85905bce616b6f7327efca1c7196f4758752561a0c41bca23401c1fee4ece3f2`.

The versioned Bubblewrap profile is `av-atlas-bubblewrap-pilot/1.0.0`, with profile SHA-256
`b69562979857a6c33d59d7db88ce8a14a7ceaa46504539284edc86d0d0e07a0a`. The hash binds the exact
static argument prefix/suffix and fixed tool paths used by the runner. Its current-host namespace
smoke test passed without network access. That smoke test is a dependency/capability measurement,
not the complete synthetic-pilot gate and not evidence of real-media safety. Pilot mode fails
closed if Bubblewrap is missing, changed, or incapable. AV-Atlas does not install it; on this
Ubuntu host the minimal operator command would be `sudo apt-get install bubblewrap`.

Bubblewrap is not a model, checkpoint, trained weight, or inference service. The checkpoint
inventory remains empty. `RLIMIT_NPROC` applies to the host real UID before namespace entry and is
therefore a bounded host-UID control, not a precise per-sandbox process counter. The sandbox's
minimum read-only host runtime and kernel namespace implementation remain part of the trusted
computing base.
