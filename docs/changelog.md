# Change Log of the Local Agent Platform

This log records implementation decisions and scoped validation evidence. Entries are not a commit log: several changes accumulated after the October 7 Git baseline before being prepared together for publication. Deployment and acceptance statements apply only to their stated checks and dates.

**October 28, 2026 — diagnose and correct the GitHub runner mismatch**

- Read the authenticated first-run logs: three native PKI/gateway tests failed because the Ubuntu 24.04 OpenSSL did not match the pinned 3.5.5 host contract.
- Select the officially available Ubuntu 26.04 runner, add a fail-fast PKI tooling check and pin checkout v6 by commit. Keep the actual PKI version guard and all native tests.
- The linked account has repository administrator permissions, but the connector exposes no administrative write endpoint. Browser configuration requires the owner's separate GitHub sign-in; no branch/security setting is claimed changed yet.

**October 28, 2026 — prepare repository publication and security hardening**

- Record accumulated work in local commits with the complete hook sequence; do not invent historical incremental commits or publish runtime data.
- Reject forced private backup/key-container paths, including absent working-copy files still staged in Git; cover the bypass with real temporary-repository tests.
- Prepare GitHub validation using full history, a commit-pinned checkout, checksum-verified mise and a read-only token; first remote execution and branch protection remain unverified.
- Query OSV for PyYAML 6.0.3 in the host uv.lock: no advisories returned on this date. This excludes container/OS/tool dependencies and is not a frozen database scan.
- Publish a scoped security policy and a prioritized hardening plan; retain incomplete OAuth, effective egress, per-user dynamic acceptance, recovery and telemetry gaps.
- Remove trailing spaces from copied MIT license comment headers in test fixtures; keep reference function bodies unchanged.
- Repair hook rehearsal on clean checkouts: create a harmless nonempty fixture commit inside the temporary clone and report only a fixed failure phase.
- Public GitHub API readback reports the default main branch as unprotected; record required-check enforcement as a concrete pending action, with detailed access/security settings still unverified.

**October 28, 2026 — recover services and repair local Qwen thinking control**

- Remount existing bounded household filesystems before starting stopped services. Preserve accounts, keys, certificates and user data; do not start disposable isolation pilots.
- Restore Authentik, both personal instances, the gateway, the local compatibility instance and observability. Regenerate Collector log mounts after stale container IDs prevented startup; restore Ollama's declared agent-link network attachment for LiteLLM.
- Verify trusted HTTPS login, unauthenticated personal-app redirects, both native/Canvas APIs and model discovery. The synthetic observability stack test passes; actual household conversation correlation remains pending.
- Replace the ignored native `think` field with `reasoning_effort: none` for the OpenAI-compatible endpoint. Add guarded, credential-preserving profile tuning and apply it to both existing local Qwen profiles.
- A bounded direct request completed in 5.66 seconds without reasoning output. Existing conversation settings and full agent latency acceptance remain unchanged/pending.

**October 26, 2026 — distinguish MFA acceptance from incomplete OAuth continuation**

- Add bounded authenticated-session, TOTP verification/throttling and native failure-event readback without returning cookies, codes, keys or OAuth parameters.
- Observe an accepted TOTP and an incomplete authorization plan. Start a fresh exchange from OpenHands; Alejandro subsequently reaches his personal Canvas.
- Treat stale/incomplete continuation as a diagnosis of the observed state, not proof of its original cause or a permanent fix. No MFA removal, password reset or access-policy weakening.

**October 26, 2026 — plan an enforced owner Internet switch**

- Record the requested per-user/global Internet switch with default-off public HTTP/HTTPS scope, external proxy enforcement and active-connection cutoff.
- Specify owner-only control, CSRF, audit, DNS/rebinding/IPv4/IPv6 bypass and local-inference acceptance; prefer Canvas integration without exposing a self-enable tool.
- Documentation only: no new network access, accounts, privileges, proxy deployment or working UI switch. Backend/model connection acceptance remains first.

**October 26, 2026 — require cross-family model evaluation**

- Correct the overly homogeneous Qwen-only tier proposal: retain its pinned compatibility baselines and add explicitly unlocked Phi, Mistral, Gemma and newer-Qwen comparison candidates.
- Mark GPT-OSS 20B experimental with unproven VRAM margin; no automatic download, activation or quality/speed superiority claim.
- Define local latency/memory/Spanish/tool/agent-completion measurements before promotion. No runtime model or profile changes.

**October 26, 2026 — correct the model diagnostic's native API contract**

- The initial checker incorrectly requested /api/server_info and read a frontend-only key alias. Use /server_info and llm_api_key_is_set, matching the pinned SDK/client/router.
- Update the tests to native response shapes and exact endpoint paths. Prior 4xx/false key flags do not justify changing credentials.
- Keep the Qwen/agent-reference readback and add fixed HTTP status reporting; connection acceptance remains pending corrected runtime evidence.

**October 26, 2026 — distinguish browser onboarding, backend health and model tiers**

- User requests fast, balanced and heavier local reasoning options. Pin official 4B/8B/14B candidate manifests and bounded contexts without downloading or claiming hardware/quality acceptance.
- Pinned Canvas forces onboarding per browser for its seeded local backend, even with server-side LLM settings. Treat the missing agent-reference explanation as unverified until native readback.
- Add a read-only per-instance model/API diagnostic that checks both native and Canvas proxy endpoints, Qwen settings/profile and default agent reference without secrets, profile writes or restarts.
- Browser probing observed a login redirect; backend process failure remains unconfirmed. Connection repair and model deployment require further runtime evidence.

**October 26, 2026 — retain Authentik CSRF proof through Caddy**

- Pinned Authentik uses X-authentik-CSRF; the identity proxy wildcard removed it. Reproduce a protected POST 403 with real pinned Caddy and synthetic credentials before fixing header forwarding.
- Restore only the browser CSRF header after removing untrusted identity assertions. Keep missing/invalid CSRF rejection and forged-identity denial in native regression coverage.
- Extend exact-source configuration refresh to the deployed pre-CSRF revision without signing, replacing keys or weakening drift checks; update operational task description.
- Record error-only logging limitations and pending real browser authorization after deployment.

**October 26, 2026 — diagnose generic authorization responses after TOTP**

- Owner confirms active account and confirmed TOTP; the remaining error is on family-authorize. Extend bounded identity logs with fixed-route HTTP failure counts and error-level presence.
- Add TLS/OAuth/TOTP markers without exposing original messages or request parameters; test aggregation, malformed lines, unknown routes and credential omission.
- Read-only diagnostics only; no account, MFA, invitation, service or policy changes.

**October 26, 2026 — preserve the approved connection diagrams**

- Copy both conversation-approved Mermaid maps verbatim into the household architecture document, including their Spanish labels, ports and recorded LAN IP; retain the certificate-custody diagram.
- Add published-port and Docker-network tables, source links, HTTP/TLS boundaries and the explicit direct-Ollama household telemetry gap.
- Link the architecture from README and household runbook. Documentation only; no deployment, certificate, account or networking changes.

**October 26, 2026 — correct embedded outpost browser origin**

- Live personal-app navigation exposed an HTTP localhost:9000 authorization redirect. Pinned embedded outposts use authentik_host for browser endpoints; set it to the public LAN HTTPS origin alongside authentik_host_browser.
- Verify actual authorization redirect origins for both personal apps after identity apply, without owner cookies/credentials. Reject localhost, external or downgraded destinations and omit all query state from diagnostics.
- Keep external accounts and existing authorization/MFA controls; backchannel routing remains native.

**October 26, 2026 — finish household enrollment in the personal application**

- The external household user reached Authentik's internal-only generic interface. Configure the successful invitation plan's final redirect to the reserved user's OpenHands canvas.
- Preserve external account type, own-app authorization, password handling and mandatory TOTP/session stages; reject client-chosen destinations.
- Test both tenant URLs, rejected registrations, compiled policy substitution and unchanged MFA ordering; add native destination readback.

**October 26, 2026 — restart stale browser plans when opening a new invitation**

- Owner diagnostics found two generation-mismatched enrollment sessions while the newer invitation remained pending. Pinned FlowExecutor resumes same-flow plans before rechecking invitation query parameters.
- Generate entry links through native cancellation with a strictly encoded relative enrollment target; keep expiry, single-use, generation revocation and MFA enforced.
- Test both users, redirect/token encoding, invalid origins, path/query injection and unchanged issuance/revocation behavior. Real browser enrollment remains pending.

