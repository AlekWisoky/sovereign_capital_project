# Mobile launch wizard

The mobile launch flow now guides the operator through five steps:
1. choose launch mode
2. review active families
3. inspect readiness and blockers
4. review rollout recommendation
5. confirm activation / revert / quarantine action

The wizard uses:
- `/api/launch/state`
- `/api/launch/enable-next`
- `/api/launch/pause-family`
- `/api/launch/revert-family`
- `/api/launch/quarantine-family`
- `/api/launch/family/{family}`
