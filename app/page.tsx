'use client';

import { useState, useCallback, useEffect } from 'react';
import Sidebar from '@/components/Sidebar';
import UploadZone from '@/components/UploadZone';
import ProjectCard, { ProjectStatus } from '@/components/ProjectCard';
import {
  fetchProjects,
  uploadVideo,
  startProcessing,
  deleteProject,
  checkHealth,
  formatDuration,
  formatDate,
  type Project,
  type HealthStatus,
} from '@/lib/api';

export default function Dashboard() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadedFileName, setUploadedFileName] = useState('');
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [backendOnline, setBackendOnline] = useState(false);

  // Load projects and health on mount
  useEffect(() => {
    loadProjects();
    loadHealth();
    const interval = setInterval(loadProjects, 5000); // Refresh every 5s
    return () => clearInterval(interval);
  }, []);

  const loadProjects = async () => {
    try {
      const data = await fetchProjects();
      setProjects(data);
      setBackendOnline(true);
    } catch {
      setBackendOnline(false);
    }
  };

  const loadHealth = async () => {
    try {
      const h = await checkHealth();
      setHealth(h);
      setBackendOnline(true);
    } catch {
      setBackendOnline(false);
    }
  };

  const handleFileSelect = useCallback(async (file: File) => {
    setUploadedFileName(file.name);
    setIsUploading(true);
    setUploadProgress(0);

    try {
      // Simulate upload progress
      const progressInterval = setInterval(() => {
        setUploadProgress((prev) => Math.min(prev + Math.random() * 20, 90));
      }, 300);

      // Upload file
      const project = await uploadVideo(file);

      clearInterval(progressInterval);
      setUploadProgress(100);

      // Start processing immediately
      await startProcessing(project.id);

      setTimeout(() => {
        setIsUploading(false);
        setUploadProgress(0);
        loadProjects();
      }, 500);
    } catch (err: any) {
      console.error('Upload failed:', err);
      setIsUploading(false);
      setUploadProgress(0);
      alert(`Erreur: ${err.message}\n\nVérifie que le backend Python tourne sur localhost:8000`);
    }
  }, []);

  const totalVideos = projects.length;
  const completedVideos = projects.filter((p) => p.status === 'completed').length;
  const processingVideos = projects.filter((p) => p.status === 'processing').length;
  const totalTimeSaved = projects
    .filter((p) => p.status === 'completed' && p.duration_seconds)
    .reduce((acc, p) => acc + (p.duration_seconds || 0) * 3, 0); // Assume 3x time saved

  return (
    <div className="app-layout">
      <Sidebar />
      <main className="main-content">
        <div className="page-container">
          {/* Header */}
          <div className="page-header animate-fade-in">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="page-title">Dashboard</h1>
                <p className="page-subtitle">Montage vidéo automatisé par IA — 100% local</p>
              </div>
              <div className="flex items-center gap-3">
                <span
                  className={`badge ${backendOnline ? 'badge-completed' : 'badge-failed'}`}
                  title={backendOnline ? 'Backend connecté' : 'Backend déconnecté'}
                >
                  <span className="badge-dot" />
                  {backendOnline ? 'Connecté' : 'Backend hors ligne'}
                </span>
                {health && (
                  <>
                    <span className={`badge ${health.ffmpeg ? 'badge-completed' : 'badge-failed'}`}>
                      FFmpeg {health.ffmpeg ? '✓' : '✗'}
                    </span>
                    <span className={`badge ${health.ollama ? 'badge-completed' : 'badge-queued'}`}>
                      Ollama {health.ollama ? '✓' : '—'}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Backend offline warning */}
          {!backendOnline && (
            <div
              className="card section animate-fade-in"
              style={{
                borderColor: 'rgba(249, 115, 22, 0.3)',
                background: 'rgba(249, 115, 22, 0.05)',
              }}
            >
              <div className="flex items-center gap-4">
                <span style={{ fontSize: 28 }}>⚠️</span>
                <div>
                  <p className="font-semibold" style={{ marginBottom: 'var(--space-1)' }}>
                    Backend Python non détecté
                  </p>
                  <p className="text-sm text-secondary">
                    Lance le serveur backend avec : <code style={{
                      background: 'var(--bg-tertiary)',
                      padding: '2px 8px',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: 'var(--text-xs)',
                    }}>
                      cd backend && source .venv/bin/activate && python main.py
                    </code>
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Stats */}
          <div className="stats-grid section animate-fade-in stagger-1">
            <div className="stat-card">
              <div className="stat-card-icon violet">🎬</div>
              <div className="stat-card-value">{totalVideos}</div>
              <div className="stat-card-label">Projets total</div>
            </div>
            <div className="stat-card">
              <div className="stat-card-icon green">✅</div>
              <div className="stat-card-value">{completedVideos}</div>
              <div className="stat-card-label">Terminés</div>
            </div>
            <div className="stat-card">
              <div className="stat-card-icon orange">⚡</div>
              <div className="stat-card-value">{processingVideos}</div>
              <div className="stat-card-label">En cours</div>
            </div>
            <div className="stat-card">
              <div className="stat-card-icon blue">🕐</div>
              <div className="stat-card-value">{formatDuration(totalTimeSaved)}</div>
              <div className="stat-card-label">Temps gagné</div>
            </div>
          </div>

          {/* Upload Zone */}
          <div className="section animate-fade-in stagger-2">
            <div className="section-header">
              <h2 className="section-title">Nouveau projet</h2>
            </div>
            <UploadZone
              onFileSelect={handleFileSelect}
              isUploading={isUploading}
              uploadProgress={uploadProgress}
              uploadedFileName={uploadedFileName}
            />
          </div>

          {/* Projects List */}
          <div className="section animate-fade-in stagger-3">
            <div className="section-header">
              <h2 className="section-title">Projets récents</h2>
              {projects.length > 0 && (
                <span className="badge badge-processing">
                  {projects.length} projet{projects.length > 1 ? 's' : ''}
                </span>
              )}
            </div>

            {projects.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">🎥</div>
                <h3 className="empty-state-title">Aucun projet</h3>
                <p className="empty-state-text">
                  Glisse une vidéo ci-dessus pour lancer ton premier montage automatique avec Nabi AI
                </p>
              </div>
            ) : (
              <div className="projects-grid">
                {projects.map((project) => (
                  <ProjectCard
                    key={project.id}
                    id={project.id}
                    title={project.title}
                    status={project.status as ProjectStatus}
                    duration={formatDuration(project.duration_seconds)}
                    createdAt={formatDate(project.created_at)}
                    progress={project.progress}
                    onDelete={async (id) => {
                      try {
                        await deleteProject(id);
                        loadProjects();
                      } catch (e) {
                        alert('Erreur lors de la suppression');
                      }
                    }}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
