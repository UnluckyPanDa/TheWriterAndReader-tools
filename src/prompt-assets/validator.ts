import type {
  PromptAsset,
  PromptAssetInputType,
  PromptAssetResponseSchema,
  PromptAssetValidationResult,
  ResponseSchemaFieldType,
} from "./types.ts";

const REQUIRED_FIELDS = [
  "id",
  "version",
  "name",
  "description",
  "inputs",
  "output",
  "template",
  "response_schema",
] as const;

const INPUT_TYPES = new Set<PromptAssetInputType>([
  "string",
  "array",
  "number",
  "boolean",
  "object",
]);

const RESPONSE_TYPES = new Set<ResponseSchemaFieldType>([
  "string",
  "array",
  "number",
  "boolean",
  "object",
]);

export function validatePromptAsset(asset: unknown): PromptAssetValidationResult {
  const errors: string[] = [];

  if (!isRecord(asset)) {
    return { valid: false, errors: ["Prompt asset must be an object."] };
  }

  for (const field of REQUIRED_FIELDS) {
    if (!(field in asset)) {
      errors.push(`Missing required field: ${field}.`);
    }
  }

  validateString(asset, "id", errors);
  validateString(asset, "version", errors);
  validateString(asset, "name", errors);
  validateString(asset, "description", errors);
  validateInputs(asset.inputs, errors);
  validateOutput(asset.output, errors);
  validateTemplate(asset.template, errors);
  validateResponseSchema(asset.response_schema, errors);
  validateOptimization(asset.optimization, errors);

  return { valid: errors.length === 0, errors };
}

export function assertValidPromptAsset(asset: unknown): asserts asset is PromptAsset {
  const result = validatePromptAsset(asset);
  if (!result.valid) {
    throw new Error(result.errors.join(" "));
  }
}

export function validateResponse(
  schema: PromptAssetResponseSchema,
  response: unknown,
): PromptAssetValidationResult {
  const errors: string[] = [];

  if (!isRecord(response)) {
    return { valid: false, errors: ["Response must be an object."] };
  }

  for (const [field, type] of Object.entries(schema)) {
    if (!(field in response)) {
      errors.push(`Missing response field: ${field}.`);
      continue;
    }

    if (!matchesType(response[field], type)) {
      errors.push(`Response field ${field} must be ${type}.`);
    }
  }

  return { valid: errors.length === 0, errors };
}

function validateString(record: Record<string, unknown>, field: string, errors: string[]) {
  if (field in record && typeof record[field] !== "string") {
    errors.push(`${field} must be a string.`);
  }
}

function validateInputs(value: unknown, errors: string[]) {
  if (!isRecord(value)) {
    errors.push("inputs must be an object.");
    return;
  }

  for (const [name, input] of Object.entries(value)) {
    if (!isRecord(input)) {
      errors.push(`Input ${name} must be an object.`);
      continue;
    }

    if (!INPUT_TYPES.has(input.type as PromptAssetInputType)) {
      errors.push(`Input ${name} has unsupported type.`);
    }
  }
}

function validateOutput(value: unknown, errors: string[]) {
  if (!isRecord(value)) {
    errors.push("output must be an object.");
    return;
  }

  if (value.format !== "json" && value.format !== "text") {
    errors.push("output.format must be json or text.");
  }

  if ("schema" in value && typeof value.schema !== "string") {
    errors.push("output.schema must be a string.");
  }
}

function validateTemplate(value: unknown, errors: string[]) {
  if (!isRecord(value)) {
    errors.push("template must be an object.");
    return;
  }

  for (const [role, content] of Object.entries(value)) {
    if (typeof content !== "string") {
      errors.push(`template.${role} must be a string.`);
    }
  }
}

function validateResponseSchema(value: unknown, errors: string[]) {
  if (!isRecord(value)) {
    errors.push("response_schema must be an object.");
    return;
  }

  for (const [field, type] of Object.entries(value)) {
    if (!RESPONSE_TYPES.has(type as ResponseSchemaFieldType)) {
      errors.push(`response_schema.${field} has unsupported type.`);
    }
  }
}

function validateOptimization(value: unknown, errors: string[]) {
  if (value === undefined) {
    return;
  }

  if (!isRecord(value)) {
    errors.push("optimization must be an object.");
    return;
  }

  if ("max_input_tokens" in value && typeof value.max_input_tokens !== "number") {
    errors.push("optimization.max_input_tokens must be a number.");
  }

  if ("target_output_tokens" in value && typeof value.target_output_tokens !== "number") {
    errors.push("optimization.target_output_tokens must be a number.");
  }

  if (
    "allow_lossy_compression" in value &&
    typeof value.allow_lossy_compression !== "boolean"
  ) {
    errors.push("optimization.allow_lossy_compression must be a boolean.");
  }
}

function matchesType(value: unknown, type: ResponseSchemaFieldType): boolean {
  if (type === "array") {
    return Array.isArray(value);
  }

  if (type === "object") {
    return isRecord(value);
  }

  return typeof value === type;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
