'use client';

import { useState, useEffect, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import ProgressTracker, { StepStatus } from '@/components/ProgressTracker';
import VideoPlayer from '@/components/VideoPlayer';
import {
  fetchProject,
  deleteProject,
  cancelProcessing,
  startProcessing,
  connectWebSocket,
  getDownloadUrl,
  getVideoUrl,
  formatDuration,
  formatDate,
  type Project,
  type ProgressUpdate,
} from '@/lib/api';

const PIPELINE_STEPS = ['transcription', 'analysis', 'motion_design', 'broll', 'render'];

const STEP_LABELS: Record<string, { title: string; subtitle: string }> = {
  transcription: { title: 'Transcription', subtitle: 'mlx-whisper (large-v3-turbo)' },
  analysis: { title: 'Analyse IA', subtitle: 'Ollama — Décisions de montage' },
  motion_design: { title: 'Motion Design', subtitle: 'HyperFrames — Animations IA' },
  broll: { title: 'B-roll', subtitle: 'Pexels API — Clips stock' },
  render: { title: 'Rendu Final', subtitle: 'FFmpeg — Composition' },
};

export default function ProjectPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = params.id as string;

  const [project, setProject] = useState<Project | null>(null);
  const [currentStep, setCurrentStep] = useState<string>('');
  const [stepProgress, setStepProgress] = useState(0);
  const [stepMessage, setStepMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState('');
  const [videoTab, setVideoTab] = useState<'source' | 'output'>('output');
  const [motionDesignEnabled, setMotionDesignEnabled] = useState(true);
  const wsRef = useRef<WebSocket | null>(null);

  // Delete project
  const handleDelete = async () => {
    if (!confirm('Supprimer ce projet et tous ses fichiers ?')) return;
    setActionLoading('delete');
    try {
      await deleteProject(projectId);
      router.push('/');
    } catch (e) {
      alert('Erreur lors de la suppression');
      setActionLoading('');
    }
  };

  // Cancel processing
  const handleCancel = async () => {
    if (!confirm('Arrêter le traitement en cours ?')) return;
    setActionLoading('cancel');
    try {
      await cancelProcessing(projectId);
      const p = await fetchProject(projectId);
      setProject(p);
      setCurrentStep('');
      setStepMessage('');
      setStepProgress(0);
    } catch (e) {
      alert('Erreur lors de l\'annulation');
    }
    setActionLoading('');
  };

  // Restart processing
  const handleRestart = async () => {
    setActionLoading('restart');
    try {
      await startProcessing(projectId, { motion_design_enabled: motionDesignEnabled });
      const p = await fetchProject(projectId);
      setProject(p);
    } catch (e) {
      alert('Erreur lors du redémarrage');
    }
    setActionLoading('');
  };

  // Load project
  useEffect(() => {
    if (!projectId) return;

    const load = async () => {
      try {
        const p = await fetchProject(projectId);
        setProject(p);
        setCurrentStep(p.current_step || '');
        setLoading(false);
      } catch {
        setLoading(false);
      }
    };
    load();
  }, [projectId]);

  // Connect WebSocket for live updates
  useEffect(() => {
    if (!projectId) return;

    const ws = connectWebSocket(projectId, (update: ProgressUpdate) => {
      if (update.type === 'progress') {
        setCurrentStep(update.data.step || '');
        setStepProgress(update.data.progress || 0);
        setStepMessage(update.data.message || '');
      }
      if (update.type === 'project_state') {
        setProject(update.data as unknown as Project);
      }

      // Refresh project data on completion/error
      if (
        update.data.step === 'completed' ||
        update.data.step === 'error'
      ) {
        fetchProject(projectId).then(setProject).catch(() => {});
      }
    });

    wsRef.current = ws;

    return () => {
      ws.close();
    };
  }, [projectId]);

  // Derive step statuses
  const getStepStatus = (stepId: string): StepStatus => {
    if (!project) return 'pending';
    if (project.status === 'completed') return 'completed';
    if (project.status === 'failed' && currentStep === stepId) return 'failed';

    const currentIdx = PIPELINE_STEPS.indexOf(currentStep);
    const stepIdx = PIPELINE_STEPS.indexOf(stepId);

    if (stepIdx < currentIdx) return 'completed';
    if (stepIdx === currentIdx) return 'active';
    return 'pending';
  };

  const steps = PIPELINE_STEPS.map((id) => {
    let title = STEP_LABELS[id].title;
    let subtitle = currentStep === id && stepMessage
      ? stepMessage
      : STEP_LABELS[id].subtitle;

    // Show disabled state for motion_design step when skipped
    if (id === 'motion_design' && getStepStatus(id) === 'completed' && stepMessage?.includes('désactivé')) {
      subtitle = 'Désactivé pour ce projet';
    }

    return {
      id,
      title,
      subtitle,
      status: getStepStatus(id),
    };
  });

  const completedSteps = steps.filter((s) => s.status === 'completed').length;
  const overallProgress = project?.status === 'completed'
    ? 100
    : Math.round((completedSteps / steps.length) * 100);

  const edl = project?.edit_decision_list;
  const transcription = project?.transcription;

  if (loading) {
    return (
      <div className="app-layout">
        <Sidebar />
        <main className="main-content">
          <div className="page-container">
            <div className="empty-state">
              <div style={{ width: 32, height: 32, border: '3px solid var(--accent-violet)', borderTop: '3px solid transparent', borderRadius: '50%', animation: 'spin 1s linear infinite', margin: '0 auto var(--space-4)' }} />
              <p className="text-secondary">Chargement du projet...</p>
            </div>
          </div>
        </main>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="app-layout">
        <Sidebar />
        <main className="main-content">
          <div className="page-container">
            <div className="empty-state">
              <div className="empty-state-icon">❌</div>
              <h3 className="empty-state-title">Projet introuvable</h3>
              <a href="/" className="btn btn-primary" style={{ marginTop: 'var(--space-4)' }}>
                Retour au dashboard
              </a>
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="app-layout">
      <Sidebar />
      <main className="main-content">
        <div className="page-container">
          {/* Header */}
          <div className="page-header animate-fade-in">
            <div className="flex items-center gap-4" style={{ marginBottom: 'var(--space-2)', justifyContent: 'space-between' }}>
              <a href="/" className="btn btn-ghost btn-sm" style={{ gap: 'var(--space-2)' }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="15 18 9 12 15 6" />
                </svg>
                Retour
              </a>
              <div className="flex items-center gap-2">
                {/* Cancel button — only when processing */}
                {project.status === 'processing' && (
                  <button
                    onClick={handleCancel}
                    disabled={actionLoading === 'cancel'}
                    className="btn btn-sm"
                    style={{
                      background: 'rgba(251, 191, 36, 0.1)',
                      border: '1px solid rgba(251, 191, 36, 0.3)',
                      color: '#fbbf24',
                      gap: 'var(--space-2)',
                    }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="6" y="6" width="12" height="12" rx="2" />
                    </svg>
                    {actionLoading === 'cancel' ? 'Annulation...' : 'Arrêter'}
                  </button>
                )}
                {/* Restart button — when queued or failed */}
                {(project.status === 'queued' || project.status === 'failed') && (
                  <button
                    onClick={handleRestart}
                    disabled={actionLoading === 'restart'}
                    className="btn btn-primary btn-sm"
                    style={{ gap: 'var(--space-2)' }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="23 4 23 10 17 10" />
                      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                    </svg>
                    {actionLoading === 'restart' ? 'Lancement...' : 'Relancer'}
                  </button>
                )}
                {/* Delete button */}
                <button
                  onClick={handleDelete}
                  disabled={!!actionLoading}
                  className="btn btn-sm"
                  style={{
                    background: 'rgba(239, 68, 68, 0.1)',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                    color: '#ef4444',
                    gap: 'var(--space-2)',
                  }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  </svg>
                  {actionLoading === 'delete' ? 'Suppression...' : 'Supprimer'}
                </button>
              </div>
            </div>
            <h1 className="page-title">{project.title}</h1>
            <div className="flex items-center gap-3">
              <span className={`badge ${project.status === 'processing' ? 'badge-processing' : project.status === 'completed' ? 'badge-completed' : project.status === 'failed' ? 'badge-failed' : 'badge-queued'}`}>
                <span className="badge-dot" />
                {project.status === 'processing' ? 'En cours' : project.status === 'completed' ? 'Terminé' : project.status === 'failed' ? 'Erreur' : 'En attente'}
              </span>
              {project.duration_seconds && (
                <span className="text-sm text-secondary">
                  Durée : {formatDuration(project.duration_seconds)}
                </span>
              )}
              <span className="text-sm text-secondary">
                {formatDate(project.created_at)}
              </span>
            </div>
          </div>

          {/* Error message */}
          {project.status === 'failed' && project.error_message && (
            <div
              className="card section animate-fade-in"
              style={{ borderColor: 'rgba(239, 68, 68, 0.3)', background: 'rgba(239, 68, 68, 0.05)' }}
            >
              <div className="flex items-center gap-3">
                <span style={{ fontSize: 24 }}>❌</span>
                <div>
                  <p className="font-semibold" style={{ color: 'var(--accent-red-light)' }}>Erreur du pipeline</p>
                  <p className="text-sm text-secondary" style={{ marginTop: 'var(--space-1)' }}>
                    {project.error_message}
                  </p>
                </div>
              </div>
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 'var(--space-6)', alignItems: 'start' }}>
            {/* Main Column */}
            <div>
              {/* Video Preview */}
              <div className="section animate-fade-in stagger-1">
                <div className="section-header">
                  <div className="flex items-center gap-2">
                    <h2 className="section-title">Aperçu</h2>
                    {project.source_video_path && (
                      <div className="flex items-center gap-1" style={{ marginLeft: 'var(--space-3)' }}>
                        <button
                          onClick={() => setVideoTab('source')}
                          className={`btn btn-sm ${videoTab === 'source' ? 'btn-primary' : 'btn-ghost'}`}
                          style={{ fontSize: 'var(--text-xs)', padding: '4px 10px' }}
                        >
                          Source
                        </button>
                        {project.output_video_path && (
                          <button
                            onClick={() => setVideoTab('output')}
                            className={`btn btn-sm ${videoTab === 'output' ? 'btn-primary' : 'btn-ghost'}`}
                            style={{ fontSize: 'var(--text-xs)', padding: '4px 10px' }}
                          >
                            Montage
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                  {project.output_video_path && (
                    <a
                      href={getDownloadUrl(project.id)}
                      download
                      className="btn btn-primary btn-sm"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                        <polyline points="7 10 12 15 17 10" />
                        <line x1="12" y1="15" x2="12" y2="3" />
                      </svg>
                      Télécharger
                    </a>
                  )}
                </div>
                <VideoPlayer
                  src={
                    videoTab === 'output' && project.output_video_path
                      ? getVideoUrl(project.id, 'output')
                      : project.source_video_path
                        ? getVideoUrl(project.id, 'source')
                        : undefined
                  }
                />
              </div>

              {/* Overall Progress */}
              <div className="section animate-fade-in stagger-2">
                <div className="section-header">
                  <h2 className="section-title">Progression globale</h2>
                  <span className="text-sm font-semibold" style={{ color: 'var(--accent-violet-light)' }}>
                    {overallProgress}%
                  </span>
                </div>
                <div className="progress-bar" style={{ height: 8, marginBottom: 'var(--space-4)' }}>
                  <div className="progress-bar-fill" style={{ width: `${overallProgress}%` }} />
                </div>
                {stepMessage && project.status === 'processing' && (
                  <p className="text-sm text-secondary">{stepMessage}</p>
                )}
              </div>

              {/* Transcription text */}
              {transcription?.text && (
                <div className="section animate-fade-in stagger-3">
                  <div className="section-header">
                    <h2 className="section-title">Transcription</h2>
                    <span className="badge badge-completed">
                      {transcription.segments?.length || 0} segments
                    </span>
                  </div>
                  <div className="card" style={{ maxHeight: 300, overflowY: 'auto', padding: 'var(--space-4)' }}>
                    <p className="text-sm" style={{ lineHeight: 1.8, color: 'var(--text-secondary)' }}>
                      {transcription.text}
                    </p>
                  </div>
                </div>
              )}

              {/* Assets generated */}
              <div className="section animate-fade-in stagger-3">
                <div className="section-header">
                  <h2 className="section-title">Assets générés</h2>
                </div>
                <div className="card">
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-4)', textAlign: 'center' }}>
                    <div>
                      <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, fontFamily: 'var(--font-display)' }}>
                        {edl?.total_ai_images || 0}
                      </div>
                      <div className="text-xs text-secondary" style={{ marginTop: 'var(--space-1)' }}>Motion Design</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, fontFamily: 'var(--font-display)' }}>
                        {edl?.total_brolls || 0}
                      </div>
                      <div className="text-xs text-secondary" style={{ marginTop: 'var(--space-1)' }}>Clips B-roll</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, fontFamily: 'var(--font-display)' }}>
                        {formatDuration(transcription?.duration || 0)}
                      </div>
                      <div className="text-xs text-secondary" style={{ marginTop: 'var(--space-1)' }}>Durée source</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Sidebar — Pipeline Steps */}
            <div className="animate-fade-in stagger-2">
              <div className="card" style={{ padding: 'var(--space-5)' }}>
                <h3 className="section-title" style={{ marginBottom: 'var(--space-4)' }}>Pipeline</h3>
                <ProgressTracker steps={steps} vertical />
              </div>

              {/* Project Info */}
              <div className="card" style={{ padding: 'var(--space-5)', marginTop: 'var(--space-4)' }}>
                <h3 className="section-title" style={{ marginBottom: 'var(--space-4)' }}>Détails</h3>
                <div className="flex flex-col gap-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-secondary">Résolution</span>
                    <span className="text-sm font-semibold">1080p</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-secondary">Format</span>
                    <span className="text-sm font-semibold">MP4 H.264</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-secondary">Segments</span>
                    <span className="text-sm font-semibold">{edl?.segments?.length || '—'}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-secondary">Langue</span>
                    <span className="text-sm font-semibold">{transcription?.language?.toUpperCase() || '—'}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-secondary">Motion Design</span>
                    <span className="text-sm font-semibold">{motionDesignEnabled ? '✓ Activé' : '✗ Désactivé'}</span>
                  </div>
                </div>
              </div>

              {/* Motion Design Toggle — visible for restart */}
              {(project.status === 'queued' || project.status === 'failed' || project.status === 'completed') && (
                <div className="card" style={{ padding: 'var(--space-4)', marginTop: 'var(--space-4)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                      <span style={{ fontSize: 18 }}>{motionDesignEnabled ? '🎬' : '📹'}</span>
                      <div>
                        <div className="text-sm font-semibold">
                          {motionDesignEnabled ? 'Motion Design' : 'Mode Standard'}
                        </div>
                        <div className="text-xs text-secondary">
                          {motionDesignEnabled ? 'Animations IA activées' : 'Sans motion design'}
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={() => setMotionDesignEnabled(!motionDesignEnabled)}
                      className="btn btn-sm"
                      style={{
                        minWidth: 56,
                        background: motionDesignEnabled ? 'var(--accent-violet)' : 'var(--bg-tertiary)',
                        color: motionDesignEnabled ? '#fff' : 'var(--text-secondary)',
                        border: motionDesignEnabled ? '1px solid var(--accent-violet)' : '1px solid var(--border-primary)',
                        fontWeight: 600,
                        fontSize: 'var(--text-xs)',
                        transition: 'all 0.2s ease',
                      }}
                    >
                      {motionDesignEnabled ? 'ON' : 'OFF'}
                    </button>
                  </div>
                </div>
              )}

              {/* EDL Summary */}
              {edl?.summary && (
                <div className="card" style={{ padding: 'var(--space-5)', marginTop: 'var(--space-4)' }}>
                  <h3 className="section-title" style={{ marginBottom: 'var(--space-3)' }}>Résumé EDL</h3>
                  <p className="text-sm text-secondary" style={{ lineHeight: 1.6 }}>
                    {edl.summary}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
