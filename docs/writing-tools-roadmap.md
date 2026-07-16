# Writing Tools Quality Roadmap

## Goal

The writing workflow produces scene-driven fiction from compact story facts,
checks correctness and novel quality independently, applies scoped revisions,
and derives continuity state from accepted prose.

## Implemented Architecture

1. Context records classify voice, facts, constraints, beats, references,
   source text, and forbidden reveals. Canon-facing sections are bounded,
   relevance-ranked fact records with wording reuse disabled.
2. Every generation run validates a scene contract with pressure, opposition,
   required state change, reveal boundaries, and an ending turn.
3. Scene skeletons define purpose, entry, causal action, escalation, emotional
   turns, and exit before prose generation.
4. `twr write draft` executes separate first-prose, narrative-deepening,
   compression/de-duplication, and voice-polish passes.
5. Viewpoint behavior is supplied through the writer profile and
   `writer/viewpoint_profiles.yaml` without prose imitation samples.
6. Chapter plans track plot, character, and mystery progression, pressure,
   information movement, character choice, and carry-forward state.
7. Deterministic diagnostics flag repeated phrases, repeated openings,
   adjacent semantic repetition, paragraph-function runs, direct emotion
   labels, exposition concentration, and source wording reuse.
8. Generation and revision runs persist model attempts, stage routing,
   intermediate artifacts, context counts, diagnostics, and quality metrics.
9. Targeted revision modes constrain changes to compression, deepening,
   de-duplication, dialogue, viewpoint, exposition, transition, hook, or prose
   polish while preserving canon, events, decisions, and reveal timing.
10. Review packs contain the complete draft, scene contract, skeleton,
    deterministic diagnostics, active chapter direction, canon constraints,
    and reveal lock.
11. Style and pacing reviewers assess narrative movement, embodiment,
    viewpoint specificity, repetition, exposition, dialogue, local pacing,
    scene pacing, chapter pacing, transitions, and ending force.
12. Correctness and Novelness Gates are independent. Missing evidence fails
    closed, and exact source wording forces revision even when model reviewers
    return a pass.
13. Accepted-draft promotion verifies the reviewed draft hash, copies that
    exact prose to `chapters/`, and derives summary, handover, and state from
    the accepted chapter.
14. One writer explanation may receive a configured higher-intelligence
    re-review. The original report is retained, the replacement report rebuilds
    current gates, and a second explanation for the same reviewer is refused.

## Public Workflow

```text
twr write pack
twr write plan-scene
twr write draft-scene
twr write assemble-chapter
twr write draft
twr write diagnose
twr write revise --mode <mode>
twr write revise-scene --scene <id> --mode <mode>
twr review run
twr review novelness
twr review rereview --reviewer <id> --explanation-file <path>
twr write accept
```

`twr write draft` remains the orchestration command for the planning, drafting,
deepening, compression, polish, diagnostic, and provenance stages.

## Acceptance Evidence

- Scene contracts and skeletons are JSON Schema validated.
- Source phrase thresholds and semantic repetition threshold are configurable.
- Review reports require exact location, observation, reader effect, issue type,
  severity, scope, and rewrite recommendation.
- Novelness outcomes are `accept`, `targeted_revision`, `scene_rewrite`, or
  `chapter_rewrite`.
- Draft, review, revision, and acceptance actions write only to approved story
  output directories and never edit canon.
- Focused unit and integration tests cover context construction, scene planning,
  multi-pass generation, diagnostics, targeted revision, review gating,
  acceptance, and command orchestration.

## Acceptance Criteria Audit

1. Canon is rendered as bounded `[FACT]` records with
   `wording_reuse_allowed: false`; generation prompts treat it as private truth
   constraints.
2. Orchestrated and explicit scene drafting both require a JSON Schema-validated
   scene contract.
3. Every scene requires at least one change axis, a nonempty required change,
   new information, and an ending turn.
4. Scene first drafts, narrative deepening, de-duplication, and voice polish are
   separate model calls with separate run artifacts.
5. Diagnostics detect adjacent semantic repetition and repeated draft phrases,
   with a configurable semantic threshold.
6. Exact and distinctive source wording are checked against canon, plans,
   summaries, accepted chapters, reviewer reports, and writer profiles.
7. Reviewer and planning terminology are source inputs to similarity checks and
   are explicitly prohibited from narrative output.
8. The editor and tone reviewers check narrative movement, viewpoint,
   embodiment, repetition, exposition, dialogue, rhythm, transitions, and
   ending force.
9. The pacing reviewer receives the complete draft, scene contract, and
   skeleton and reports local, scene, and chapter pacing separately.
10. The Novelness Gate produces `accept`, `targeted_revision`, `scene_rewrite`,
    or `chapter_rewrite` independently of correctness.
11. Required editor, pacing, tone, and character evidence plus deterministic
    copying and repetition checks prevent a canon-correct generic pass from
    accepting lifeless prose.
12. Nine chapter revision modes and scene-local revision apply changes to the
    requested problem scope.
13. Write packs rank bounded canon, character, relationship, location, state,
    and series facts against active chapter direction and omit inactive context
    beyond category limits.
14. Writer scaffolds describe narrative behavior and per-character perception;
    they contain no imitation chapters.
15. Promotion verifies the current accepted review hash and generates summary,
    handover, and state from the exact promoted chapter.
16. Scene contracts require pressure, opposition, causal action, a state change,
    new information, and a concrete ending turn.
17. Viewpoint profiles express character differences through attention,
    interpretation, physical habits, stress behavior, vocabulary, and choice.
18. Drafting and review contracts allow technical information only when it
    creates conflict, risk, characterization, or a decision.
19. Deepening, compression, polish, chapter revision, and scene revision all
    prohibit silent canon, event, decision, scene-order, or reveal changes.
20. Generation, revision, re-review, and acceptance provenance records retain
    context counts, model attempts, stage artifacts, diagnostics, revision
    reasons, output paths, and quality metrics.

The complete repository validation command is `./tests/run_tests.sh`. It covers
Python workflows and the Node prompt-asset contract tests.
