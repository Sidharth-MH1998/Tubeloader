# Tubeloader

A self-hosted YouTube video and audio downloader with a simple web interface.

- **Video with sound:** MP4 with video and audio together.
- **Audio only:** MP3, M4A, WAV, FLAC, or Opus; adjustable MP3 bitrate.
- **Both files:** a video with sound and a separate audio file.
- Video resolution limits, a download queue, progress, and file links.

The Docker image includes Python, FFmpeg, and Deno. No Python or JavaScript
installation is needed on your server. You need a Linux server with Docker
Engine and Docker Compose v2, or a Portainer **Docker Standalone** environment.

> Public source, private service: this app has no login. Run it only on a trusted
> home network or localhost. Everyone with network access can use it and access
> listed downloads. Do not expose port 8765 to the Internet.

## Deploy from Git in Portainer

This path uses a **public Git repository** and builds the image on your Docker
server. No image registry account or GitHub Actions run is required. It is not a
Docker Swarm stack. The server must have Internet access to Git, container
registries, package repositories, and YouTube.

1. Upload this clean repository to your Git provider. Keep `.env` and credentials
   out of Git. Use the normal HTTPS clone URL, without an embedded token.
2. In Portainer select your **Docker Standalone** environment.
3. Open **Stacks → Add stack → Repository** and name it `tubeloader`.
4. Enter your repository URL and branch reference (for example `refs/heads/main`).
5. Set **Compose path** to `compose.portainer.yaml`.
6. Add these **Environment variables** in Portainer:

| Variable | Value |
| --- | --- |
| `TUBELOADER_GIT_URL` | Your public HTTPS Git clone URL, such as `https://github.com/YOUR_ACCOUNT/tubeloader.git#main` |
| `TUBELOADER_BIND_IP` | Your server's private LAN IPv4 address |
| `TUBELOADER_SERVER_HOST` | The same IP address, without `http://` or a port |
| `TUBELOADER_PORT` | `8765`, or another unused port |

7. Click **Deploy the stack**. The first build downloads dependencies and can take
   several minutes. Wait for the container to show **healthy**.
8. Open `http://YOUR_SERVER_IP:8765` from a device on that network.

The repository URL appears twice intentionally: Portainer fetches the stack
definition, and Docker uses `TUBELOADER_GIT_URL` as a remote build context. This
avoids depending on Portainer's local checkout directory or Business Edition
relative bind-mount support. Keep both references on the same branch/tag/commit.
For a reproducible deployment, use a commit ID after `#` in the build URL.

If using another external port, change `TUBELOADER_PORT` and use that port in the
browser. The container itself always listens on 8765. If using a hostname in your
browser, set `TUBELOADER_SERVER_HOST` to that hostname instead of the IP.

**Do not use a Git credential in the build URL.** This documented method is for
public repositories. Private repositories require a separately configured,
authenticated build process.

## Deploy with Docker Compose

Clone the repository and enter its directory:

```sh
git clone https://github.com/YOUR_ACCOUNT/tubeloader.git
cd tubeloader
cp .env.example .env
```

Edit `.env`. For LAN access, set `TUBELOADER_BIND_IP` and
`TUBELOADER_SERVER_HOST` to your server's private IP. Without changes the
application is only reachable from the server at `http://127.0.0.1:8765`.

```sh
docker compose up -d --build
docker compose ps
docker compose logs --tail=50
```

There is no hardcoded personal IP, username, folder, or image-registry account.
Consider a DHCP reservation so the server's LAN address stays the same.

## Always running

`restart: unless-stopped` restarts the container after crashes and Docker daemon
restarts. It does not restart a container you explicitly stopped, and an
`unhealthy` health check alone does not cause a restart. Docker must start at boot
and the server must stay powered on.

On a Debian server with systemd, if Docker is installed but not enabled:

```sh
sudo systemctl enable --now docker
```

No SSH tunnel or open terminal is required for the configured LAN deployment.

## Storage and limits

Downloads are saved in a Docker named volume mounted at `/data`, under
`/data/downloads`. The process runs as UID/GID 10001. Default named volumes get
their initial ownership from the image. No host path or Docker socket is mounted.

Restarting/recreating the container preserves the volume. Keep the same stack
name to keep using the same stack-scoped volume. **Do not remove the volume or
run `docker compose down -v` unless you intend to erase the downloads.**

The queue/file links are held in memory and disappear on restart; files remain
in the volume. This release has no persistent library browser or automatic
cleanup. Back up the volume and monitor its disk use.

