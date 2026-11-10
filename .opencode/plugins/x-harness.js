/**
 * x-harness plugin for OpenCode (V1 plugin API, `tool.execute.before`).
 *
 * Every tool call goes through adapters/agent-hook.py, which runs the project's own
 * .claude/hooks (policies are not copied here). Exit 2 from the adapter = the call is rejected.
 * Projects without x-harness are a no-op inside the adapter.
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const adapter = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../adapters/agent-hook.py");

// Subagent roles: one source, the project's .claude/agents/*.md (Claude model names are not OpenCode models, so no model).
const projectAgents = (directory) => {
  const dir = path.join(directory, ".claude/agents");
  if (!fs.existsSync(path.join(directory, ".claude/hooks/plans-drift.sh")) || !fs.existsSync(dir)) return {};
  const agents = {};
  for (const file of fs.readdirSync(dir).filter((f) => f.endsWith(".md"))) {
    const match = fs.readFileSync(path.join(dir, file), "utf8").match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
    if (!match) continue;
    const description = match[1].match(/^description:\s*(.+)$/m)?.[1]?.trim();
    if (description) agents[file.slice(0, -3)] = { description, mode: "subagent", prompt: match[2].trim() };
  }
  return agents;
};

export const XHarnessPlugin = async ({ directory }) => ({
  config: async (config) => {
    config.agent = { ...projectAgents(directory), ...(config.agent ?? {}) };
  },
  "tool.execute.before": async (input, output) => {
    const payload = {
      hook_event_name: "PreToolUse",
      session_id: input.sessionID,
      cwd: directory,
      tool_name: input.tool,
      tool_input: output.args ?? {},
    };
    const result = spawnSync("python3", [adapter, "opencode", "PreToolUse"], {
      input: JSON.stringify(payload),
      encoding: "utf8",
      timeout: 300_000,
    });
    if (result.status === 2) {
      throw new Error((result.stderr || "Blocked by x-harness").trim());
    }
  },
});
