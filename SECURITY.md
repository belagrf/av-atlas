# Security policy

AV-Atlas processes hostile media and invokes native parsers. Its current safeguards are
defense-in-depth, not an operating-system sandbox. Use only local media you are authorized to
process, apply resource isolation for adversarial inputs, and keep FFmpeg and Tesseract patched.

## Reporting a vulnerability

Use GitHub's private vulnerability-reporting feature for this repository when available. If it is
unavailable, open a minimal public issue requesting a private maintainer contact; do not include an
exploit, secret, private media, personal data, or sensitive path in the issue. Do not upload sample
media without explicit authorization.

Reports should identify the affected commit, impact, reproduction preconditions, and whether a
crafted media file is involved. Maintainers will acknowledge reports when capacity permits; no
response-time guarantee is currently offered.

No repository secret is required by CI. Media text, OCR, subtitles, metadata, and filenames are
untrusted data and must never become instructions or executable commands.
