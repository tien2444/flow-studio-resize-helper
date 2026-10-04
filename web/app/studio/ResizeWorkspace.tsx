'use client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowDownToLine,
  Check,
  CheckCircle2,
  CloudUpload,
  Crop,
  FolderOpen,
  Image,
  LoaderCircle,
  Monitor,
  Plus,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Square,
  Tags,
  Trash2,
  Upload,
  Video,
  X,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import type { Asset } from '@/lib/studio/types';
import { appCodeForTarget } from '@/lib/studio/app-code';
import {
  detectHelperPlatform,
  HELPER_DOWNLOADS,
  helperDownload,
  helperPlatformName,
  type HelperPlatform,
} from '@/lib/studio/helper-platform';
import {
  EXPORT_SIZES,
  exportBusy,
  friendlyDriveError,
  outputBlob,
  processor,
  processorPost,
  type DriveTarget,
  type ExportJob,
  type ExportItem,
  type LocalInput,
  type ProcessorSession,
  type ResizeMode,
} from '@/lib/studio/local-processor';
import './resize-workspace.css';

type Source = {
  id: string;
  name: string;
  mime: string;
  size: number;
  url: string;
  file?: File;
  asset?: Asset;
};
const sizeLabel = (bytes = 0) =>
  bytes < 1048576
    ? `${Math.round(bytes / 1024)} KB`
    : `${(bytes / 1048576).toFixed(1)} MB`;
const fileName = (path: string) => path.split(/[\\/]/).pop() || path;
const AUTO_FOLDER_PATTERN = '{YYMM}/{YYMMDD}/{Theme}';
const MIN_HELPER_VERSION = 12;
const dateCode = (value: Date) =>
  `${String(value.getFullYear()).slice(-2)}${String(value.getMonth() + 1).padStart(2, '0')}${String(value.getDate()).padStart(2, '0')}`;
const folderSafe = (value: string) =>
  value.replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').replace(/\s+/g, ' ').trim() || '_unknown_theme';
const jobProgress = (value?: ExportJob | null) =>
  value?.items.length
    ? Math.round(value.items.reduce((total, item) => total + item.progress, 0) / value.items.length)
    : 0;
const finishedJob = (value: ExportJob) =>
  value.status === 'succeeded' || value.status === 'cancelled';

