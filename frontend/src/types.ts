export type Settings = { strength: number; motion: number; zoom: number; quality: 'draft' | 'balanced' | 'high'; autoOrbit: boolean };
export type Depth = { job_id: string; width: number; height: number; grid_width: number; grid_height: number; grid_dtype: string; assets: Record<string, string>; inference_seconds: number; processing_seconds: number; tensor_dimensions: number[]; model: { model: string; sha256: string; upstream_commit: string } };
export type Panorama = { job_id: string | null; width: number; height: number; projection: 'equirectangular'; ai_generated: boolean; provider: string; model?: string; assets: Record<string, string> };
export type Region = { x: number; y: number; width: number; height: number };
export type Subject = Region & { token: string; assets: { preview: string } };
export type ObjectResult = { job_id: string; provider: string; ai_generated: boolean; model: string; assets: Record<string, string>; warning: string };
export type Job = { id: string; project_id: string; job_type: 'depth' | 'panorama' | 'object'; remote_id: string | null; status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'; stage: string; progress: number; cancel: number; error: string | null; result: Depth | Panorama | ObjectResult | null };
export type Project = { id: string; kind: 'photo' | 'panorama'; name: string; created: number; width: number; height: number; revision: number; settings: Settings; assets: Record<string, string>; depth: Depth | null; panorama: Panorama | null; object: ObjectResult | null; subject: Subject | null; job: Job | null };
export type Capabilities = { configuration_source?: 'streamlit-secrets' | 'local-env'; panorama_generation: { configured: boolean; model: string | null; error: string | null }; object_generation?: { configured: boolean; model: string | null; error: string | null } };
export type Health = { status: string; model_ready: boolean; worker: { alive: boolean; state: string }; mode: string };
export const defaultSettings: Settings = { strength: 0.38, motion: 0.45, zoom: 1, quality: 'balanced', autoOrbit: false };

export function apiUrl(url: string): string {
  // Community Cloud strips /~/+/ before forwarding, so preserve the browser's prefix.
  const root = window.location.pathname.replace(/\/workspace\/?$/, '/');
  return `${root.endsWith('/') ? root : root + '/'}api${url}`;
}

export async function api<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(apiUrl(url), { ...options, headers: { ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...options.headers } });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.error?.message || `Request failed (${response.status}).`);
  }
  if (!response.headers.get('Content-Type')?.includes('application/json')) {
    throw new Error('The hosting page was returned instead of the editor API. Refresh the Streamlit app and open the editor again.');
  }
  // Backend asset URLs are server-relative; resolve them through the same browser prefix.
  return JSON.parse(await response.text(), (_key, value) => typeof value === 'string' && value.startsWith('/api/') ? apiUrl(value.slice(4)) : value) as T;
}

export function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function formatSeconds(value: number) { return value < 1 ? `${Math.round(value * 1000)} ms` : `${value.toFixed(1)} s`; }