**October 26, 2026 — distinguish invitation generation failures**

- Extend read-only household diagnosis with bounded native session checks that return only fixed booleans for generation presence/shape/equality.
- Add regressions for matching, replaced, missing and malformed generation state and suppression of unrelated sessions/credential values; preserve enrollment/revocation policies.

**October 26, 2026 — add the approved header mark**

- Draw a blue three-layer vector beside the upper-left product name using CSS clipping; no image URL, external font, or authentication change.
- Align the 24px mark with the desktop and mobile header padding. Live appearance still requires applying the updated brand and reloading normal login.

**October 26, 2026 — correct appearance against the live login**

- Inspect the real Authentik login: native `::after` stacking hid the descriptive sidebar text; explicitly bring it above the background.
- Add the product header, compact the native provider logo/card and remove inappropriate locale/footer contrast filters on the light theme.
- Keep native authentication controls and provider attribution; source/configuration checks do not substitute for desktop/mobile visual acceptance.

**October 26, 2026 — use the actual prompt HTTP session plan**

- Owner password submission reached the missing-context rejection with no account created. Review of pinned PromptValidationPolicyEngine shows it supplies prompt_data, while FlowExecutor restores its plan from the HTTP session under SESSION_KEY_PLAN. Earlier tests/native probes injected flow_plan manually and missed this boundary.
- Read only the actual HTTP session plan in the invitation policy; bind it to the reserved executor route and invitation flow PK. Keep consumed-in-session invitation continuation, expiry/generation, fixed username/group and password checks. No public signup or invitation reactivation is introduced.
- Update native probing to use HttpRequest/session and unit fixtures to omit flow_plan. Add session-present/context-absent acceptance, consumed-row continuation, missing-session/context-injection refusal and cross-flow regressions.
- Apply through household:identity:apply and retry the existing browser tab; actual account/TOTP/browser acceptance remains pending owner execution.

**October 26, 2026 — match the public identity brand including port**

- Live public API probes reproduced the discrepancy: normal IP:8443 Host selected authentik-default/automatic/no CSS; the same request with bare-IP Host selected the expected light family brand. The pinned middleware compares request.get_host(), including port.
- Generate the family brand domain as IP:8443. Inside the existing identity transaction rename only the verified non-default family bare-IP brand; reject collisions/admin/unmanaged brands and preserve its identity/settings.
- Read back the public current-brand API after identity-only apply and household checks, verifying exact origin, light theme and CSS. Database field assertions alone no longer count as proof that the browser receives the intended brand.
- Add migration preservation/refusal and live-response regressions. Owner apply and renewed invitation remain pending interactive Docker authentication.

**October 26, 2026 — distinguish brand readback and serializer whitespace**

- Owner identity apply failed at a grouped appearance assertion. The original result did not distinguish brand scope, CSS, theme or layout. Split fixed stages, including each reserved flow layout.
- Fix a reproduced false negative when native CharField serialization trims the CSS boundary whitespace: compare stripped CSS while still rejecting internal rule changes. Preserve default-brand refusal and theme/layout readback checks; do not bypass assertions or alter authentication.
- Add seven regressions for trimming, internal drift, admin-brand refusal, preference preservation and exact readback stages. Native owner retry is required to confirm the live rejecting condition and successful appearance deployment.

**October 26, 2026 — owner approved the side-panel login**

- Record explicit approval of Panel lateral; select native content_right for all five family flows while preserving their designations and stage/security bindings.
- Adapt local light CSS to a left welcome panel/right native form, with responsive fallback and no hidden security/form/error content or external assets.
- Add native layout readback and a flow-designation regression. Prepared source is distinct from owner-applied branding and live visual acceptance; no certificate, account or agent restart is involved.

**October 26, 2026 — visible enrollment feedback and light household brand**

- Owner diagnosis shows no account creation after invitation consumption, no configured factor and no recent error indicators; the exact rejecting condition remains unconfirmed. Replace silent policy False results with native, fixed ak_message feedback without changing password/identity/MFA requirements or logging secrets.
- Prepare the requested light minimal native brand CSS, selecting the native theme base while preserving unrelated attributes and the default localhost brand. Keep error messages, factor instructions and focus indicators visible; introduce no remote assets.
- Add household:identity:apply for policy/brand import/readback without agent recreation or invitation issuance, plus feedback/redaction/non-default-brand/identity-only regressions. Owner application and actual browser appearance/registration remain pending.

**October 26, 2026 — inspect stalled enrollment without disclosing logs**

- Add identity:logs:check for fixed recent-log indicators with container-label validation; include read-only account/TOTP/pending-invite state in household diagnostics.
- No raw errors, passwords, TOTP secrets/codes or invitation links are returned. Empty logs are not acceptance of a successful flow. Owner terminal authentication remains required to access Docker; no services/accounts are changed.
- Add redaction, wrong-container refusal, unavailable probe, bounded-output and quiet-log regressions.

**October 26, 2026 — select the existing gateway certificate for IP clients**

- Reproduced the live failure with read-only host probes: public root HTTP 200, TLS internal alert for IP clients, successful TLS with login.home.arpa SNI. Native Caddy validation and existing release checks passed.
- Add default_sni login.home.arpa for clients omitting SNI behind Docker, retaining chain/IP SAN verification and all HTTP authorization controls.
- Add an exact previous-revision configuration refresh with native validation, guarded atomic config/manifest replacement and rollback on manifest failure. Do not regenerate or replace any CA/leaf keys or certificates. Recreate only Caddy on gateway:up so updated bind-file content is selected.
- Add native different-IP/listener TLS coverage and refresh preservation/rejection tests. Actual owner restart and mobile login acceptance remain pending.

**October 26, 2026 — complete readonly model relay temporary paths**

- Owner setup now reaches model discovery. Source review found missing FastCGI/uWSGI/SCGI temporary path overrides in the dedicated Nginx relay, unlike the existing hardened ingress. Add them under bounded /tmp while preserving readonly root, non-root identity and the exact API allowlist.
- Migrate only the exact reviewed legacy relay configuration after checking ownership/mode/link count, using atomic replacement. Arbitrary drift is rejected. Recreate only model-relay so its bind-mounted inode and Ollama DNS resolution are refreshed.
- Run pinned Nginx configuration validation under the deployed non-root/readonly restrictions before identity/agent startup. Retry transient model discovery for 30 seconds and distinguish fixed network/HTTP/JSON/schema/missing-model errors without raw data.
- Add migration, no-adoption, discovery failure/deadline and hardening regressions. Native preflight and actual family login remain owner-run; source omission is confirmed, but the earlier live model-discovery error alone did not prove a unique cause.

**October 26, 2026 — wait for the personal agent's first-start key**

- Owner read-only diagnosis confirms healthy identity services, committed family providers/enrollment flows and no current database blocking. This does not identify the prior setup failure or prove agent availability.
- Fix an independently reproduced first-start race: the agent seed script previously read its native key before waiting for initialization. Wait for a valid key and backend within a deadline, retain fixed failure stages through the privileged helper, and write the bootstrap marker only after model-settings readback.
- Extend read-only diagnosis to all six personal agent/ingress/relay containers. Add delayed/missing/malformed key, redaction and real bootstrap-script execution regressions with isolated IO boundaries. Native household deployment and browser acceptance remain pending.

**October 26, 2026 — retain household identity transport diagnostics**

- The owner's next setup failed with a generic outer error before agent startup. That output does not establish the underlying cause. Preserve fixed Engine failure categories (unavailable/timeout, exec failure, excessive output), JSON/schema failures, and allowlisted native stage/exception categories without exposing raw output.
- Add `household:diagnose` to read identity process state, typed outpost flags, family provider/flow presence and aggregate blocked/idle-in-transaction database sessions. It performs no blueprint import, account change or service restart.
- Split native outpost lookup/config/provider/save/readback stages and add progress around identity setup. Add negative redaction, malformed response and read-only diagnostic regressions. Live cause and deployment acceptance still require owner-terminal output.

**October 26, 2026 — preserve typed embedded outpost configuration**

- Owner setup reached the embedded outpost step after invitation import/readback/policy checks. Fix the invalid dictionary conversion of Authentik's OutpostConfig dataclass using dataclasses.replace and its native setter.
- Preserve unrelated typed options and existing providers; read back the saved URLs and required provider membership inside the enclosing identity transaction.
- Add regressions reproducing the previous TypeError, preserving options/providers, repeat application and rejecting persisted readback drift. Owner rerun is still needed for native deployment acceptance.