| Setting | Default | Meaning |
| --- | --- | --- |
| `TUBELOADER_MAX_DURATION` | `7200` | Maximum duration in seconds per video |
| `TUBELOADER_MAX_DOWNLOAD_MB` | `2048` | Approximate maximum downloaded bytes per stream, in MiB |
| `TUBELOADER_MIN_FREE_MB` | `1024` | Minimum free space to start/continue, in MiB |

Set these in Portainer or `.env`; all must be positive integers. Defaults also
limit the container to 2 GiB RAM and 128 processes, with rotating logs. Merging
and conversion can temporarily need much more disk space than one stream.
These guards are not a filesystem quota or a guarantee against disk exhaustion.
No live/upcoming streams, playlists, or channel downloads are supported by the
web interface. The CLI retains its separate batch/playlist functionality.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Build says `TUBELOADER_GIT_URL` is missing | Add the public clone URL in Portainer's environment variables. |
| Cannot find repository | Confirm it is public and that the branch/ref exists. |
| Cannot assign requested address | Bind IP must actually belong to the Docker host. |
| Port already allocated | Stop the old app/service, or select another external port. |
| `403 Invalid host` | Browser hostname/IP must match `TUBELOADER_SERVER_HOST`; check the external port too. |
| Browser cannot connect | Check container health, LAN address, host firewall, and Wi-Fi client isolation. |
| Permission denied under `/data` | Use the provided named volume. A custom bind mount must be writable by UID/GID 10001. Do not solve this by running as root. |
| Container restarts | Read Portainer logs; check memory, output permissions, runtime checks, and invalid environment values. |
| Healthy but download fails | Health checks verify the HTTP server, not YouTube connectivity. Check logs, disk space, source availability, and yt-dlp updates. |
| YouTube asks for sign-in or blocks the server IP | This can happen on hosting providers. No cookies or account credentials are included. Do not commit them to Git. |
| File links disappear after reboot | Expected: queue is in memory; media is still in the volume. |

Firewall rules should allow the chosen port only from your trusted LAN. Do not
enable router Internet port forwarding. Docker port publishing interacts with
host firewalls; review your Docker host's firewall setup instead of assuming a
generic firewall rule protects the published port.

## Updates

Stop/finish active downloads before updating. In Portainer pull the updated Git
stack and rebuild/redeploy. With the CLI:

```sh
git pull
docker compose build --pull
docker compose up -d
```

The named volume persists. Refresh the page after restart to get a new session
token. If a rebuild does not pick up a changed dependency, rebuild without cache.
The pinned yt-dlp version and Deno image tag should be reviewed and updated when
YouTube changes or security fixes are released; Dependabot configuration is
included to propose updates on GitHub.

## Public Git checklist

Upload only the files from this clean repository. Do not upload a previous
project folder or its Git history.

- Include hidden files such as `.gitignore`, `.dockerignore`, `.env.example`,
  and `.github/`.
- Exclude `.env`, virtual environments, logs, downloads, cookies, backup files,
  generated installers, and private keys.
- Review `git status` and the staged diff before pushing.
- If a secret was ever committed elsewhere, ignoring/deleting its file does not
  remove it from history: revoke it and clean that history separately.

Create a new empty repository on your Git provider, then:

```sh
git init -b main
git add .
git diff --cached --stat
git commit -m "Initial Tubeloader release"
git remote add origin https://github.com/YOUR_ACCOUNT/tubeloader.git
git push -u origin main
```

Git commits use your configured author identity. Choose a provider's no-reply
email if you do not want your personal email published.

## Development and verification

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
docker compose config --quiet
docker compose build
```

GitHub CI runs Python tests, builds the Linux amd64 image, and checks container
health and the non-root user. Tests do not contact YouTube. Docker runtime
verification must pass in CI or on your server before treating a deployment as
verified. Native Linux arm64 builds use the same Dockerfile but need separate
verification.

## License and upstream software

Tubeloader's application code is MIT licensed; see `LICENSE`. Third-party
components retain their own licenses, including yt-dlp, its EJS component,
FFmpeg, Python, and Deno. Use the service only for content you are authorized
to download.

References: [Portainer Git stacks](https://docs.portainer.io/user/docker/stacks/add),
[Docker Compose build contexts](https://docs.docker.com/reference/compose-file/build/),
[Deno Docker images](https://docs.deno.com/runtime/reference/docker/).

