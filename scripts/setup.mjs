import { spawnSync } from "node:child_process";
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

function run(cmd, args, cwd = root) {
  const result = spawnSync(cmd, args, { cwd, stdio: "inherit" });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function runNpm(args, cwd = root) {
  if (process.platform === "win32") {
    run("cmd", ["/d", "/s", "/c", "npm", ...args], cwd);
    return;
  }
  run("npm", args, cwd);
}

if (!existsSync(venvDir)) {
  run("python", ["-m", "venv", venvDir]);
}

if (!existsSync(venvPython)) {
  console.error(`Virtualenv python not found at ${venvPython}`);
  process.exit(1);
}

run(venvPython, ["-m", "pip", "install", "--upgrade", "pip"]);
run(venvPython, ["-m", "pip", "install", "-e", backendDir]);

if (!existsSync(join(root, "node_modules"))) {
  runNpm(["install"]);
}

if (!existsSync(join(frontendDir, "node_modules"))) {
  runNpm(["install"], frontendDir);
}
