import { readFile } from "node:fs/promises";
import { extname } from "node:path";
import { assertValidPromptAsset } from "./validator.ts";
import type { PromptAsset } from "./types.ts";

type YamlFrame = {
  indent: number;
  value: Record<string, unknown>;
};

export async function loadPromptAsset(path: string): Promise<PromptAsset> {
  const raw = await readFile(path, "utf8");
  return parsePromptAsset(raw, extname(path));
}

export function parsePromptAsset(source: string, extension = ".yaml"): PromptAsset {
  const parsed = extension === ".json"
    ? JSON.parse(source)
    : parseSimpleYaml(source);
  assertValidPromptAsset(parsed);
  return parsed;
}

export function parseSimpleYaml(source: string): unknown {
  const root: Record<string, unknown> = {};
  const stack: YamlFrame[] = [{ indent: -1, value: root }];
  const lines = source.replace(/\r\n/g, "\n").split("\n");

  for (let index = 0; index < lines.length; index += 1) {
    const rawLine = lines[index];
    if (!rawLine.trim() || rawLine.trimStart().startsWith("#")) {
      continue;
    }

    const indent = rawLine.length - rawLine.trimStart().length;
    const trimmed = rawLine.trim();
    const match = trimmed.match(/^([^:]+):(.*)$/);
    if (!match) {
      throw new Error(`Invalid YAML line ${index + 1}: ${rawLine}`);
    }

    const key = match[1].trim();
    const rawValue = match[2].trim();
    while (stack.length > 1 && indent <= stack[stack.length - 1].indent) {
      stack.pop();
    }

    const parent = stack[stack.length - 1].value;
    if (rawValue === "|" || rawValue === ">") {
      const block = collectBlock(lines, index + 1, indent, rawValue);
      parent[key] = block.value;
      index = block.endIndex;
      continue;
    }

    if (rawValue === "") {
      const child: Record<string, unknown> = {};
      parent[key] = child;
      stack.push({ indent, value: child });
      continue;
    }

    parent[key] = parseScalar(rawValue);
  }

  return root;
}

function collectBlock(
  lines: string[],
  startIndex: number,
  parentIndent: number,
  mode: "|" | ">",
): { value: string; endIndex: number } {
  const blockLines: string[] = [];
  let endIndex = startIndex - 1;
  let blockIndent: number | undefined;

  for (let index = startIndex; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line.trim()) {
      blockLines.push("");
      endIndex = index;
      continue;
    }

    const indent = line.length - line.trimStart().length;
    if (indent <= parentIndent) {
      break;
    }

    blockIndent ??= indent;
    blockLines.push(line.slice(blockIndent));
    endIndex = index;
  }

  const value = mode === "|"
    ? `${blockLines.join("\n")}\n`
    : `${blockLines.join(" ").trim()}\n`;
  return { value, endIndex };
}

function parseScalar(value: string): unknown {
  if (value === "true") {
    return true;
  }

  if (value === "false") {
    return false;
  }

  if (/^-?\d+(\.\d+)?$/.test(value)) {
    return Number(value);
  }

  if (value.startsWith("[") && value.endsWith("]")) {
    return value
      .slice(1, -1)
      .split(",")
      .map((item) => parseScalar(item.trim()));
  }

  return value.replace(/^["']|["']$/g, "");
}
