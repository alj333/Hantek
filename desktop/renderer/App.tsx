import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
  Activity as ActivityIcon, ArrowDownToLine, ArrowRight, Camera, Check,
  ChevronDown, Clock3, Folder, FolderOpen, Images, Info, LayoutDashboard,
  LoaderCircle, Monitor, Play, Plug, RefreshCw, Search, Settings2,
  ShieldCheck, Square, Unplug, Usb, X,
} from 'lucide-react';
import type { AppState, Capture, ScopeMode, Settings } from '../shared/contracts';

type View = 'workspace' | 'captures' | 'settings';
type Notice = { kind: 'success' | 'info' | 'error'; message: string };

const EMPTY_STATE: AppState = {
  appVersion: '', settings: { mode: 'hardware', storageDir: '', refreshIntervalMs: 5000, interfaceGuid: '' },
  connected: false, busy: false, device: null, captures: [], activity: [],
};
const dateTime = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Time unavailable' : date.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
};
const clockTime = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleTimeString(undefined, {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
};
const errorMessage = (error: unknown) => error instanceof Error ? error.message : String(error);
const captureTitle = (capture: Capture) => capture.label.trim() || `Capture · ${dateTime(capture.createdAt)}`;

function SourceBadge({ source }: { source: ScopeMode }) {
  return <span className={`source-badge ${source}`}><span />{source === 'demo' ? 'DEMO' : 'HARDWARE'}</span>;
}

function Graticule() {
  return <svg className="empty-graticule" viewBox="0 0 800 480" aria-hidden="true">
    <defs>
      <pattern id="minor-grid" width="20" height="20" patternUnits="userSpaceOnUse">
        <path d="M 20 0 L 0 0 0 20" fill="none" stroke="currentColor" strokeWidth="0.5" />
      </pattern>
      <pattern id="major-grid" width="80" height="80" patternUnits="userSpaceOnUse">
        <rect width="80" height="80" fill="url(#minor-grid)" />
        <path d="M 80 0 L 0 0 0 80" fill="none" stroke="currentColor" strokeWidth="0.8" />
      </pattern>
      <radialGradient id="grid-shade"><stop offset="0%" stopColor="#111e25" stopOpacity=".97" /><stop offset="100%" stopColor="#111e25" stopOpacity="0" /></radialGradient>
    </defs>
    <rect width="800" height="480" fill="url(#major-grid)" />
    <path d="M 400 0 V 480 M 0 240 H 800" stroke="currentColor" strokeDasharray="2 7" />
    <rect width="800" height="480" fill="url(#grid-shade)" />
  </svg>;
}

function Screen({ capture, connected, mode, now, interval }: {
  capture: Capture | null; connected: boolean; mode: ScopeMode; now: number; interval: number;
}) {
  const stage = useRef<HTMLDivElement>(null);
  const [stageHeight, setStageHeight] = useState<number>();
  const fitToViewport = useCallback(() => {
    const element = stage.current;
    if (!element) return;
    const top = element.getBoundingClientRect().top + window.scrollY;
    const footerHeight = element.nextElementSibling?.getBoundingClientRect().height ?? 36;
    const noteHeight = element.parentElement?.nextElementSibling?.getBoundingClientRect().height ?? 55;
    const available = window.innerHeight - top - footerHeight - noteHeight - 18;
    const height = Math.floor(Math.min(element.clientWidth * 480 / 800, Math.max(160, available)));
    setStageHeight((previous) => previous !== undefined && Math.abs(previous - height) < 2 ? previous : height);
  }, []);
  // Notices and toolbar wrapping can move the screen without a window resize.
  useLayoutEffect(() => { fitToViewport(); });
  useEffect(() => {
    window.addEventListener('resize', fitToViewport);
    const observer = new ResizeObserver(fitToViewport);
    if (stage.current?.parentElement) observer.observe(stage.current.parentElement);
    return () => { window.removeEventListener('resize', fitToViewport); observer.disconnect(); };
  }, [fitToViewport]);
  const age = capture ? Math.max(0, now - new Date(capture.createdAt).getTime()) : 0;
  const stale = Boolean(capture && (!connected || age > Math.max(15000, interval * 2)));
  return <div className="screen-shell">
    <div className="screen-heading">
      <span className="screen-heading-label"><span className={`screen-led ${capture && !stale ? 'ready' : ''}`} />
        {capture ? capture.saved ? 'SAVED CAPTURE' : stale ? 'STALE PREVIEW' : 'SCREEN PREVIEW' : 'SCREEN PREVIEW'}</span>
      <div className="screen-heading-right"><SourceBadge source={capture?.source ?? mode} />
        <span>{capture ? clockTime(capture.createdAt) : '800 × 480'}</span></div>
    </div>
    <div className="scope-screen" ref={stage} style={stageHeight === undefined ? undefined : { height: stageHeight }}>
      {capture ? <img src={capture.imageUrl} alt={`${capture.source === 'demo' ? 'Demo ' : ''}oscilloscope screen captured ${dateTime(capture.createdAt)}`} /> : <>
        <Graticule />
        <div className="screen-empty">
          <span className="screen-empty-icon"><Monitor size={30} strokeWidth={1.25} /></span>
          <h2>{connected ? 'Ready for your first capture' : mode === 'demo' ? 'A place to explore' : 'Your instrument, in view'}</h2>
          <p>{connected ? 'Capture the screen to bring it into your workspace.' : mode === 'demo' ? 'Connect to the demo to explore simulated screen captures.' : 'Connect your DSO5102P to start capturing its screen.'}</p>
          <span className="screen-empty-caption">{mode === 'demo' ? 'SIMULATED IMAGES · NO HARDWARE ACCESS' : 'LOCAL USB CONNECTION'}</span>
        </div>
      </>}
    </div>
    <div className="screen-footer">
      <span><Clock3 size={13} />{capture ? `${capture.saved ? 'Saved' : 'Preview'} ${dateTime(capture.createdAt)}${stale ? ' · historical view' : ''}` : 'No capture yet'}</span>
      <span>{capture?.source === 'demo' ? 'Simulated screen' : capture?.checksumVerified ? <><ShieldCheck size={13} />Checksums verified</> : 'Screen images · not waveform samples'}</span>
    </div>
  </div>;
}

export default function App() {
  const [state, setState] = useState<AppState>(EMPTY_STATE);
  const [loaded, setLoaded] = useState(false);
  const [view, setView] = useState<View>('workspace');
  const [operation, setOperation] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [search, setSearch] = useState('');
  const [sourceFilter, setSourceFilter] = useState<'all' | ScopeMode>('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [preview, setPreview] = useState<Capture | null>(null);
  const [label, setLabel] = useState('');
  const [notes, setNotes] = useState('');
  const [guid, setGuid] = useState('');
  const [advanced, setAdvanced] = useState(false);
  const mounted = useRef(true);
  const operationLock = useRef(false);
  const stateRef = useRef(state);
  const refreshGeneration = useRef(0);

  const ingest = useCallback((next: AppState) => {
    const previous = stateRef.current;
    const settingsChanged = previous.settings.mode !== next.settings.mode ||
      previous.settings.storageDir !== next.settings.storageDir ||
      previous.settings.interfaceGuid !== next.settings.interfaceGuid ||
      previous.settings.refreshIntervalMs !== next.settings.refreshIntervalMs;
    if (settingsChanged || !next.connected) {
      refreshGeneration.current += 1;
      if (mounted.current) setAutoRefresh(false);
    }
    if (mounted.current && (previous.settings.mode !== next.settings.mode ||
      previous.settings.storageDir !== next.settings.storageDir ||
      previous.settings.interfaceGuid !== next.settings.interfaceGuid)) setPreview(null);
    stateRef.current = next;
    if (mounted.current) setState(next);
  }, []);
  const stopRefresh = useCallback(() => {
    refreshGeneration.current += 1;
    if (mounted.current) setAutoRefresh(false);
  }, []);
  const showNotice = useCallback((kind: Notice['kind'], message: string) => {
    if (mounted.current) setNotice({ kind, message });
  }, []);

  useEffect(() => {
    mounted.current = true;
    let cancelled = false;
    const api = window.scopeApp;
    if (!api) {
      setNotice({ kind: 'error', message: 'The desktop connection is unavailable. Open Hantek Studio as a desktop application.' });
      return () => { mounted.current = false; };
    }
    const unsubscribe = api.onStateChanged((next) => { if (!cancelled) ingest(next); });
    void api.getState().then((next) => {
      if (!cancelled) { ingest(next); setLoaded(true); }
    }).catch((error: unknown) => { if (!cancelled) showNotice('error', errorMessage(error)); });
    return () => { cancelled = true; mounted.current = false; refreshGeneration.current += 1; unsubscribe(); };
  }, [ingest, showNotice]);

  useEffect(() => { setGuid(state.settings.interfaceGuid); }, [state.settings.interfaceGuid]);
  useLayoutEffect(() => { window.scrollTo(0, 0); }, [view]);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const withOperation = useCallback(async <T,>(name: string, task: () => Promise<T>): Promise<T | undefined> => {
    if (!mounted.current || operationLock.current || stateRef.current.busy || !window.scopeApp) return undefined;
    operationLock.current = true;
    if (mounted.current) setOperation(name);
    try {
      const result = await task();
      if (mounted.current) ingest(await window.scopeApp.getState());
      return result;
    } catch (error) {
      stopRefresh();
      showNotice('error', errorMessage(error));
      return undefined;
    } finally {
      operationLock.current = false;
      if (mounted.current) setOperation(null);
    }
  }, [ingest, showNotice, stopRefresh]);

  const takeCapture = useCallback(async (save = true) => {
    const result = await withOperation(save ? 'Saving screen capture' : 'Refreshing preview',
      () => save ? window.scopeApp.capture() : window.scopeApp.capture({ save: false }));
    if (result && mounted.current) setPreview(result);
    return result;
  }, [withOperation]);

  useEffect(() => {
    if (!autoRefresh || view !== 'workspace' || !state.connected) return;
    const generation = ++refreshGeneration.current;
    let timer: number | undefined;
    let cancelled = false;
    const interval = Math.max(3000, state.settings.refreshIntervalMs);
    const tick = async () => {
      if (cancelled || generation !== refreshGeneration.current || !mounted.current || !stateRef.current.connected) return;
      await takeCapture(false);
      if (!cancelled && generation === refreshGeneration.current && mounted.current) timer = window.setTimeout(() => { void tick(); }, interval);
    };
    timer = window.setTimeout(() => { void tick(); }, interval);
    return () => { cancelled = true; refreshGeneration.current += 1; if (timer !== undefined) window.clearTimeout(timer); };
  }, [autoRefresh, view, state.connected, state.settings.mode, state.settings.refreshIntervalMs,
    state.settings.interfaceGuid, state.settings.storageDir, takeCapture]);

  useEffect(() => { if (!state.connected) stopRefresh(); }, [state.connected, stopRefresh]);

  const sortedCaptures = useMemo(() => [...state.captures].sort((a, b) => b.createdAt.localeCompare(a.createdAt)), [state.captures]);
  const latest = preview?.source === state.settings.mode ? preview : sortedCaptures.find((capture) => capture.source === state.settings.mode) ?? null;
  const selected = sortedCaptures.find((capture) => capture.id === selectedId) ?? null;
  const filteredCaptures = sortedCaptures.filter((capture) =>
    (sourceFilter === 'all' || capture.source === sourceFilter) &&
    `${capture.label} ${capture.notes} ${dateTime(capture.createdAt)}`.toLowerCase().includes(search.toLowerCase()));
  const recentActivity = [...state.activity].sort((a, b) => b.at.localeCompare(a.at)).slice(0, 5);
  const busy = Boolean(operation || state.busy);
  const ready = loaded && !busy;
  const captureReady = ready && state.connected;
  const demo = state.settings.mode === 'demo';

  useEffect(() => {
    setLabel(selected?.label ?? ''); setNotes(selected?.notes ?? '');
  }, [selected?.id, selected?.label, selected?.notes]);

  const navigate = (next: View) => { stopRefresh(); setView(next); setNotice(null); };
  const connect = async () => {
    stopRefresh();
    const result = await withOperation('Connecting', () => window.scopeApp.connect());
    if (result) {
      showNotice('success', result.settings.mode === 'demo' ? 'Demo connected. Captures are simulated.' : 'Scope connected. Ready to capture its screen.');
      if (result.connected) await takeCapture(false);
    }
  };
  const disconnect = async () => {
    stopRefresh();
    const result = await withOperation('Disconnecting', () => window.scopeApp.disconnect());
    if (result) showNotice('info', 'Disconnected. Saved captures remain in your library.');
  };
  const acquisition = async (action: 'start' | 'stop') => {
    stopRefresh();
    const result = await withOperation(action === 'start' ? 'Sending Run request' : 'Sending Stop request', () => window.scopeApp.setAcquisition(action));
    if (result) {
      if (result.capture && mounted.current) setPreview(result.capture);
      showNotice('info', result.message);
    }
  };
  const saveSettings = async (patch: Partial<Pick<Settings, 'mode' | 'refreshIntervalMs' | 'interfaceGuid'>>) => {
    stopRefresh();
    const result = await withOperation('Saving settings', () => window.scopeApp.updateSettings(patch));
    if (result) showNotice('success', 'Settings saved.');
  };
  const chooseStorage = async () => {
    stopRefresh();
    await withOperation('Choosing storage', () => window.scopeApp.chooseStorageDirectory());
  };
  const checkConnection = async () => {
    stopRefresh();
    const result = await withOperation('Testing connection', () => window.scopeApp.checkConnection());
    if (result) showNotice('info', result.message);
  };
  const exportCapture = async (capture: Capture) => {
    const result = await withOperation('Exporting capture', () => window.scopeApp.exportCapture(capture.id));
    if (result && !result.cancelled) showNotice('success', 'PNG exported.');
  };
  const revealCapture = async (capture: Capture) => {
    await withOperation('Opening capture folder', () => window.scopeApp.revealCapture(capture.id));
  };
  const saveDetails = async () => {
    if (!selected) return;
    const result = await withOperation('Saving capture details', () => window.scopeApp.updateCapture({ id: selected.id, label, notes }));
    if (result) showNotice('success', 'Capture details saved.');
  };
  const openLibrary = (id?: string) => {
    stopRefresh(); setSelectedId(id ?? null); setView('captures'); setNotice(null);
  };

  return <div className="app-layout">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark"><ActivityIcon size={26} strokeWidth={1.8} /></span>
        <div><strong>Hantek<span>Studio</span></strong><small>THE CONNECTED BENCH</small></div></div>
      <div className="nav-heading">YOUR INSTRUMENT</div>
      <nav aria-label="Main navigation">
        <button className={`nav-item ${view === 'workspace' ? 'active' : ''}`} onClick={() => navigate('workspace')} aria-current={view === 'workspace' ? 'page' : undefined}><LayoutDashboard size={18} />Workspace<span className="nav-current-dot" /></button>
        <button className={`nav-item ${view === 'captures' ? 'active' : ''}`} onClick={() => navigate('captures')} aria-current={view === 'captures' ? 'page' : undefined}><Images size={18} />Captures<span className="nav-count">{state.captures.length}</span></button>
        <button className={`nav-item ${view === 'settings' ? 'active' : ''}`} onClick={() => navigate('settings')} aria-current={view === 'settings' ? 'page' : undefined}><Settings2 size={18} />Settings</button>
      </nav>
      <div className="sidebar-spacer" />
      <div className="connection-card">
        <div className="connection-card-icon"><Usb size={20} /><span className={`status-dot ${state.connected ? 'connected' : ''}`} /></div>
        <div className="connection-card-title">{demo ? 'Demo instrument' : state.device?.model ?? 'DSO5102P'}<SourceBadge source={state.settings.mode} /></div>
        <p>{!loaded ? 'Waiting for the desktop app' : state.connected ? demo ? 'Simulated session connected' : 'Connected through USB' : 'Instrument disconnected'}</p>
        <button className={`button connection-button ${state.connected ? 'secondary' : 'primary'}`} disabled={!ready} onClick={() => { void (state.connected ? disconnect() : connect()); }}>
          {operation === 'Connecting' ? <LoaderCircle size={15} className="spin" /> : state.connected ? <Unplug size={15} /> : <Plug size={15} />}
          {state.connected ? 'Disconnect' : demo ? 'Connect demo' : 'Connect scope'}
        </button>
      </div>
      <div className="sidebar-footer"><span className="local-dot" />Local workspace<span>{state.appVersion ? `v${state.appVersion}` : ''}</span></div>
    </aside>

    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb">Your bench<span>/</span><strong>{view === 'workspace' ? 'Workspace' : view === 'captures' ? 'Captures' : 'Settings'}</strong></div>
        <div className="topbar-right">{busy && <span className="operation-indicator" role="status"><LoaderCircle size={13} className="spin" />{operation ?? 'Working'}</span>}<span className="local-only"><ShieldCheck size={13} />Stored locally</span><SourceBadge source={state.settings.mode} /></div>
      </header>
      <main className={`main-content view-${view}`}>
        {notice && <div className={`notice ${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'}><span>{notice.kind === 'success' ? <Check size={17} /> : <Info size={17} />}</span><p>{notice.message}</p><button aria-label="Dismiss message" className="icon-button" onClick={() => setNotice(null)}><X size={16} /></button></div>}
        {demo && <div className="demo-ribbon"><span className="demo-ribbon-dot" />Demo workspace<span>Simulated screens. Your scope is not accessed.</span></div>}

        {view === 'workspace' && <>
          <div className="page-heading workspace-heading"><div><h1>Scope workspace</h1></div><button className="button secondary" onClick={() => openLibrary()}><Images size={16} />Capture library<ArrowRight size={14} /></button></div>
          <div className="workspace-grid">
            <section className="instrument-panel" aria-label="Oscilloscope workspace">
              <div className="instrument-heading"><div className="instrument-icon"><Monitor size={22} strokeWidth={1.5} /></div><div><h2>{demo ? 'Demo oscilloscope' : state.device?.model ?? 'Hantek DSO5102P'}</h2><p>{demo ? 'Simulated instrument preview' : 'Digital storage oscilloscope'}</p></div><span className={`connection-pill ${state.connected ? 'connected' : ''}`}><span />{state.connected ? 'Connected' : 'Disconnected'}</span></div>
              <div className="instrument-toolbar"><div className="toolbar-actions"><button className="button primary" disabled={!captureReady} onClick={() => { void takeCapture(); }}><Camera size={16} />Save capture</button><div className="acquisition-buttons"><button className="button quiet" disabled={!captureReady} onClick={() => { void acquisition('start'); }} title="Request that the oscilloscope resume acquisition"><Play size={14} />Run</button><button className="button quiet" disabled={!captureReady} onClick={() => { void acquisition('stop'); }} title="Request that the oscilloscope stop acquisition"><Square size={13} />Stop</button></div></div>
                <label className="auto-refresh-control"><input type="checkbox" role="switch" checked={autoRefresh} disabled={!state.connected || !loaded || (busy && !autoRefresh)} onChange={(event) => { if (event.target.checked) setAutoRefresh(true); else stopRefresh(); }} /><span className="switch-track"><span /></span><span>Auto-refresh<small>Every {Math.max(3000, state.settings.refreshIntervalMs) / 1000}s</small></span></label>
              </div>
              <Screen capture={latest} connected={state.connected} mode={state.settings.mode} now={now} interval={state.settings.refreshIntervalMs} />
              <div className="instrument-footnote"><Info size={14} /><span>Run and Stop request a change to scope acquisition. Verify the resulting indicator on the captured screen.</span>{latest && (latest.saved ? <button className="text-button" onClick={() => openLibrary(latest.id)}>View capture<ArrowRight size={13} /></button> : <div className="preview-actions"><button className="text-button" disabled={!ready} onClick={() => { void exportCapture(latest); }}>Export preview<ArrowDownToLine size={13} /></button><button className="icon-button" disabled={!ready} aria-label="Show preview in folder" onClick={() => { void revealCapture(latest); }}><FolderOpen size={13} /></button></div>)}</div>
            </section>
            <aside className="workspace-aside">
              <section className="card session-card"><div className="card-heading"><h2>Session overview</h2><span className="tiny-label">THIS WORKSPACE</span></div>
                <div className="session-row"><span>Connection</span><strong>{state.connected ? demo ? 'Demo session' : 'USB · WinUSB' : 'Not connected'}</strong></div>
                <div className="session-row"><span>Last capture</span><strong>{latest ? clockTime(latest.createdAt) : '—'}</strong></div>
                <div className="session-row"><span>Screen size</span><strong>{latest ? `${latest.width} × ${latest.height}` : '800 × 480'}</strong></div>
                <div className="session-row"><span>Saved captures</span><strong>{state.captures.length.toString().padStart(2, '0')}</strong></div>
                <div className="storage-summary"><Folder size={17} /><div><span>CAPTURE STORAGE</span><p title={state.settings.storageDir}>{state.settings.storageDir || 'Loading storage location…'}</p></div><button className="icon-button" aria-label="Open storage folder" disabled={!ready || !state.settings.storageDir} onClick={() => { void withOperation('Opening storage', () => window.scopeApp.openStorage()); }}><ArrowRight size={15} /></button></div>
              </section>
              <section className="capture-tip"><span className="tip-icon"><Images size={21} /></span><p className="eyebrow">A RECORD OF YOUR BENCH</p><h3>Keep the useful moments.</h3><p>Save a screen, add a note, and return to it when you need the context.</p><button className="text-button" onClick={() => openLibrary()}>Explore your captures<ArrowRight size={14} /></button><div className="tip-decoration" aria-hidden="true"><span /><span /><span /><span /><span /><span /><span /></div></section>
            </aside>
          </div>
          <section className="card activity-card"><div className="card-heading"><h2><ActivityIcon size={16} />Recent activity</h2><span className="tiny-label">{recentActivity.length ? 'LATEST FIRST' : 'SESSION LOG'}</span></div>
            {recentActivity.length ? <ul className="activity-list">{recentActivity.map((entry) => <li key={entry.id}><span className={`activity-symbol ${entry.kind}`}>{entry.kind === 'success' ? <Check size={13} /> : <Info size={13} />}</span><p>{entry.message}</p><time dateTime={entry.at}>{clockTime(entry.at)}</time></li>)}</ul> : <div className="activity-empty"><Clock3 size={17} /><p>Your connection checks and captures will appear here.</p></div>}
          </section>
        </>}

        {view === 'captures' && <>
          <div className="page-heading"><div><p className="eyebrow">YOUR VISUAL NOTEBOOK</p><h1>Capture library<span className="heading-count">{state.captures.length}</span></h1><p>Saved screens, with the context that makes them useful.</p></div><button className="button secondary" disabled={!ready} onClick={() => { void withOperation('Refreshing library', () => window.scopeApp.listCaptures()); }}><RefreshCw size={15} />Refresh library</button></div>
          <div className="library-tools"><label className="search-box"><Search size={17} /><input aria-label="Search captures" placeholder="Search captures or notes…" value={search} onChange={(event) => setSearch(event.target.value)} />{search && <button className="icon-button" aria-label="Clear capture search" onClick={() => setSearch('')}><X size={14} /></button>}</label><div className="filter-tabs" role="group" aria-label="Filter capture source">{(['all', 'hardware', 'demo'] as const).map((source) => <button key={source} aria-pressed={sourceFilter === source} className={sourceFilter === source ? 'selected' : ''} onClick={() => setSourceFilter(source)}>{source === 'all' ? 'All captures' : source === 'demo' ? 'Demo' : 'Hardware'}</button>)}</div><span className="sort-label">Newest first<ChevronDown size={13} /></span></div>
          <div className={`library-layout ${selected ? 'with-selection' : ''}`}>
            <section className="capture-grid" aria-label="Saved captures">
              {filteredCaptures.length ? filteredCaptures.map((capture) => <button key={capture.id} className={`capture-card ${selectedId === capture.id ? 'selected' : ''}`} onClick={() => setSelectedId(capture.id)} aria-pressed={selectedId === capture.id}><div className="capture-thumbnail"><img src={capture.imageUrl} alt={`${capture.source === 'demo' ? 'Demo ' : ''}${captureTitle(capture)}`} loading="lazy" /><SourceBadge source={capture.source} />{selectedId === capture.id && <span className="capture-selected-check"><Check size={14} /></span>}</div><div className="capture-card-description"><h3>{captureTitle(capture)}</h3><div><time dateTime={capture.createdAt}>{dateTime(capture.createdAt)}</time><span>PNG</span></div>{capture.notes && <p>{capture.notes}</p>}</div></button>) : <div className="library-empty"><span><Images size={33} strokeWidth={1.3} /></span><h2>{search || sourceFilter !== 'all' ? 'No matching captures' : 'Your first capture belongs here'}</h2><p>{search || sourceFilter !== 'all' ? 'Try another search or choose a different source.' : 'Connect an instrument and save a screen from your workspace.'}</p><button className="button secondary" onClick={() => { if (search || sourceFilter !== 'all') { setSearch(''); setSourceFilter('all'); } else navigate('workspace'); }}>{search || sourceFilter !== 'all' ? 'Clear filters' : 'Go to workspace'}<ArrowRight size={14} /></button></div>}
            </section>
            {selected && <aside className="capture-detail card" aria-label="Capture details"><div className="card-heading"><h2>Capture details</h2><button className="icon-button" aria-label="Close capture details" onClick={() => setSelectedId(null)}><X size={16} /></button></div><div className="detail-image"><img src={selected.imageUrl} alt={`Selected ${selected.source} capture`} /><SourceBadge source={selected.source} /></div><div className="detail-form"><label>Capture name<input value={label} maxLength={120} onChange={(event) => setLabel(event.target.value)} placeholder="Give this capture a name" /></label><label>Notes<textarea rows={5} value={notes} maxLength={8000} onChange={(event) => setNotes(event.target.value)} placeholder="What were you looking at? Add the context you want to keep." /></label><button className="button primary" disabled={!ready || (label === selected.label && notes === selected.notes)} onClick={() => { void saveDetails(); }}><Check size={15} />Save details</button></div><dl className="capture-facts"><div><dt>Captured</dt><dd>{dateTime(selected.createdAt)}</dd></div><div><dt>Dimensions</dt><dd>{selected.width} × {selected.height}</dd></div><div><dt>Source</dt><dd>{selected.source === 'demo' ? 'Simulated demo' : 'USB instrument'}</dd></div><div><dt>Integrity</dt><dd>{selected.source === 'demo' ? 'Demo image' : selected.checksumVerified ? 'Checksums verified' : 'Not verified'}</dd></div></dl><div className="detail-actions"><button className="button secondary" disabled={!ready} onClick={() => { void exportCapture(selected); }}><ArrowDownToLine size={15} />Export PNG</button><button className="button quiet" disabled={!ready} onClick={() => { void revealCapture(selected); }}><FolderOpen size={15} />Show in folder</button></div></aside>}
          </div>
        </>}

        {view === 'settings' && <>
          <div className="page-heading"><div><p className="eyebrow">MAKE ROOM FOR YOUR WORK</p><h1>Workspace settings</h1><p>Your instrument connection and where your captures live.</p></div></div>
          <div className="settings-layout"><div className="settings-sections">
            <section className="card settings-card"><div className="settings-section-heading"><span><Usb size={20} /></span><div><h2>Instrument connection</h2><p>Choose how you want to use this workspace.</p></div></div><div className="mode-options" role="group" aria-label="Instrument mode"><button className={`mode-option ${!demo ? 'selected' : ''}`} disabled={!ready} onClick={() => { if (demo) void saveSettings({ mode: 'hardware' }); }} aria-pressed={!demo}><span className="mode-option-top"><Usb size={20} /><span className="radio-indicator">{!demo && <span />}</span></span><strong>USB instrument</strong><span>Connect your Hantek DSO5102P.</span></button><button className={`mode-option ${demo ? 'selected' : ''}`} disabled={!ready} onClick={() => { if (!demo) void saveSettings({ mode: 'demo' }); }} aria-pressed={demo}><span className="mode-option-top"><Monitor size={20} /><span className="radio-indicator">{demo && <span />}</span></span><strong>Demo workspace<SourceBadge source="demo" /></strong><span>Explore with simulated screen images.</span></button></div><div className="settings-inline-note"><Info size={15} /><p>{demo ? 'Demo mode does not access a USB instrument. All generated captures are marked as demo.' : 'Use the rear USB-B connection on your powered scope. The configured WinUSB driver is used locally.'}</p></div><div className="connection-test-row"><span><span className={`status-dot ${state.connected ? 'connected' : ''}`} />{state.connected ? demo ? 'Demo connected' : 'Instrument connected' : 'Not connected'}</span><button className="button secondary" disabled={!captureReady} onClick={() => { void checkConnection(); }}><Plug size={15} />Test connection</button></div></section>
            <section className="card settings-card"><div className="settings-section-heading"><span><Folder size={20} /></span><div><h2>Capture storage</h2><p>Keep screen images and their supporting records together.</p></div></div><div className="folder-field"><FolderOpen size={19} /><p>{state.settings.storageDir || 'Storage location unavailable'}</p><button className="button secondary" disabled={!ready} onClick={() => { void chooseStorage(); }}>Choose folder</button></div><p className="field-help">New captures use this location. Export an individual PNG from the capture library when you want a copy elsewhere.</p></section>
            <section className="card settings-card"><div className="settings-section-heading"><span><RefreshCw size={20} /></span><div><h2>Screen refresh</h2><p>Set the pause between completed captures.</p></div></div><div className="refresh-setting-row"><div><label htmlFor="refresh-interval">Auto-refresh interval</label><p>Enable auto-refresh from the workspace when connected.</p></div><select id="refresh-interval" value={Math.max(3000, state.settings.refreshIntervalMs)} disabled={!ready} onChange={(event) => { void saveSettings({ refreshIntervalMs: Number(event.target.value) }); }}>{[3000, 5000, 10000, 15000, 30000, ...( ![3000, 5000, 10000, 15000, 30000, 60000].includes(Math.max(3000, state.settings.refreshIntervalMs)) ? [Math.max(3000, state.settings.refreshIntervalMs)] : [])].sort((a, b) => a - b).map((ms) => <option key={ms} value={ms}>Every {ms / 1000} seconds</option>)}</select></div><p className="field-help">Captures run one at a time. Auto-refresh stops when you leave the workspace, change settings, disconnect, or encounter an error.</p></section>
            <section className="card settings-card advanced-card"><button className="advanced-heading" aria-expanded={advanced} aria-controls="advanced-connection" onClick={() => setAdvanced(!advanced)}><span><Settings2 size={18} /><strong>Advanced connection</strong></span><ChevronDown size={17} className={advanced ? 'rotated' : ''} /></button>{advanced && <div id="advanced-connection" className="advanced-content"><p className="field-help">The interface identifier must match the existing WinUSB setup for your scope.</p><label className="field-label" htmlFor="interface-guid">Device interface GUID</label><div className="guid-field"><input id="interface-guid" value={guid} onChange={(event) => setGuid(event.target.value)} spellCheck={false} autoComplete="off" /><button className="button secondary" disabled={!ready || !guid.trim() || guid === state.settings.interfaceGuid} onClick={() => { void saveSettings({ interfaceGuid: guid.trim() }); }}>Save identifier</button></div></div>}</section>
          </div><aside className="settings-aside"><div className="settings-note"><ShieldCheck size={26} strokeWidth={1.5} /><h3>At home on your bench.</h3><p>Hantek Studio connects through local USB. Your captures stay in the folder you choose.</p><div /><p>Screen images preserve the displayed instrument view. They do not contain raw waveform samples.</p><span>HANTEK STUDIO{state.appVersion && ` · ${state.appVersion}`}</span></div></aside></div>
        </>}
        <footer className="content-footer"><span>HANTEK STUDIO</span><span>Your instrument. Your workspace.</span></footer>
      </main>
    </div>
  </div>;
}
