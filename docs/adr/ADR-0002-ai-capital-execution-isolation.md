# ADR-0002: AI → Capital Isolation (Hard Boundary)

**Status:** Accepted

## Context
Unbounded “AI executes trades” collapses responsibility and makes auditability impossible. Personal wealth systems require control boundaries.

## Decision
Enforce a hard separation:

1) **AI proposes** (what to do, and why)
2) **Capital engine validates** (risk/caps/probation/defensive clamps)
3) **Execution executes** (build calldata, simulate, sign, submit)

The boundary is enforced via Command Center controls and a must-pass gate path.

## Consequences
- ✅ Capital can be frozen while auto-trading continues (baseline sizing)
- ✅ Kill switches are meaningful and immediate
- ✅ Each capital move can be explained with “who/why/what checks passed”
- ❌ More plumbing: proposals, approvals, and execution lifecycle logs