**October 26, 2026 — invitation-based household enrollment**

- Replace owner-entered account passwords with native per-user invitation flows for alejandro/kimberly. Setup preserves existing accounts and prepares services; recipients set their own password and enroll TOTP through LAN HTTPS.
- Register Task operations to issue 24-hour single-use invitations and revoke/replace pending invitations. Keep bearer links in new owner-only private files outside Git/CloudDrive; no automatic message delivery or public signup.
- Enforce fixed server-side identity/group assignment, expiry/generation checks and existing-account refusal. Document native consumption on link opening and safe partial-enrollment recovery.
- Add negative policy and private-file tests plus native setup readback. Source tests do not establish actual Authentik browser enrollment or phone acceptance; these remain pending owner execution.

**October 25, 2026 — run Caddy without vendor file capabilities**

- Owner probe confirmed a non-root/no-capability execution denial after image pull. The pinned official image assigns cap_net_bind_service to its Caddy executable, which is unnecessary for the configured high ports.
- Keep cap_drop ALL, non-root, no-new-privileges and AppArmor. Copy only the pinned executable's bytes to a 96 MiB nosuid/nodev executable tmpfs, verify SHA-256 equality, then exec it without inherited file xattrs. Mount the reviewed bootstrap read-only; leave other temporary areas noexec and the root filesystem read-only.
- Bound gateway memory at 256 MiB and inspect its bootstrap/tmpfs declarations. Use the identical launcher in the environment image probe and real Compose deployment. Add native byte-integrity/xattr/no-overwrite regressions. Actual Docker acceptance still needs the owner-terminal rerun; no CA or account changes are involved.

**October 25, 2026 — distinguish gateway environment failures**

- Owner environment setup failed after sudo authentication, before household preparation or leaf issuance. The old fixed error did not identify whether image download or hardened image execution failed.
- Add separate stages, fixed diagnostic categories/exit codes and regressions that prohibit raw native output or credentials in reports. No capabilities, credentials, CA or service restrictions were changed; actual Docker failure cause still requires the owner-terminal rerun.

**October 25, 2026 — named-user mobile OpenHands delivery**

- Correct the earlier login-only scope: prepare alejandro/kimberly standard accounts, mandatory TOTP setup, individual Authentik proxy applications/groups and exact-user Caddy authorization before Canvas/API/WebSocket access.
- Prepare separate real-user projects/UIDs and fixed-size filesystems, preserving synthetic pilot and previous demo data. Environment allocation stays in mise; account/service operations stay in Task.
- Enable native session bootstrap only behind per-user authorization, with no directly published agent/ingress ports. Seed working local model profiles through restricted per-instance Ollama relays without overwriting later settings.
- Expand native Caddy tests for own/cross/anonymous/forged identity behavior and document a single complete installation sequence. Passwords remain hidden/in memory; real user creation, deployment and phone acceptance still require owner execution.

**October 25, 2026 — Caddy first-LAN-login delivery prepared**

- Owner confirmed root USB removal and selected Caddy. Pin Caddy native tooling/image and register environment setup separately from Task operations.
- Prepare IP/DNS 30-day server-only leaf issuance under the existing encrypted intermediate with hidden owner input, immutable releases and native configuration validation. No CA regeneration or automatic trust installation.
- Prepare private-IP HTTPS Authentik routing, public-root-only HTTP download and a closed portal. Add runtime/process/port/mount checks, stale-IP-independent cleanup and native synthetic TLS/header/denial tests.
- Validate the cached image executable under non-root/no-new-privileges/capability restrictions before any real signing.
- Document the current milestone, target architecture and manual device enrollment. Real signing/deployment/device login remain pending; automatic renewal, per-user agent authorization and household readiness are not claimed.

**October 25, 2026 — owner CA creation accepted**

- Owner completed connected root/intermediate creation with separate encrypted private keys and stopped default-context containers. Independently verified both public certificate fingerprints against the owner report.
- Recorded public validity/fingerprint evidence and updated the plan. USB removal is unconfirmed; issuer/gateway deployment, DNS/client trust and household authorization remain pending.
- Documentation and public-certificate verification only in this step; no private-key reads, key regeneration, service starts or trust installation.

**October 25, 2026 — USB ancestry validation correction**

- Request explicit lsblk JSON tree output: selecting PATH without NAME does not implicitly preserve parent/child ancestry. A flat inventory incorrectly rejected a removable USB partition.
- Add a realistic flat-versus-tree regression, mismatched UUID/non-removable negatives and an unrelated-USB/internal-partition refusal. No media write, key creation or service change is part of this fix.

**October 25, 2026 — explicit connected CA ceremony choice**

- At the owner's request, add connected preflight and creation Task operations with explicit online opt-in. Default creation remains offline-only.
- Retain stopped-container, media, encryption, distinct-phrase and existing-output guards. Reports record accepted online exposure rather than offline assurance.
- Add five regressions, bringing PKI coverage to 21 passing tests, and update the owner guide/plan. No real key generation, USB write, networking change or service stop was performed.

**October 25, 2026 — guarded offline CA toolkit prepared**

- Pin Smallstep CLI in mise and register environment installation/checks. Task operations delegate ceremony logic to scripts/pki; the reviewed profile is YAML.
- Add verified removable-media and offline snapshots, exclusive output creation, separate hidden phrases, anonymous descriptor delivery and encrypted PKCS#8 (PBKDF2-SHA256/600,000, AES-256-CBC) before persistent key writes.
- Add 16 temporary native/guard tests; all 398 repository tests passed. Document the single-host trust limits and owner execution sequence. No real keys, USB writes, network changes, trust installation or workload stops were performed.

**October 25, 2026 — setup priority and single-computer CA custody**

- Owner deferred the remaining full-application recovery rehearsal until later; the accepted encrypted SQL restore remains valid within its recorded scope.
- Advanced the active plan to HTTPS/identity gateway, CA/DNS/client trust and authenticated per-user routing preparation.
- Recorded the available single computer/storage USB and preferred encrypted-key/passphrase separation, including optional online recovery-copy limitations. No USB formatting/write, root generation, trust installation or cloud upload was performed.

**October 24, 2026 — full application restore rehearsal prepared**

- Added an explicit YAML rehearsal profile derived from the reviewed local Compose: separate loopback host/port, private internal bridges, no logs, bounded RAM state, restored file-based secrets and no live data mounts.
- Added Task lifecycle/check/accept/cleanup operations with owner-side recovery prompts, native restored signing/TOTP readback and separate browser evidence. The runtime verifier retains its current defaults and accepts explicit rehearsal boundaries.
- Documented the diagram, snapshot credentials, no-new-admin/MFA rule, RAM/reboot cleanup and acceptance limits. No live rehearsal was deployed or browser login accepted by these changes.
- All 382 repository tests passed, including 118 identity tests and 23 new rehearsal-related regressions. Installed Compose source parsing, registered Task plan, mise source checks and Python/shell/whitespace/link checks passed; native startup and browser acceptance remain pending.

**October 24, 2026 — revised identity SQL restore accepted**

- Owner report `identity-backup-JD09hAso.json` was read back: archive integrity, isolated SQL restore and cleanup all passed through the revised owner/root boundary; terminal input remained hidden in the supplied transcript.
- Closed revised-path live execution only. Full native application restore, browser/TOTP recovery, offline-copy refresh and household readiness remain pending.
- Evidence/documentation only; no backup, credential, container, network or service changes by the assistant.

**October 24, 2026 — recovery prompts moved outside sudo**

- Owner completed hidden-input passphrase rewrap; the next restore was blocked by the foreground guard before secret entry or SQL creation. No further key change is required for that error.
- Moved restore crypto/prompts to the desktop user. Privileged noninteractive helpers only read fixed-directory ciphertext or validate/restore an archive supplied through stdin; no key or phrase is sent to those helpers.
- Retained no-echo/foreground checks, bounded memory-only payload handling, archive validation on both sides, isolated DB constraints and cleanup. Revised live restoration remains pending owner execution.
- The full 358-test repository run passed; the updated 95-test identity suite also passed with the added privileged-timeout cleanup check. Real revised restoration remains pending.

**October 24, 2026 — native SQL restore acceptance and recovery terminal repair**

