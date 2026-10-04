const nativeProcessor = typeof window !== 'undefined' ? (window as unknown as { flowNativeProcessor?: string }).flowNativeProcessor : undefined;
export const PROCESSOR_URL = nativeProcessor && /^http:\/\/127\.0\.0\.1:\d{4,5}$/.test(nativeProcessor) ? nativeProcessor : 'http://127.0.0.1:43127';
export const EXPORT_SIZES = [
  { id: '916', label: '9:16', width: 1080, height: 1920, caption: 'Portrait' },
  { id: '11', label: '1:1', width: 1080, height: 1080, caption: 'Square' },
  { id: '169', label: '16:9', width: 1920, height: 1080, caption: 'Landscape' },
  { id: '45', label: '4:5', width: 1080, height: 1350, caption: 'Feed' },
] as const;
export type ResizeMode = 'fit' | 'crop' | 'blur' | 'color';
export type LocalInput = {
  id: string;
  name: string;
  size: number;
  kind: 'video' | 'image';
};
export type DriveTarget = {
  id: string;
  name: string;
  available: boolean;
  video_folder: string;
  image_folder: string;
  thumbnail_folder: string;
};
export type ProcessorSession = {
  token: string;
  platform: string;
  outputFolder: string;
  targets: DriveTarget[];
  version: number;
};
export type ExportItem = {
  id: string;
  inputId: string;
  name: string;
  kind: string;
  size: string;
  status: string;
  progress: number;
  bytes?: number;
  path?: string;
  thumbnail?: string;
  error?: string;
  driveStatus: string;
  copiedTo?: { app: string; path: string }[];
};
export type ExportJob = {
  id: string;
  status: string;
  createdAt: number;
  items: ExportItem[];
  outputFolder: string;
  error?: string;
  options: { theme: string; folderPattern?: string; namingMode?: string };
  targets: Record<string, unknown>;
};
export const exportBusy = (job?: ExportJob | null) =>
  !!job && ['queued', 'running', 'cancelling', 'uploading'].includes(job.status);

export function friendlyDriveError(value?: string) {
  if (!value) return '';
  if (
    /userRateLimitExceeded|sharingRateLimitExceeded|rateLimitExceeded|HTTP 429|rate limit exceeded/i.test(
      value,
    )
  )
    return 'Google Drive đang giới hạn tốc độ. Tool đã tự thử lại; file vẫn an toàn trên máy. Hãy thử upload Drive lại sau ít phút.';
  return value;
}

export async function processor<T>(
  path: string,
  token?: string,
  init: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(PROCESSOR_URL + path, {
      ...init,
      headers: {
        ...(token ? { 'X-Flow-Token': token } : {}),
        ...Object.fromEntries(new Headers(init.headers)),
      },
      signal: init.signal || AbortSignal.timeout(
        path === '/inputs'
          ? 120000
          : path.endsWith('/retry-drive')
            ? 30 * 60 * 1000
            : path === '/refresh-targets'
              ? 45000
              : 10000,
      ),
    });
  } catch (error) {
    if (init.signal?.aborted) throw error;
    throw Error(
      'Chưa kết nối bộ xử lý trên máy. Hãy mở Flow Studio Helper, cho phép truy cập mạng nội bộ nếu được hỏi, rồi bấm Kết nối lại.',
    );
  }
  const data = await response
    .json()
    .catch(() => ({ error: 'The processor returned an invalid response.' }));
  if (!response.ok)
    throw Error(
      (data as { error?: string }).error || 'Local processing failed.',
    );
  return data as T;
}
export const processorPost = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});
export async function outputBlob(
  job: string,
  item: string,
  kind: 'output' | 'thumbnail',
  token: string,
) {
  const response = await fetch(
    `${PROCESSOR_URL}/files/${job}/${item}/${kind}`,
    { headers: { 'X-Flow-Token': token }, signal: AbortSignal.timeout(120000) },
  );
  if (!response.ok)
    throw Error(
      'Không mở được file kết quả trên máy. Hãy kết nối lại bộ xử lý rồi thử lại.',
    );
  return response.blob();
}
