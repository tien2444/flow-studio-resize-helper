import { identity } from '@/lib/auth';
import { errorResponse, json } from '@/lib/server';
import targets from '@/lib/processor-targets.json';
import driveCatalog from '@/lib/processor-drive-targets.json';

const driveTargets = driveCatalog.targets as Record<string, Record<string, unknown>>;
const canonicalTargets = Object.fromEntries(
  Object.entries(targets).map(([name, target]) => [
    name,
    { ...target, ...(driveTargets[name] || {}) },
  ]),
);

export async function GET(req: Request) {
  try {
    await identity(req);
    return json({ version: '2026-09-29.138', targets: canonicalTargets });
  } catch (error) {
    return errorResponse(error);
  }
}
