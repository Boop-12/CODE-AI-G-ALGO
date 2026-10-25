# GNK Algo: Windows laptop -> GitHub -> Oracle Ubuntu -> Cloudflare

Target domain: **gnkalgo.com**. Origin: **130.210.34.12**. Local folder: **D:\CODE-AI-G-ALGO**. Repository: https://github.com/Boop-12/CODE-AI-G-ALGO.git .

Status (25 October 2026): deployed on Oracle Ubuntu at /opt/CODE-AI-G-ALGO. Public root/www HTTPS and API readiness were verified; app.gnkalgo.com redirects to the canonical domain. Docker Nginx uses the renewed Let's Encrypt certificate for all three names; Certbot renewal simulation passed. Use SERVICE_COMMANDS.md for this existing installation's start/stop/rebuild/update commands. The setup instructions below also describe a fresh-install example layout.

## 1. Test on the Windows laptop

Start Docker Desktop with the Linux engine. From PowerShell:

```powershell
Set-Location D:\CODE-AI-G-ALGO
# Only create .env if it does not already exist.
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env and set a strong URL-safe POSTGRES_PASSWORD.
notepad .env
docker compose config --quiet
docker compose up --build -d --wait
Invoke-RestMethod http://localhost/api/ready
```

Open http://localhost . Register your own account with a 12+ character password. Create a paper order; verify it is pending; click Simulate fill; verify cash and positions. Try a sell, cancel, broker disconnect, and pause-all control. Check mobile width, dark mode, profile/consent and support requests.

Native development alternative (two PowerShell windows):

```powershell
Set-Location D:\CODE-AI-G-ALGO\backend
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:DATABASE_URL='sqlite+aiosqlite:///./local.db'
.\venv\Scripts\python.exe -m alembic upgrade head
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
Set-Location D:\CODE-AI-G-ALGO\frontend
npm ci
npm run dev
```

Open http://localhost:3000 . Native /api requests proxy to the local backend. SQLite is for local practice; production uses PostgreSQL. No broker or payment keys are needed.

Run checks:

```powershell
Set-Location D:\CODE-AI-G-ALGO\backend
.\venv\Scripts\python.exe -m pytest tests -q
Set-Location D:\CODE-AI-G-ALGO\frontend
npm run lint
npm run build
npm run typecheck
```

## 2. Put the reviewed local changes on GitHub

The folder initially had no Git metadata; it is now initialized and linked to your repository. The remote check returned no existing history. Check the final handoff for whether the upload succeeded. Never force-push over history.

For subsequent changes from this connected folder:

```powershell
Set-Location D:\CODE-AI-G-ALGO
git status --short
git switch -c gnkalgo-next-update
# Edit and test the application.
git add .
git diff --cached --stat
git diff --cached --check
git commit -m "Describe the reviewed GNK Algo update"
git push -u origin gnkalgo-next-update
```

Create a pull request against main. Review changes, run GNK Algo CI, then merge. GitHub authentication uses your own Git Credential Manager or GitHub CLI session. Never put a personal access token in a remote URL. The included CI uses a dedicated disposable PostgreSQL database for migrations and tests, plus frontend and container smoke checks. CI is not verified until its run completes successfully. The initial publication to an empty repository can create main directly; later updates should go through review.

## 3. Verify the Oracle instance and recover SSH access

In Oracle Cloud Console -> Compute -> Instances, confirm the instance is running, uses Ubuntu, has public IP 130.210.34.12, and is attached to a public subnet with an internet gateway/route. Confirm the SSH key installed at instance creation. Ubuntu images normally use ubuntu; confirm the actual image and account. Verify the host fingerprint against trusted console evidence before accepting a new host key.

```powershell
ssh -i "C:\path\to\your-instance-key" ubuntu@130.210.34.12
```

If publickey authentication fails, use Oracle console access or its documented recovery flow to install your public key. A key belonging to another instance will not work. Do not disable host-key verification.

On the server:

```bash
cat /etc/os-release
uname -m
free -h
df -h
```

Prefer an Ubuntu LTS image supported by Docker, with sufficient RAM/disk for Next builds and PostgreSQL. Size the VM after observing real build/runtime usage; the current instance capacity has not been measured. Both amd64 and arm64 base images are used, but the final containers must be tested on your instance architecture.

## 4. Configure OCI and Ubuntu networking

OCI Network Security Group/security list ingress:

