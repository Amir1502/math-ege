import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const backendRoot = fileURLToPath(new URL('../../backend/', import.meta.url));
export const courseRoot = resolve(backendRoot, 'content/course');
export const backendPython = resolve(backendRoot, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');

/** Independent Python oracle; never inherit application secrets or resolve Python from PATH. */
export function pythonJson<T>(code: string, input?: unknown): T {
  const env: NodeJS.ProcessEnv = { PYTHONIOENCODING: 'utf-8' };
  for (const key of ['SystemRoot', 'WINDIR', 'TEMP', 'TMP']) {
    if (process.env[key]) env[key] = process.env[key];
  }
  const source = 'import sys\nsys.stdin.reconfigure(encoding="utf-8")\nsys.stdout.reconfigure(encoding="utf-8")\nsys.path.insert(0, sys.argv[1])\n' + code;
  return JSON.parse(execFileSync(backendPython, ['-I', '-B', '-c', source, backendRoot], {
    cwd: backendRoot, env, input: input === undefined ? undefined : JSON.stringify(input),
    encoding: 'utf8', windowsHide: true, timeout: 120_000, maxBuffer: 12 * 1024 * 1024,
  })) as T;
}