- Verified the owner's local fixed report: encrypted archive integrity, isolated PostgreSQL restore and cleanup passed. Full native Authentik/browser recovery remains pending.
- Replaced direct age access to the sudo terminal with a private crypto PTY and foreground/no-echo input checks. Stop signals fail explicitly; native terminal output is not streamed into reports.
- All 353 repository tests passed (89 identity); synthetic PTY coverage verifies old/new phrase privacy and prior-ciphertext compatibility, alongside unsafe-terminal/stopped-child/failure-preservation regressions.
- Added verified atomic passphrase rewrap preserving the same private/public key and existing backup compatibility. No real credential was read, used or changed by the assistant; owner execution and refresh of offline copies remain pending.

**October 24, 2026 — owner-run repeat instance acceptance**

- Recorded the complete successful two-pilot lifecycle/isolation/network/WebSocket/recovery chain after the missing-mount report; all six extended source fingerprints match the current files.
- Documented explicit remount/check prerequisites and the distinction between synthetic pilot recovery and the pending encrypted identity backup/application recovery.
- Evidence/documentation only; no scripts, services, accounts, secrets, storage configuration or readiness policy changed.

**October 20, 2026 — encrypted identity backup candidate**

- Added age 1.3.2 with resolved checksums, environment verification, encrypted recovery-key creation and operational snapshot/isolated SQL restore tasks.
- Snapshots pause/resume Authentik writers, bundle native DB dump and required files/secrets, retain plaintext in memory and publish private ciphertext outside Git/CloudDrive. The isolated restore has no network, ports or host mounts and never restores in place.
- All 347 repository tests passed, including 83 identity tests and 24 new backup/key regressions. Native age encryption and passphrase-encrypted key prompts/decryption were tested with synthetic data. Real key custody, backup, SQL restore and full native application/browser recovery remain pending owner execution.
- Recorded owner-reported forced TOTP enrollment and invalid-code rejection for a synthetic user; test-account deactivation is not assumed.

**October 20, 2026 — owner-reported administrator TOTP acceptance**

- Recorded the owner's successful administrator password recovery, TOTP enrollment and private-window invalid/valid code checks, separately from automated/runtime evidence.
- Documented the owner-tested interactive password-reset command and active brand/flow/MFA inspection gate. No-factor enforcement, lost-factor recovery and encrypted backup/restore remain pending.
- Documentation only: no account, active flow, service, certificate or network changes. Household readiness remains pending.

**October 18, 2026 — persistent localhost identity candidate**

- Added a pinned PostgreSQL/server/worker definition publishing only 127.0.0.1:9000, isolated from agent/model/observability networks and with no Docker socket.
- Added one-time root-private state/credential preparation, repeat-setup preservation, private secret-integrity fingerprints and fail-closed drift checks. Lifecycle operations inspect applied restrictions and preserve data on down/failure.
- Registered environment setup in mise and service operations in Task, with a first-login guide. Native admin setup is manual; no household blueprint, account, DNS, trust store or LAN exposure is automatically applied.
- All 323 repository tests (59 identity tests) and installed Compose source parsing passed, along with source/shell/whitespace checks. Registered mise source checks and Task plan also passed; Gitleaks found no findings across 226 candidate files, staged content and local refs. Actual persistent deployment and browser acceptance remain pending owner execution.

**October 18, 2026 — owner-run native identity acceptance**

- Owner report `identity-native-QLUmr7yU.json` passed native blueprint validation, import/readback, repeat import and disposable cleanup; all five fingerprints match current source.
- Updated identity status and plan to close native compatibility acceptance only. Persistent identity deployment, browser MFA, gateway authorization and household readiness remain pending.
- Documentation-only evidence update; no service, account, network or certificate changes.

**October 18, 2026 — native blueprint rejection diagnostics and outpost schema**

- Owner execution reached native validation but was rejected; temporary cleanup completed. Native import and household acceptance remain pending.
- Declared required proxy outpost type and null service connection, with strict source and ORM checks. The original rejection did not identify an entry, so this omission is not claimed as its sole cause.
- Use typed importer validation errors instead of sanitized log objects. Return only known public entry/field names and allowlisted machine codes; suppress error text/values. Require an actual boolean native validation pass.
- All 302 repository tests passed, including 38 identity tests and new typed-error/redaction/source regressions. Source/shell/whitespace checks passed; owner native rerun remains pending.

**October 18, 2026 — disposable identity startup corrected**

- Owner run reached checker initialization and failed at `django_setup`, before blueprint validation. The original detailed exception was not retained; no native acceptance is recorded.
- Added the image source root to PYTHONPATH, the pinned Authentik bootstrap before Django, and official lifecycle migrations. Use the default realm of the new disposable database instead of creating a tenant from an unprepared template.
- Added allowlisted failure categories and explicit cleanup outcomes, plus four startup/diagnostic regressions. All 297 repository tests (33 identity tests) and source/shell/whitespace checks passed; native owner rerun remains pending.

**October 18, 2026 — disposable native identity check prepared**

- Pinned Authentik 2026.8.4 and PostgreSQL 18.6-alpine from official registry metadata, recording index/platform digests and compressed sizes.
- Added a unique disposable Compose project with no published ports, private internal bridge, bounded tmpfs/resource limits and file-delivered temporary credentials outside Git/CloudDrive.
- Added native migrations, serializer-field validation, import, ORM readback and repeat-import checks; strict summary validation, bounded operations and cleanup failure handling prevent false success.
- Preparation checks passed: 293 repository tests (29 identity tests), installed Compose config parsing, source/shell/whitespace validation and Gitleaks with no findings across 221 candidate files, staged content and local refs.
- Added source/orchestration regression tests and Task plan/check commands. Native owner execution, browser MFA and household acceptance remain pending; no persistent identity stack or client trust changed.

**October 18, 2026 — native identity source candidate**

- Added an opt-in Authentik blueprint with mandatory MFA, isolated application group bindings, restricted session settings and no bundled users/credentials. Automatic instantiation is disabled.
- Added a narrow, non-executing YAML/graph source guard and mutation regressions, with mise environment validation and Task code tests. Existing security discovery includes them.
- Registered mise/Task entry points passed, all 281 tests passed (17 new identity tests), and the pinned Gitleaks scan found no findings across 215 candidate files, staged content and local refs.
- Added the identity sequence diagram, mixed-client requirements and deployment prerequisites. Authentik release/native validation, gateway, TLS/CA, account creation and browser acceptance remain pending; no services or trust stores changed.

**October 18, 2026 — owner-run instance acceptance**

- Owner completed guarded recreation, runtime/API validation, filesystem/HTTP isolation, selected peer IPv4 TCP denial, native session WebSocket isolation and synthetic restart/import checks for both pilots.
- Native keys were preserved, synthetic cleanup completed and the generated manifest was removed. The six extended source fingerprints match current code.
- Updated instance status and plan with report basenames and explicit scope. Household readiness remains pending; no authentication, networking or service configuration changed in this documentation update.

**October 18, 2026 — instance verifier regression fixes**

- Restrict inspected network modes to the service's declared pilot bridges and require explicit private PID/UTS modes and private or shareable IPC. Missing, host, foreign-container and unknown namespace modes fail closed; full network attachment validation remains required.
- Open native keys, recovery markers and synthetic manifests with `O_NONBLOCK | O_NOFOLLOW`, then validate the descriptor as a regular file before reading. Real FIFO regression probes run in bounded child processes and verify storage-lock release.
- Add negative runtime UID/GID and recovery tests for lost/corrupt records, peer secret/conversation exposure and changes to either native key. Preserve changed markers rather than deleting them during cleanup.
- Validation: 60 instance tests and all 264 repository tests passed with the pinned Gitleaks binary on PATH. In-memory removal of recovery verification produced 7 test failures; bypassing runtime user identity produced 10. Repository structure and shell syntax checks passed.
- Validation is local and unprivileged; these changes do not recreate services or establish household acceptance.

**October 6, 2026 — transparency and infrastructure guide (this run)**

- New `AGENTS.md`: save the user's instruction to announce and display modifications always, with code/diff, validation, and application status.
- New `docs/infrastructure_walkthrough.md`: explain host/GPU, mise/Task, Ollama, OpenHands, permissions, networks, LiteLLM, privacy, logs, backends, provisioning, golden signals, totals, cache, and pending limits through fragments of the actual files.
- The guide includes the optional location of LangChain/LangGraph and an explicitly non-installed and non-executed example, in response to the user's question.
- New `docs/changelog.md`: centralize this change log and separate retrospective reconstruction from real diff.
- `README.md`: link guide/log and correct the old observability status with the already registered acceptance. The new cache passed the host's full test; a new observed conversation call maintains pending acceptance.
- `.gitignore`: exclude `.idea/` without modifying or deleting the IDE files.
- First local commit requested by the user, with Git identity already configured and an explicit selection of project files. Remote GitHub pending URL.
- No changes to Compose, images, models, callbacks, dashboards, credentials, or services in this run.

