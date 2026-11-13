import { useRef, useState } from 'react';
import { ArrowRight, Globe, ImagePlus, LoaderCircle, Upload } from 'lucide-react';
import { api, apiUrl, type Capabilities, type Project } from './types';

type Props = { projects: Project[]; project: Project | null; capabilities: Capabilities | null; workerAlive: boolean; busy: boolean; onSelect: (id: string) => void; onOpen: (project: Project) => void; onCreated: (project: Project) => void; onRefresh: () => Promise<unknown>; run: (action: () => Promise<void>) => Promise<void> };

export default function EnvironmentStudio({ projects, project, capabilities, workerAlive, busy, onSelect, onOpen, onCreated, onRefresh, run }: Props) {
  const photoInput = useRef<HTMLInputElement>(null), panoInput = useRef<HTMLInputElement>(null);
  const [description, setDescription] = useState('');
  const [quality, setQuality] = useState('medium');
  const [consent, setConsent] = useState(false);
  const config = capabilities?.panorama_generation;
  const processing = project?.job?.status === 'running' || project?.job?.status === 'queued';
  async function upload(file: File | undefined, kind: string) {
    if (!file) return;
    await run(async () => {
      const form = new FormData(); form.append('file', file);
      const created = await api<Project>(`/projects?kind=${kind}`, { method: 'POST', body: form });
      onCreated(created); setConsent(false);
      if (kind === 'panorama') onOpen(created);
      await onRefresh();
    });
  }
  return <section className="environment-studio">
    <div className="environment-intro"><span className="eyebrow">Environment 360°</span><h2>See what surrounds you.</h2><p>Turn one photograph into an AI imagined environment, then look all around from a fixed viewpoint.</p></div>
    <div className="environment-columns"><div className="environment-form">
      <h3>Choose a reference</h3>
      <input className="visually-hidden" ref={photoInput} type="file" accept="image/jpeg,image/png,image/webp" aria-label="Upload environment reference" onChange={e => { upload(e.target.files?.[0], 'photo'); e.target.value = ''; }} />
      <label className="select-label">Reference photograph<select aria-label="Environment reference" value={project?.kind === 'photo' ? project.id : ''} onChange={e => { onSelect(e.target.value); setConsent(false); }} disabled={busy || processing}><option value="">Choose a photo</option>{projects.filter(p => p.kind === 'photo').map(p => <option value={p.id} key={p.id}>{p.name}</option>)}</select></label>
      {project?.kind === 'photo' && <img className="environment-reference" src={project.assets.image} alt="Selected environment reference" />}
      <button className="secondary" onClick={() => photoInput.current?.click()} disabled={busy || processing}><ImagePlus size={15} />Upload reference photo</button>
      <h3>Imagine the surroundings</h3>
      <label className="text-field">Scene guidance <small>(optional)</small><textarea aria-label="Scene guidance" value={description} onChange={e => setDescription(e.target.value)} maxLength={1000} rows={3} placeholder="Keep the same lighting. Extend the forest behind the camera…" disabled={busy || processing} /></label>
      <label className="select-label">Generation quality<select aria-label="Generation quality" value={quality} onChange={e => setQuality(e.target.value)} disabled={busy || processing}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label>
      <p className="environment-meta">OpenAI · {config?.model || 'Image API'} · 2048 × 1024 target</p>
      {!config?.configured && <p className="service-warning">{config?.error || (capabilities?.configuration_source === 'streamlit-secrets' ? 'Add OPENAI_API_KEY in Streamlit app settings > Secrets. Keep the key private.' : 'Add OPENAI_API_KEY to your private .env file in the application folder. This screen checks configuration automatically. Keep the key out of chat.')}</p>}
      <label className="consent-field"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} disabled={busy || processing} /><span>Send this selected photo to OpenAI. Generation uses my API credits, and unseen surroundings will be AI invented.</span></label>
      <button className="primary" disabled={busy || processing || !config?.configured || !workerAlive || !consent || project?.kind !== 'photo'} onClick={() => run(async () => { await api(`/projects/${project!.id}/panorama-jobs`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ description, quality, allow_external_processing: consent }) }); await onRefresh(); })}>{processing ? <LoaderCircle size={15} className="spin" /> : <Globe size={15} />}Generate with OpenAI</button>
      {!workerAlive && <p className="service-warning">Start DepthFrame to connect the processing worker.</p>}
      {processing && <div className="environment-progress" role="status"><strong>{project!.job!.stage}</strong><progress max={100} value={project!.job!.progress} /><p>This can take several minutes. You can return later.</p><button className="text-button" disabled={Boolean(project!.job!.cancel)} onClick={() => run(async () => { await api(`/jobs/${project!.job!.id}/cancel`, { method: 'POST' }); await onRefresh(); })}>{project!.job!.cancel ? 'Cancellation requested' : 'Cancel generation'}</button><p>Stopping locally may still use credits if OpenAI has received the request.</p></div>}
      {project?.job?.status === 'failed' && <p className="job-error" role="alert">{project.job.error}</p>}
      {project?.panorama && <button className="secondary open-environment" onClick={() => onOpen(project)}>Open 360° environment<ArrowRight size={15} /></button>}
    </div><aside className="environment-demo">
      <h3>Look around an example</h3><img src={apiUrl("/panorama-example-photo")} alt="Captured 360 degree landscape at Kiara dawn" /><p>A real, captured panorama lets you try the full 360° viewer locally.</p><button className="secondary" disabled={busy} onClick={() => run(async () => { const created = await api<Project>('/panorama-examples', { method: 'POST' }); onCreated(created); onOpen(created); await onRefresh(); })}>Try 360° example<ArrowRight size={15} /></button>
      <small>Kiara 1 Dawn by Greg Zaal / <a href="https://polyhaven.com/a/kiara_1_dawn" target="_blank" rel="noreferrer">Poly Haven</a> · CC0. Captured panorama; not an AI result.</small>
      <div className="environment-import"><h3>Already have a panorama?</h3><p>Import a 2:1 equirectangular image, up to 8192 × 4096 pixels and 15 MB.</p><input className="visually-hidden" ref={panoInput} type="file" accept="image/jpeg,image/png,image/webp" aria-label="Import panorama" onChange={e => { upload(e.target.files?.[0], 'panorama'); e.target.value = ''; }} /><button className="secondary" onClick={() => panoInput.current?.click()} disabled={busy}><Upload size={15} />Import panorama</button></div>
      <p className="environment-limits">360° means looking in every direction from one position. AI may introduce seams or inconsistent details. It does not produce a walkable 3D scene or recover the real hidden surroundings.</p>
    </aside></div>
  </section>;
}
