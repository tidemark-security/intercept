#!/usr/bin/env node

import DOMPurify from "dompurify";
import mermaid from "mermaid";

const MAX_ERROR_LINES = 20;

function collectErrorLines(error) {
  const combined = [error?.message, error?.str, String(error ?? "")]
    .filter((part) => typeof part === "string" && part.trim().length > 0)
    .join("\n");

  const lines = [];
  const seen = new Set();

  for (const rawLine of combined.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || seen.has(line)) {
      continue;
    }
    seen.add(line);
    lines.push(line);
    if (lines.length >= MAX_ERROR_LINES) {
      break;
    }
  }

  return lines;
}

async function readDiagramFromStdin() {
  const chunks = [];

  for await (const chunk of process.stdin) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(String(chunk)));
  }

  return Buffer.concat(chunks).toString("utf-8");
}

async function main() {
  try {
    const diagram = await readDiagramFromStdin();

    // Mermaid parser expects browser-like DOMPurify hooks in some parse paths.
    if (typeof DOMPurify.addHook !== "function") {
      DOMPurify.addHook = () => {};
    }
    if (typeof DOMPurify.removeHook !== "function") {
      DOMPurify.removeHook = () => {};
    }
    if (typeof DOMPurify.removeAllHooks !== "function") {
      DOMPurify.removeAllHooks = () => {};
    }
    if (typeof DOMPurify.sanitize !== "function" && typeof DOMPurify === "function") {
      DOMPurify.sanitize = DOMPurify;
    }

    mermaid.initialize({ startOnLoad: false });
    await mermaid.parse(diagram);

    process.exitCode = 0;
  } catch (error) {
    const lines = collectErrorLines(error);
    const output = lines.length > 0 ? lines : ["Mermaid validation failed."];
    for (const line of output) {
      process.stderr.write(`${line}\n`);
    }
    process.exitCode = 1;
  }
}

await main();