- TCP 22 from your laptop public IP /32 (and the chosen CI deployment source, if enabling GitHub SSH deployments).
- TCP 443 from Cloudflare's current published proxy ranges once proxied; for initial troubleshooting, any broader access should be temporary and deliberate.
- TCP 80 if HTTP redirects are needed. It only redirects in production.
- Do not expose 3000, 8000, 5432 or 6379.

OCI routing, security rules and the Ubuntu firewall all need to permit the intended traffic. Docker-published ports can bypass UFW; use OCI NSGs and appropriate DOCKER-USER rules for container access control. Preserve SSH rules before changing firewall configuration. Do not flush Oracle's existing iptables rules.

## 5. Install Docker Engine and Git on Ubuntu

Follow Docker's official Ubuntu repository instructions. On a clean supported Ubuntu server:

```bash
sudo apt update
sudo apt install -y ca-certificates curl git openssl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
printf 'Types: deb\nURIs: https://download.docker.com/linux/ubuntu\nSuites: %s\nComponents: stable\nArchitectures: %s\nSigned-By: /etc/apt/keyrings/docker.asc\n' "$VERSION_CODENAME" "$(dpkg --print-architecture)" | sudo tee /etc/apt/sources.list.d/docker.sources
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu
```

Log out and SSH in again. Then:

```bash
docker version
docker compose version
```

Docker group membership grants root-equivalent container administration; use a dedicated trusted deploy account. Do not run installation blindly on a host with an existing Docker installation or application; inspect it first.

## 6. Clone the merged repository and configure secrets

For a private GitHub repository, create a server-specific read-only deploy key and add only its public half under GitHub repository Settings -> Deploy keys. Do not reuse your laptop/server login private key as the repository credential. Verify github.com's SSH host fingerprint using GitHub's published fingerprints.

```bash
sudo install -d -o ubuntu -g ubuntu /opt/gnkalgo
sudo install -d -o ubuntu -g ubuntu -m 700 /opt/gnkalgo/tls
cd /opt/gnkalgo
git clone https://github.com/Boop-12/CODE-AI-G-ALGO.git app
# For a private repository configured with a read-only deploy key, use the SSH URL instead.
cd app
git switch main
cp .env.production.example .env
chmod 600 .env
openssl rand -hex 32
openssl rand -hex 48
nano .env
```

Set POSTGRES_USER and POSTGRES_DB to the role and database used when the PostgreSQL volume was initialized. For a new volume, keep the template defaults (`postgres`); for an existing volume, inspect its configured role and database rather than assuming the defaults. Set POSTGRES_PASSWORD to the matching database password and SECRET_KEY to the second random value. Keep ENVIRONMENT=production, COOKIE_SECURE=true, ALLOWED_ORIGINS=https://gnkalgo.com,https://www.gnkalgo.com, TLS_DIR=/opt/gnkalgo/tls. Do not print .env in logs. Hex passwords avoid connection-URL escaping issues. Changing POSTGRES_USER, POSTGRES_DB, or POSTGRES_PASSWORD does not alter an existing database cluster; coordinate any credential or database changes with a verified backup.

## 7. Configure Cloudflare DNS and origin TLS

Add gnkalgo.com to your Cloudflare account, then set the registrar nameservers to the exact pair Cloudflare assigns. DNS changes require control of this domain; they have not been made here.

In Cloudflare DNS:

| Type | Name | Target | Proxy |
| --- | --- | --- | --- |
| A | @ | 130.210.34.12 | Proxied |
| CNAME | www | gnkalgo.com | Proxied |

Remove only conflicting old A/AAAA records after verifying they are not serving another intended origin. Do not add AAAA without a configured IPv6 origin.

Cloudflare SSL/TLS -> Origin Server -> Create Certificate: include gnkalgo.com and *.gnkalgo.com. Store its certificate at /opt/gnkalgo/tls/origin.pem and its private key at /opt/gnkalgo/tls/origin.key on the server. The Compose file mounts this folder read-only. Set owner/root permissions so the Nginx master can read them; keep the private key mode 600. Download the matching RSA/ECC Cloudflare Origin CA root certificate from the official Origin CA documentation into /opt/gnkalgo/tls/cloudflare-origin-ca.pem for the deployment script's local TLS check. Select the CA matching the issued certificate, not an unrelated browser CA file.

Set Cloudflare encryption to **Full (strict)** after origin TLS is installed. Set Always Use HTTPS. Do not use Flexible. Do not create cache-everything rules for /api; auth/account responses must bypass cache. Honor no-store response headers. Avoid JavaScript challenges on API endpoints. Configure trusted Cloudflare real-IP ranges before relying on per-user source-IP limits: the baseline Nginx limits use the connecting proxy IP, so users sharing an edge may share a rate bucket. Never trust arbitrary CF-Connecting-IP headers from unrestricted origins.