**October 6, 2026 — recent cache expansion**

| File | Concrete Change |
| --- | --- |
| `infra/observability/litellm.yaml` | Add native Prometheus callback, enable only the two token counters cache-read/cache-write with model label, require auth in /metrics/ |
| `infra/observability/collector.yaml` | Authenticated Prometheus receiver for LiteLLM; metric and model selection, limited labels; cache pipeline and scrape status |
| `infra/observability/compose.yaml` | Deliver the existing key to the Collector for reading authenticated metrics |
| `infra/observability/grafana/dashboards/platform-overview.json` | Add Cache Hit/Write, periods, rates, percentage, and scrape status; file version 5 |
| `infra/observability/grafana/dashboards/llm-cost-routing.json` | Same cache breakdown in the LLM dashboard; file version 3 |
| `scripts/openhands/usage-check.sh` and `.py` | New route diagnostics and numeric usage of a conversation, without messages or keys |
| `scripts/observability/check-cache.sh` and `.py` | Compare two new LiteLLM calls with the exported cache counter |
| `scripts/observability/test-cache.sh` and `.py` | Isolated test with the pinned Collector: auth, accumulated, redaction, and HTTP failure |
| `scripts/observability/test-privacy.py` | Isolate the canary test of the new scrape dependency from the proxy |
| `scripts/observability/validate-config.py` | Verify that the Collector receives the required credential without displaying its value |
| `Taskfile.yml` | `openhands:usage:check`, `observability:cache:check` and `observability:cache:test` |
| `docs/dashboards.md`, `observability.md`, `plan.md` | Document source, scope, deployment, and pending acceptance |
| `docs/architecture/adr-001-observability.md`, `observability_diagrams.md` | Decision of existing integration and cache traversal |
| `docs/diagnostics/tokens-2026-10-06.md` | Real Ollama evidence, clarification of the OpenHands capture and different proxy coverage |

Prepared and tested in isolation; after that applied and validated on the host on October 6 at 09:57 Europe/Berlin. Two synthetic calls produced 1,623 tokens reused and the counter increased exactly 1,623. The dashboards loaded by provisioning show real cache series. Missing to compare a new conversation call. The derivation test from spans does not form part of the final implementation; the existing Prometheus exporter was chosen that handles the nested field of Ollama.

**October 5–6, 2026 — observability, golden signals and totals**

- Stack Collector/Prometheus/Tempo/Loki/Grafana/LiteLLM/Blackbox pinned by digest, internal networks and only Grafana published in loopback.
- Native LiteLLM OTel callback, privacy processors, limited filelog and optional native OpenHands tracing.
- Strong persistent master key outside of Git/CloudDrive after rejection of startup without key; correction of the reserved filter gen_ai.token.type.
- Seven dashboards and sources provisioned; nine HTTP probes, internal Collector metrics and two local alerts.
- Golden signals with explicit scope; current accumulated totals separated from period increase and rate. Do not sum counter samples.
- Acceptance of the stack and synthetic request registered in `docs/diagnostics/observability-2026-10-06.md`. Full correlation of a pending conversation.

**October 4–5, 2026 — environment base and local platform**

- Git structure, LICENSE, README, docs, infra and scripts categorized. Remote Git pending.
- mise with Task pinned and locked; bootstrap and host scripts with pinned packages, signed APT, backups, NVIDIA runtime and checks.
- Ollama/Qwen3 pinned by digest, weights in Docker volume, API loopback, GPU ID 0 and limits; context increased from 8192 to 32768.
- OpenHands Agent Canvas with persistent state, workspace /projects, host group and Nginx loopback; preservation of variables when using sudo.
- Real GPU/Docker/inference tests and demo/bugfix exercises. Separate generation time from load/prefill and synthetic check of general agent quality.

The [code guide](infrastructure_walkthrough.md) relates these decisions to the current files.

## Host Consumption and Acceptance Tracking

- Updated README, infrastructure guide, plan, observability, dashboards, and diagnostics with the cache full test already approved on the host.
- In the UI, `local-qwen3-8b` was reselected in the existing conversation, using its saved configuration pointing to LiteLLM. Secrets were not modified. Missing to check a new response for that conversation; the historical OpenHands counters are not imported.

## October 6, 2026 — YAML maintained by humans

- Migrated to YAML `infra/observability/collector` and the manifests `versions` of host, LLM, OpenHands and observability. Values, types, digests and limits are preserved.
- Updated readers with `yaml.safe_load`, Compose paths, validation scripts and privacy/cache tests.
- Pinned Python 3.14.4 and created the venv; Task coordinates scripts `scripts/environment/` to install/verify PyYAML 6.0.3 from an official wheel with hash.
- JSON is preserved for Grafana dashboards, the bootstrap manifest of mise, API responses/artifacts and automatically generated artifacts.
- The running stack is not restarted to change only the format. YAML configuration and override generation are validated before their next application.

- Confirmed diagnosis: the inspected conversation was still in `direct Ollama`, although the saved profile had been edited. Prepared `openhands:route:proxy` (verified conversation/default change) and `observability:stream:check` (SSE→counters usage). Both tasks were applied on the host: effective/default LiteLLM path and active streaming; SSE test with exact increment 23/8. Grafana confirmed later input 16,646, output 2,243 and total 18,889. There was no change in queries or import of historical tokens. Full conversation correlation is still pending.


## October 7, 2026 — Environment in mise, operation in Task

- Moved preparation/validation tasks env/Python/GPU/Docker/repository to mise, with brief calls to categorized scripts. No duplicated aliases in Task.
- `scripts/environment/plan.sh`, `setup.sh` and `check.sh` preserve sequential order and immediate failure. Host scripts maintain their original actions and controls.
- Task preserves deployments, logs, state, inference, telemetry and code tests. Deployments use `mise run repo:check` as preflight.
- Removed the aggregator `dev:check`: environment and inference are invoked separately. Updated guides and error messages. No versions or running services are modified.


- Documentation convention: the 17 Markdown files of `docs/`, including architecture/diagnostics, use lowercase names. Links and references required by scripts were updated. README.md, LICENSE and AGENTS.md retain their conventional names at the root.


- Python dependencies migrated from infra to `pyproject.toml`/`uv.lock` at the root. Metadata and comments explain purpose, PyYAML, platform and environment limits. mise fixes uv 0.12.23; setup/check use uv with strict lock. The previous requirements were removed, without duplicating definitions.

**October 7, 2026 — secret control before publishing**

- Gitleaks 8.30.1 and artifact/checksum fixed in mise; additional rule for the local master key of LiteLLM.
- New Task `security:secrets`, implemented in `scripts/security/`: publishable files, staged content and complete local history; redacted reports and canary test.
- `security:test`: five tests with the real scanner in temporary repositories; new secrets, divergent staging, deleted history, symlinks and credentials ignored.
- `docs/security.md`: coverage applied and proposed; Semgrep/OSV/Trivy/ASVS still pending, without declaring OWASP certification.
- README registers the requested GitHub repository; SSH push pending.

**October 7, 2026 — publishing and inline review**

- First push completed: `main` in `alejandro-onatra/local-agent-platform`; commit `320fe6c` verified with GitHub via SSH.
- `AGENTS.md` preserves the preference to announce each action block, explain method/purpose and show inline diffs step by step. A link to the patch does not replace that explanation.
- README registers real publication and tracking of `origin/main`; secrets, artifacts and local environments remain outside the repository.

## October 7, 2026 — English documentation and commit validation

- Translated repository documentation, diagram labels and example comments to English. Technical commands, paths, versions and recorded evidence are preserved; token thousands use English separators.
- Replaced educational-use framing with `docs/project_scope.md`; kept the MIT license and its warranty terms.
- Saved the requirement to announce actions and explain actual inline diffs step by step in `AGENTS.md`.
- Set the GitHub repository description to: Model-agnostic local agent platform with OpenHands, Ollama, Docker Compose, and OpenTelemetry observability.
- Added versioned `.githooks/pre-commit`, safe local installation/check scripts and corresponding mise tasks. Task owns the sequential environment/code/security validation calls. The hook is active in this checkout and performs no package installation or Docker operations.
- Added disposable-clone tests for clean commits, rejected secrets, invalid shell syntax and preservation of a different existing hooks path. Isolated inherited Git environment variables in the nested secret tests.
- Initial commits were pushed to `origin/main` over SSH. No runtime configuration, model weights or running containers were changed for documentation or hooks.

