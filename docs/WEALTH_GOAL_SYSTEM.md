# Wealth Goal System

The wealth-goal system is a canonical operator and runtime control layer.

It provides:
- goal creation and update through `/api/wealth/goal`
- deterministic progress tracking from treasury aggressiveness state
- safe next-goal suggestion logic
- achieved-goal history
- posture controls used by execution sizing and flash-loan borrowing
- mobile/operator visibility for current goal, pacing, and why-not-larger reasoning

## Canonical model

Each active goal tracks:
- target return percent
- timeframe days
- risk tolerance
- max drawdown percent
- capital commitment percent
- current return percent
- progress percent
- goal achieved state
- suggested next target percent
- pacing
- aggressiveness cap
- next-goal eligibility and reasons

## Safety

Wealth-goal posture is advisory on summary paths and bounded on execution paths.
It can clamp aggressiveness, but it cannot bypass:
- drawdown hard stop
- kill switch
- exposure limits
- family budgets
- endpoint / adversarial / route realism gates

## Flash-loan integration

Large flash-loan borrowing reads wealth-goal posture to cap borrow scaling.
This allows larger trades only when:
- route net EV remains positive after realism adjustments
- provider limits allow it
- drawdown and kill-switch state allow it
- wealth-goal pacing does not demand a slower posture

## Canonical state fields

- `capitalBaseUsd`: bounded capital base used for next-goal laddering
- `stabilityScore`: realized-performance stability score used to block unsafe escalation
- `executionRealismScore`: bounded execution realism score used to block unrealistic escalation
- `nextGoalBlockedReasons`: explicit reasons a larger goal is not yet allowed
- `goalLadder`: bounded ladder of safe next-goal targets

## Canonical data root

The canonical runtime data root is `backend/data`. Legacy root-level `data/` is treated only as a migration source.


## Canonical posture inputs

Wealth-goal pacing and next-goal suggestions are bounded by deterministic runtime signals:

- capital base
- realized return progress
- drawdown / hard-stop / kill-switch state
- stability score
- execution realism score
- fund stage
- risk posture

These signals affect posture only through explicit bounded controls such as pacing, aggressiveness caps, and large-trade sizing caps.

## Canonical persistence

Canonical wealth-goal state lives under `backend/data/wealth_goals/`. The final repo treats `backend/data` as the only canonical persistence root.
