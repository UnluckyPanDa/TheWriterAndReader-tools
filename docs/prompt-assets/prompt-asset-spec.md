# Prompt Asset Spec

Prompt Assets are reusable AI prompt contracts. A prompt asset declares its identity, inputs, output format, prompt template, response schema, and optimization limits.

Prompt Assets are loaded before runtime execution so skills can depend on stable prompt contracts.

## Required Fields

- `id`: stable prompt asset identifier
- `version`: semantic version string
- `name`: human-readable name
- `description`: purpose and usage notes
- `inputs`: named input declarations
- `output`: output format and schema reference
- `template`: prompt message templates keyed by role
- `response_schema`: expected structured response shape
- `optimization`: token and compression policy

## Compress Context for Goal

```yaml
id: prompt.context.compress_for_goal
version: 0.1.0
name: Compress Context for Goal
description: >
  Compress context while preserving information required to satisfy a goal.
inputs:
  goal:
    type: string
  context_chunk:
    type: string
  preservation_rules:
    type: array
output:
  format: json
  schema: compressed_context_result
template:
  system: |
    You compress context for downstream AI execution.
    Preserve facts, constraints, entities, dates, numbers, and decisions.
  user: |
    Goal:
    {{goal}}
    Context:
    {{context_chunk}}
    Preservation rules:
    {{preservation_rules}}
response_schema:
  compressed_text: string
  preserved_facts: array
  removed_details: array
  confidence: number
optimization:
  max_input_tokens: 6000
  target_output_tokens: 1200
  allow_lossy_compression: true
```

## Runtime Contract

A runtime loads a prompt asset from YAML or JSON, validates required fields, resolves all `{{variables}}` from supplied inputs, renders final prompt messages, and validates the model response against `response_schema`.

The optimizer skill uses `prompt.context.compress_for_goal` as its `compress_context_for_goal` prompt asset when compression is allowed by policy and retained context must be reduced to fit the budget.
