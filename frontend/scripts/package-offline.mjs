import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdir, readFile, realpath, writeFile } from 'node:fs/promises';
import { isAbsolute, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontend = fileURLToPath(new URL('../', import.meta.url));
const backend = fileURLToPath(new URL('../../backend/', import.meta.url));
const source = resolve(backend, 'content/course');
const filenames = ['profile.json', 'lessons.json', 'tasks.json'];
const python = resolve(backend, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const validator = fileURLToPath(new URL('../src/offline/core/package.py', import.meta.url));

function within(root, path) {
  const child = relative(root, path);
  return child === '' || (!isAbsolute(child) && child !== '..' && !child.startsWith(`..${sep}`));
}

async function resolvedDestination(path) {
  try {
    return await realpath(path);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    const parent = resolve(path, '..');
    if (parent === path) throw error;
    return resolve(await resolvedDestination(parent), relative(parent, path));
  }
}

/** Validate the exact bytes before writing; Python is build-only and gets no application environment. */
export async function packageOffline(outputDirectory = resolve(frontend, 'dist-offline/course')) {
  const output = await resolvedDestination(resolve(outputDirectory));
  const backendPath = await realpath(backend);
  if (within(backendPath, output)) throw new Error('Offline output cannot overwrite backend source data.');
  const buffers = Object.fromEntries(await Promise.all([...filenames, 'manifest.json'].map(async (name) => [
    name, await readFile(resolve(source, name)),
  ])));
  const env = {};
  for (const name of ['SystemRoot', 'WINDIR', 'TEMP', 'TMP']) {
    if (process.env[name]) env[name] = process.env[name];
  }
  const validated = JSON.parse(execFileSync(python, ['-I', '-B', validator, backend], {
    cwd: backend, env, shell: false, windowsHide: true, encoding: 'utf8', timeout: 120_000,
    maxBuffer: 4 * 1024 * 1024,
    input: JSON.stringify(Object.fromEntries(Object.entries(buffers).map(([name, bytes]) => [name, bytes.toString('base64')]))),
  }));
  const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');
  const files = Object.fromEntries(filenames.map((name) => [name, {
    sha256: sha256(buffers[name]), bytes: buffers[name].length,
  }]));
  const revision = sha256(Buffer.from(JSON.stringify({ files, source_manifest_sha256: sha256(buffers['manifest.json']) })));
  const manifest = {
    ...validated.source_manifest,
    version: '1', package_revision: `offline-v1-${revision}`, slot_count: 13,
    checker_revision: 'fraction-v1', instance_key_revision: 'app.instances.instance_key-v1',
    source_manifest_sha256: sha256(buffers['manifest.json']), files,
    instance_keys: validated.instance_keys,
  };
  await mkdir(output, { recursive: true });
  // The manifest is written last. An interrupted package fails the loader's hashes.
  for (const name of filenames) await writeFile(resolve(output, name), buffers[name]);
  await writeFile(resolve(output, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n', 'utf8');
  return manifest;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (process.argv.length > 3) throw new Error('Usage: node scripts/package-offline.mjs [output-directory]');
  const manifest = await packageOffline(process.argv[2]);
  console.log(`Offline course: ${manifest.task_count} tasks, ${manifest.lesson_count} lessons, ${manifest.slot_count} slots; ${manifest.package_revision}`);
}
