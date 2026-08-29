# Phase 20 — Runtime reproduction

## Purpose

Close the gap between a test that invokes the execution shell and the runtime that is actually constructed in production.

The Phase 20 regression intentionally uses the real `RuntimeBundle` constructor and the real `_execute_auto` method. Only external resources and live execution I/O are replaced with deterministic test doubles.

## Verified production-shaped path

`RuntimeBundle.__init__ -> RuntimeBundle._execute_auto -> RuntimeExecuteDispatchFacade._prepare_auto_execution_dispatch -> ExecutionService admission -> ExecutionService superstructure -> ExecutionService governance -> ExecutionService FIOA wrapper -> try_execute_opportunity -> ExecutionService post-execute bookkeeping -> runtime._record_exec`

The regression verifies that canonical decision ID and correlation ID survive into the execution result plan and that a successful submission updates the runtime's last-submitted block.

## Deployment boundary

The deployed process uses the same `RuntimeBundle` constructor and `_execute_auto` implementation. Phase 20 therefore removes the prior test seam where the runtime object was created with `__new__` and manually populated.

Phase 20 does **not** claim live end-to-end trading. RPC, signing, and capital movement remain outside the regression and must be verified separately in the deployment environment.

## Safety

- no live RPC
- no signing
- no capital movement
- governance and admission remain authoritative
- OMAR remains recommendation/learning-only
- canonical outcome/learning lineage remains downstream of actual execution results