## October 7, 2026 — First offline runtime contract slice

- Added Python component protocols and a synchronous synthetic-triage runtime, independent of OpenHands and provider SDKs.
- Added two offline model substitutes, deterministic decision rules, default-deny policy and explicit action-bound, expiring one-use approvals.
- Added in-memory state/audit/receipts and safe repeated resume of completed runs; no database, external tool effects or restart persistence.
- Added synthetic YAML fixtures, categorized workflow scripts, Task demos/tests and workflow checks in the pre-commit sequence.
- Documented current scope, diagram, ADR 002 and pending PostgreSQL/model/OTel integrations. Existing Docker services and Python dependency pins are unchanged.

Validation: both provider variants passed the four synthetic fixture outcomes. The default demo produced zero record receipts; explicitly approving the pending action produced one. Waiting requests remain waiting on premature resume. Documentation links and shell syntax were checked.

The 21 workflow tests and 31 existing tests passed through the expanded pre-commit sequence in a disposable clone. Real commit acceptance/rejection checks passed; no new dependencies, model calls or Docker changes were required.


## October 8, 2026 — Household access security design

- Recorded portal.home.arpa, local Authentik accounts, mandatory MFA and a persistent
  OpenHands instance/state/workspace per approved identity as agreed requirements.
- Added SEC-01 through SEC-15 with explicit pending implementation/acceptance and
  evidence for LAN exposure, TLS, identity, permissions, isolation, secrets and recovery.
- Added docs/lan_access.md with diagrams, offline encrypted root custody, separate
  online intermediate/server keys, verified public-certificate distribution and CA
  compromise handling. Caddy's default online root is not claimed to meet this design.
- Added the household milestone before further runtime expansion and linked the
  design from README/OpenHands/security documentation.
- Documentation only: no key generation, certificate enrollment, package installation,
  credential/group changes, Docker restart, port exposure or deployed authentication.


## October 8, 2026 — Automated SEC validation foundation

- Added versioned SEC-01 through SEC-15 evidence requirements, seven offline
  Compose source guards and opt-in verified-root portal TLS checks.
- Added Task commands for configuration, SEC readiness and regression testing;
  included the offline configuration guard in local pre-commit validation.
- Added deliberate unsafe-source, pending-evidence and synthetic TLS tests;
  extended disposable-clone hook acceptance to reject wildcard port exposure.
- Reports contain fixed reasons and source hashes, use mode 0600 and remain
  excluded from Git. Missing deployed/physical evidence remains pending.
- Household deployment, MFA/isolation acceptance, key generation and scanning
  against dated vulnerability databases are still pending.
- Validation: all 83 regression tests passed (31 new SEC tests); actual commits in
  a disposable clone confirmed unsafe-port rejection. SEC readiness reported
  zero passed, zero failed and fifteen pending controls, with checker exit 2.


## October 8, 2026 — Phase-A host inventory started

- Added `mise run env:lan:inventory`, with categorized shell/Python implementation
  and private local reports. No package, firmware, VM or network changes.
- Added an explicit pending VM capacity proposal and ADR 003 with actual resource
  observations, visible prerequisite gaps, Wi-Fi constraints and remaining inputs.
- Added ten code regression tests for complete collection, missing evidence, capacity, private reports
  and bounded network observations, integrated into local commit validation.
- VM/dedicated-host choice, host KVM validation, router/client inventory and the
  offline CA ceremony remain pending; no household SEC control is accepted.
- Validation: real inventory succeeded with sufficient candidate capacity and
  pending KVM/owner prerequisites; all 93 code tests and disposable-clone hook
  checks passed. Twenty-five Markdown documents and 95 local links were verified.


## October 8, 2026 — Selected host-container boundary and prepared hardening

- Owner selected host containers; KVM is no longer a prerequisite. Updated the
  environment inventory, ADR and plan while retaining VM sizing as an alternative.
- Prepared an opt-in verified-UID/GID, readonly-root/init/AppArmor profile with
  bounded tmpfs, persistent-data preservation and explicit apply/rollback tasks.
- Added selected-field runtime checks for process identity, kernel filters,
  cgroups, mounts, network declaration, log rotation and synthetic file canaries.
  Reports exclude raw inspection data/content and remain private and outside Git.
- Added source regression guarding of the candidate and tests for unsafe runtime
  mutations, activation metadata and simulated apply failure/rollback.
- Live Docker verification/application remains pending interactive host
  authentication. Per-user authorization/networks, persistent disk quotas,
  storage outside CloudDrive and real egress/load acceptance remain pending.
- Validation: all 117 code tests passed (11 environment, 11 LLM, 15 observability,
  59 security, 21 workflow); real Gitleaks checked 175 publishable candidates,
  staged content and local refs without findings. Compose overlay syntax passed
  using synthetic UID/GID inputs only. Disposable-clone hooks accepted a valid
  commit and rejected secrets, unintended exposure and invalid shell syntax.
- The real read-only inventory reports the VM as `not_required` for the selected
  host-container boundary. Twenty-seven Markdown files and 107 local links were
  checked without broken links. No activation record exists; no live container
  was recreated and runtime acceptance remains pending owner Docker authentication.


## October 9, 2026 — Diagnose missing or stopped OpenHands

- Runtime discovery now includes stopped agents and checks validated state before
  attempting process probes. Reports distinguish Docker permission failures,
  missing agents, stopped agents and ambiguous selection. Raw errors stay private.
- Security plan reports a missing or stopped existing instance explicitly;
  OpenHands status includes stopped containers. Neither check starts a service or
  changes the existing restart policy.
- Added seven regression tests covering discovery, invalid state, redaction and
  rejection of plans for stopped agents.
- The owner confirmed the expected agent exists and exited with code 255. The
  termination cause and OOM flag remain unverified; no service was restarted.
  A stopped service is a prerequisite failure, not a security acceptance result.
- Validation: all 124 code tests passed, including 66 security tests. Gitleaks
  scanned 175 candidate files, staged content and local refs without findings.
  Shell syntax, Python environment and source guards passed; 107 local links
  across 27 Markdown files resolved. Two scanner false positives in prose were
  removed by reformulating the sentences; no scanner exception was added.


## October 9, 2026 — Owner recovered the baseline services

- Owner reports show Ollama healthy, OpenHands UI HTTP 200 and a successful
  container-to-Ollama model digest check after existing service startup tasks.
- The runtime report passed 13 of 14 selected checks; only readonly-root failed.
  The previous stopped-state report had exit code 255 and OOM flag false, which
  does not identify the termination cause.
- Updated plan and operating documentation with these owner-provided results.
  The optional hardening profile remains unapplied; no service operation was
  executed from this task. Full household security acceptance remains pending.


## October 9, 2026 — Correct automated exec terminal handling

- Host inspection found stopped Compose exec processes under a security plan
  and an apply invocation. No activation record existed. The precise stop
  signal was not captured; user authentication had already completed.
- Identity checks now disable interactive exec and close stdin explicitly.
  Inline startup permission and model checks use the same mode; commands fed
  Python code through stdin retain their input transport.
- Added phase messages and a pseudo-terminal regression for the identity probe.
  No service recreation, profile activation or sudo policy change was performed
  by this task. Live confirmation of the fix remains pending.


## October 9, 2026 — Owner applied the hardening profile

- The updated plan completed with verified UID/GID 10001:10001. The owner applied
  the profile and reported OpenHands/proxy recreation and passing UI/model checks.
- This task independently observed UI HTTP 200 and validated the activation
  record and mode 0600. It did not execute Docker apply itself.
- Updated current plan and operating status. Post-apply process/filesystem
  restrictions, synthetic agent compatibility and household acceptance remain
  pending the corresponding live checks.


## October 9, 2026 — Owner verified the applied runtime baseline

- Post-apply report `container-dvvhad0x.json` passed all 14 selected runtime checks,
  including readonly-root, effective process filters/cgroups, expected mounts,
  internal network declaration, bounded logs and synthetic filesystem canaries.
