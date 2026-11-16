# Release validation

Prepared for public Git sharing on 2026-11-16.

- Nine non-network Python tests passed locally.
- Python application source syntax checked.
- Compose, Portainer, Dependabot, and GitHub Actions YAML parsed successfully.
- Local and Portainer service definitions agree apart from their build context.
- Public output uses an explicit file allowlist; no Git history, credentials,
  environment files, logs, media, backups, virtual environments, or installers
  are copied from the previous project.
- A text scan checked for known personal identifiers and common credential
  formats. This is not an exhaustive security audit or dependency CVE scan.

Not verified here:

- The local HTTP integration test was blocked by sandbox socket restrictions;
  approval review could not run because of a usage limit.
- No Docker engine is available on the build machine, so no image build,
  container startup, or Portainer deployment was executed here.
- No live YouTube download was performed for this release.

The included GitHub workflow executes the full test suite and Docker smoke
checks after upload. Confirm it passes, then verify deployment on your server.
No software can be guaranteed fail-safe. Keep the service on a trusted private
network and read SECURITY.md before use.
