# ADR 003: Household isolation and phase-A environment

Date: October 8, 2026
Status: host containers selected by the owner; live restrictions and household
acceptance pending. The earlier VM proposal below is retained as history.

## Updated decision

The owner authorized proceeding with restricted containers on the current host.
KVM/UEFI SVM is not required for that path; absent KVM no longer blocks the selected
environment. `config/lan/candidate.yaml` records `decision: host_containers`.
Read [container isolation and acceptance](../container_isolation.md) for the
optional readonly-root profile, runtime evidence and remaining storage/network
requirements. Sharing the host kernel is an acknowledged boundary limit, not an
accepted claim that all SEC controls pass.

## Context and actual observations

Phase A has started with a read-only host inventory. The current computer exposes
16 logical CPUs, approximately 30.24 GiB total RAM and approximately 70 GiB free
on the filesystem containing `/var/lib/docker`. Free resources are snapshots,
not reservations or concurrency acceptance. The observed default route uses Wi-Fi
and DHCP. Private IPs remain in excluded local diagnostic reports, not this ADR.

The execution context did not expose VMX/SVM CPU flags, `/dev/kvm`, KVM modules
or the virtualization commands. This does not establish hardware incapability or
a firmware setting. Repeat the inventory in the host terminal and use a host-side
KVM check before diagnosing firmware or installing a virtualization stack.
Do not change firmware, load modules or restart the computer from this inventory.

## Historical VM investigation — October 8, 2026

The owner reran the inventory directly in the host terminal. It still found no
visible CPU virtualization flag, KVM device/module or virtualization tools.
A separate read-only check found 16 CPU flag records, none with `svm`, and kernel
configuration `CONFIG_KVM=m` / `CONFIG_KVM_AMD=m`. No hypervisor was detected by
`systemd-detect-virt`; no `clearcpuid` boot option was observed. These observations
agree with the inventory parser; no inventory code change was required.

The principal hypothesis is disabled UEFI SVM mode, not a confirmed firmware
setting. The observed board is ASUS ROG STRIX X570-E GAMING. For the optional VM alternative only, the owner could
inspect UEFI Advanced / CPU Configuration / SVM Mode, enable it if disabled, save
and reboot when their work is saved, then rerun `mise run env:lan:inventory`.
Menu placement can vary by firmware version. The expected first change is a
visible CPU flag; missing tools and the boundary decision may remain pending.
No firmware setting or reboot was performed by the agent. See the
[ASUS AMD virtualization procedure](https://www.asus.com/uk/support/faq/1045141/).

## Earlier proposed boundary (superseded)

Prefer a KVM/libvirt VM for the household identity, HTTPS gateway and agent
containers on the current computer, subject to owner choice and host support.
Another Linux host is an alternative. Direct host containers require an explicit
assessment of the shared personal-host kernel boundary.

The initial proposal used `decision: pending`; the updated selection is above. Start
capacity assessment at four vCPUs, 8 GiB guest memory and 40 GiB guest storage,
while retaining 8 GiB available host memory and 20 GiB free storage. Adjust after
user count, intended tasks and measured load are known. No disk or VM is allocated.

Keep the existing GPU inference service on the host initially. A future guest
model route must be authenticated and reachable only through an explicitly
restricted interface/source; it must not expose the existing proxy master key or
make the model API generally available on the LAN. GPU passthrough is not proposed
for this first candidate. That connection is still to be implemented and tested.

Inside the guest, separate OpenHands instances, state, workspaces and networks
per identity. Sharing a guest still shares its kernel and administrative boundary;
it does not automatically prove tenant isolation. Mount no personal host HOME,
SSH/browser credentials or Docker management socket into the guest or agents.
The offline root CA is never part of this VM. Online intermediate signing material
requires a separate restricted service; guest administrator compromise remains a
key-custody risk. No currently accepted SEC control follows from this proposal.

## Network implications

A conventional Ethernet Linux bridge is not the default approach for the observed
Wi-Fi interface. Evaluate a private guest network and narrowly controlled HTTPS
ingress, or use an Ethernet/dedicated-host option. Libvirt's default NAT allows
outgoing traffic; it is not an agent egress policy. Model access and unrelated
LAN/host access need explicit rules and negative reachability tests.

Reserve a stable LAN address and configure household DNS after confirming router
capabilities. Do not publish ports, alter NetworkManager/netplan/firewall rules or
assume guest-network isolation during inventory. IPv4 and IPv6 acceptance remain
required. Existing desktop loopback services stay running in their current form.

## Reproducible inventory

```bash
mise run env:lan:inventory
mise exec -- task repo:environment:test
```

The mise command calls `scripts/environment/inventory-lan.sh` and its Python
implementation. It reads Linux resource/KVM observations and bounded `ip` query
commands. It does not install software, enumerate other devices, invoke sudo or
inspect secret stores. It writes `artifacts/diagnostics/lan-host-*.json` with mode
0600. Full observed addressing stays in that excluded report; console output
contains capacity and prerequisite states. MAC addresses are discarded.

Exit 0 means inventory collection succeeded, even when the proposed VM remains
pending or lacks capacity. Exit 1 means collection failed; raw errors are withheld.
The JSON distinguishes capacity, visible prerequisites and an owner decision.
Missing evidence never becomes a pass. No result approves MFA, firewall rules,
client trust, private-key custody or family access.

Code regression tests run through Task and the existing local commit validation
sequence. This separates environment inspection from testing the inspection code.
No additional Python dependency or environment-tool version is required.

## Inputs needed before installation

- Host containers are selected; the shared-kernel boundary is recorded.
- Initial user count is 2–3; client device/platform list and peak simultaneous jobs remain needed.
- Router DNS/reservation capability and trusted/guest segment behavior.
- Confirmed offline root storage, two separate removable copies and a separately
  protected passphrase record. Never upload passwords or private materials.

The owner applied the [synthetic storage pilot](../storage_isolation.md) on
October 11; its four mounted capacity/UID-denial probes passed. This does not
migrate real users or establish authenticated application isolation.

Next: prepare separate application instances and required-mount startup guards;
verify their state/credentials separation and restricted model/ingress networks;
then prepare identity/gateway/issuer definitions and the supervised CA ceremony.
No VM lifecycle, household login service or CA is installed by this pilot.
Phase A and household SEC acceptance remain open.

## Recorded validation — October 8, 2026

The real mise inventory succeeded and recorded capacity as sufficient for the
candidate snapshot; VM prerequisites and the owner decision remain pending.
The report used mode 0600. Versioned source hashes identify the candidate/checker;
private network addressing was not added to Git.

The full commit validation sequence passed 93 code tests, including ten inventory
regressions; the secret gate checked 166 publishable files, staged content and
local history without findings and passed its canary. Disposable-clone hook
acceptance/rejection checks passed. Documentation resolved 95 local links across
25 Markdown files, and `git diff --check` passed. These results neither allocate
a VM nor accept any deployed household SEC control.

## Primary references

- [Ubuntu libvirt/KVM prerequisites](https://ubuntu.com/server/docs/how-to/virtualisation/libvirt/)
- [Libvirt NAT and wireless bridge limitations](https://wiki.libvirt.org/Networking.html)
- [Authentik small-scale Compose installation and optional socket removal](https://docs.goauthentik.io/install-config/install/docker-compose/)
- [Smallstep offline root and online intermediate custody](https://smallstep.com/docs/step-ca/certificate-authority-server-production/)
