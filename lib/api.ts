/**
 * Nabi AI — API Client
 * Communicates with the Python FastAPI backend on localhost:8000
 */

const API_BASE = 'http://localhost:8000';

// ── Types ────────────────────────────────────

export interface Project {
  id: string;
  title: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  source_video_path: string | null;
  output_video_path: string | null;
  duration_seconds: number | null;
  transcription: any | null;
  edit_decision_list: any | null;
  settings: any;
  current_step: string | null;
  progress: number;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface HealthStatus {
  status: string;
  version: string;
  ffmpeg: boolean;
  ollama: boolean;
  pexels_api_key: boolean;
  motion_mode: string;
  hyperframes: boolean;
  projects_dir: string;
}

export interface PipelineEstimate {
  transcription: number;
  analysis: number;
  images: number;
  broll: number;
  render: number;
  total: number;
  estimated_assets: {
    brolls: number;
    images: number;
  };
}

export interface ProgressUpdate {
  type: 'progress' | 'project_state';
  data: {
    step?: string;
    progress?: number;
    message?: string;
  } & Partial<Project>;
}

export interface Settings {
  pexels_api_key: string;
  ollama_model: string;
  whisper_model: string;
  motion_mode: 'hyperframes' | 'pillow';
  da_primary: string;
  da_secondary: string;
  da_background: string;
  da_accent_2: string;
  output_resolution: string;
  output_dir: string;
  pip_enabled: string;
  remove_silences: string;
}

// ── API Functions ────────────────────────────

export async function fetchProjects(): Promise<Project[]> {
  const res = await fetch(`${API_BASE}/api/projects`);
  if (!res.ok) throw new Error(`Failed to fetch projects: ${res.status}`);
  return res.json();
}

export async function fetchProject(id: string): Promise<Project> {
  const res = await fetch(`${API_BASE}/api/projects/${id}`);
  if (!res.ok) throw new Error(`Failed to fetch project: ${res.status}`);
  return res.json();
}

export async function deleteProject(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/projects/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete project: ${res.status}`);
}

export async function uploadVideo(file: File): Promise<Project> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${API_BASE}/api/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
}

export async function startProcessing(projectId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/process/${projectId}`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to start processing: ${res.status}`);
  }
}

export async function cancelProcessing(projectId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/cancel/${projectId}`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to cancel processing: ${res.status}`);
  }
}

export async function fetchSettings(): Promise<Settings> {
  const res = await fetch(`${API_BASE}/api/settings`);
  if (!res.ok) throw new Error(`Failed to fetch settings: ${res.status}`);
  return res.json();
}

export async function saveSettings(settings: Partial<Settings>): Promise<void> {
  const res = await fetch(`${API_BASE}/api/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  if (!res.ok) throw new Error(`Failed to save settings: ${res.status}`);
}

export async function checkHealth(): Promise<HealthStatus> {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}

export function getDownloadUrl(projectId: string): string {
  return `${API_BASE}/api/download/${projectId}`;
}

export function getVideoUrl(projectId: string, type: 'source' | 'output'): string {
  return `${API_BASE}/api/video/${projectId}/${type}`;
}

export async function fetchEstimate(projectId: string): Promise<PipelineEstimate> {
  const res = await fetch(`${API_BASE}/api/estimate/${projectId}`);
  if (!res.ok) throw new Error(`Failed to fetch estimate: ${res.status}`);
  return res.json();
}

// ── WebSocket ────────────────────────────────

export function connectWebSocket(
  projectId: string,
  onMessage: (update: ProgressUpdate) => void,
  onError?: (error: Event) => void,
): WebSocket {
  const WS_URL = 'ws://localhost:8000';
  const ws = new WebSocket(`${WS_URL}/ws/${projectId}`);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch {
      // Ignore non-JSON messages (e.g., "pong")
    }
  };

  ws.onerror = (event) => {
    // Silently handle — backend may not be running
    onError?.(event);
  };

  // Ping every 30 seconds to keep alive
  const pingInterval = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send('ping');
    }
  }, 30000);

  const originalClose = ws.close.bind(ws);
  ws.close = (...args) => {
    clearInterval(pingInterval);
    originalClose(...args);
  };

  return ws;
}

// ── Helpers ──────────────────────────────────

export function formatDuration(seconds: number | null): string {
  if (!seconds) return '—';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString('fr-FR', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

export function formatRelativeTime(isoString: string): string {
  const diff = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "À l'instant";
  if (mins < 60) return `Il y a ${mins} min`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `Il y a ${hours}h`;
  const days = Math.floor(hours / 24);
  return `Il y a ${days}j`;
}
