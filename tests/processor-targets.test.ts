import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

type LocalTarget = {
  folder: string;
  video_folder: string;
  image_folder: string;
  thumbnail_folder: string;
};

type DriveCatalog = {
  shared_drive: { id: string; name: string };
  targets: Record<string, {
    drive_id: string;
    video_folder_id: string;
    image_folder_id: string;
    thumbnail_folder_id: string;
  }>;
};

const readJson = <T,>(path: string) =>
  JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8')) as T;

test('processor catalog contains all 138 canonical Drive apps', () => {
  const local = readJson<Record<string, LocalTarget>>('../web/lib/processor-targets.json');
  const drive = readJson<DriveCatalog>('../web/lib/processor-drive-targets.json');
  const names = Object.keys(local);

  assert.equal(names.length, 138);
  assert.deepEqual(names, Object.keys(drive.targets));
  assert.equal(drive.shared_drive.name, 'iKame Apps - Creative');

  for (const name of names) {
    const root = `G:\\Shared drives\\iKame Apps - Creative\\Creative Asset - MKT\\${name}\\Creative Ads`;
    assert.equal(local[name].folder, `${root}\\Video`);
    assert.equal(local[name].video_folder, `${root}\\Video`);
    assert.equal(local[name].image_folder, `${root}\\Image`);
    assert.ok(
      local[name].thumbnail_folder === `${root}\\Image` ||
        local[name].thumbnail_folder === `${root}\\Thumbnail`,
    );
    assert.equal(drive.targets[name].drive_id, drive.shared_drive.id);
    assert.ok(drive.targets[name].video_folder_id);
    assert.ok(drive.targets[name].image_folder_id);
    assert.ok(drive.targets[name].thumbnail_folder_id);
  }
});
