# Winter Sports — initial Codex prompt

Implement a new `winter_sports` game package in this repository. This file is the implementation brief, not player-facing documentation. Read the repository and `AGENTS.md` first, then inspect the existing Dance and Shadow Run games before changing code.

## Goal

Build a deliberately simple but playable Winter Sports collection for the dance mat. The first priority is mechanics, physics, input feel, and tunability — not polished graphics. It should already be fun enough that the player must react and make corrections rather than discover one fixed input sequence that always wins.

Target hardware is Raspberry Pi 1 B+, so keep the implementation small and cheap. Develop and test on desktop first.

## Display and rendering contract

- The logical game surface is **427x240**.
- Scale it exactly 2x to **854x480** using **nearest-neighbour** scaling.
- Keep the simulation independent from pixels. Positions, velocities, balance, speed, wind, steering, timing, etc. must use float state in continuous/world coordinates. Rendering is only a quantized visual approximation of that state.
- Do not derive simulation state back from sprite rectangles or integer screen coordinates.
- Start with a vertical top-down view. Do not implement pseudo-3D for the initial version.
- POC graphics should be intentionally primitive:
  - player = coloured square/rectangle;
  - track boundaries = simple curved/segmented white lines;
  - gates, start/finish, jump-distance marks and similar landmarks = simple coloured lines/triangles;
  - minimal text outside menus/debug tuning.
- Keep simulation and renderer separable so art can be replaced later without rewriting physics.

## Input

The dance mat is the primary controller, but every action must be usable from the keyboard during development. Reuse the repository's shared input/action conventions where possible instead of reading raw joystick events directly in gameplay.

The core physical vocabulary should be shared across sports:

1. **Cadence / stepping** — alternating foot releases/presses, used for starts and propulsion.
2. **Balance / lean** — while standing on two contacts, unloading one side steers or corrects balance.
3. **Biased cadence** — continue stepping while maintaining a directional lean, e.g. speed skating through a turn.
4. **Airborne / jump** — both contacts released. Depending on the sport this may be a real jump or a light braking action.
5. **Row transition / stance change** — jump and land one row forward/back when a sport needs a discrete state transition.
6. **Leave stance / brake** — step/jump away from the active stance to brake strongly after the finish.

Do not make every sport interpret the same gesture identically. The shared layer should detect useful physical facts/events; each sport decides their meaning.

## Shared movement/gesture model

Create a small reusable layer that can expose values/events such as:

- left/right contact state;
- current stance/contact pair;
- cadence rate;
- cadence regularity;
- cadence symmetry;
- lean / balance input;
- lean velocity if useful;
- airborne state and airborne duration;
- landing asymmetry/timing;
- stance/row transition events.

Avoid making this more abstract than needed for the sports below. Keep it testable without physical hardware.

## Game flow

On startup:

1. show a simple minigame selection list;
2. if the sport has multiple courses/variants, show course selection;
3. show a temporary **developer tuning screen** for that sport;
4. after confirmation show a **3 second countdown**;
5. run the event;
6. show a simple result and allow retry/back.

The tuning screen is part of development and may be removed later. It should expose useful numeric parameters with simple sliders/adjusters, for example wind strength/variability, steering gain/inertia, balance drift/response, cadence propulsion, takeoff/landing windows, landing instability, braking strength, crash threshold, etc. Only expose parameters relevant to the selected sport.

Persist the latest tuning values locally so reopening the game starts with the values used last time. Provide a `Reset defaults` action. Keep the storage simple (JSON/INI is fine) and robust to newly added parameters.

Also provide a toggleable developer overlay during gameplay with useful live values such as speed, lean/balance, balance velocity, wind, cadence, current segment and required/ideal lean. It is for tuning, not final UI.

## Selection-list refactor

Before implementing the new menus, inspect the current song selection in **Shadow Run**. Its list behaviour, selection, viewport/scrolling and visual treatment are currently the best version in the repository.

Extract/generalize the useful list/selection/scrolling behaviour into a small reusable component in an appropriate shared module. Do not drag Shadow Run-specific song knowledge into the generic component.

Then:

- keep Shadow Run using the shared component;
- replace the older/similar selection list in the Dance game with the shared component;
- use the same component for Winter Sports minigame selection;
- use it again for Winter Sports course/map selection.

Preserve the existing player-visible behaviour of Shadow Run unless a small change is required by the extraction. Keep navigation compatible with keyboard and dance-pad actions.

## Physics/gameplay principle

The game must not reward blindly replaying one memorized sequence. Add small controlled variability and state dependence so the player has to react.

Useful tools include:

- seeded per-run environmental variation such as wind/grip/balance disturbance;
- response depending on current speed, lean, lateral velocity and previous mistakes;
- inertia and delayed response where appropriate;
- trade-offs where aggressive steering/stepping gives more immediate effect but costs stability/speed;
- errors that can propagate into the next section rather than always causing an immediate fail.

