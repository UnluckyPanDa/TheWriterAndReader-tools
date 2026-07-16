import assert from "node:assert/strict";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import {
  loadPromptAsset,
  parsePromptAsset,
  renderPromptMessages,
  validatePromptAsset,
  validatePromptAssetResponse,
} from "../src/prompt-assets/index.ts";

const __dirname = dirname(fileURLToPath(import.meta.url));
const assetPath = resolve(
  __dirname,
  "../docs/prompt-assets/examples/optimizer-skill-package/prompt-assets/compress_context_for_goal.yaml",
);

test("loads prompt asset YAML", async () => {
  const asset = await loadPromptAsset(assetPath);

  assert.equal(asset.id, "prompt.context.compress_for_goal");
  assert.equal(asset.output.format, "json");
  assert.equal(asset.optimization?.max_input_tokens, 6000);
});

test("validates required prompt asset fields", () => {
  const result = validatePromptAsset({ id: "missing.required.fields" });

  assert.equal(result.valid, false);
  assert.match(result.errors.join(" "), /Missing required field: version/);
});

test("parses prompt asset JSON", () => {
  const asset = parsePromptAsset(
    JSON.stringify({
      id: "prompt.example",
      version: "0.1.0",
      name: "Example",
      description: "Example prompt asset.",
      inputs: {
        topic: { type: "string" },
      },
      output: { format: "json", schema: "example_result" },
      template: {
        user: "Topic: {{topic}}",
      },
      response_schema: {
        result: "string",
      },
    }),
    ".json",
  );

  assert.equal(asset.id, "prompt.example");
});

test("renders final prompt messages", async () => {
  const asset = await loadPromptAsset(assetPath);
  const messages = renderPromptMessages(asset, {
    goal: "Summarize the API contract.",
    context_chunk: "The loader accepts JSON and YAML files.",
    preservation_rules: ["keep dates", "keep identifiers"],
  });

  assert.deepEqual(
    messages.map((message) => message.role),
    ["system", "user"],
  );
  assert.match(messages[1].content, /Summarize the API contract/);
  assert.match(messages[1].content, /keep identifiers/);
});

test("validates declared response schema", async () => {
  const asset = await loadPromptAsset(assetPath);
  const validResponse = validatePromptAssetResponse(asset, {
    compressed_text: "Short context.",
    preserved_facts: ["loader accepts YAML"],
    removed_details: [],
    confidence: 0.91,
  });
  const invalidResponse = validatePromptAssetResponse(asset, {
    compressed_text: "Short context.",
    preserved_facts: "loader accepts YAML",
    removed_details: [],
    confidence: 0.91,
  });

  assert.equal(validResponse.valid, true);
  assert.equal(invalidResponse.valid, false);
  assert.match(invalidResponse.errors.join(" "), /preserved_facts must be array/);
});
