import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const root = process.cwd();
const failures = [];

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), 'utf8');
}

function fail(message) {
  failures.push(message);
}

if (fs.existsSync(path.join(root, 'pnpm-workspace.yaml'))) {
  const workspace = read('pnpm-workspace.yaml');
  if (/plane-community/.test(workspace)) {
    fail('plane-community must not be added to the root pnpm workspace');
  }
}

const planePackage = JSON.parse(read('plane-community/package.json'));

const planePm = String(planePackage.packageManager ?? '');
if (!planePm.startsWith('pnpm@11.')) {
  fail(`expected Plane pnpm 11.x, found ${planePm || 'unset'}`);
}

const planeNode = String(planePackage.engines?.node ?? '');
if (!planeNode.includes('22.18')) {
  fail(`expected Plane Node requirement to include 22.18, found ${planeNode || 'unset'}`);
}

const upstream = read('plane-community/.garden-upstream');
if (!/^ref=v1\.4\.2$/m.test(upstream)) {
  fail('Plane upstream pin is no longer v1.4.2; review the upgrade deliberately');
}

if (!fs.existsSync(path.join(root, 'plane-community/GARDEN_CHANGES.md'))) {
  fail('missing plane-community/GARDEN_CHANGES.md');
}

if (!fs.existsSync(path.join(root, 'scripts/plane-garden/update-upstream.sh'))) {
  fail('missing safe Plane upstream staging script');
}

if (failures.length) {
  console.error('Plane/Garden boundary verification failed:');
  for (const message of failures) console.error(`- ${message}`);
  process.exit(1);
}

console.log('Plane/Garden boundary verified.');
console.log(`Plane package manager: ${planePm}`);
console.log(`Plane Node engine: ${planeNode}`);
console.log('No GitHub Actions files are required by this verifier.');
