# Shared Schemas

Reusable JSON or YAML schemas belong here when multiple tools or templates need the same contract.

Guidelines:

- Keep schemas story-neutral.
- Do not encode active story names, private canon, or manuscript text.
- Add only schemas that are validated by a tool, test, or documented workflow.

`relationship_graph.schema.json` defines the story-neutral character and
relationship contract used by the wizard's local 3D relationship plot and by
chapter context packs.

`scene_contract.schema.json` defines the required scene goals, pressure, state
changes, and ending turns validated before chapter drafting.

`review_decision.schema.json` defines canonical model-produced fiction review
decisions. `review_run_record.schema.json` defines the trusted TWR provenance
envelope for one reviewer run.
