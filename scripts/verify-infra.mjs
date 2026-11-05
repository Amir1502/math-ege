import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = path => readFileSync(path, 'utf8');
const compose = read('compose.yaml');
const nginx = read('infra/nginx.conf');
const backend = read('backend/Dockerfile');
const frontend = read('frontend/Dockerfile');
const workflow = read('.github/workflows/ci.yml');
const dockerignore = read('.dockerignore');
const attributes = read('.gitattributes');

assert.match(compose, /127\.0\.0\.1:8080:8080/);
assert.doesNotMatch(compose, /^\s+-\s+["']?(?:5432:5432|8000:8000)/m);
assert.match(compose, /postgres_data:\/var\/lib\/postgresql\s*$/m);
assert.match(compose, /POSTGRES_PASSWORD:\s*\$\{POSTGRES_PASSWORD:\?/);
assert.equal((compose.match(/read_only: true/g) ?? []).length, 2);
assert.equal((compose.match(/no-new-privileges:true/g) ?? []).length, 2);
assert.match(backend, /^USER app$/m);
assert.match(frontend, /^USER 101$/m);
assert.match(frontend, /npm ci --ignore-scripts/);
for (const text of [backend, frontend]) {
  for (const [, image] of text.matchAll(/^FROM (\S+)/gm)) {
    assert.match(image, /@sha256:[a-f0-9]{64}$/);
  }
}
assert.match(nginx, /pid \/tmp\/nginx\.pid;/);
assert.match(nginx, /resolver 127\.0\.0\.11 valid=10s ipv6=off;/);
assert.match(nginx, /zone api_backend 64k;/);
assert.match(nginx, /server api:8000 resolve;/);
assert.match(nginx, /proxy_pass http:\/\/api_backend;/);
assert.match(nginx, /proxy_set_header Host \$http_host;/);
assert.match(nginx, /client_max_body_size 16k;/);
assert.match(nginx, /limit_req_status 429;/);
assert.match(nginx, /frame-ancestors 'none'/);
assert.match(nginx, /error_page 502 = @bad_gateway;/);
assert.match(nginx, /error_page 504 = @gateway_timeout;/);
assert.match(dockerignore, /^\*\*\/\.env$/m);
assert.match(dockerignore, /^\*\*\/\.env\.\*$/m);
assert.match(dockerignore, /^android\/?$/m);
for (const extension of ['apk', 'jks', 'keystore', 'p12']) {
  assert.ok(dockerignore.split(/\r?\n/).includes(`**/*.${extension}`), `Exclude ${extension} files from container build contexts.`);
}
assert.doesNotMatch(nginx, /Access-Control-Allow-Origin/);
for (const rule of ['* text=auto eol=lf', '*.png binary', '*.woff2 binary']) {
  assert.ok(attributes.split(/\r?\n/).includes(rule), `Preserve the existing Git attribute rule: ${rule}`);
}
for (const path of ['android/gradle/verification-metadata.xml', 'android/gradlew.bat']) {
  assert.ok(attributes.split(/\r?\n/).includes(`${path} -text whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol`),
    `Preserve reviewed Android bytes without disabling whitespace checks: ${path}`);
}
assert.match(workflow, /permissions:\s*\n\s+contents: read/);
assert.doesNotMatch(workflow, /pull_request_target/);
assert.doesNotMatch(workflow, /secrets\./);
assert.match(workflow, /persist-credentials: false/);
const frontendInstall = workflow.indexOf('npm ci --ignore-scripts');
const browserInstall = workflow.indexOf('npx playwright install --with-deps chromium');
assert.ok(frontendInstall >= 0 && browserInstall > frontendInstall && browserInstall < workflow.indexOf('npm test'),
  'Install Chromium after frontend dependencies and before browser-mounted component tests.');
console.log('Infrastructure invariants: loopback publish, private database, non-root images, CSP and read-only CI passed.');
