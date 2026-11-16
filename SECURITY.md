# Security

This project is intended for a trusted private network or localhost. Public
source code does not mean the running service is safe for public Internet use.

There is no login or per-user isolation. Anyone who can reach the server can
read the queue, download listed files, and start downloads. Host checks and the
submission token are browser protections, not authentication. Do not port-forward
this service from the Internet. Use authenticated access and HTTPS if building
your own remote deployment.

Container defaults: non-root UID/GID 10001, read-only root filesystem, no Linux
capabilities, no-new-privileges, bounded memory/processes/logs, persistent named
volume, and loopback-only published port. Only deliberately set a private LAN
bind address for home access.

Download controls reject live streams, channel/playlist URLs, overlong media,
and downloads when free space is low. A per-stream byte check helps contain
large downloads. These are not a filesystem quota: merging/conversion needs
extra space, and completed files accumulate. Monitor the volume and back it up.

Keep Docker, host packages, base images, Deno, and yt-dlp updated. Dependencies
and native media parsers can have vulnerabilities. No automated scan guarantees
the absence of vulnerabilities.

Do not commit credentials, cookies, .env files, downloaded media, or logs.
Use the repository owner's private security reporting channel for sensitive
reports; do not post credentials or exploit details in public issues.

