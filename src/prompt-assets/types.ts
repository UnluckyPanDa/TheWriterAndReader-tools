export type PromptAssetInputType = "string" | "array" | "number" | "boolean" | "object";

export interface PromptAssetInput {
  type: PromptAssetInputType;
  description?: string;
  required?: boolean;
}

export interface PromptAssetOutput {
  format: "json" | "text";
  schema?: string;
}

export type PromptAssetTemplate = Record<string, string>;

export type ResponseSchemaFieldType =
  | "string"
  | "array"
  | "number"
  | "boolean"
  | "object";

export type PromptAssetResponseSchema = Record<string, ResponseSchemaFieldType>;

export interface PromptAssetOptimization {
  max_input_tokens?: number;
  target_output_tokens?: number;
  allow_lossy_compression?: boolean;
}

export interface PromptAsset {
  id: string;
  version: string;
  name: string;
  description: string;
  inputs: Record<string, PromptAssetInput>;
  output: PromptAssetOutput;
  template: PromptAssetTemplate;
  response_schema: PromptAssetResponseSchema;
  optimization?: PromptAssetOptimization;
}

export interface PromptMessage {
  role: string;
  content: string;
}

export type PromptVariables = Record<string, unknown>;

export interface PromptAssetManifest {
  prompt_assets: PromptAsset[];
}

export interface PromptAssetValidationResult {
  valid: boolean;
  errors: string[];
}
