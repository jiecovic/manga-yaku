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
const isWindows = process.platform === "win32";

function run(cmd, args, cwd = root) {
  const result = spawnSync(cmd, args, { cwd, stdio: "inherit" });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function resolvePython() {
  const candidates = isWindows ? ["python"] : ["python3", "python"];
  for (const candidate of candidates) {
    const result = spawnSync(candidate, ["-V"], { stdio: "ignore" });
    if (result.status === 0) {
      return candidate;
    }
  }
  return null;
}

function runNpm(args, cwd = root) {
  if (isWindows) {
    run("cmd", ["/d", "/s", "/c", "npm", ...args], cwd);
    return;
  }
  run("npm", args, cwd);
}

const pythonCmd = resolvePython();
if (!pythonCmd) {
  console.error(
    "Python interpreter not found. Install Python 3 and ensure it is on PATH.",
  );
  process.exit(1);
}

if (!existsSync(venvDir)) {
  run(pythonCmd, ["-m", "venv", venvDir]);
}

if (!existsSync(venvPython)) {
  console.error(`Virtualenv python not found at ${venvPython}`);
  process.exit(1);
}

run(venvPython, ["-m", "pip", "install", "--upgrade", "pip"]);
run(venvPython, ["-m", "pip", "install", "-e", `${backendDir}[dev]`]);

const hasRootDeps =
  existsSync(join(root, "node_modules", ".bin", "concurrently")) ||
  existsSync(join(root, "node_modules", ".bin", "concurrently.cmd"));
const hasFrontendDeps =
  existsSync(join(frontendDir, "node_modules", ".bin", "vite")) ||
  existsSync(join(frontendDir, "node_modules", ".bin", "vite.cmd"));

if (!hasRootDeps) {
  runNpm(["install"]);
}

if (!hasFrontendDeps) {
  runNpm(["install"], frontendDir);
}
