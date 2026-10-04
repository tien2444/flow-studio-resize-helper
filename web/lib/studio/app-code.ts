import appCodes from '../app-code-map.ts';

const normalizeAppName = (value: string) =>
  value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('en')
    .replace(/[^a-z0-9]+/g, '');

const normalizedCodes = new Map<string, string>();

for (const [name, code] of Object.entries(appCodes)) {
  const key = normalizeAppName(name);
  const existing = normalizedCodes.get(key);
  if (existing && existing !== code) {
    throw new Error(`Conflicting app codes for ${name}.`);
  }
  normalizedCodes.set(key, code);
}

export function appCodeForTarget(name: string) {
  return normalizedCodes.get(normalizeAppName(name)) || '';
}
