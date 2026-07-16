import { loadPromptAsset } from "./loader.ts";
import type { PromptAsset, PromptAssetManifest } from "./types.ts";

export function createPromptAssetManifest(promptAssets: PromptAsset[]): PromptAssetManifest {
  return { prompt_assets: promptAssets };
}

export async function loadPromptAssetManifest(paths: string[]): Promise<PromptAssetManifest> {
  const promptAssets = await Promise.all(paths.map((path) => loadPromptAsset(path)));
  return createPromptAssetManifest(promptAssets);
}

export function findPromptAsset(
  manifest: PromptAssetManifest,
  id: string,
): PromptAsset | undefined {
  return manifest.prompt_assets.find((asset) => asset.id === id);
}