- Updated current plan and operating evidence with the owner-provided result.
  Exit 2 represents incomplete household acceptance even though the selected
  baseline passed. No exit-status or acceptance requirement was weakened.
- Next: synthetic agent execution under the applied profile, then persistent
  storage quotas, tenant networks/authorization, egress and shared inference checks.

## October 9, 2026 — backend readiness gap

- Confirmed frontend HTTP 200 while backend `/ready` and `/api/settings` return
  HTTP 502 after the owner applied hardening. The underlying startup cause remains
  unconfirmed; the selected runtime restriction baseline remains separate.
- OpenHands startup/application checks now require authenticated Agent Server
  and Canvas proxy JSON responses. Secrets and settings bodies are not exported.
- Added `openhands:backend:check` with fixed log error indicators, bounded health
  retries and regression coverage for a live frontend with a failed backend.
- Prepared code only; no container recreation or security relaxation in this change.

## October 9, 2026 — noexec compatibility candidate

- Observed actual noexec temporary mount flags and absence of an Agent Server
  process, alongside owner-reported backend startup timeout. The pinned PyInstaller
  one-file build requires temporary executable library mappings; exact loader
  error and extraction capacity remain unverified.
- Prepared a read-only, narrowly allow-listed launcher for the existing locked
  Python Agent Server 1.49.6 module. Plan verifies availability before recreation;
  no packages are installed and noexec/read-only/kernel/resource controls remain.
- Extended native loader diagnostics and added preflight, launcher and mount
  regression tests. Candidate application and live recovery remain pending.

## October 9, 2026 — Owner verified Python launcher API recovery

- Owner-provided plan/apply/backend results verified the installed 1.49.6 module,
  authenticated Agent Server and proxy, and container-to-Ollama model digest.
- Independently observed frontend/readiness HTTP 200 and protected settings
  HTTP 401 without credentials. Actual authenticated success is owner-provided.
- Read-only filesystem and traceback log indicators remain unresolved. Extended
  diagnostics with fixed path categories without exporting names or raw text.
- No additional writable mount or permission relaxation. Selected runtime checks,
  synthetic agent tool execution and complete household readiness remain pending.

## October 9, 2026 — Agent response failures after API recovery

- Owner reported no agent response, then a model connection error and unavailable
  Grafana. Independent health checks reached OpenHands and Ollama but not Grafana.
  Owner status confirmed all seven observability containers exited with code 255
  approximately 25 hours earlier; proxy inference recovery remains pending.
- Sanitized read-only error categories identified the unmounted `.config`
  directory. Prepared a 64 MiB noexec/nosuid/nodev, mode-0700 temporary mount for
  that directory only, preserving read-only root and existing restrictions.
- Runtime write checks now require configuration writes; source guard and negative
  tests reject unbounded/executable/world-writable or redirected config mounts.
- No services restarted by this task. Complete agent operation is not claimed from
  authenticated API readiness; actual response and selected runtime rechecks remain.

## October 9, 2026 — Applied configuration fix and proxy recovery evidence

- Owner plan/apply/backend output passed after the configuration tmpfs change;
  all ten recognized error indicators were false in the reviewed recent log tail.
- Independently observed OpenHands/Ollama/Grafana health HTTP 200 and read fresh
  owner-generated streamed proxy report `llm-stream-PjpUlJ.json`: usage 23/8 and
  matching exported counter increments. No Docker deployment was performed here.
- Updated current plan/operating status. Effective restrictions after recreation,
  a real agent tool task and complete household acceptance remain pending.


## October 10, 2026 — prepared SDK cache-usage compatibility backport

- Matched the reported `PromptTokensDetailsWrapper.cache_creation_tokens`
  AttributeError to upstream OpenHands SDK PR #5327 and verified the official
  1.49.6/1.50.0 source diff. This is a normalization bug, not evidence of a GPU
  failure or a reason to relax read-only-root restrictions.
- Prepared an exact-version/source-guarded process-memory backport in the
  existing hardened Python launcher. It adds the upstream attribute guard,
  preserves function aliases and checks real installed usage types before launch.
- Added a locked upstream reference function and regression tests reproducing
  the old crash, preserving numeric totals/cache buckets and Responses API usage,
  rejecting changed source/version, and stopping startup safely on self-test
  failure. Added a fixed log indicator without exporting raw error payloads.
- Deployment and actual conversation recovery remain pending owner recreation;
  the previous authenticated health results do not accept full agent operation.
- Validation: the repository gate passed 156 local tests (11 environment, 11 LLM,
  15 observability, 98 security and 21 workflow); Gitleaks found no secrets across
  183 candidate files, staged content and local history. `git diff --check` passed.
  The patched normalizer's executable AST matches upstream SDK 1.50.0. Local
  regression tests use the locked official function with synthetic usage types;
  the installed SDK/LiteLLM self-test and actual agent recovery require owner plan/apply.


## October 10, 2026 — legacy fix applied; stable 1.26.0 upgrade prepared

- Recorded owner output: legacy SDK 1.49.6 real cache-usage self-test passed,
  recreation succeeded, authenticated backend/proxy and Ollama checks passed;
  reviewed log indicators were false. Actual agent execution remained pending.
- Verified latest stable Canvas 1.26.0 release on October 8, registry digest,
  linux/amd64 manifest, source revision, installed-runtime Dockerfile and backend
  defaults: SDK/Agent Server 1.53.0 and Automation 1.19.0.
- Prepared updated image/version locks and native normalizer verification,
  removing the active memory backport. Kept the earlier failing function only as
  a regression reference; updated the route utility's SDK contract guard.
- Added backed-up operational upgrade tasks, candidate UID/native-usage preflight,
  private stopped state/project archives, overlapping-operation lock and ordinary
  startup guard. Backups precede recreation; failures before recreation restart
  existing containers, while failures after recreation stop the candidate and
  retain archives without an automatic potentially incompatible state downgrade.
- Use bundled LiteLLM pricing metadata and suppress the SDK startup banner;
  local session-key HTML injection remains disabled as in the new upstream default.
- Saved public source recovery files outside Git/CloudDrive before these edits.
  Docker execution still requires owner interactive sudo; deployment, agent
  execution and post-upgrade security acceptance remain pending.
- Validation: repository gate passed 168 tests (11 environment, 11 LLM, 15
  observability, 110 security and 21 workflow); configuration guards passed and
  Gitleaks found no secrets across 188 candidate files, staged content or local
  history. Release/image/source consistency and `git diff --check` passed.
  Candidate Docker preflight, backup generation and actual upgrade remain pending
  owner host execution, not established by fake-engine transaction tests.


## October 11, 2026 — owner applied OpenHands 1.26.0 upgrade

- Recorded owner plan/apply output: candidate identity, installed modules and
  native cache-usage self-test passed; consistent private backups were validated
  before OpenHands/proxy recreation. UI, authenticated backend/proxy and Ollama
  model checks passed.
- Independently checked backup metadata and archive hashes against the saved
  manifest: directory 0700, archives 0600, both hashes matched. Archive contents
  were not displayed; restoration has not been tested.
- Updated current status in the plan, OpenHands guide, isolation record and
  upgrade procedure. Earlier runtime-control results do not establish restrictions
  of the new container. Collector log mount refresh, streamed proxy usage and
  a real read-only agent tool task remain pending, along with household acceptance.
- This bookkeeping change does not recreate services, change runtime settings,
  commit files or publish repository changes.


## October 11, 2026 — stopped services block post-upgrade acceptance

- Recorded owner checks: OpenHands stopped with exit code 0, no OOM flag and
  `agent_not_running`; log mounts could not be configured; LiteLLM stopped with
  exit code 0 and no OOM flag, preventing the streamed usage test.
- Independently observed Docker startup at 11:20:57 UTC, after the upgrade, while
  the host boot preceded it. Ollama was reachable; OpenHands and Grafana were not.
  Their different restart policies make daemon restart a plausible explanation;
  container stop timestamps are still needed for correlation.
- Documented ordered recovery through existing startup tasks, preserving recorded
  hardening, credentials and persistent data. No runtime policy, service, image,
  backup or dependency was changed by this documentation update.


## October 11, 2026 — service recovery and deployment-lock image verification

- Recorded owner recovery: authenticated OpenHands APIs and Ollama checks passed;
  seven observability services started and three selected Collector log mounts
  were refreshed. Streamed proxy usage and counter increments matched at 23/8;
  independently confirmed those numeric fields in the local diagnostic report.
