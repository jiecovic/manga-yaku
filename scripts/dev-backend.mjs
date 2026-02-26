import { spawn } from "node:child_process";
import { existsSync, statSync, watch } from "node:fs";
import { fileURLToPath } from "node:url";
import { extname, join, resolve } from "node:path";
import process from "node:process";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const backendDir = join(root, "backend-python");
const venvDir = join(backendDir, ".venv");
const venvPython =
  process.platform === "win32"
    ? join(venvDir, "Scripts", "python.exe")
    : join(venvDir, "bin", "python");
const port = process.env.MANGAYAKU_BACKEND_PORT || "8101";
const host = process.env.MANGAYAKU_BACKEND_HOST || "127.0.0.1";

if (!existsSync(venvPython)) {
  console.error(
    `Virtualenv python not found at ${venvPython}. Run "npm run setup" first.`,
  );
  process.exit(1);
}

const cliNoReload = process.argv.includes("--no-reload");
const cliReload = process.argv.includes("--reload");
let enableReload = process.env.MANGAYAKU_BACKEND_RELOAD !== "0";
if (cliNoReload) {
  enableReload = false;
}
if (cliReload) {
  enableReload = true;
}
const debug = process.env.MANGAYAKU_BACKEND_DEBUG === "1";
const restartExitCode = Number.parseInt(
  process.env.MANGAYAKU_BACKEND_RESTART_EXIT_CODE || "75",
  10,
);
const logDebug = (...args) => {
  if (debug) {
    console.log("[dev-backend]", ...args);
  }
};
const useUvicornReload = enableReload && process.platform !== "win32";
const forcePolling =
  process.platform === "win32" && process.env.MANGAYAKU_WATCH_POLL !== "0";
const reloadDirs = [
  join(backendDir, "api"),
  join(backendDir, "core"),
  join(backendDir, "infra"),
];
const args = [
  "-m",
  "uvicorn",
  "app:app",
  "--no-access-log",
  "--host",
  host,
  "--port",
  port,
  "--app-dir",
  backendDir,
];

if (useUvicornReload) {
  args.push("--reload");
  reloadDirs.forEach((dir) => {
    args.push("--reload-dir", dir);
  });
}

const watchedExtensions = new Set([".py", ".pyi", ".yml", ".yaml"]);
const watchHandles = [];
const lastMtimeByPath = new Map();
let child = null;
let restartTimer = null;
let isRestarting = false;
let isShuttingDown = false;

const childEnv = {
  ...process.env,
  PYTHONDONTWRITEBYTECODE: "1",
  MANGAYAKU_SELF_RESTART_ENABLED: "1",
  MANGAYAKU_BACKEND_RESTART_EXIT_CODE: String(
    Number.isFinite(restartExitCode) ? restartExitCode : 75,
  ),
};

if (useUvicornReload) {
  childEnv.WATCHFILES_DEBUG = process.env.MANGAYAKU_WATCH_DEBUG || undefined;
  childEnv.WATCHFILES_FORCE_POLLING = forcePolling ? "1" : undefined;
  childEnv.WATCHFILES_POLL_DELAY_MS = forcePolling ? "500" : undefined;
}

const spawnServer = () => {
  logDebug("Starting backend", {
    enableReload,
    useUvicornReload,
    reloadDirs,
    host,
    port,
  });
  child = spawn(venvPython, args, {
    stdio: "inherit",
    cwd: backendDir,
    env: childEnv,
  });

  child.on("exit", (code, signal) => {
    logDebug("Backend exited", { code, signal });
    if (isRestarting || isShuttingDown) {
      return;
    }
    if (
      Number.isFinite(restartExitCode) &&
      code === restartExitCode
    ) {
      logDebug("Restart requested by backend process");
      spawnServer();
      return;
    }
    process.exit(code ?? 1);
  });
  child.on("error", (err) => {
    logDebug("Backend process error", err);
  });
};

const killServer = () => {
  if (!child || child.killed) {
    return;
  }
  child.kill();
  const stillRunning = child;
  setTimeout(() => {
    if (stillRunning && stillRunning.exitCode === null) {
      stillRunning.kill("SIGKILL");
    }
  }, 1500);
};

const restartServer = () => {
  if (isRestarting || !child) {
    return;
  }
  isRestarting = true;
  logDebug("Restarting backend");
  child.once("exit", () => {
    isRestarting = false;
    spawnServer();
  });
  killServer();
};

const scheduleRestart = () => {
  if (restartTimer) {
    clearTimeout(restartTimer);
  }
  restartTimer = setTimeout(restartServer, 150);
};

const shouldWatch = (filename) => {
  if (!filename) {
    return true;
  }
  const ext = extname(filename).toLowerCase();
  return watchedExtensions.has(ext);
};

const startWatchers = () => {
  reloadDirs.forEach((dir) => {
    const watcher = watch(
      dir,
      { recursive: true },
      (_event, filename) => {
        if (!shouldWatch(filename)) {
          return;
        }
        if (!filename) {
          logDebug("File change detected (unknown)", { dir });
          scheduleRestart();
          return;
        }
        const fullPath = join(dir, filename);
        let mtime = null;
        try {
          mtime = statSync(fullPath).mtimeMs;
        } catch (err) {
          logDebug("File change detected (missing)", { dir, filename });
          scheduleRestart();
          return;
        }
        const lastMtime = lastMtimeByPath.get(fullPath);
        if (lastMtime !== undefined && lastMtime === mtime) {
          logDebug("Ignoring change (mtime unchanged)", { dir, filename });
          return;
        }
        lastMtimeByPath.set(fullPath, mtime);
        logDebug("File change detected", { dir, filename });
        scheduleRestart();
      },
    );
    watcher.on("error", (err) => {
      logDebug("Watcher error", { dir, error: String(err) });
    });
    watchHandles.push(watcher);
  });
};

const shutdown = () => {
  logDebug("Shutting down backend");
  isShuttingDown = true;
  if (restartTimer) {
    clearTimeout(restartTimer);
  }
  watchHandles.forEach((watcher) => watcher.close());
  killServer();
};

process.on("SIGINT", () => {
  logDebug("Received SIGINT");
  shutdown();
});
process.on("SIGTERM", () => {
  logDebug("Received SIGTERM");
  shutdown();
});

spawnServer();

if (enableReload && !useUvicornReload) {
  startWatchers();
}
