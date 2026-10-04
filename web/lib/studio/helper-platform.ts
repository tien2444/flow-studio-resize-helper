export type HelperPlatform = 'mac' | 'windows' | 'other';

export const HELPER_DOWNLOADS = {
  mac: '/downloads/Flow-Studio-Helper-macOS.zip',
  windows: '/downloads/Flow-Studio-Helper-Windows-x64.zip',
} as const;

export function detectHelperPlatform(userAgent: string): HelperPlatform {
  if (/windows|win64|win32/i.test(userAgent)) return 'windows';
  if (/macintosh|mac os x/i.test(userAgent)) return 'mac';
  return 'other';
}

export function helperDownload(platform: HelperPlatform) {
  return platform === 'windows' ? HELPER_DOWNLOADS.windows : HELPER_DOWNLOADS.mac;
}

export function helperPlatformName(platform: HelperPlatform) {
  if (platform === 'windows') return 'Windows 10/11 x64';
  if (platform === 'mac') return 'macOS Apple Silicon';
  return 'máy tính';
}