An Origin CA certificate is trusted by Cloudflare, not normal browsers making a direct-IP origin visit. This is expected. Track its expiry and renewal; do not enable strict TLS with a missing/expired origin certificate.

## 8. Deploy the paper MVP

```bash
cd /opt/gnkalgo/app
bash deploy/deploy.sh
docker compose -f docker-compose.yml -f docker-compose.production.yml ps
docker compose -f docker-compose.yml -f docker-compose.production.yml logs --tail=100 api web nginx
```

The script validates configuration, builds, waits for PostgreSQL, runs migrations, starts healthy services, validates Nginx and verifies local origin TLS using the Cloudflare CA at `tls/cloudflare-origin-ca.pem` (or `ORIGIN_CA_FILE`). The Compose configuration and backup script use POSTGRES_USER and POSTGRES_DB so they can target an existing initialized volume. Before the first migration on any pre-existing database, create and validate a backup, inspect its schema and migration version, and review DATABASE_DESIGN.md. The script does not claim public DNS success.

Create an administrator interactively (no default credentials):

```bash
docker compose exec api python -m app.bootstrap
```

Register normal customers from the website. No real broker credentials or payment credentials should be collected in this release.

## 9. Verify the public application

```bash
bash deploy/validate.sh
curl -I https://gnkalgo.com
```

On your laptop, open https://gnkalgo.com and repeat the paper round trip from step 1. Confirm /api/ready returns ready, cookies are Secure and HttpOnly, a non-admin gets 403 from the admin API, and live trading is disabled. Verify data survives a container restart. Check Cloudflare SSL status and DNS after propagation. A successful image build alone does not verify production.

## 10. Optional manual GitHub Actions deployment

After the first manual deploy works, configure GitHub environment production with required reviewers and repository secrets ORACLE_SSH_PRIVATE_KEY and ORACLE_SSH_KNOWN_HOSTS. The latter must contain the verified server host-key entry, not blindly scanned trust. The SSH key must authorize ubuntu on this instance and be restricted to this purpose. The instance also needs read access to the repository. If using another username, update the workflow first. GitHub-hosted runner egress changes; choose a fixed-egress/self-hosted deployment runner or a controlled access mechanism instead of opening SSH broadly just for CI.

Actions -> Deploy Oracle Ubuntu -> Run workflow on main. It requires a successful push CI run for the exact commit, backs up the database, fetches main, checks out that exact SHA and runs deploy.sh. The workflow is manual; pushes do not deploy automatically. Production secrets stay on the server. The first repository administrator must configure protections/secrets; they were not configured by this agent.

## 11. Backups, updates and rollback

```bash
cd /opt/gnkalgo/app
bash deploy/backup.sh
```

Copy backups to encrypted off-server storage with retention and periodic restore drills. Save TLS and .env securely outside Git as part of recovery. Named volumes alone are not backups. To inspect a dump:

```bash
cat backups/YOUR_BACKUP.dump | docker compose exec -T postgres pg_restore --list
```

Restore into an **empty recovery database**, validate application data and migrations, then plan a controlled cutover. Do not pipe restore into production casually. CI currently tests an empty migration cycle, not disaster recovery. Schedule backups/alerts only after choosing a destination and retention policy.

For an update, record the deployed SHA, create a backup, fetch the reviewed commit, ensure a clean checkout, check out the exact commit, and run deploy.sh. If app deployment fails, inspect logs and restore the previous compatible app commit. Do not automatically downgrade a database: migration compatibility and restore need review. Keep old images until verification completes. Do not run docker compose down -v; it deletes database volumes.

## 12. What remains before commercial/live production

See IMPLEMENTATION_CHECKLIST.md and DEVELOPMENT_ROADMAP.md. Missing services include verified KYC, recovery/MFA, real broker adapters, licensed feeds, automation, payments, advanced admin controls, monitoring and disaster recovery. This release must be described as a paper MVP, not a completed live brokerage product.

## Official references checked

- Docker Ubuntu installation and firewall behavior: https://docs.docker.com/engine/install/ubuntu/
- Oracle instance connection: https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/accessinginstance.htm
- Cloudflare Full (strict): https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/
- Cloudflare Origin CA setup/root certificates: https://developers.cloudflare.com/ssl/origin-configuration/origin-ca/
- Cloudflare proxy ranges: https://www.cloudflare.com/ips/