Prefer deterministic seeded randomness so a run can be reproduced while tuning.

There should be no hard fail screen for small mistakes. Losing balance should normally mean speed loss, wobble, bad line, poorer distance/style or a recoverable near-crash. A severe threshold may produce a fall/crash for sports where it makes sense.

## Initial sports

Implement the common framework so these can share as much code as is naturally useful. A sport may have a small sport-specific state machine and physics profile; do not force everything into configuration if code is clearer.

### Ski jumping

Variants: at least **small hill** and **large hill**.

- Start stance is on two contacts on the rear/bottom row.
- During in-run the player balances by unloading left/right as forces disturb them.
- At the takeoff edge the player performs a two-foot jump/row transition forward.
- Takeoff timing, balance and left/right asymmetry affect launch quality and flight stability/distance.
- During flight the player continues correcting balance; include wind with modest per-run variation.
- Landing is another two-foot row transition forward.
- Landing timing/symmetry and balance at touchdown affect style, remaining distance and whether the skier wobbles/falls.
- Show simple distance marks on the hill.

### Bobsleigh

- Start with alternating fast stepping to simulate the push start. Reward useful cadence/regularity, not merely impossible maximum tapping.
- At the boarding point the player settles onto the normal two-contact stance.
- Through the course, leaning left/right steers the sled. Strong unnecessary corrections should cost speed and/or stability.
- Both feet briefly airborne may act as mild braking/coasting rather than a jump.
- After the finish, leaving the normal stance / moving a row forward or backward should brake strongly.
- Use several predefined courses.

### Luge / skeleton

These may reuse bobsleigh courses and most runtime code but use distinctly different response curves/profiles. Luge/skeleton should feel more sensitive and less inertial than a bobsleigh, not merely be renamed bobsleigh.

### Speed skating

Variants: **short track** and **large oval**.

- Straights are cadence-driven propulsion.
- Turns combine inward lean with continued/asymmetric cadence.
- Going as fast as possible should not simply mean stepping as fast as physically possible: excessive/aggressive cadence should reduce efficiency/stability.
- Incorrect lean at high speed should push the player wide or make them lose speed/balance.
- Stopping after the finish can use leaving the active contacts / a braking stance.

### Alpine skiing

Support predefined courses and profiles such as slalom / giant slalom / downhill (a smaller subset is acceptable for the first implementation if architecture already supports the rest).

- Short cadence start to represent pole pushes.
- Main gameplay is balance/lean steering.
- Different disciplines should mainly differ through course geometry and response curves: steering responsiveness, inertia, target speed, penalty for late turn-in, etc.
- Crossing/stepping away after the finish is braking.

### Snowboard slalom

May share alpine course/runtime concepts but must feel different through slower edge-to-edge transition, different inertia/steering curves and different consequences for late transitions.

### Ski cross

Share alpine steering/balance where useful, but terrain includes jumps/rollers.

- Both-feet-airborne means a real jump here, not braking.
- Takeoff timing/line affects jump state.
- Landing asymmetry/timing feeds directly into post-landing balance and speed.
- Bad landings should often cause a recoverable wobble that makes the next turn harder rather than instantly ending the run.

## Course representation

Keep courses simple and data-driven enough to make several tracks cheaply. A course can be a sequence/spline of segments with values such as distance/length, centerline/curvature, width, slope, feature/gate/jump markers and optional surface/environment modifiers.

Do not tie course geometry to screen pixels. The camera/rendering layer projects the relevant world section onto the 427x240 view.

## Shared simulation profiles

It is fine to use explicit per-sport coefficients such as acceleration curve, steering gain, steering latency/inertia, balance disturbance, environment force, braking curve, cadence efficiency and crash/fall thresholds. The important thing is that Bob/Luge/Skeleton or Ski/Snowboard do not feel identical.

## Provider / launcher integration

When the Winter Sports entry point is runnable, register it in `src/pi_py_games/provider.py` so it appears in the external `pi-games-launcher` manifest like the other games. Add any example/default config needed by the provider, following existing patterns.

Do not leave the manifest pointing at a missing module.

## Tests

Add lightweight tests for the parts that are easiest to regress without graphics, especially:

- gesture/cadence/airborne/landing detection;
- course/profile math;
- deterministic seeded variation;
- persistence/default/reset behaviour;
- any generic list-selection scrolling behaviour extracted from Shadow Run.

Run the existing test suite as well as the new tests.

## Working style

This repository is single-developer. Follow the repository `AGENTS.md`: after a coherent working change, agents may commit and push directly to `main`. Keep commits understandable rather than making one enormous dump.

If the target Raspberry Pi is reachable, deployment smoke testing may be done with `ssh pi286`, using the clone at `/home/dietpi/pi-py-games`. Pull the new `main` there and run only safe/non-destructive smoke tests. If the host is unavailable, do not block the implementation.

For the first pass, favour correct mechanics and easy tuning over visual polish. Do not spend time generating final art before the sports are physically playable.