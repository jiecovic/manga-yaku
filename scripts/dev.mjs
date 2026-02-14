import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join, resolve } from "node:path";
import process from "node:process";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));

const backendDir = join(root, "backend-python");
const frontendDir = join(root, "frontend");
const venvDir = join(backendDir, ".venv");
const venvPython =
  process.platform === "win32"
    ? join(venvDir, "Scripts", "python.exe")
    : join(venvDir, "bin", "python");

function spawnNpm(args, cwd = root) {
  if (process.platform === "win32") {
    return spawn("cmd", ["/d", "/s", "/c", "npm", ...args], {
      cwd,
      stdio: "inherit",
    });
  }
  return spawn("npm", args, { cwd, stdio: "inherit" });
}

const needsSetup =
  !existsSync(venvPython) ||
  !existsSync(join(root, "node_modules")) ||
  !existsSync(join(frontendDir, "node_modules"));

const backendPort = process.env.MANGAYAKU_BACKEND_PORT || "8101";
const backendHost = process.env.MANGAYAKU_BACKEND_HOST || "127.0.0.1";
if (!process.env.VITE_API_BASE) {
  const frontendHost = backendHost === "0.0.0.0" ? "localhost" : backendHost;
  process.env.VITE_API_BASE = `http://${frontendHost}:${backendPort}`;
}

if (needsSetup) {
  const setup = spawnSync("node", [join(root, "scripts", "setup.mjs")], {
    stdio: "inherit",
    shell: true,
  });
  if (setup.status !== 0) {
    process.exit(setup.status ?? 1);
  }
}

const dev = spawnNpm(["run", "dev:raw"], root);
dev.on("exit", (code) => {
  process.exit(code ?? 1);
});

