import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowDownToLine, ArrowLeft, ArrowRight, Box, Camera, Check, ChevronDown, CircleHelp, Expand, FolderOpen, ImagePlus, Layers, LoaderCircle, Maximize, MoreHorizontal, Pause, Play, Plus, RotateCcw, Search, Settings2, Trash2, Upload, Video, X } from 'lucide-react';
import Viewer, { type ViewerMethods } from './Viewer';
import EnvironmentStudio from './EnvironmentStudio';
import ObjectStudio from './ObjectStudio';
import { api, apiUrl, defaultSettings, formatSeconds, type Health, type Project, type Settings, type Capabilities } from './types';

function Mark() { return <svg viewBox="0 0 36 36" width="30" height="30" fill="none" aria-hidden="true"><path d="M5 5h21v21H5zM11 11h20v20H11" stroke="currentColor" strokeWidth="1.6" /></svg>; }
function IconButton({ label, children, onClick, disabled = false }: { label: string; children: React.ReactNode; onClick: () => void; disabled?: boolean }) { return <button className="icon-button" title={label} aria-label={label} onClick={onClick} disabled={disabled}>{children}</button>; }
function Slider({ label, value, min = 0, max = 1, step = 0.01, onChange, disabled, format }: { label: string; value: number; min?: number; max?: number; step?: number; onChange: (value: number) => void; disabled?: boolean; format?: (value: number) => string }) { return <label className="slider-field"><span>{label}<output>{format ? format(value) : `${Math.round(value * 100)}%`}</output></span><input type="range" aria-label={label} min={min} max={max} step={step} value={value} onChange={event => onChange(Number(event.target.value))} disabled={disabled} /></label>; }

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState(50);
  const [projectId, setProjectId] = useState<string | null>(() => localStorage.getItem('depthframe-project'));
  const [health, setHealth] = useState<Health | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [view, setView] = useState<'editor' | 'library' | 'studio' | 'object'>('editor');
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [revision, setRevision] = useState(0);
  const [mode, setMode] = useState('original');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [drawer, setDrawer] = useState(false);
  const [search, setSearch] = useState('');
  const [help, setHelp] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [recording, setRecording] = useState<number | null>(null);
  const [ready, setReady] = useState(false);
  const [fps, setFps] = useState(0);
  const [renameOpen, setRenameOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const controller = useRef<ViewerMethods | null>(null);
  const uploadInput = useRef<HTMLInputElement>(null);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const project = projects.find(item => item.id === projectId) || null;
  const hosted = health?.mode === 'streamlit-private-hosted';
  const panoramic = mode === 'panorama' && Boolean(project?.panorama);
  const processing = project?.job?.status === 'queued' || project?.job?.status === 'running';
  const dirty = project && JSON.stringify(settings) !== JSON.stringify(project.settings);
  const filtered = projects.filter(item => item.name.toLowerCase().includes(search.toLowerCase()));
  const showError = useCallback((message: string) => setError(message), []);
  const markReady = useCallback((value: boolean) => setReady(value), []);
  const takeCameraControl = useCallback(() => setSettings(previous => previous.autoOrbit ? { ...previous, autoOrbit: false } : previous), []);

  const refresh = useCallback(async () => {
    const [listing, state, caps] = await Promise.all([api<{ items: Project[]; total: number }>(`/projects?limit=${Math.min(limit, 100)}`), api<Health>('/health'), api<Capabilities>('/capabilities')]);
    for (let offset = 100; offset < Math.min(limit, listing.total); offset += 100) {
      const next = await api<{ items: Project[] }>(`/projects?offset=${offset}&limit=${Math.min(100, limit - offset)}`);
      listing.items.push(...next.items);
    }
    setProjects(listing.items); setTotal(listing.total); setHealth(state); setCapabilities(caps); setLoading(false);
    return listing.items;
  }, [limit]);

  useEffect(() => {
    let alive = true, timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try { await refresh(); } catch (exception) { if (alive) { setError((exception as Error).message.includes('fetch') ? 'Cannot reach the local service. Start DepthFrame and retry.' : (exception as Error).message); setLoading(false); } }
      if (alive) timer = setTimeout(tick, 1800);
    };
    tick(); return () => { alive = false; clearTimeout(timer); };
  }, [refresh]);

  useEffect(() => {
    if (project) { setSettings(project.settings); setRevision(project.revision); setMode(project.panorama ? 'panorama' : project.depth ? '3d' : 'original'); }
    setReady(false); setFps(0);
    if (projectId) localStorage.setItem('depthframe-project', projectId); else localStorage.removeItem('depthframe-project');
    // A poll must never overwrite unsaved edits. Load settings only on project selection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id]);
  useEffect(() => { if (project?.depth) setMode('3d'); }, [project?.depth?.job_id]);
  useEffect(() => { if (project?.panorama) setMode('panorama'); }, [project?.panorama?.job_id, project?.kind]);
  useEffect(() => { if (notice) { const timer = setTimeout(() => setNotice(''), 4500); return () => clearTimeout(timer); } }, [notice]);
  useEffect(() => {
    if (!help && !exportOpen && !renameOpen && !deleteOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]');
    const selector = 'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), [tabindex="0"]';
    dialog?.querySelector<HTMLElement>(selector)?.focus();
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setHelp(false); setExportOpen(false); setRenameOpen(false); setDeleteOpen(false); }
      if (event.key === 'Tab' && dialog) {
        const elements = [...dialog.querySelectorAll<HTMLElement>(selector)];
        const first = elements[0], last = elements[elements.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener('keydown', keyboard);
    return () => { document.removeEventListener('keydown', keyboard); previous?.focus(); };
  }, [help, exportOpen, renameOpen, deleteOpen]);

  function change<K extends keyof Settings>(key: K, value: Settings[K]) { setSettings(previous => ({ ...previous, [key]: value })); }
  async function run(action: () => Promise<void>) {
    setError(''); setBusy(true);
    try { await action(); } catch (exception) { setError((exception as Error).message); } finally { setBusy(false); }
  }
  async function generate(id: string) {
    await api(`/projects/${id}/depth-jobs`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ inference_size: 384 }) });
    await refresh();
  }
  async function upload(file?: File) {
    if (!file) return;
    if (file.size > 15 * 1024 * 1024) { setError('Photo exceeds the 15 MB limit.'); return; }
    if (dirty && !window.confirm('Discard the unsaved settings on this photo?')) return;
    await run(async () => {
      const form = new FormData(); form.append('file', file);
      const created = await api<Project>('/projects', { method: 'POST', body: form });
      setProjects(previous => [created, ...previous]); setProjectId(created.id); setView('editor'); setDrawer(false);
      if (health?.model_ready) await generate(created.id);
      else setNotice('Photo saved. Install the depth model to generate 3D.');
    });
  }
  async function loadExample() {
    if (dirty && !window.confirm('Discard the unsaved settings on this photo?')) return;
    await run(async () => {
      const created = await api<Project>('/examples', { method: 'POST' });
      setProjects(previous => [created, ...previous]); setProjectId(created.id); setView('editor'); setDrawer(false);
      await generate(created.id);
    });
  }
  async function save() {
    if (!project) return;
    setSaving(true); setError('');
    try {
      const saved = await api<Project>(`/projects/${project.id}/settings`, { method: 'PATCH', body: JSON.stringify({ ...settings, revision }) });
      setRevision(saved.revision); setProjects(previous => previous.map(item => item.id === saved.id ? saved : item)); setNotice('Project settings saved.');
    } catch (exception) { setError((exception as Error).message); } finally { setSaving(false); }
  }
  function select(item: Project) {
    if (dirty && !window.confirm('Discard the unsaved settings on this photo?')) return;
    setProjectId(item.id); setView(item.object ? 'object' : 'editor'); setDrawer(false); setError('');
  }
  async function exportAction(kind: 'png' | 'video' | 'glb') {
    if (!controller.current) { setError('Wait for the 3D photo to load.'); return; }
    setExportOpen(false); setError('');
    try {
      if (kind === 'video') { setRecording(0); await controller.current.video(setRecording); setNotice('Animation downloaded.'); }
      if (kind === 'png') { await controller.current.snapshot(); setNotice('Still image downloaded.'); }
      if (kind === 'glb') { await controller.current.glb(); setNotice('Depth mesh downloaded.'); }
    } catch (exception) { setError((exception as Error).message); } finally { setRecording(null); }
  }
  const statusLabel = processing ? project!.job!.stage : project?.job?.status === 'failed' ? 'Processing failed' : project?.depth ? 'Depth ready' : project ? 'Ready to generate' : 'Your local photo workspace';

  return <div className="app" data-theme="dark" onDragOver={event => { event.preventDefault(); if (recording === null) setDragging(true); }} onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false); }} onDrop={event => { event.preventDefault(); setDragging(false); if (!busy && recording === null) upload(event.dataTransfer.files[0]); }}>
    <input ref={uploadInput} className="visually-hidden" type="file" accept="image/jpeg,image/png,image/webp" aria-label="Upload photo" onChange={event => { upload(event.target.files?.[0]); event.target.value = ''; }} />
    <aside className={`sidebar ${drawer ? 'is-open' : ''}`}>
      <a className="brand" href="#" onClick={event => { event.preventDefault(); setView('editor'); }}><Mark /><span>DepthFrame<span className="brand-ai">AI</span></span></a>
      <div className="workspace-name"><span className="status-dot" />{hosted ? 'Hosted workspace' : 'Local workspace'}<small>{hosted ? 'Saved on the app server' : 'Saved on this computer'}</small></div>
      <button className="primary upload-main" onClick={() => uploadInput.current?.click()} disabled={busy || recording !== null}><Plus size={16} />New photo</button>
      <nav aria-label="Main navigation">
        <button className={view === 'editor' ? 'active' : ''} onClick={() => { setView('editor'); setDrawer(false); }}><Layers size={17} />Photo editor</button>
        <button className={view === 'library' ? 'active' : ''} onClick={() => { setView('library'); setDrawer(false); }}><FolderOpen size={17} />Project library</button>
        <button className={view === 'studio' ? 'active' : ''} onClick={() => { setView('studio'); setDrawer(false); }}><Box size={17} />Environment 360°</button>
        <button className={view === 'object' ? 'active' : ''} onClick={() => { setView('object'); setDrawer(false); }}><Box size={17} />Object 360°</button>
      </nav>
      <div className="sidebar-section"><span>Recent photos</span><span>{total}</span></div>
      {projects.length > 3 && <label className="search small-search"><Search size={14} /><input aria-label="Search recent photos" value={search} onChange={event => setSearch(event.target.value)} placeholder="Find a photo" /></label>}
      <div className="recent-list">
        {filtered.slice(0, 7).map(item => <button className={`recent-project ${item.id === projectId ? 'selected' : ''}`} key={item.id} onClick={() => select(item)} disabled={recording !== null}><img src={item.assets.thumbnail} alt="" /><span><strong>{item.name}</strong><small>{item.object ? '360° object' : item.panorama ? '360° environment' : item.depth ? '3D photo' : item.job?.status === 'failed' ? 'Needs attention' : item.job?.status === 'running' || item.job?.status === 'queued' ? 'Processing' : 'Original photo'}</small></span></button>)}
        {!projects.length && <p className="sidebar-empty">Your photographs will be saved here.</p>}
      </div>
      <div className="sidebar-bottom"><button className="text-button" onClick={() => setHelp(true)}><CircleHelp size={16} />Guide &amp; shortcuts</button><div className="runtime-line"><span className={`status-dot ${health?.worker.alive ? '' : 'muted-dot'}`} /><span>{health?.worker.alive ? 'CPU worker connected' : 'CPU worker offline'}</span></div><small>Depth Anything V2 · Small</small></div>
    </aside>
    {drawer && <button className="drawer-scrim" aria-label="Close navigation" onClick={() => setDrawer(false)} />}

    <main>
      <header className="topbar"><div className="breadcrumb"><button className="mobile-menu icon-button" aria-label="Open navigation" onClick={() => setDrawer(true)}><Mark /></button><span className="breadcrumb-root">Workspace</span><span className="breadcrumb-separator">/</span><h1>{view === 'library' ? 'Project library' : view === 'studio' ? 'Environment 360°' : view === 'object' ? 'Object 360°' : project?.name || 'Photo editor'}</h1>{project && view === 'editor' && <IconButton label="Rename project" onClick={() => { setNewName(project.name); setRenameOpen(true); }} disabled={recording !== null}><MoreHorizontal size={17} /></IconButton>}</div><div className="header-actions">{project && view === 'editor' && <><span className="saved-label">{dirty ? 'Unsaved changes' : hosted ? 'Saved on app server' : 'Saved locally'}</span><button className="secondary" onClick={save} disabled={!dirty || saving || recording !== null}>{saving ? <LoaderCircle size={14} className="spin" /> : <Check size={14} />}Save</button><button className="primary" onClick={() => { if (!project.depth && project.panorama) setMode('panorama'); setExportOpen(true); }} disabled={!(project.depth || project.panorama) || recording !== null}><ArrowDownToLine size={15} />Export<ChevronDown size={13} /></button></>}<IconButton label="Help" onClick={() => setHelp(true)}><CircleHelp size={18} /></IconButton></div></header>
      {error && <div className="message error-message" role="alert"><span>{error}</span><IconButton label="Dismiss error" onClick={() => setError('')}><X size={16} /></IconButton></div>}
      {notice && <div className="toast" role="status"><Check size={16} />{notice}</div>}

      {view === 'editor' && <div className="editor-layout">
        <section className="editor-center">
          <div className="editor-heading"><div><span className="eyebrow">{panoramic ? 'Environment 360°' : '3D photo'}</span><h2>{panoramic ? 'Look around. Every direction.' : project ? 'A little depth. A new perspective.' : 'Give your photograph a new perspective.'}</h2></div><span className="mode-tag"><span className="status-dot" />{panoramic ? 'Full spherical view' : 'CPU powered'}</span></div>
          <div className="viewport-shell" ref={workspaceRef}>
            <div className="viewport-top"><div className="view-tabs" aria-label="Preview mode">{[...(!project || project.kind === 'photo' ? [['original', 'Original'], ['depth', 'Depth'], ['3d', '3D photo']] : []), ...(project?.panorama ? [['panorama', '360° view']] : [])].map(([id, label]) => <button key={id} className={mode === id ? 'selected' : ''} aria-pressed={mode === id} onClick={() => setMode(id)} disabled={(id === 'depth' || id === '3d') && !project?.depth || recording !== null}>{label}</button>)}</div><span className="viewport-resolution">{project ? `${project.width} × ${project.height}` : 'Example photograph'}</span></div>
            <div className="viewport-content" style={{ '--photo-aspect': panoramic ? 1.48 : project ? project.width / project.height : 1.48 } as React.CSSProperties}>
              {project ? <Viewer key={project.id} project={project} settings={settings} mode={mode} locked={recording !== null} controller={controller} onError={showError} onReady={markReady} onFps={setFps} onZoom={value => change('zoom', value)} onInteract={takeCameraControl} /> : <div className="example-stage"><img src={apiUrl("/example-photo")} alt="Example photograph of a lake, forest, and distant mountains" /><div className="example-caption"><span>One photo. Another dimension.</span><p>Create depth and explore a photograph from a fresh angle.</p><button className="primary" onClick={loadExample} disabled={busy || !health?.model_ready}>{busy ? <LoaderCircle size={15} className="spin" /> : <Play size={14} />}Try example photo<ArrowRight size={14} /></button></div></div>}
              {processing && <div className="processing-card" role="status"><div className="processing-title"><LoaderCircle size={17} className="spin" /><strong>{project!.job!.stage}</strong><span>{project!.job!.progress}%</span></div><progress max="100" value={project!.job!.progress} /><p>{project!.job!.cancel ? 'Cancellation requested. Waiting for the current stage to stop.' : 'Your photo is saved. You can leave this page and come back.'}</p><button className="text-button" onClick={() => run(async () => { await api(`/jobs/${project!.job!.id}/cancel`, { method: 'POST' }); await refresh(); })} disabled={Boolean(project!.job!.cancel)}>Cancel processing</button></div>}
              {recording !== null && <div className="recording-banner"><span className="record-dot" />Recording animation · {Math.round(recording)}%<button onClick={() => controller.current?.cancelRecording()}>Cancel</button></div>}
            </div>
            <div className="viewport-bottom"><div className="viewport-hint">{panoramic ? <><span className="status-dot" /><span>Drag to look all around</span></> : project?.depth && mode === '3d' ? <><span className="status-dot" /><span>Drag to change angle</span><span className="keyboard-hint">← ↑ ↓ →</span></> : <span>{project ? 'The original moment, preserved.' : 'Example: landscape with foreground and distance'}</span>}</div><div className="viewport-tools"><IconButton label="Reset camera" disabled={!ready || recording !== null} onClick={() => { takeCameraControl(); controller.current?.reset(); change('zoom', 1); }}><RotateCcw size={16} /></IconButton><IconButton label={settings.autoOrbit ? 'Pause auto-orbit' : 'Start auto-orbit'} disabled={!ready || recording !== null} onClick={() => change('autoOrbit', !settings.autoOrbit)}>{settings.autoOrbit ? <Pause size={16} /> : <Play size={16} />}</IconButton><IconButton label="Fullscreen viewer" onClick={() => { if (document.fullscreenElement) document.exitFullscreen().catch(exception => showError(exception.message)); else workspaceRef.current?.requestFullscreen().catch(exception => showError(exception.message)); }}><Expand size={16} /></IconButton></div></div>
          </div>
          {panoramic ? <div className="panorama-provenance"><strong>{project?.panorama?.ai_generated ? 'AI imagined environment · OpenAI' : 'Imported / captured panorama'}</strong><p>{project?.panorama?.ai_generated ? 'Unseen surroundings are invented. Inspect the seam and poles.' : 'A spherical image viewed from one fixed position.'}</p></div> : <div className="image-strip"><div className="image-strip-label"><Layers size={17} /><div><strong>{project?.depth ? 'Your depth scene' : 'Start with one photograph'}</strong><span>{project?.depth ? 'Original + relative depth → interactive photo' : 'Landscapes, portraits, interiors. Find a little foreground.'}</span></div></div>{project?.depth ? <div className="asset-pair"><button onClick={() => setMode('original')} title="View original"><img src={project.assets.thumbnail} alt="Original photo thumbnail" /><span>Original</span></button><span className="asset-plus">+</span><button onClick={() => setMode('depth')} title="View depth"><img src={project.depth.assets.preview} alt="Depth map thumbnail" /><span>Depth map</span></button></div> : <button className="secondary" onClick={() => uploadInput.current?.click()} disabled={busy}><Upload size={14} />Upload a photo</button>}</div>}
          <div className="editor-footnote"><span>{panoramic ? `${project!.panorama!.width} × ${project!.panorama!.height} · equirectangular` : project?.depth ? `Depth Anything V2 Small · ${formatSeconds(project.depth.inference_seconds)} inference` : 'JPG, PNG or WebP · Up to 15 MB · Maximum 4096 × 4096 px'}</span><span>{ready && (mode === '3d' || panoramic) ? `${fps || '—'} FPS` : hosted ? 'CPU processing stays on the app server' : 'CPU processing stays local'}</span></div>
          {!project && <p className="photo-credit">Example photo by <a href="https://www.pexels.com/photo/landscape-photography-of-lake-surrounded-by-trees-417074/" target="_blank" rel="noreferrer">Pixabay / Pexels</a>.</p>}
        </section>

        {panoramic ? <aside className="controls-panel" aria-label="Environment controls"><div className="panel-title"><Box size={17} /><h2>Environment settings</h2></div><section className="control-section"><h3>Look around</h3><p>Drag horizontally for a complete turn. Drag vertically to see the sky and ground. Arrow keys turn 15°; Home returns to the start.</p><Slider label="Zoom" value={settings.zoom} min={0.7} max={2} onChange={value => change('zoom', value)} format={value => `${value.toFixed(2)}×`} /><label className="toggle-field"><span>Auto look-around<small>Continuous 360° rotation</small></span><input aria-label="Auto look-around" type="checkbox" role="switch" checked={settings.autoOrbit} onChange={event => change('autoOrbit', event.target.checked)} /></label><button className="text-button reset-settings" onClick={() => { setSettings(defaultSettings); controller.current?.reset(); }}><RotateCcw size={14} />Reset settings</button></section><section className="control-section"><h3>Source</h3><p>{project?.panorama?.ai_generated ? `AI generated with ${project.panorama.model}. Surroundings outside the reference photo are inferred.` : 'Imported equirectangular panorama. The example is Kiara 1 Dawn by Greg Zaal / Poly Haven (CC0).'}</p></section><div className="perspective-note"><Box size={19} /><strong>One position. Every direction.</strong><p>This is a full spherical environment. Walking through the scene requires a separate 3D reconstruction.</p></div><button className="secondary" onClick={() => setView('studio')}>Environment studio<ArrowRight size={15} /></button></aside> : <aside className="controls-panel" aria-label="Photo controls"><div className="panel-title"><Settings2 size={17} /><h2>Photo settings</h2></div><section className="control-section"><div className="section-heading"><h3>Depth &amp; perspective</h3></div><p>Bring the foreground closer. Keep the moment intact.</p><Slider label="Depth intensity" value={settings.strength} onChange={value => change('strength', value)} disabled={!project?.depth || recording !== null} /><div className="range-labels"><span>Subtle</span><span>Pronounced</span></div><Slider label="Camera movement" value={settings.motion} onChange={value => change('motion', value)} disabled={!project?.depth || recording !== null} /><Slider label="Zoom" value={settings.zoom} min={0.7} max={2} onChange={value => change('zoom', value)} format={value => `${value.toFixed(2)}×`} disabled={!project?.depth || recording !== null} /></section>
          <section className="control-section"><div className="section-heading"><h3>Preview</h3></div><label className="select-label">Quality<select aria-label="Preview quality" value={settings.quality} onChange={event => change('quality', event.target.value as Settings['quality'])} disabled={!project?.depth || recording !== null}><option value="draft">Draft · 64 grid</option><option value="balanced">Balanced · 128 grid</option><option value="high">High · 256 grid</option></select></label><label className="toggle-field"><span>Auto-orbit<small>Gentle, bounded camera motion</small></span><input aria-label="Auto-orbit" type="checkbox" role="switch" checked={settings.autoOrbit} onChange={event => change('autoOrbit', event.target.checked)} disabled={!project?.depth || recording !== null} /></label><button className="text-button reset-settings" disabled={!project || recording !== null} onClick={() => { setSettings(defaultSettings); controller.current?.reset(); }}><RotateCcw size={14} />Reset settings</button></section>
          <section className="control-section"><div className="section-heading"><h3>Processing</h3></div><div className="processing-info"><span>Model</span><strong>Depth Anything V2 Small</strong><span>Device</span><strong>CPU · local</strong><span>Output</span><strong>Relative depth</strong></div><div className="job-state"><span className={`status-dot ${project?.job?.status === 'failed' ? 'error-dot' : ''}`} /><span>{statusLabel}</span></div>{project?.job?.error && <p className="job-error">{project.job.error}</p>}{project && !processing && <button className="secondary generate-button" disabled={busy || !health?.model_ready || !health.worker.alive || recording !== null} onClick={() => run(() => generate(project.id))}><Layers size={14} />{project.depth ? 'Regenerate depth' : project.job?.status === 'failed' ? 'Retry depth generation' : 'Generate depth'}</button>}{health && (!health.model_ready || !health.worker.alive) && <p className="service-warning">{!health.model_ready ? hosted ? 'The CPU model downloads on first start. Allow setup to finish, then retry.' : 'Install the model with the setup script.' : 'Start the CPU worker with Start-DepthFrame.ps1.'}</p>}</section>
          <div className="perspective-note"><Box size={19} /><strong>A photograph, with depth.</strong><p>Small camera movements reveal perspective. Hidden areas are not reconstructed.</p></div>
        </aside>}
      </div>}

      {view === 'library' && <section className="library-view"><div className="page-heading"><div><h2>Your photographs</h2><p>{total} {total === 1 ? 'project' : 'projects'} saved {hosted ? 'on the app server' : 'on this computer'}</p></div><button className="primary" onClick={() => uploadInput.current?.click()} disabled={busy}><Plus size={16} />New photo</button></div><label className="search library-search"><Search size={16} /><input aria-label="Search project library" placeholder="Search your photographs" value={search} onChange={event => setSearch(event.target.value)} /></label>{loading ? <p>Loading your library…</p> : <div className="project-grid">{filtered.map(item => <button className="project-card" key={item.id} onClick={() => select(item)}><img src={item.assets.thumbnail} alt={item.name} /><div><strong>{item.name}</strong><ArrowRight size={16} /></div><p>{new Date(item.created * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}<span>{item.depth ? 'Depth ready' : item.job?.status || 'Original'}</span></p></button>)}{!filtered.length && <div className="library-empty"><ImagePlus size={28} /><h3>{projects.length ? 'No matching photographs' : 'Your first perspective starts here.'}</h3><p>{projects.length ? 'Try another search.' : 'Upload a photograph or explore the example landscape.'}</p><button className="secondary" onClick={loadExample} disabled={busy || !health?.model_ready}>Try example photo<ArrowRight size={15} /></button></div>}</div>}{projects.length < total && <button className="secondary" onClick={() => setLimit(previous => previous + 50)}>Load more photographs</button>}</section>}

      {view === 'studio' && <EnvironmentStudio projects={projects} project={project} capabilities={capabilities} workerAlive={Boolean(health?.worker.alive)} busy={busy} onSelect={id => { if (!dirty || window.confirm('Discard unsaved settings?')) setProjectId(id || null); }} onOpen={item => { select(item); setView('editor'); setMode('panorama'); }} onCreated={created => { setProjects(previous => [created, ...previous]); setProjectId(created.id); }} onRefresh={refresh} run={run} />}
      {view === 'object' && <ObjectStudio projects={projects} project={project} capabilities={capabilities} workerAlive={Boolean(health?.worker.alive)} busy={busy} onSelect={id => { if (!dirty || window.confirm('Discard unsaved settings?')) setProjectId(id || null); }} onCreated={created => { setProjects(previous => [created, ...previous]); setProjectId(created.id); }} onRefresh={refresh} run={run} onError={showError} />}
    </main>

    {dragging && <div className="drop-overlay"><ImagePlus size={40} /><strong>Drop a photograph to begin</strong><span>JPG, PNG or WebP · up to 15 MB</span></div>}
    {help && <div className="modal-backdrop" onClick={() => setHelp(false)}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="guide-title" onClick={event => event.stopPropagation()}><div className="modal-heading"><h2 id="guide-title">A new perspective</h2><IconButton label="Close guide" onClick={() => setHelp(false)}><X size={18} /></IconButton></div><p>Upload one photo, let the CPU estimate relative depth, then choose 3D photo and drag to set the viewing angle. CPU depth processing happens on {hosted ? 'the app server' : 'this computer'}. Environment 360° can send your selected reference to OpenAI when you explicitly generate it, using your API credits. You can also import a panorama or try the captured 360° example locally.</p><dl className="help-list"><dt>Drag / arrow keys</dt><dd>Release to keep the angle; Home resets it</dd><dt>Home / reset button</dt><dd>Return to the reference camera</dd><dt>Zoom slider</dt><dd>Adjust framing</dd><dt>Save</dt><dd>Persist depth, camera and quality settings</dd><dt>Export</dt><dd>Download depth, a still, a 5-second animation, or a textured GLB mesh</dd></dl><p>Depth is relative, not measured distance. Glass, hair, thin objects and newly revealed areas may have artifacts. A GLB is a photo depth mesh, not a complete 3D reconstruction.</p><p>Video export requires a supported browser encoder. Keep this tab visible while recording. Uploads must be still images, 32–4096 pixels per side.</p><button className="primary" onClick={() => setHelp(false)}>Got it</button></section></div>}
    {exportOpen && project?.depth && !panoramic && <div className="modal-backdrop" onClick={() => setExportOpen(false)}><section className="modal export-modal" role="dialog" aria-modal="true" aria-labelledby="export-title" onClick={event => event.stopPropagation()}><div className="modal-heading"><div><h2 id="export-title">Take your perspective with you.</h2><p>{project.name}</p></div><IconButton label="Close export" onClick={() => setExportOpen(false)}><X size={18} /></IconButton></div><div className="export-options"><button disabled={!ready} onClick={() => exportAction('png')}><Camera size={21} /><span><strong>Still image</strong><small>PNG · current 3D viewpoint</small></span><ArrowDownToLine size={16} /></button><button disabled={!ready} onClick={() => exportAction('video')}><Video size={21} /><span><strong>Orbit animation</strong><small>5 seconds · 720p · browser-supported video</small></span><ArrowDownToLine size={16} /></button><a href={project.depth.assets.depth16 + '&download=true'} download><Layers size={21} /><span><strong>Depth map</strong><small>16-bit PNG · light is near, dark is far</small></span><ArrowDownToLine size={16} /></a><button disabled={!ready} onClick={() => exportAction('glb')}><Box size={21} /><span><strong>Textured depth mesh</strong><small>GLB · image texture included</small></span><ArrowDownToLine size={16} /></button><a href={apiUrl(`/projects/${project.id}/bundle`)} download><FolderOpen size={21} /><span><strong>Project bundle</strong><small>ZIP · photo, raw depth, manifest, settings</small></span><ArrowDownToLine size={16} /></a><a href={project.assets.original + '?download=true'} download><ImagePlus size={21} /><span><strong>Original photograph</strong><small>Unchanged source · may contain EXIF/GPS metadata</small></span><ArrowDownToLine size={16} /></a></div><p className="export-note">Exports use the current depth result. Save settings before downloading a project bundle.</p></section></div>}
    {exportOpen && panoramic && project?.panorama && <div className="modal-backdrop" onClick={() => setExportOpen(false)}><section className="modal export-modal" role="dialog" aria-modal="true" aria-labelledby="panorama-export-title" onClick={event => event.stopPropagation()}><div className="modal-heading"><h2 id="panorama-export-title">Export your environment</h2><IconButton label="Close export" onClick={() => setExportOpen(false)}><X size={18} /></IconButton></div><div className="export-options"><button disabled={!ready} onClick={() => exportAction('png')}><Camera size={21} /><span><strong>Still image</strong><small>PNG · current viewing direction</small></span><ArrowDownToLine size={16} /></button><a href={project.panorama.assets.panorama + (project.panorama.assets.panorama.includes('?') ? '&' : '?') + 'download=true'} download><ImagePlus size={21} /><span><strong>360° panorama</strong><small>Full 2:1 equirectangular image</small></span><ArrowDownToLine size={16} /></a>{project.panorama.assets.panorama_manifest && <a href={project.panorama.assets.panorama_manifest + '&download=true'} download><FolderOpen size={21} /><span><strong>Generation manifest</strong><small>JSON · model, projection and provenance</small></span><ArrowDownToLine size={16} /></a>}</div><p className="export-note">The panorama image can be used in compatible 360° viewers.</p></section></div>}
    {renameOpen && project && <div className="modal-backdrop"><form className="modal small-modal" role="dialog" aria-modal="true" aria-labelledby="rename-title" onSubmit={event => { event.preventDefault(); run(async () => { await api(`/projects/${project.id}`, { method: 'PATCH', body: JSON.stringify({ name: newName }) }); setRenameOpen(false); await refresh(); }); }}><div className="modal-heading"><h2 id="rename-title">Project details</h2><IconButton label="Close project details" onClick={() => setRenameOpen(false)}><X size={18} /></IconButton></div><label className="text-field">Photo name<input autoFocus value={newName} onChange={event => setNewName(event.target.value)} maxLength={100} required /></label><div className="modal-actions"><button className="danger text-button" type="button" onClick={() => { setRenameOpen(false); setDeleteOpen(true); }}><Trash2 size={15} />Delete photo</button><button className="primary" disabled={busy || !newName.trim()}>Save name</button></div></form></div>}
    {deleteOpen && project && <div className="modal-backdrop"><section className="modal small-modal" role="dialog" aria-modal="true" aria-labelledby="delete-title"><h2 id="delete-title">Delete “{project.name}”?</h2><p>The photo, depth results and saved settings will be removed from {hosted ? 'the app server' : 'this computer'}. Active processing will be cancelled. Downloaded exports are kept.</p><div className="modal-actions"><button className="secondary" onClick={() => setDeleteOpen(false)}>Keep photo</button><button className="danger-button" disabled={busy} onClick={() => run(async () => { await api(`/projects/${project.id}`, { method: 'DELETE' }); setDeleteOpen(false); setProjectId(null); await refresh(); setView('library'); })}>Delete photo</button></div></section></div>}
  </div>;
}
