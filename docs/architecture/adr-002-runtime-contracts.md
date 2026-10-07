# ADR 002: start the decoupled runtime with an offline contract slice

Date: October 7, 2026. Status: accepted for the reference implementation.

## Context

The local OpenHands/Ollama stack and proxy telemetry have passed recorded checks.
The platform still needs a runtime that does not depend on a specific agent UI,
provider SDK or model-generated permission. A first use case in the plan is
synthetic message triage with deterministic decisions and explicit approval.

## Decision

Use small Python protocols and immutable value objects for the runtime, model,
router, decisions, state, approval, policy and tools. Reuse the locked Python and
standard library. Test two offline provider substitutes through the same runtime.
Use an in-memory reference store to verify transitions and approval contracts
before implementing the planned PostgreSQL persistence adapter.

The only tools are read-only synthetic preview and an approval-gated in-memory
receipt. Model output cannot select shell commands or grant permissions. Decision
rules select among workflow routes; authorization remains in the policy/gateway.

No LangChain, LangGraph or Jev dependency is needed for this slice. A later
orchestrator/framework adapter can be evaluated against the same behavior and
state/security requirements. This does not implement adapters for OpenHands itself,
OpenAI, Anthropic or Ollama yet.

## Consequences

- We can verify component replacement, denial and approval handling without GPU,
  credentials or inference cost.
- No database or new service is deployed. This step does not close the persistent
  state/recovery phase or the complete end-to-end MVP.
- Approval identity and effects are synthetic. Real workers require authenticated
  actors, isolation, transactional state and uncertain-outcome recovery.
- Local audit operations define initial instrumentation boundaries. Real OTel
  export, privacy allowlists and dashboard acceptance are separate work.

See [implementation and acceptance](../synthetic_workflow.md).