function ResultImage({
  job,
  item,
  token,
}: {
  job: string;
  item: ExportItem;
  token: string;
}) {
  const [src, setSrc] = useState('');
  useEffect(() => {
    let active = true,
      url = '';
    outputBlob(job, item.id, item.thumbnail ? 'thumbnail' : 'output', token)
      .then((blob) => {
        if (active) {
          url = URL.createObjectURL(blob);
          setSrc(url);
        }
      })
      .catch(() => {});
    return () => {
      active = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [job, item.id, item.thumbnail, token]);
  return src ? <img src={src} alt={item.name} /> : <Video size={22} />;
}

export function ResizeWorkspace({
  open,
  onOpenChange,
  request,
  assets,
  projectId,
  projectName,
  canvasId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  request: { assets: Asset[]; theme?: string; flowToken?: string };
  assets: Asset[];
  projectId: string;
  projectName: string;
  canvasId: string;
}) {
  const [session, setSession] = useState<ProcessorSession | null>(null);
  const [clientPlatform, setClientPlatform] = useState<HelperPlatform>('other');
  const [connecting, setConnecting] = useState(false);
  const [syncingTargets, setSyncingTargets] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [local, setLocal] = useState<Source[]>([]);
  const [search, setSearch] = useState('');
  const [sizes, setSizes] = useState<string[]>(['916', '11', '169', '45']);
  const [activeSize, setActiveSize] = useState('916');
  const [mode, setMode] = useState<ResizeMode>('blur');
  const [color, setColor] = useState('#16171b');
  const [blur, setBlur] = useState(24);
  const [quality, setQuality] = useState('balanced');
  const [theme, setTheme] = useState('Creative exports');
  const [namingMode,setNamingMode]=useState<'source'|'OS'|'AUTO'|'W2W'|'W2WOS'>('OS');
  const [appCode,setAppCode]=useState(''),[language,setLanguage]=useState('EN'),[flowToken,setFlowToken]=useState('');
  const [sync, setSync] = useState(true);
  const [destinations, setDestinations] = useState<string[]>([]);
  const [targetAppCodes, setTargetAppCodes] = useState<Record<string, string>>({});
  const [targetSearch, setTargetSearch] = useState('');
  const [job, setJob] = useState<ExportJob | null>(null);
  const [history, setHistory] = useState<ExportJob[]>([]);
  const [showFinished, setShowFinished] = useState(false);
  const [viewingFinished, setViewingFinished] = useState(false);
  const [deletingJob, setDeletingJob] = useState('');
  const [retryingDriveJob, setRetryingDriveJob] = useState('');
  const [tab, setTab] = useState<'setup' | 'results'>('setup');
  const [setupStep, setSetupStep] = useState<1 | 2 | 3>(1);
  const [transferring, setTransferring] = useState(false);
  const [transferStatus, setTransferStatus] = useState('');
  const [clock, setClock] = useState(() => new Date());
  const [preview, setPreview] = useState<{ url: string; name: string } | null>(
    null,
  );
  useEffect(() => {
    setClientPlatform(detectHelperPlatform(navigator.userAgent));
  }, []);
  const fileInput = useRef<HTMLInputElement>(null),
    configInput = useRef<HTMLInputElement>(null);
  const sourceUrls = useRef(new Set<string>());
  const inputCache = useRef(new Map<string, LocalInput>());
  const transferAbort = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      sourceUrls.current.forEach(URL.revokeObjectURL);
    };
  }, []);
  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview.url);
    },
    [preview],
  );
  const sources = useMemo<Source[]>(
    () => [
      ...local,
      ...Array.from(new Map([...assets, ...request.assets].map(a => [a.id, a])).values())
        .filter((a) => /^(video|image)\//.test(a.mime))
        .map((a) => ({ ...a, id: 'asset:' + a.id, asset: a })),
    ],
    [local, assets, request],
  );
  const chosen = sources.filter((s) => selected.includes(s.id));
  const visible = sources
    .filter((s) => s.name.toLowerCase().includes(search.toLowerCase()))
    .slice(0, 80);
  const first = chosen[0];
  const shape = EXPORT_SIZES.find((s) => s.id === activeSize)!;
  const busy = transferring;
  const lastRequest = useRef<typeof request | null>(null);
  const wasOpen = useRef(false);
  useEffect(() => {
    const justOpened = open && !wasOpen.current;
    wasOpen.current = open;
    if (!open || (!justOpened && lastRequest.current === request)) return;
    lastRequest.current = request;
    setSelected(request.assets.map(a => 'asset:' + a.id));
    setTheme((request.theme?.trim() || projectName.trim() || 'Creative exports').slice(0, 120));
    setClock(new Date());
    if (request.flowToken?.trim()) setFlowToken(request.flowToken.trim().slice(0, 80));
    setSearch('');
    setTab(transferring ? 'results' : 'setup');
    if (!transferring) setSetupStep(1);
    setNotice('');
  }, [open, request, transferring]);
  useEffect(() => {
    if (!open) return;
    const timer = window.setInterval(() => setClock(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, [open]);
  useEffect(() => {
    if (!open || destinations.length || !session?.targets.length || !projectName.trim()) return;
    const key = projectName.toLocaleLowerCase('vi').replace(/[^a-z0-9]+/g, '');
    const available = session.targets.filter(target => target.available);
    const exact = available.find(target => target.name.toLocaleLowerCase('vi').replace(/[^a-z0-9]+/g, '') === key);
    if (exact) setDestinations([exact.id]);
  }, [open, session?.targets, projectName, destinations.length]);
  const outputCount = chosen.reduce(
    (n, s) => n + (s.mime.startsWith('video/') ? sizes.length : 1),
    0,
  );
  const completed =
    job?.items.filter((i) => i.status === 'succeeded').length || 0;
  const progress = jobProgress(job);
  const selectedDestinations = destinations
    .map(id => session?.targets.find(target => target.id === id))
    .filter((target): target is DriveTarget => !!target);
  const targetCodesReady = !sync || namingMode === 'source' ||
    selectedDestinations.every(target => !!targetAppCodes[target.id]?.trim());
  const namingReady = namingMode === 'source' || (
    !!appCode.trim() && !!language.trim() &&
    (!['W2W', 'W2WOS'].includes(namingMode) || !!flowToken.trim()) && targetCodesReady
  );
  const selectedDestination = session?.targets.find(target => target.id === destinations[0]);
  const suggestedAppCode = selectedDestination
    ? appCodeForTarget(selectedDestination.name || selectedDestination.id)
    : '';
  const availableTargetCount = session?.targets.filter(target => target.available).length || 0;
  const helperOutdated = !!session && session.version < MIN_HELPER_VERSION;
  const driveReady = !sync || (!!selectedDestinations.length && selectedDestinations.every(target => target.available));
  const queueJobs = history.filter(entry => !finishedJob(entry));
  const finishedJobs = history.filter(finishedJob);
  const activeJobCount = history.filter(exportBusy).length;
  const setupReady = !!session && !helperOutdated && !!chosen.length && outputCount > 0 && !!theme.trim() && namingReady && driveReady;
  const liveDateCode = dateCode(clock);
  const liveFolder = `${liveDateCode.slice(0, 4)}/${liveDateCode}/${folderSafe(theme)}`;

  useEffect(() => {
    if (!selectedDestination) return;
    const code = targetAppCodes[selectedDestination.id] || appCodeForTarget(selectedDestination.name || selectedDestination.id);
    setTargetAppCodes(current => current[selectedDestination.id] || !code ? current : { ...current, [selectedDestination.id]: code });
    setAppCode(code);
  }, [selectedDestination?.id, selectedDestination?.name, targetAppCodes]);
  const normalizedFlowToken = flowToken.trim()
    ? (/^W2W/i.test(flowToken.trim()) ? flowToken.trim() : `W2W${flowToken.trim()}`)
    : 'W2W01';
  const filePreview = namingMode === 'source'
    ? 'ten-goc_916_30s.mp4'
    : `${theme.trim() || 'Theme'}_${appCode.trim() || 'APP'}_A12B7C31D4E18F9G26_${language.trim() || 'EN'}_${namingMode === 'OS' ? 'OS' : namingMode === 'AUTO' ? 'AT' : `${normalizedFlowToken}${namingMode === 'W2WOS' ? '_OS' : ''}`}_916_30s_${liveDateCode}.mp4`;
  const setupBlocker = !session
    ? 'Mở local processor để resize trên máy.'
    : helperOutdated
      ? 'Cập nhật Flow Studio Helper để kết nối ổn định với Google Drive mới.'
    : !chosen.length
      ? 'Chọn ít nhất một video nguồn.'
      : !namingReady
        ? 'Điền đủ thông tin đặt tên hàng loạt.'
        : outputCount === 0
          ? 'Chọn ít nhất một tỷ lệ resize.'
          : !theme.trim()
            ? 'Pack chưa có tên để đồng bộ Theme.'
            : !driveReady
              ? 'Chọn đúng app/thư mục Drive trước khi chạy.'
              : '';

  const [folderDraft, setFolderDraft] = useState('');
  const [choosingFolder, setChoosingFolder] = useState(false);
  const nativeFolders = typeof window !== 'undefined' ? (window as unknown as { flowDesktop?: { chooseOutputFolder: () => Promise<string | null> } }).flowDesktop : undefined;
  useEffect(() => { setFolderDraft(session?.outputFolder || ''); }, [session?.outputFolder]);
  const changeOutputFolder = async () => {
    if (!session || busy || transferring) return;
    setChoosingFolder(true); setError('');
    try {
      const path = nativeFolders ? await nativeFolders.chooseOutputFolder() : folderDraft;
      if (!path) return;
      const result = await processor<{outputFolder: string}>('/output-folder', session.token, processorPost({outputFolder: path}));
      setSession(old => old ? {...old, ...result} : old);
      setNotice('Output folder saved. New exports will use this folder.');
    } catch(e) { setError((e as Error).message); }
    finally { setChoosingFolder(false); }
  };

  const reconnect = useCallback(async () => {
    setConnecting(true);
    setError('');
    try {
      let next = await processor<ProcessorSession>('/session');
      try {
        const targetResponse = await fetch('/api/processor-targets', { cache: 'no-store' });
        const canonical = await targetResponse.json() as { error?: string; version: string; targets: Record<string, Record<string, unknown>> };
        if (!targetResponse.ok) throw Error(canonical.error || 'Không tải được danh sách app chuẩn.');
        await processor<{ targets: DriveTarget[] }>('/targets', next.token, processorPost(canonical.targets));
        const synced = await processor<{ targets: DriveTarget[] }>('/refresh-targets', next.token, processorPost({}));
        next = { ...next, targets: synced.targets };
      } catch (targetError) {
        // An already-configured helper remains usable during a transient API
        // outage. A fresh helper must receive the canonical app directory.
        if (!next.targets.length) throw targetError;
      }
      if (!mounted.current) return;
      setSession(next);
      const all = await processor<{ jobs: ExportJob[] }>('/jobs', next.token);
      if (!mounted.current) return;
      setHistory(all.jobs);
      setJob((old) =>
        old
          ? all.jobs.find((j) => j.id === old.id) || old
          : all.jobs[0] || null,
      );
    } catch (e) {
      if (mounted.current) {
        setSession(null);
        setError((e as Error).message);
      }
    } finally {
      if (mounted.current) setConnecting(false);
    }
  }, []);
  const syncDriveApps = useCallback(async () => {
    if (!session || syncingTargets) return;
    setSyncingTargets(true);
    setError('');
    try {
      const next = await processor<{ targets: DriveTarget[] }>(
        '/refresh-targets',
        session.token,
        processorPost({}),
      );
      if (!mounted.current) return;
      setSession(current => current ? { ...current, targets: next.targets } : current);
      setDestinations(current => current.filter(id => next.targets.some(target => target.id === id && target.available)));
      const available = next.targets.filter(target => target.available).length;
      setNotice(
        available
          ? `Đã đồng bộ ${available} app đang có trên Google Drive của máy này.`
          : 'Chưa thấy Shared Drive iKame. Hãy mở Google Drive for Desktop, đăng nhập tài khoản được cấp quyền rồi đồng bộ lại.',
      );
    } catch (e) {
      if (mounted.current) setError((e as Error).message);
    } finally {
      if (mounted.current) setSyncingTargets(false);
    }
  }, [session, syncingTargets]);
  useEffect(() => {
    if (open) void reconnect();
  }, [open, reconnect]);
  useEffect(() => {
    if (!open || !session) return;
    let stop = false,
      pending = false;
    const poll = async () => {
      if (pending) return;
      pending = true;
      try {
        const next = await processor<{ jobs: ExportJob[] }>('/jobs', session.token);
        if (!stop) {
          setHistory(next.jobs);
          setJob(current => current
            ? next.jobs.find(candidate => candidate.id === current.id) || current
            : next.jobs[0] || null);
          setError('');
        }
      } catch (e) {
        if (!stop) setError((e as Error).message);
      } finally {
        pending = false;
      }
    };
    void poll();
    const timer = setInterval(() => void poll(), 1500);
    return () => {
      stop = true;
      clearInterval(timer);
    };
  }, [open, session]);
  useEffect(() => {
    if (job && finishedJob(job) && !viewingFinished) setJob(null);
  }, [job, viewingFinished]);
  const toggle = (id: string) => {
    if (!busy)
      setSelected((ids) =>
        ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id],
      );
  };
  const toggleDestination = (target: DriveTarget) => {
    if (busy || !target.available) return;
    setDestinations(current => {
      if (current.includes(target.id)) return current.filter(id => id !== target.id);
      if (current.length >= 20) {
        setError('Mỗi pack chọn tối đa 20 app đích.');
        return current;
      }
      return [...current, target.id];
    });
    setTargetAppCodes(current => current[target.id]
      ? current
      : { ...current, [target.id]: appCodeForTarget(target.name || target.id) });
  };
  const removeDestination = (targetId: string) => {
    if (busy) return;
    setDestinations(current => current.filter(id => id !== targetId));
  };
  const addFiles = (files: File[]) => {
    if (busy) return;
    const accepted = files.filter(
      (f) =>
        /\.(mp4|mov|webm|mkv|avi|png|jpe?g|webp)$/i.test(f.name) &&
        f.size > 0 &&
        f.size <= 512 * 1048576,
    );
    if (accepted.length !== files.length)
      setError(
        'Some files were skipped. Use videos or images up to 512 MB each.',
      );
    const added = accepted.slice(0, 50 - local.length).map((file) => {
      const url = URL.createObjectURL(file);
      sourceUrls.current.add(url);
      return {
        id: crypto.randomUUID(),
        name: file.name,
        mime:
          file.type ||
          (/\.(png|jpe?g|webp)$/i.test(file.name) ? 'image/png' : 'video/mp4'),
        size: file.size,
        url,
        file,
      };
    });
    setLocal((x) => [...x, ...added]);
    setSelected((x) => [...x, ...added.map((s) => s.id)]);
  };
  const start = async () => {
    if (!session || busy || !chosen.length) return;
    setError('');
    setNotice('');
    setTransferring(true);
    const controller = new AbortController();
    transferAbort.current = controller;
    const signal = AbortSignal.any([
      controller.signal,
      AbortSignal.timeout(120000),
    ]);
    try {
      const inputIds: string[] = [];
      for (let i = 0; i < chosen.length; i++) {
        const source = chosen[i];
        setTransferStatus(
          `Preparing ${i + 1} of ${chosen.length}: ${source.name}`,
        );
        let input = inputCache.current.get(source.id);
        if (!input) {
          let blob: Blob = source.file!;
          if (!blob) {
            const response = await fetch(source.url, {
              headers:
                new URL(source.url, location.href).origin === location.origin
                  ? { 'x-flow-project': projectId, 'x-flow-canvas': canvasId }
                  : {},
              signal,
            });
            if (!response.ok)
              throw Error(
                `Could not retrieve ${source.name}. Refresh the media library and retry.`,
              );
            blob = await response.blob();
          }
          input = await processor<LocalInput>('/inputs', session.token, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/octet-stream',
              'X-File-Name': encodeURIComponent(source.name),
            },
            body: blob,
            signal,
          });
          inputCache.current.set(source.id, input);
        }
        inputIds.push(input.id);
      }
      signal.throwIfAborted();
      // Once submitted, retain the returned job ID so cancellation targets that job.
      transferAbort.current = null;
      const next = await processor<ExportJob>(
        '/jobs',
        session.token,
        processorPost({
          inputIds,
          sizes,
          mode,
          color,
          blur,
          quality,
          theme,
          folderPattern: AUTO_FOLDER_PATTERN,
          namingMode,
          appCode,
          language,
          flowToken,
          targets: sync ? destinations : [],
          targetAppCodes: sync
            ? Object.fromEntries(destinations.map(id => [id, targetAppCodes[id] || appCode]))
            : {},
        }),
      );
      setViewingFinished(false);
      setJob(next);
      setTab('results');
      setHistory((h) => [next, ...h.filter((j) => j.id !== next.id)]);
      setNotice('Đã đưa pack vào hàng chờ trên máy. Bạn có thể đóng cửa sổ web hoặc tạo pack khác; Helper vẫn tiếp tục chạy nền.');
    } catch (e) {
      if (controller.signal.aborted)
        setNotice('File preparation cancelled. No export was started.');
      else setError((e as Error).message);
    } finally {
      transferAbort.current = null;
      setTransferring(false);
      setTransferStatus('');
    }
  };
  const cancel = async () => {
    if (!job || !session) return;
    try {
      setJob(
        await processor<ExportJob>(
          `/jobs/${job.id}/cancel`,
          session.token,
          processorPost({}),
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const deleteFinishedJob = async (entry: ExportJob) => {
    if (!session || exportBusy(entry) || deletingJob) return;
    if (session.version < MIN_HELPER_VERSION) {
      setError('Cập nhật Flow Studio Helper để xoá pack đã xử lý.');
      return;
    }
    if (!window.confirm(`Xoá pack “${entry.options.theme || 'Pack resize'}” khỏi lịch sử và xoá các file resize đã lưu trên máy?\n\nFile đã upload lên Google Drive vẫn được giữ nguyên.`)) return;
    setDeletingJob(entry.id);
    setError('');
    try {
      await processor<{deleted: string; filesDeleted: number}>(
        `/jobs/${entry.id}/delete`,
        session.token,
        processorPost({}),
      );
      setHistory(current => current.filter(candidate => candidate.id !== entry.id));
      if (job?.id === entry.id) {
        setJob(null);
        setViewingFinished(false);
      }
      setNotice(`Đã xoá pack “${entry.options.theme || 'Pack resize'}” và file local. File trên Drive vẫn được giữ.`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDeletingJob('');
    }
  };
  const retryDriveUpload = async (entry: ExportJob) => {
    if (!session || exportBusy(entry) || retryingDriveJob) return;
    if (session.version < MIN_HELPER_VERSION) {
      setError('Cập nhật Flow Studio Helper để thử upload Drive mà không render lại.');
      return;
    }
    setRetryingDriveJob(entry.id);
    setError('');
    setNotice('Đang tải lại các file lỗi lên Google Drive. File đã resize trên máy được giữ nguyên.');
    try {
      const next = await processor<ExportJob>(
        `/jobs/${entry.id}/retry-drive`,
        session.token,
        processorPost({}),
      );
      setJob(next);
      setHistory(current => [next, ...current.filter(candidate => candidate.id !== next.id)]);
      const remaining = next.items.filter(item => item.driveStatus === 'failed').length;
      if (remaining) {
        setError(`Còn ${remaining} file chưa upload được. File local vẫn an toàn; hãy kiểm tra quyền Drive rồi thử lại.`);
      } else {
        setNotice('Đã upload lại toàn bộ file lỗi lên Google Drive, không render lại video.');
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRetryingDriveJob('');
    }
  };
  const openOutput = async (item: ExportItem, download = false) => {
    if (!session || !job) return;
    try {
      const blob = await outputBlob(job.id, item.id, 'output', session.token),
        url = URL.createObjectURL(blob);
      if (download) {
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName(item.path || item.name);
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 30000);
      } else setPreview({ url, name: fileName(item.path || item.name) });
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const importTargets = async (file: File) => {
    if (!session) return;
    try {
      if (file.size > 500000)
        throw Error('This destination file is too large.');
      const value = JSON.parse(await file.text());
      const next = await processor<{ targets: DriveTarget[] }>(
        '/targets',
        session.token,
        processorPost(value),
      );
      setSession({ ...session, targets: next.targets });
      setDestinations([]);
      setNotice('Destinations imported. Choose where to copy this batch.');
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="resize-workspace" showCloseButton={false}>
          <header className="resize-heading">
            <span className="resize-brand-icon">
              <Crop size={23} />
            </span>
            <div>
              <DialogTitle>Đặt tên · Resize · Upload Drive</DialogTitle>
              <DialogDescription>
                Xử lý trọn pack theo đúng thứ tự và kiểm tra app đích trước khi chạy.
              </DialogDescription>
            </div>
            <span className={'resize-connection ' + (session ? 'online' : '')}>
              <Monitor size={14} />
              {connecting
                  ? 'Đang kết nối…'
                  : session
                  ? `Bộ xử lý ${session.platform === 'win32' ? 'Windows' : session.platform === 'darwin' ? 'macOS' : 'trên máy'} sẵn sàng`
                  : 'Bộ xử lý đang offline'}
            </span>
            <button
              className="resize-icon"
              aria-label="Close Resize & Export"
              onClick={() => onOpenChange(false)}
            >
              <X size={20} />
            </button>
          </header>
          <nav className="resize-tabs">
            <button
              className={tab === 'setup' ? 'active' : ''}
              onClick={() => setTab('setup')}
            >
              <SlidersHorizontal size={16} /> Thiết lập pack
            </button>
            <button
              className={tab === 'results' ? 'active' : ''}
              onClick={() => setTab('results')}
            >
              <FolderOpen size={16} /> Kết quả xử lý{' '}
              {!!history.length && (
                <span>
                  {queueJobs.length
                    ? `${queueJobs.length} trong hàng chờ`
                    : `${finishedJobs.length} đã xong`}
                </span>
              )}
            </button>
            <span className="resize-tabs-end">XỬ LÝ TRÊN MÁY</span>
          </nav>
          {tab === 'setup' && <div className="resize-flow-steps" aria-label="Các bước xử lý pack">
            <button type="button" className={setupStep===1?'current':chosen.length?'done':''} onClick={()=>setSetupStep(1)}><i>{chosen.length ? <Check size={13}/> : '1'}</i><span><b>1. Chọn nguồn</b><small>{chosen.length ? `${chosen.length} video đã chọn` : 'Chưa chọn video'}</small></span></button>
            <button type="button" className={setupStep===2?'current':driveReady?'done':''} disabled={!chosen.length} onClick={()=>setSetupStep(2)}><i>{driveReady ? <Check size={13}/> : '2'}</i><span><b>2. Chọn ứng dụng</b><small>{sync ? selectedDestinations.length ? `${selectedDestinations.length} app đích` : 'Chưa chọn app' : 'Không upload Drive'}</small></span></button>
            <button type="button" className={setupStep===3?'current':namingReady&&outputCount>0?'done':''} disabled={!chosen.length || !driveReady} onClick={()=>setSetupStep(3)}><i>{namingReady&&outputCount>0 ? <Check size={13}/> : '3'}</i><span><b>3. Thiết lập</b><small>{namingMode === 'source' ? 'Tên gốc' : `${namingMode === 'AUTO' ? 'Auto' : namingMode} · ${sizes.length} tỷ lệ`}</small></span></button>
          </div>}
          {error && (
            <div role="alert" className="resize-alert">
              {error}
              <button onClick={() => void reconnect()} disabled={connecting}>
                <RefreshCw size={14} /> Kết nối lại
              </button>
            </div>
          )}
          {tab === 'setup' && !session && !connecting && (
            <section className="resize-onboarding" aria-label="Cài bộ xử lý trên máy">
              <Monitor size={22} />
              <div>
                <strong>Cài một lần trên {helperPlatformName(clientPlatform)}</strong>
                <p>Flow Studio Helper resize trên máy; Google Drive for desktop đưa đúng Shared Drive vào máy. Mỗi máy cần cài riêng, sau đó Helper tự chạy khi đăng nhập.</p>
                <div className="resize-install-steps">
                  <span><b>1</b>Tải và mở Helper</span>
                  <span><b>2</b>Đăng nhập Google Drive</span>
                  <span><b>3</b>Bấm Kiểm tra lại</span>
                </div>
              </div>
              <div className="resize-onboarding-actions">
                <a className="primary" href={helperDownload(clientPlatform)} download>
                  <ArrowDownToLine size={15} /> Tải Helper cho {clientPlatform === 'windows' ? 'Windows' : 'macOS'}
                </a>
                <a href="https://www.google.com/drive/download/" target="_blank" rel="noreferrer">
                  <CloudUpload size={15} /> Tải Google Drive
                </a>
                <button type="button" onClick={() => void reconnect()} disabled={connecting}>
                  <RefreshCw size={15} /> Kiểm tra lại
                </button>
                <div className="resize-other-platforms">
                  <span>Tải cho máy khác:</span>
                  <a href={HELPER_DOWNLOADS.windows} download>Windows</a>
                  <a href={HELPER_DOWNLOADS.mac} download>macOS</a>
                </div>
              </div>
            </section>
          )}
          {tab === 'setup' && helperOutdated && (
            <section className="resize-onboarding" aria-label="Cập nhật bộ xử lý trên máy">
              <RefreshCw size={22} />
              <div>
                <strong>Cần cập nhật Flow Studio Helper</strong>
                <p>Tải đúng bản cho hệ điều hành đang dùng. Cập nhật không xoá hàng chờ hoặc file đã resize trên máy.</p>
              </div>
              <div className="resize-onboarding-actions">
                <a className="primary" href={helperDownload(clientPlatform)} download>
                  <ArrowDownToLine size={15} /> Tải Helper cho {clientPlatform === 'windows' ? 'Windows' : 'macOS'}
                </a>
                <button type="button" onClick={() => void reconnect()} disabled={connecting}>
                  <RefreshCw size={15} /> Kiểm tra lại
                </button>
              </div>
            </section>
          )}
          {tab === 'setup' && session && !helperOutdated && sync && availableTargetCount === 0 && (
            <section className="resize-onboarding drive-missing" aria-label="Google Drive chưa sẵn sàng">
              <CloudUpload size={22} />
              <div>
                <strong>Helper đã chạy, nhưng chưa thấy Shared Drive iKame</strong>
                <p>Mở Google Drive for Desktop, đăng nhập tài khoản @ikameglobal.com đã được cấp quyền và chờ thư mục iKame Apps - Creative xuất hiện.</p>
              </div>
              <div className="resize-onboarding-actions">
                <a href="https://www.google.com/drive/download/" target="_blank" rel="noreferrer">
                  <ArrowDownToLine size={15} /> Cài Google Drive
                </a>
                <button type="button" onClick={() => void syncDriveApps()} disabled={syncingTargets}>
                  <RefreshCw size={15} className={syncingTargets ? 'spin' : ''} /> Đồng bộ lại app
                </button>
              </div>
            </section>
          )}
          {notice && (
            <div role="status" className="resize-notice">
              {notice}
            </div>
          )}
          {tab === 'setup' ? (
            <div className={`resize-body resize-step-${setupStep}`}>
              {setupStep===1 && <aside className="resize-sources">
                <div className="resize-section-title">
                  <h3>1. Video trong pack</h3>
                  <span>{chosen.length} đã chọn</span>
                </div>
                <button
                  className="resize-drop"
                  disabled={busy}
                  onClick={() => fileInput.current?.click()}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    addFiles([...e.dataTransfer.files]);
                  }}
                >
                  <Upload size={23} />
                  <strong>Thêm file từ máy</strong>
                  <small>hoặc kéo thả video vào đây</small>
                </button>
                <input
                  ref={fileInput}
                  hidden
                  type="file"
                  multiple
                  accept="video/*,image/png,image/jpeg,image/webp"
                  onChange={(e) => {
                    addFiles([...(e.target.files || [])]);
                    e.target.value = '';
                  }}
                />
                <div className="resize-search">
                  <Search size={15} />
                  <input
                    aria-label="Search export media"
                    placeholder="Tìm video trong dự án…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
                <div className="resize-media-list">
                  {visible.map((source) => (
                    <button
                      key={source.id}
                      className={
                        'resize-source ' +
                        (selected.includes(source.id) ? 'selected' : '')
                      }
                      onClick={() => toggle(source.id)}
                      disabled={busy}
                      aria-pressed={selected.includes(source.id)}
                      aria-label={'Select ' + source.name}
                    >
                      <div className="resize-source-thumb">
                        {source.mime.startsWith('image/') ? (
                          <img src={source.url} alt="" loading="lazy" />
                        ) : (
                          <Video size={23} />
                        )}
                      </div>
                      <span>
                        <strong>{source.name}</strong>
                        <small>
                          {source.file ? 'File trên máy' : 'Video dự án'} ·{' '}
                          {sizeLabel(source.size)}
                        </small>
                      </span>
                      <i>
                        {selected.includes(source.id) ? (
                          <Check size={13} />
                        ) : null}
                      </i>
                    </button>
                  ))}
                  {!visible.length && (
                    <p className="resize-empty-small">
                      Thêm file từ máy hoặc chọn một pack video đã tạo.
                    </p>
                  )}
                </div>
                <button
                  className="resize-text-button"
                  disabled={busy || !selected.length}
                  onClick={() => setSelected([])}
                >
                  <Trash2 size={14} /> Bỏ chọn tất cả
                </button>
              </aside>}
              {setupStep!==2 && <section className="resize-preview-column">
                <div className="resize-section-title">
                  <h3>Xem trước khung hình</h3>
                  <span>
                    {shape.width} × {shape.height}
                  </span>
                </div>
                <div className="resize-preview-stage">
                  <div className="resize-preview-area">
                    <div
                      className={'resize-preview-frame mode-' + mode}
                      style={{
                        width: `min(100cqw, ${(100 * shape.width) / shape.height}cqh)`,
                        height: `min(100cqh, ${(100 * shape.height) / shape.width}cqw)`,
                        background: mode === 'color' ? color : '#08090b',
                      }}
                    >
                      {first ? (
                        <>
                          {mode === 'blur' &&
                            (first.mime.startsWith('video/') ? (
                              <video
                                className="resize-blur-layer"
                                src={first.url}
                                muted
                                preload="metadata"
                                style={{ filter: `blur(${blur / 2}px)` }}
                              />
                            ) : (
                              <img
                                className="resize-blur-layer"
                                src={first.url}
                                alt=""
                                style={{ filter: `blur(${blur / 2}px)` }}
                              />
                            ))}
                          {first.mime.startsWith('video/') ? (
                            <video
                              className="resize-main-media"
                              src={first.url}
                              controls
                              playsInline
                              preload="metadata"
                            />
                          ) : (
                            <img
                              className="resize-main-media"
                              src={first.url}
                              alt={first.name}
                            />
                          )}
                        </>
                      ) : null}
                    </div>
                    {!first && (
                      <div className="resize-preview-empty">
                        <Video size={38} />
                        <strong>Chọn video để xem trước</strong>
                        <span>Khung hình sẽ thay đổi theo tỷ lệ resize.</span>
                      </div>
                    )}
                  </div>
                </div>
                <div className="resize-preview-sizes">
                  {EXPORT_SIZES.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => setActiveSize(s.id)}
                      className={activeSize === s.id ? 'active' : ''}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
                <p className="resize-preview-hint">
                  {mode === 'crop'
                    ? 'Crop lấp đầy khung; phần thừa bên ngoài sẽ bị cắt.'
                    : 'Giữ trọn chủ thể trong tỷ lệ đã chọn.'}{' '}
                  Bản xuất cuối được xử lý bằng FFmpeg trên máy.
                </p>
                <div className="resize-local-note">
                  <Monitor size={18} />
                  <span>
                    <strong>Xử lý trên máy này</strong>
                    <small>
                      FFmpeg · H.264 + AAC · Tạo thumbnail từ khung hình đầu
                    </small>
                  </span>
                </div>
              </section>}
              <aside className="resize-options">
                {setupStep===3 && <><section className="resize-option-card resize-naming-card">
                  <div className="resize-card-heading">
                    <span><Tags size={17}/></span>
                    <div><small>BƯỚC 2</small><h3>Đặt tên hàng loạt</h3></div>
                    <em className={namingReady ? 'ready' : ''}>{namingReady ? 'Đủ thông tin' : 'Cần điền'}</em>
                  </div>
                  <p className="resize-card-help">Chọn chuẩn tên giống Advanced Rename. Tên này được áp dụng trước khi resize và upload.</p>
                  <div className="resize-name-mode-grid" aria-label="Quy tắc đặt tên">
                    {(['OS','AUTO','W2W','W2WOS','source'] as const).map(value=><button type="button" key={value} className={namingMode===value?'selected':''} disabled={busy} onClick={()=>setNamingMode(value)}>{value==='source'?'Tên gốc':value==='AUTO'?'Auto':value==='W2WOS'?'W2W Outsource':value}</button>)}
                  </div>
                  {namingMode!=='source'&&<div className="resize-naming-grid">
                    <label>
                      Mã app · tự lấy theo app đích
                      <input
                        aria-label="Mã app"
                        placeholder={selectedDestination && !suggestedAppCode ? 'Chưa có mã trong bảng master' : 'Ví dụ: FS1'}
                        value={appCode}
                        disabled={busy}
                        onChange={e=>{
                          setAppCode(e.target.value);
                          if (selectedDestination) setTargetAppCodes(current => ({...current,[selectedDestination.id]:e.target.value}));
                        }}
                      />
                    </label>
                    <label>Nhãn từng video · tự tạo, không trùng<input aria-label="Nhãn tự động" value="A…B…C…D…E…F…G…" readOnly aria-readonly="true" /></label>
                    <label>Ngôn ngữ<input aria-label="Language" placeholder="EN" value={language} disabled={busy} onChange={e=>setLanguage(e.target.value.toUpperCase())}/></label>
                    {(namingMode==='W2W'||namingMode==='W2WOS')&&<label>Mã luồng W2W<input aria-label="W2W flow token" placeholder="Ví dụ: 07" value={flowToken} disabled={busy} onChange={e=>setFlowToken(e.target.value)}/></label>}
                  </div>}
                  {namingMode!=='source'&&sync&&selectedDestinations.length>1&&<div className="resize-target-code-list">
                    <small>MÃ FILE THEO TỪNG APP ĐÍCH</small>
                    {selectedDestinations.map(target=><label key={target.id}><span>{target.name}</span><input aria-label={`Mã app ${target.name}`} value={targetAppCodes[target.id]||''} placeholder="Mã app" disabled={busy} onChange={event=>setTargetAppCodes(current=>({...current,[target.id]:event.target.value}))}/></label>)}
                  </div>}
                  <label className="resize-field">
                    Theme · lấy từ tên pack, có thể chỉnh sửa
                    <input
                      aria-label="Theme"
                      value={theme}
                      maxLength={120}
                      disabled={busy}
                      onChange={e=>setTheme(e.target.value)}
                    />
                  </label>
                  <label className="resize-field">Thư mục Drive · tự động theo ngày xử lý<input value={liveFolder} readOnly aria-readonly="true"/></label>
                  <div className="resize-name-preview"><small>TÊN FILE MẪU</small><strong>{filePreview}</strong></div>
                </section>

                <section className="resize-option-card">
                  <div className="resize-card-heading">
                    <span><Crop size={17}/></span>
                    <div><small>BƯỚC 3</small><h3>Resize video</h3></div>
                    <em className={outputCount > 0 ? 'ready' : ''}>{outputCount} file đầu ra</em>
                  </div>
                  <div className="resize-section-title"><h3>Tỷ lệ đầu ra</h3><small>Chọn nhiều tỷ lệ</small></div>
                <div className="resize-format-grid">
                  {EXPORT_SIZES.map((s) => (
                    <button
                      key={s.id}
                      disabled={busy}
                      aria-pressed={sizes.includes(s.id)}
                      className={sizes.includes(s.id) ? 'selected' : ''}
                      onClick={() => {
                        setSizes((v) =>
                          v.includes(s.id)
                            ? v.filter((x) => x !== s.id)
                            : [...v, s.id],
                        );
                        setActiveSize(s.id);
                      }}
                    >
                      <span
                        className="resize-ratio-icon"
                        style={{ aspectRatio: `${s.width}/${s.height}` }}
                      />
                      <strong>{s.label}</strong>
                      <small>
                        {s.width} × {s.height}
                      </small>
                      {sizes.includes(s.id) && <Check size={14} />}
                    </button>
                  ))}
                </div>
                <h3>Khung hình & nền</h3>
                <div className="resize-mode-grid">
                  {(['fit', 'crop', 'blur', 'color'] as ResizeMode[]).map(
                    (m) => (
                      <button
                        key={m}
                        disabled={busy}
                        className={mode === m ? 'selected' : ''}
                        onClick={() => setMode(m)}
                      >
                        {m === 'fit'
                          ? 'Fit / nền đen'
                          : m === 'crop'
                            ? 'Crop đầy khung'
                            : m === 'blur'
                              ? 'Nền blur'
                              : 'Nền màu'}
                      </button>
                    ),
                  )}
                </div>
                {mode === 'blur' && (
                  <label className="resize-slider">
                    Độ mờ nền <span>{blur}</span>
                    <input
                      type="range"
                      min={1}
                      max={60}
                      value={blur}
                      disabled={busy}
                      onChange={(e) => setBlur(+e.target.value)}
                    />
                  </label>
                )}
                {mode === 'color' && (
                  <label className="resize-field">
                    Màu nền
                    <input
                      type="color"
                      value={color}
                      disabled={busy}
                      onChange={(e) => setColor(e.target.value)}
                    />
                  </label>
                )}
                <label className="resize-field">
                  Tốc độ xuất
                  <select
                    value={quality}
                    disabled={busy}
                    onChange={(e) => setQuality(e.target.value)}
                  >
                    <option value="balanced">Cân bằng · file nhỏ hơn</option>
                    <option value="fast">Nhanh · file lớn hơn</option>
                  </select>
                </label>
                </section></>}

                {setupStep===2 && <section className="resize-option-card resize-drive-card">
                  <div className="resize-card-heading">
                    <span><CloudUpload size={17}/></span>
                    <div><small>BƯỚC 4</small><h3>Upload Google Drive</h3></div>
                  <label className="resize-switch">
                    <input
                      aria-label="Upload kết quả lên Google Drive"
                      type="checkbox"
                      checked={sync}
                      disabled={busy}
                      onChange={(e) => setSync(e.target.checked)}
                    />
                    <span />
                  </label>
                  </div>
                <div className="resize-drive-sync-row">
                  <p className="resize-card-help">Chọn một hoặc nhiều app đích. Helper resize một lần rồi copy đúng tên và mã app vào từng thư mục Drive.</p>
                  <button type="button" disabled={busy || !session || helperOutdated || syncingTargets} onClick={() => void syncDriveApps()}>
                    <RefreshCw size={13} className={syncingTargets ? 'spin' : ''}/>
                    {helperOutdated ? 'Cập nhật Helper để đồng bộ' : syncingTargets ? 'Đang quét…' : `Đồng bộ app (${availableTargetCount})`}
                  </button>
                </div>
                {sync && (
                  <div className="resize-drive-options">
                    <input
                      className="resize-target-search"
                      aria-label="Tìm app đích trên Drive"
                      placeholder="Tìm app đích…"
                      value={targetSearch}
                      onChange={(e) => setTargetSearch(e.target.value)}
                    />
                    <div className="resize-targets">
                      {session?.targets
                        .filter((t) =>
                          t.name
                            .toLowerCase()
                            .includes(targetSearch.toLowerCase()),
                        )
                        .map((t) => (
                          <label key={t.id} title={t.video_folder} className={destinations.includes(t.id)?'selected':''}>
                            <input
                              type="checkbox"
                              disabled={busy || !t.available}
                              checked={destinations.includes(t.id)}
                              onChange={() => toggleDestination(t)}
                            />
                            <span>
                              <strong>{t.name}</strong>
                              <small>
                                {t.available
                                  ? t.video_folder
                                  : 'Mở Drive for Desktop để dùng thư mục này'}
                              </small>
                            </span>
                            {destinations.includes(t.id)&&<em>{targetAppCodes[t.id]||appCodeForTarget(t.name)||'Thiếu mã'}</em>}
                          </label>
                        ))}
                      {!session?.targets.length && (
                        <p>
                          Chưa tải được danh sách app chuẩn. Hãy kết nối lại bộ xử lý.
                        </p>
                      )}
                    </div>
                    <button
                      className="resize-text-button"
                      disabled={busy || !session}
                      onClick={() => configInput.current?.click()}
                    >
                      <Plus size={14} /> Nhập danh sách app đích
                    </button>
                    <input
                      ref={configInput}
                      hidden
                      type="file"
                      accept="application/json,.json"
                      onChange={(e) => {
                        if (e.target.files?.[0])
                          void importTargets(e.target.files[0]);
                        e.target.value = '';
                      }}
                    />
                    {!!selectedDestinations.length && <div className="resize-selected-target"><CheckCircle2 size={16}/><span><small>ĐÃ CHỌN {selectedDestinations.length} APP ĐÍCH</small><div className="resize-selected-target-list">{selectedDestinations.map(target=><span key={target.id}><strong>{target.name}</strong><button type="button" aria-label={`Bỏ app ${target.name}`} title={`Bỏ ${target.name}`} disabled={busy} onClick={()=>removeDestination(target.id)}><X size={12}/></button></span>)}</div><em>Bấm × để bỏ app không muốn upload.</em></span></div>}
                  </div>
                )}
                {!sync && <button type="button" className="resize-drive-skip" onClick={()=>setSync(true)} disabled={busy}>Đang bỏ qua Drive · Bật upload</button>}
                </section>}
                {setupStep===3 && <section className="resize-option-card resize-drive-summary"><div className="resize-card-heading"><span><CloudUpload size={17}/></span><div><small>ỨNG DỤNG ĐÍCH</small><h3>{sync ? selectedDestinations.length ? `${selectedDestinations.length} app đã chọn` : 'Chưa chọn app' : 'Không upload Drive'}</h3></div><button type="button" onClick={()=>setSetupStep(2)}>Đổi app</button></div>{sync&&!!selectedDestinations.length&&<div className="resize-selected-target-list">{selectedDestinations.map(target=><span key={target.id}><strong>{target.name}</strong><button type="button" aria-label={`Bỏ app ${target.name}`} title={`Bỏ ${target.name}`} disabled={busy} onClick={()=>removeDestination(target.id)}><X size={12}/></button></span>)}</div>}</section>}
              </aside>
            </div>
          ) : (
            <section className="resize-results">
              <div className="resize-results-heading">
                <div>
                  <h3>Hàng chờ Resize</h3>
                  <p>
                    {queueJobs.length
                      ? `${activeJobCount} pack đang xử lý, ${queueJobs.length - activeJobCount} pack cần kiểm tra. Helper vẫn chạy khi đóng cửa sổ này.`
                      : finishedJobs.length
                        ? 'Hàng chờ đã trống. Pack hoàn tất nằm trong danh sách Đã xong.'
                        : 'Pack resize sẽ xuất hiện tại đây.'}
                  </p>
                </div>
                <button
                  className="resize-text-button"
                  onClick={() => {
                    setTab('setup');
                    setSetupStep(1);
                    void reconnect();
                  }}
                >
                  <Plus size={16} /> Tạo pack khác
                </button>
              </div>
              {!!queueJobs.length && <div className="resize-queue-list" aria-label="Hàng chờ resize">
                {queueJobs.map(entry=>{
                  const entryProgress=jobProgress(entry);
                  const done=entry.items.filter(item=>item.status==='succeeded').length;
                  return <button type="button" key={entry.id} className={job?.id===entry.id?'selected':''} onClick={()=>{setViewingFinished(false);setJob(entry);}}>
                    <span><strong>{entry.options.theme||'Pack resize'}</strong><small>{new Date(entry.createdAt).toLocaleString('vi-VN')} · {done}/{entry.items.length} file</small></span>
                    <em className={entry.status}>{entry.status==='queued'?'Đang chờ':entry.status==='running'?'Đang chạy':entry.status==='succeeded'?'Hoàn tất':entry.status==='partial'?'Cần kiểm tra':entry.status==='cancelling'?'Đang dừng':entry.status==='cancelled'?'Đã dừng':entry.status}</em>
                    <progress value={entryProgress} max={100}/>
                    <b>{entryProgress}%</b>
                  </button>;
                })}
              </div>}
              {!!finishedJobs.length && <section className="resize-finished-jobs" aria-label="Pack đã xong">
                <button type="button" className="resize-finished-toggle" onClick={()=>setShowFinished(value=>!value)}>
                  <span><CheckCircle2 size={16}/><strong>Đã xong</strong><b>{finishedJobs.length}</b></span>
                  <small>{showFinished ? 'Thu gọn' : 'Xem danh sách'}</small>
                </button>
                {showFinished && <div className="resize-finished-list">
                  {finishedJobs.map(entry=>{
                    const done=entry.items.filter(item=>item.status==='succeeded').length;
                    return <div key={entry.id} className={job?.id===entry.id?'selected':''}>
                      <button type="button" className="resize-finished-open" onClick={()=>{setViewingFinished(true);setJob(entry);}}>
                        <span><strong>{entry.options.theme||'Pack resize'}</strong><small>{new Date(entry.createdAt).toLocaleString('vi-VN')}</small></span>
                        <em className={entry.status}>{entry.status==='succeeded'?`${done}/${entry.items.length} file`:'Đã dừng'}</em>
                      </button>
                      <button
                        type="button"
                        className="resize-finished-delete"
                        aria-label={`Xoá pack ${entry.options.theme||'resize'}`}
                        title={session && session.version < MIN_HELPER_VERSION ? 'Cập nhật Helper để xoá pack' : 'Xoá khỏi lịch sử và xoá file local'}
                        disabled={deletingJob===entry.id || !session || session.version < MIN_HELPER_VERSION}
                        onClick={()=>void deleteFinishedJob(entry)}
                      >
                        {deletingJob===entry.id?<LoaderCircle className="spin" size={14}/>:<Trash2 size={14}/>}<span>Xoá</span>
                      </button>
                    </div>;
                  })}
                </div>}
              </section>}
              {job && (
                <>
                  <div className="resize-selected-job-heading"><span><strong>{job.options.theme}</strong><small>{completed}/{job.items.length} file đã lưu trên máy</small></span><b>{progress}%</b></div>
                  <div className="resize-job-progress">
                    <div style={{ width: progress + '%' }} />
                  </div>
                  {job.items.some(item => item.driveStatus === 'failed') && (
                    <button
                      type="button"
                      className="resize-drive-retry-button"
                      disabled={!session || session.version < MIN_HELPER_VERSION || !!retryingDriveJob}
                      onClick={() => void retryDriveUpload(job)}
                    >
                      {retryingDriveJob === job.id
                        ? <LoaderCircle className="spin" size={16}/>
                        : <CloudUpload size={17}/>} {retryingDriveJob === job.id
                          ? 'Đang thử upload lại…'
                          : `Thử upload lại ${job.items.filter(item => item.driveStatus === 'failed').length} file lỗi`}
                    </button>
                  )}
                  <div className="resize-result-grid">
                    {job.items.map((item) => (
                      <article key={item.id} className="resize-result-card">
                        <button
                          className="resize-result-preview"
                          disabled={item.status !== 'succeeded'}
                          onClick={() => void openOutput(item)}
                        >
                          {item.path && session ? (
                            <ResultImage
                              job={job.id}
                              item={item}
                              token={session.token}
                            />
                          ) : item.status === 'running' ? (
                            <LoaderCircle className="spin" size={26} />
                          ) : (
                            <Video size={26} />
                          )}
                          <span>
                            {EXPORT_SIZES.find((s) => s.id === item.size)
                              ?.label || 'Original'}
                          </span>
                        </button>
                        <div className="resize-result-info">
                          <strong title={fileName(item.path || item.name)}>{fileName(item.path || item.name)}</strong>
                          <small>
                            {item.status === 'running'
                              ? `Rendering · ${item.progress}%`
                              : item.status === 'succeeded'
                                ? `${sizeLabel(item.bytes)} · Saved locally`
                                : item.status}
                          </small>
                          {item.error && <p role="alert">{friendlyDriveError(item.error)}</p>}
                          {item.driveStatus === 'uploading' && (
                            <small className="resize-drive-uploading">
                              <LoaderCircle className="spin" size={12} /> Đang upload Drive · tự thử lại nếu bị giới hạn
                            </small>
                          )}
                          {item.driveStatus === 'copied' && (
                            <small className="resize-copied">
                              <CheckCircle2 size={12} /> Copied to Drive folder
                            </small>
                          )}
                          <button
                            disabled={item.status !== 'succeeded'}
                            onClick={() => void openOutput(item, true)}
                          >
                            <ArrowDownToLine size={14} /> Download
                          </button>
                        </div>
                      </article>
                    ))}
                  </div>
                  <p className="resize-output-path">
                    <FolderOpen size={15} />
                    {job.outputFolder}
                  </p>
                </>
              )}
              {!job && (
                <div className={'resize-empty-queue ' + (finishedJobs.length ? 'compact' : '')}>
                  <FolderOpen size={42} />
                  <p>{finishedJobs.length ? 'Chọn một pack trong Đã xong để xem lại file.' : 'Chưa có pack resize.'}</p>
                  {!finishedJobs.length && <button onClick={() => setTab('setup')}>Chọn video</button>}
                </div>
              )}
            </section>
          )}
          {tab === 'setup' && setupStep === 3 && <div className="resize-output-destination">
            <FolderOpen size={20} />
            <label><strong>Thư mục lưu trên máy</strong>
              <input aria-label="Output folder" value={folderDraft} readOnly={!!nativeFolders}
                placeholder="Chọn thư mục trên máy" onChange={e => setFolderDraft(e.target.value)} />
              <small>Mỗi pack được tạo trong một thư mục con riêng.</small>
            </label>
            <button type="button" disabled={!session || transferring || choosingFolder} onClick={() => void changeOutputFolder()}>
              <FolderOpen size={16} /> {choosingFolder ? 'Đang chọn…' : nativeFolders ? 'Chọn thư mục' : 'Lưu thư mục'}
            </button>
          </div>}
          <footer className="resize-footer">
            <div>
              <FolderOpen size={17} />
              <span>
                <strong>
                  {tab === 'setup'
                    ? `${chosen.length} video → ${outputCount} file đầu ra`
                    : job
                      ? `${completed} file đã lưu`
                      : queueJobs.length
                        ? `${queueJobs.length} pack trong hàng chờ`
                        : `${finishedJobs.length} pack đã xong`}
                </strong>
                <small>
                  {transferring
                    ? transferStatus
                    : tab === 'results'
                      ? job?.outputFolder || (queueJobs.length
                        ? 'Helper đang xử lý tuần tự trên máy.'
                        : 'Hàng chờ trống. Mở Đã xong để xem lại file.')
                      : session?.outputFolder || setupBlocker || 'Sẵn sàng chạy theo thứ tự: đặt tên → resize → Drive.'}
                </small>
              </span>
            </div>
            {tab === 'setup' && setupStep < 3 ? (
              <button className="resize-start" disabled={setupStep===1 ? !chosen.length : !driveReady} onClick={()=>setSetupStep(setupStep===1?2:3)}>
                {setupStep===1 ? 'Tiếp · Chọn ứng dụng' : 'Tiếp · Thiết lập tên & resize'}
              </button>
            ) : transferring ? (
              <button
                className="resize-cancel"
                disabled={!transferAbort.current}
                onClick={() => transferAbort.current?.abort()}
              >
                <Square size={15} /> Cancel preparation
              </button>
            ) : tab === 'results' && exportBusy(job) ? (
              <button
                className="resize-cancel"
                disabled={job?.status === 'cancelling'}
                onClick={() => void cancel()}
              >
                <Square size={15} />
                {job?.status === 'cancelling' ? 'Cancelling…' : 'Cancel export'}
              </button>
            ) : tab === 'results' ? (
              <button className="resize-start" onClick={()=>{setTab('setup');setSetupStep(1);}}>
                <Plus size={17}/> Thiết lập pack tiếp theo
              </button>
            ) : (
              <button
                className="resize-start"
                disabled={!setupReady || transferring}
                onClick={() => void start()}
              >
                {transferring ? (
                  <LoaderCircle className="spin" size={17} />
                ) : (
                  <ArrowDownToLine size={17} />
                )}{' '}
                {transferring
                  ? 'Đang chuẩn bị file…'
                  : `Đặt tên & Resize ${outputCount || ''} file${sync ? ' → Drive' : ''}`}
              </button>
            )}
          </footer>
        </DialogContent>
      </Dialog>
      <Dialog
        open={!!preview}
        onOpenChange={(v) => {
          if (!v) setPreview(null);
        }}
      >
        <DialogContent className="resize-output-modal">
          <DialogTitle>{preview?.name}</DialogTitle>
          <DialogDescription>Local export preview</DialogDescription>
          {preview &&
            (/\.(png|jpe?g|webp)$/i.test(preview.name) ? (
              <img src={preview.url} alt={preview.name} />
            ) : (
              <video src={preview.url} controls autoPlay playsInline />
            ))}
        </DialogContent>
      </Dialog>
    </>
  );
}
