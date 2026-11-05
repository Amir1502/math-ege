// Test-only production preview + migrated fresh database. No shared dist or SMTP.
import { spawn } from 'node:child_process';
import { existsSync, openSync, closeSync, writeFileSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve, relative, isAbsolute } from 'node:path';
import { build, preview } from 'vite';

const frontend = resolve(import.meta.dirname, '..');
const backend = resolve(frontend, '../backend');
const root = process.env.IDENTITY_BROWSER_RUN_ROOT;
if (!root || !process.env.LOCALAPPDATA) throw new Error('A fresh approved test directory is required.');
const temporary = resolve(process.env.LOCALAPPDATA, 'Temp/opencode');
const runRoot = resolve(root);
const within = relative(temporary, runRoot);
if (!within || within.startsWith('..') || isAbsolute(within)) throw new Error('Test directory is outside the approved temporary root.');
for (const name of ['identity.sqlite3', 'mailbox.jsonl', 'dist', 'runtime.lock']) {
  if (existsSync(resolve(runRoot, name))) throw new Error('Refusing to reuse any previous browser runtime.');
}
closeSync(openSync(resolve(runRoot, 'runtime.lock'), 'wx', 0o600));
writeFileSync(resolve(runRoot, 'clock.json'), JSON.stringify({ offset_seconds: 0 }), { flag: 'wx', mode: 0o600 });

const python = resolve(backend, '.venv/Scripts/python.exe');
const env = { ...process.env };
for (const name of Object.keys(env)) if (name.startsWith('ACCOUNTS_')) delete env[name];
Object.assign(env, {
  APP_ENV: 'test', DATABASE_URL: `sqlite:///${resolve(runRoot, 'identity.sqlite3').replaceAll('\\', '/')}`,
  ALLOW_DEMO_CONTENT: 'true', COOKIE_SECURE: 'false', ALLOWED_ORIGINS: 'http://127.0.0.1:5193',
  ACCOUNTS_ENABLED: 'false', ACCOUNTS_POLICY_APPROVED: 'false',
});
const logs = ['api.stdout.log', 'api.stderr.log'].map(name => openSync(resolve(runRoot, name), 'wx', 0o600));
let api;
let client;
let stopping = false;
async function stop() {
  if (stopping) return;
  stopping = true;
  api?.kill();
  if (client) await new Promise(accept => client.httpServer.close(accept));
  for (const descriptor of logs) closeSync(descriptor);
}
process.once('SIGINT', () => { void stop(); });
process.once('SIGTERM', () => { void stop(); });

try {
  await Promise.all([
    build({ root: frontend, configFile: resolve(frontend, 'vite.config.ts'), logLevel: 'warn', build: { outDir: resolve(runRoot, 'dist'), emptyOutDir: false } }),
    new Promise((accept, reject) => {
      const migration = spawn(python, ['-m', 'alembic', 'upgrade', 'head'], { cwd: backend, env, stdio: ['ignore', ...logs] });
      migration.once('error', reject);
      migration.once('exit', code => code === 0 ? accept() : reject(new Error('Isolated migration failed; see private runtime logs.')));
    }),
  ]);
  writeFileSync(resolve(runRoot, 'dist/privacy-test.txt'), 'Isolated automated browser test only. This is not a production privacy policy.\n', { flag: 'wx' });
  writeFileSync(resolve(runRoot, 'build-evidence.json'), JSON.stringify({
    source_hashes: Object.fromEntries(['src/pages/session.tsx', 'src/storage/identity.ts', 'src/storage/database.ts', 'src/api/history-export.ts', 'src/accounts/api.ts'].map(name => [name, createHash('sha256').update(readFileSync(resolve(frontend, name))).digest('hex')])),
    out_dir: resolve(runRoot, 'dist'), shared_dist_modified: false, built_at: new Date().toISOString(),
  }), { flag: 'wx', mode: 0o600 });
  api = spawn(python, ['-m', 'uvicorn', 'tests.identity_browser_server:create_identity_app', '--factory', '--host', '127.0.0.1', '--port', '8037', '--no-access-log'], { cwd: backend, env, stdio: ['ignore', ...logs] });
  api.once('error', () => { console.error('Isolated API failed to start.'); void stop(); process.exitCode = 1; });
  api.once('exit', code => { if (!stopping) { console.error('Isolated API exited.'); void stop(); process.exitCode = code || 1; } });
  client = await preview({ root: frontend, configFile: resolve(frontend, 'vite.config.ts'), build: { outDir: resolve(runRoot, 'dist'), emptyOutDir: false }, preview: { host: '127.0.0.1', port: 5193, strictPort: true, proxy: { '/api': { target: 'http://127.0.0.1:8037', changeOrigin: false } } } });
  writeFileSync(resolve(runRoot, 'processes.json'), JSON.stringify({ runner: process.pid, api: api.pid, started_at: new Date().toISOString() }), { flag: 'wx', mode: 0o600 });
  console.log('Identity browser production preview ready on 5193; isolated API on 8037.');
} catch {
  console.error('Identity browser runtime failed. No previous database or build was replaced.');
  await stop();
  process.exitCode = 1;
}
