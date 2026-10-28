# First household HTTPS login with Caddy

**Current scope correction:** the owner requires named users and actual mobile
OpenHands access, not login-only. Follow [the complete household sequence](household_access.md)
for alejandro/kimberly on HTTPS ports 8444/8445. The original login-only procedure
below describes the foundation; gateway startup now requires those dedicated
instances/networks. Do not use it as the complete household installation.


Status: implementation and synthetic native validation prepared. Real leaf
issuance, gateway deployment and login from another LAN device remain owner-run.
The root/intermediate CA already exist; the owner confirmed the root USB was
physically removed. Do not recreate either CA or reconnect that USB for this step.

This delivery serves Authentik login over HTTPS on one explicit RFC1918 host
address. It does not expose OpenHands or grant a family member an agent instance.
The complete [architecture and decision](architecture/household_gateway.md)
distinguishes this delivery from the remaining household platform.

## Run these steps in the owner terminal

From `/home/alejandro/CloudDrive/Engineering/agent-platform`:

```bash
mise run env:gateway:setup &&
mise exec -- task gateway:tls:issue &&
mise exec -- task identity:up &&
mise exec -- task gateway:up
```

- Environment setup installs locked Caddy 2.11.7 and caches its digest-pinned
  official Docker image and runs its version command under the same non-root,
  read-only/capability restrictions without network or keys. It may ask for sudo,
  but starts no persistent service.
- Issuance requests the **existing INTERMEDIATE phrase**, hidden in the foreground
  owner terminal. No root phrase is needed. It checks the public CA fingerprints,
  requires the root media to remain absent, issues a new server-only 30-day leaf
  for `login.home.arpa`, `portal.home.arpa` and the detected LAN IPv4 address, and
  validates Caddy with the real leaf. Never paste the phrase or key files in chat.
- Identity up resumes the existing Authentik/PostgreSQL/worker state. It does not
  reset the administrator or create users.
- Gateway up verifies the existing Authentik server identity, starts only Caddy,
  and checks its effective image/user/mounts/ports/process limits plus TLS chain,
  IP name matching, Authentik readiness and the public root download.

The result prints your private URLs. Caddy binds only the detected host address
on TCP 8443 (HTTPS) and TCP 8080 (public root download). No router, DNS, firewall,
IPv6 listener or client trust is changed automatically. Only requests from the
same detected IPv4 subnet are accepted. On multi-interface/VPN ambiguity the
plan fails; review rather than guessing which address to expose.

`mise exec -- task gateway:plan` prints the address and URL without asking for a
phrase or accessing Docker. `gateway:check` rechecks a running deployment.

## First device: public-root enrollment, then HTTPS login

Keep the device on the same home network/subnet; guest Wi-Fi isolation, a VPN or
mobile data can prevent reachability. There is no DNS prerequisite for this pilot.
Use the IP URL printed by the task, not the phone's `localhost`.

1. Download **only the public root certificate** from the printed address:
   `http://HOST_IP:8080/root.crt`. The HTTP endpoint serves no login, key, directory
   listing or other file. It returns 404 elsewhere. Public transport is not proof
   of authenticity: verify the certificate fingerprint independently before trust.
2. Compare the certificate's SHA-256 fingerprint with this accepted value:

   ```text
   e08db0333e0e5efee452e90a56688ecf3f02157496541e56372638f48762d8bc
   ```

   On Linux/macOS with OpenSSL:

   ```bash
   openssl x509 -in root.crt -noout -fingerprint -sha256
   ```

   Compare the certificate fingerprint, not a checksum of the PEM text file.
3. Explicitly install this public root into the intended device/browser trust
   store. Do not install a private key or intermediate key. Trusting this root
   grants certificate authority trust on that client; record which devices were
   enrolled and how to remove it. Do not bypass HTTPS warnings as the acceptance.
4. Open `https://HOST_IP:8443/` and log in with the existing owner account and TOTP.
   The URL must load without a certificate warning, and login must request the
   configured factor. Do not share the administrator account with family members.
   Individual standard accounts/authorization are a subsequent step.

For Windows, the following computes the certificate fingerprint from its DER
contents (without confusing it with the PEM file checksum):