- The runtime check passed 13 selected conditions but rejected the new image:
  its hardcoded digest still identified 1.24.0. Earlier tests reused that constant,
  missing its disagreement with the deployment lock.
- Removed the duplicate digest. Runtime assessment now requires the immutable
  image in `infra/openhands/versions.yaml`; invalid locks fail before Docker probes.
  Old releases and unrelated images remain rejected. No services or restrictions
  were changed by this fix.
- Added five regression tests. All 115 security tests and configuration guards
  passed. Corrected host runtime revalidation, a real agent task and household
  acceptance remain pending.


## October 11, 2026 — corrected live runtime baseline accepted

- Owner reran `security:container:check` at 14:57 UTC after service recovery;
  all 14 selected runtime conditions passed, including the pinned image.
- Independently read `container-mfk5ix6b.json` and verified its checker hash
  against current source. The report retains household readiness pending and
  rootless/user namespaces unverified. Exit 2 is the pending-acceptance result.
- Updated the current plan, isolation evidence and upgrade guide. A real agent
  tool task, cross-user/egress controls, disk limits, fair inference and
  authenticated application isolation remain pending. No services, runtime
  settings, checker code or acceptance requirements were changed in this update.


## October 11, 2026 — reported post-upgrade agent terminal exercise passed

- Owner supplied the OpenHands response to `cd /projects/demo && pwd && ls -la`:
  the working directory and existing project files were reported successfully.
  The agent stated no file modifications or dependency installations.
- Recorded the scope as an owner-reported read-only tool exercise; no private
  transcript was exported and no independent Docker run or filesystem comparison
  was performed by this task.
- Updated current status in the plan and operating guides. Existing demo test
  acceptance, this conversation's effective proxy route, broader tool behavior
  and household isolation remain separate checks. No service or code changed.


## October 11, 2026 — existing demo acceptance passed after upgrade

- Owner ran `openhands:demo:check` inside the existing agent container:
  `test_negative`, `test_positive` and `test_zero` passed, with synthetic add
  acceptance also passing. No implementation or test edits were made by this task.
- Together with the 14-condition runtime result and reported real terminal task,
  this accepts the basic upgraded runtime/demo compatibility. It does not accept
  all tools, every conversation's telemetry route or household isolation.
- Updated the current plan summary and operating evidence. Dedicated per-user
  persistent storage outside CloudDrive, verified disk limits, tenant networks,
  authentication and remaining household probes stay pending. No service,
  storage, permission, dependency or checker was changed in this update.


**October 11, 2026 — synthetic storage pilot prepared**

- Record initial household size as 2–3; use two synthetic UIDs and four separate
  128 MiB ext4 filesystems, 512 MiB total outside Git/CloudDrive.
- Add strict policy, root-controlled allocation/mount lifecycle and bounded Docker
  ENOSPC/cross-UID probes in `scripts/storage/`. Existing services/data unchanged.
- Re-reserve new images after formatting: a real disposable-file test found
  formatting can release allocated extents despite `nodiscard`.
- Register environment plan/setup/check in mise; tests, acceptance and preserved
  image unmount in Task. Add 31 regression tests to the existing security gate.
- Add storage procedure and Mermaid diagram; document partial/reboot recovery,
  report limits and pending real host/application/household acceptance.
- Host allocation, live mounted fill probes and real-user migration are not
  applied by this preparation. No accounts, CA keys or LAN services are created.

Preparation validation passed: 204 tests (31 storage), Gitleaks across 195
candidate files with no findings, 95 local documentation links and whitespace
checks. The actual read-only host plan passed with ext4 and 63.96 GiB free;
512 MiB allocation and live mounted probes remain pending.


**October 11, 2026 — owner applied and accepted synthetic storage**

- Owner plan/setup/mounted check/acceptance passed at 21:35 Europe/Berlin.
- Four 128 MiB images (512 MiB total) each reported 103.93 MiB filesystem
  capacity; each probe reached ENOSPC after writing 101.0 MiB.
- All 24 probe conditions passed, covering expected UID, own canary access,
  foreign host/UID denial, disk-full denial and scratch cleanup.
- Independently reviewed saved reports: mode 0600 and current checker hash.
- Updated status in the plan, storage procedure, container/SEC checks and ADR.
  This documentation update changes no code, dependencies, services or accounts.
- Real application tenants, persistent family budgets, network isolation,
  authenticated access and restart/restore remain pending.


**October 12, 2026 — separate synthetic OpenHands instances prepared**

- Add per-UID Compose templates and native umask wrapper; localhost 8101/8102,
  independent projects/networks, bounded state/workspace and process resources.
- Explicitly override image-declared volumes and remap only image account entries;
  host account databases and current demo/model/observability services unchanged.
- Add guarded plan/up/check/accept/down operations. Acceptance uses native
  secret and idle-conversation APIs with synthetic records and cleanup; no LLM run.
- Add private descriptor-based native key checks, no HTML key injection and
  state-preserving failure recovery. Register operations/source checks in Task.
- Document diagram, source/live distinctions, capacity limits and next acceptance.
  No instances, family accounts or identity/CA services are deployed by this edit.

Preparation validation passed: 231 tests (27 new instance regressions), 203
Gitleaks candidate files with no findings, installed Compose parsing for both
rendered documents, 103 local links and whitespace checks. Host Docker access
requires interactive sudo; real pilot deployment/acceptance remains pending.


**October 12, 2026 — instance process inspector correction**

- Owner storage and native preflight passed; both pilots started and reached
  authenticated API checks, then `runtime_process_drift` stopped the sequence.
- Correct equivalent colon/equals AppArmor/NNP option comparisons; require actual
  Docker AppArmor profile, deny duplicate/disabled/extra options and added caps.
- Report fixed tenant/service/control identifiers and per-project stop recovery.
- Add read-only `openhands:instances:diagnose` for running/stopped/missing pilots,
  without keys, logs, inspect values or runtime changes.
- Add negative, privacy and recovery regression tests; update plan and procedure.
  Actual failing Docker fields/recovery state await the owner's diagnostic.

Validation passed: 236 tests (32 instance regressions), Gitleaks without findings
across 203 candidate files, 104 local links and whitespace checks. A focused
regression also checks that stopped diagnostic state is not reported as a
running pass. Actual Docker diagnosis and instance recovery remain pending.


**October 12, 2026 — stopped pilot diagnosis recorded**

- Owner report `instances-pmm01asR.json` at 22:39 Europe/Berlin: four stopped
  pilot containers and 60 passed process-declaration checks, no failed conditions.
- Independently verified saved report mode 0600 and current checker fingerprint.
- Documented guarded down/up/check/accept recovery with state/keys preserved.
- Running mounts/networks and secret/conversation isolation remain pending.
  This update changes documentation only; no containers, code or credentials changed.


**October 12, 2026 — owner recovered and accepted both pilot instances**

- Down/up/check/accept succeeded between 22:56 and 22:57 Europe/Berlin.
- Two running instances passed applied runtime/API checks and all six synthetic
  filesystem/authentication/secret/idle-conversation categories each.
- Four saved reports independently checked: mode 0600 and matching current source.
- Updated current status in plan/procedure and recorded evidence in security/
  container docs. Pilot startup failure and selected API isolation exercise closed.
- Household login, WebSocket/egress, model gateway, restart/restore and final
  family budgets remain pending. This evidence update changes documentation only.


**October 18, 2026 — extended pilot acceptance prepared**

- Add bounded TCP peer-network probes in actual agent namespaces, with own and
  host target positive controls before/after; no raw IPs or network rule changes.
- Add native session WebSocket sync/auth/peer-conversation tests through each
  ingress using the existing pinned image; no URI/Env/CLI key delivery.
- Add idle-only, per-pilot restart and generated-record export/import checks.
  Native keys are compared in memory, not exported; real records are untouched.
- Register three service operations in Task and add privacy/failure regressions.
- Extend procedure/plan/SEC docs with a recovery diagram and explicit limits.
  No services were restarted, no LAN ports opened and no backups of real state
  created by this preparation. Live owner acceptance remains pending.

Preparation validation passed: 257 tests, including 21 new extended regressions;
208 Gitleaks candidate files with no findings, 108 local links and whitespace
checks. Source fingerprints are recorded in the instance guide. Live owner
network/session-WebSocket/restart/synthetic-import acceptance remains pending;
no deployment or restart was performed here.
