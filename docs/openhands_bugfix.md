# Second test: fixing a bug with existing tests

## Objective

Evaluate that OpenHands uses test results to diagnose and correct a bug. The model does not change. Maintain an agent, fixed local profile, and disabled subagents. This exercise uses synthetic monetary values as a programming problem; it is not a financial system and does not calculate real transactions.

The original fixtures are in `exercises/bugfix/`. The preparation task copies two files to `artifacts/openhands/projects/bugfix`, which the agent sees as `/projects/bugfix`. The previous demo is not modified, and access to the full repository is not granted.

## Prepare and check previous failure

From the host, with OpenHands running:

```bash
mise exec -- task openhands:bugfix:prepare
```

The expected result includes three failed tests and two correct ones. The task returns success only if those three specific failures appear, without import errors or missed tests. It is a deliberately defective baseline. Do not deliver the repair to the agent before observing the baseline.

The preparation refuses to overwrite an existing folder. If it was created but the container was not available, start OpenHands and run `task openhands:bugfix:baseline`. Do not delete or restart the exercise once repaired.

## Task for OpenHands

Create a new conversation with the active local profile. Paste:

> Work only in /projects/bugfix. Run pwd and the tests with python -m unittest -v. There is a bug in discounts.py: discounted_total(subtotal, discount_percent) must apply a percentage discount between 0 and 100, return a Decimal rounded to two decimal places with ROUND_HALF_UP, and reject invalid inputs. Use the failures to diagnose the problem and modify only discounts.py. Do not change test_discounts.py or skip tests. Run the tests again and summarize cause, change, and results before/after. Do not download dependencies or access the Internet. Explicitly indicate /projects/bugfix as the directory in terminal actions.

The interface may choose another initial folder; the first action must confirm the actual terminal path and explicitly switch to the indicated workspace. Do not accept an explanation without tool events.

## Check repair

Upon completion:

```bash
mise exec -- task openhands:bugfix:check
```

The acceptance compares byte by byte the tests in the workspace with the original ones in the repository, runs the five cases, and verifies additional fractional discount, zero, rounding, and Decimal type. All code of the exercise runs inside the container, not on the host. The checker does not correct the solution.

The expected result is five original tests passing and four additional checks passing. This reduces the risk of accepting a repair that only fits the given examples. It does not demonstrate full security or that the agent has not written other files: review its events and changes as well.

## Record

Share baseline, acceptance, and final summary of the agent. Record approximate time, attempts, and tool errors if available. The exercise is prepared; the actual execution with OpenHands is pending. Local fixture tests confirm the initial failure and that a reference repair in a temporary copy meets the acceptance; that repair is not delivered to the user's workspace.

## Shared result — October 5, 2026

The user executed `task openhands:bugfix:check`: the five original tests passed, without modifications according to the previous script comparison, and the four additional checks of Decimal type, discount, and rounding also passed. This validates the functional repair present in the workspace. It was not rerun from Work.

During the task, the agent sent a call `file_editor` with `command=str_replace` without the required parameter `path`, and included `file_text`. The tool validation rejected the call. The user was provided with a recovery prompt indicating the correct path and fields; later, the acceptance was shared. Do not claim autonomous recovery: there was human intervention and the complete tool history was not reviewed.

The baseline of the fixtures was verified locally before delivering them (three expected failures and two successes). The baseline output executed on the host was not received; therefore, the before/after record on the host is incomplete. The total time or number of attempts was also not measured.

Experiment conclusion: OpenHands and local Qwen3 can resolve this synthetic bug with guidance. The consistent use of tool schemas remains an observed limitation. Next step: log executions, tool errors, and interventions to evaluate autonomy and prepare observability.