```powershell
$cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new((Resolve-Path .\root.crt).Path)
$sha = [System.Security.Cryptography.SHA256]::Create()
([BitConverter]::ToString($sha.ComputeHash($cert.RawData))).Replace('-', '').ToLowerInvariant()
```

After confirming the expected fingerprint, an owner may import it for the
current Windows user with `Import-Certificate -FilePath .\root.crt -CertStoreLocation Cert:\CurrentUser\Root`.
Remove that trust later using the certificate manager or
`Remove-Item "Cert:\CurrentUser\Root\$($cert.Thumbprint)"`. Browser-specific trust
may differ; verify the browser actually used.

On Android, use the device's Security/Credential settings to install a **CA
certificate**; labels vary by manufacturer. Some apps do not use user-installed
CAs, so successful browser enrollment does not prove all apps work.
On iPhone/iPad, after installing the certificate/profile, explicitly enable SSL
trust under Settings > General > About > Certificate Trust Settings. See the
[Apple procedure](https://support.apple.com/en-us/102390); inspect the certificate
and compare its fingerprint before enabling it.

## Certificate and configuration storage

Private host directory: `~/.local/share/agent-platform/gateway/`.
Each issuance creates a new private release directory and atomically selects it
only after signing and native configuration validation. Failed releases remain
for review; the old selected deployment and both CA keys are preserved.

| File | Purpose | Mounted into Caddy? |
| --- | --- | --- |
| `server.key` | Unencrypted server leaf key, mode 0600, private directory | Read-only |
| `server.crt` | Public leaf certificate | No |
| `fullchain.crt` | Public leaf + intermediate certificate | Read-only |
| `trust/root.crt` | Public root certificate for device enrollment | Read-only |
| `Caddyfile` | Rendered gateway configuration | Read-only |
| `compose.yaml`, `deployment.json` | Private LAN binding, release and source metadata | No |
| CA `intermediate.key` | Existing encrypted CA signing key | **Never** |
| USB `root.key` | Existing encrypted root key | **Never** |

The leaf key is readable without a password by Caddy for unattended HTTPS. It is
not a signing CA key. Caddy runs as the desktop UID/GID without capabilities, with
read-only filesystem, bounded tmpfs/CPU/memory/PIDs, AppArmor and rotated error
logs. No Docker socket or access logs are configured. Root/host administrators
and processes running as the owner remain privileged within this host boundary.
Caddy shares only the existing Authentik frontend network. Authentik/PostgreSQL
ports are not newly published. Its current default private trusted-proxy ranges
are retained; tightening proxy trust to a dedicated gateway address is pending
before complete household authorization acceptance.

The public root fingerprint is pinned in the reviewed profile. Machine addresses
are discovered and stored privately, outside Git/CloudDrive. Reissuing creates a
new leaf; it never replaces CA material. A changed LAN address or reviewed source
requires reissuance. Pin/reserve the host's DHCP lease before longer-term use.

## Renewal, cleanup and failure handling

This first delivery uses **supervised issuance**, not automatic ACME renewal.
Do not claim Caddy renews a manually loaded certificate by itself. Repeat
`gateway:tls:issue` then `gateway:up` to rotate the leaf while preserving the CA.
The check/start path refuses a leaf with less than 48 hours remaining. Set a
renewal reminder yourself until the separate step-ca/ACME and alerting acceptance
is implemented; no reminder or background job is created by these tasks.

`mise exec -- task gateway:down` removes only the fixed, label-verified Caddy
container. It retains TLS files, Authentik and its database. Cleanup does not
require the old IP or a still-valid certificate. After a network/source change,
stop the old gateway and reissue before restarting. For certificate replacement,
source updates or changes to the IP, never delete/recreate the root/intermediate.
No automatic revocation of old valid leaf certificates is implied by replacement.

If another device cannot reach the ports, check same-subnet Wi-Fi, guest client
isolation and host firewall policy. Inspect with `sudo ufw status verbose` where
UFW is installed; do not disable the firewall. Docker port forwarding and IPv6
behavior require effective reachability testing; binding a private IP alone is
not a complete firewall or router exposure audit. No UPnP, WAN port forwarding or
public exposure should be enabled for this household pilot.

On a failed command, share only its fixed-category JSON and public status. Raw
container logs may include private request metadata and should be reviewed before
sharing. The script never prints phrases, native private-key output or raw crypto
error text. A generic error still requires diagnosis; do not blindly retry CA
creation or weaken TLS verification.

## Acceptance boundaries

Implemented tests cover source mutation, address ambiguity/public IP rejection,
root-media refusal, runtime drift, cleanup identity, and a real temporary
root/intermediate/leaf + native Caddy integration. That integration checks verified
HTTPS/IP SAN, server-only EKU, 30-day lifetime, forged header removal, public root
response, private-file 404s, portal 503, outside-source 403 and untrusted-root
rejection. It uses no real CA key, service, account or trust installation.

The owner still needs to run issuance/deployment, then report another-device
HTTPS login and TOTP. Full MFA/session/revocation/audit/renewal/fair-inference and
per-user OpenHands authorization acceptance remain pending. Readiness remains
pending even if the first login works.


## Official-image executable metadata compatibility

The official pinned Caddy executable has a file capability for privileged ports.
Our high-port configuration does not need it and retains an empty capability
bounding set. The reviewed read-only entrypoint copies the executable bytes into
`/run/caddy-bin`, verifies matching SHA-256, sets mode 0500 and execs the copy.
The source executable remains unchanged; copying bytes does not inherit its file
capabilities. Only this 96 MiB tmpfs permits execution, with nosuid/nodev and a
private UID/GID-owned directory. Other tmpfs areas remain noexec. Total gateway
memory is limited to 256 MiB. Both image preparation and deployment use this same
launcher. No root execution, capability additions or AppArmor disablement is
introduced. Native host tests prove byte equality, metadata non-inheritance and
refusal to execute corrupted/overwrite existing output; owner Docker execution
is a separate acceptance.


## IP TLS without SNI behind Docker

On October 26, direct host probes confirmed HTTP root download and DNS-SNI TLS
worked while IP-literal TLS failed with an internal handshake alert. Python
omits SNI for IP literals; the container's local address differs from the LAN IP
in the certificate. Configure `default_sni login.home.arpa` to select the already
loaded certificate. This does not disable client chain/IP SAN verification or
change HTTP routing, LAN restrictions or application authorization.

For the exact reviewed pre-fix deployment, `mise exec -- task gateway:config:refresh`
validates the old source hashes/rendered files and existing TLS state, validates
the proposed Caddy configuration, and atomically replaces only Caddyfile and its
source manifest. It signs nothing and does not restart services. Unrecognized
source drift, changed LAN/ownership, unsafe files or expiring certificates remain
blocked. Then run `gateway:up`, which recreates only Caddy so bind-file changes
are applied. The root/intermediate and existing leaf/key stay unchanged.
A native regression uses different certificate-IP and listener-IP addresses to
avoid the localhost-only test's previous blind spot, checking failure without
and success with the default SNI while retaining certificate verification.


## Authenticated form failures: preserve native CSRF proof

October 26 owner evidence: Alejandro exists, is active and has confirmed TOTP;
the browser failed on `family-authorize`. The pinned Authentik client sends
`X-authentik-CSRF`. The identity proxy previously deleted it with a wildcard
intended to remove untrusted identity assertions. A real pinned-Caddy regression
reproduced the missing-header 403 at a synthetic protected backend.

The reviewed fix captures the header in a Caddy request variable, strips
`X-Authentik-*` before proxying, then forwards only the saved CSRF proof upstream.
Wildcard deletion and restoration in the same upstream operation still removes
the proof; do not simplify the two-step handling. Native regression checks cover
valid/missing/incorrect proof and forged identity removal. CSRF protection, MFA,
account types and application authorization remain enabled.

For the exact reviewed deployed revision, update configuration without signing
or replacing any certificate/private key:

```bash
mise exec -- task gateway:config:refresh &&
mise exec -- task gateway:up
```

Refresh validates the complete old source/configuration and the proposed new
Caddyfile, then atomically selects it. It does not restart services. `gateway:up`
recreates only Caddy and briefly interrupts gateway traffic. Identity/agent
state remains. A current refresh is a no-op; unreviewed source/configuration
drift is rejected. Do not rerun CA creation or leaf issuance to bypass this check.
After startup, return to the existing authorization tab and use a fresh TOTP.
Record real browser/phone acceptance separately from synthetic tests.
