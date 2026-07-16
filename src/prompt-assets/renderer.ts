import { validateResponse } from "./validator.ts";
import type {
  PromptAsset,
  PromptAssetValidationResult,
  PromptMessage,
  PromptVariables,
} from "./types.ts";

const VARIABLE_PATTERN = /\{\{\s*([A-Za-z0-9_]+)\s*\}\}/g;

export function renderPromptMessages(
  asset: PromptAsset,
  variables: PromptVariables,
): PromptMessage[] {
  validateVariables(asset, variables);

  return Object.entries(asset.template).map(([role, content]) => ({
    role,
    content: renderTemplate(content, variables),
  }));
}

export function validatePromptAssetResponse(
  asset: PromptAsset,
  response: unknown,
): PromptAssetValidationResult {
  return validateResponse(asset.response_schema, response);
}

export function renderTemplate(template: string, variables: PromptVariables): string {
  return template.replace(VARIABLE_PATTERN, (_match, key: string) => {
    if (!(key in variables)) {
      throw new Error(`Missing template variable: ${key}.`);
    }

    return stringifyVariable(variables[key]);
  });
}

function validateVariables(asset: PromptAsset, variables: PromptVariables) {
  for (const [name, input] of Object.entries(asset.inputs)) {
    const required = input.required ?? true;
    if (required && !(name in variables)) {
      throw new Error(`Missing required input: ${name}.`);
    }

    if (name in variables && !matchesInputType(variables[name], input.type)) {
      throw new Error(`Input ${name} must be ${input.type}.`);
    }
  }
}

function stringifyVariable(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).join("\n");
  }

  if (typeof value === "object" && value !== null) {
    return JSON.stringify(value, null, 2);
  }

  return String(value);
}

function matchesInputType(value: unknown, type: string): boolean {
  if (type === "array") {
    return Array.isArray(value);
  }

  if (type === "object") {
    return typeof value === "object" && value !== null && !Array.isArray(value);
  }

  return typeof value === type;
}
