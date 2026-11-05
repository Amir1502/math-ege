import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

const paths = execFileSync('git', ['ls-files', '-z', '--cached', '--others', '--exclude-standard'], {
  encoding: 'utf8',
}).split('\0').filter(Boolean);
const problems = [];
const forbiddenFile = /(^|\/)(?:\.env(?:\..+)?|id_rsa|id_ed25519|credentials\.json|.*\.(?:db|sqlite|sqlite3|pem|key))$/i;
const secretPatterns = [
  /\bgh[pousr]_[A-Za-z0-9]{30,}\b/,
  /\bgithub_pat_[A-Za-z0-9_]{40,}\b/,
  /\bAKIA[A-Z0-9]{16}\b/,
  /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,
  /\bxox[baprs]-[A-Za-z0-9-]{20,}\b/,
];

for (const path of paths) {
  if (forbiddenFile.test(path) && !path.endsWith('.env.example')) {
    problems.push(`${path}: файл с данными или секретом не должен попадать в git`);
  }
  if (!/\.(?:json|[cm]?js|tsx?|py|md|txt|ya?ml|ini|toml|html|css|svg)$/.test(path)) continue;
  const source = readFileSync(path, 'utf8');
  for (const [index, line] of source.split('\n').entries()) {
    if (secretPatterns.some(pattern => pattern.test(line))) {
      problems.push(`${path}:${index + 1}: обнаружен формат секрета; значение не выводится`);
    }
  }
}

const workflow = readFileSync('.github/workflows/ci.yml', 'utf8');
for (const [, action] of workflow.matchAll(/^\s*- uses:\s+(\S+)/gm)) {
  if (!action.startsWith('./') && !/@[a-f0-9]{40}$/.test(action)) {
    problems.push(`.github/workflows/ci.yml: action ${action} не закреплён полным SHA`);
  }
}
assert.equal(problems.length, 0, problems.join('\n'));
console.log(`Source hygiene: ${paths.length} files checked; no matching secret formats or unpinned actions.`);
