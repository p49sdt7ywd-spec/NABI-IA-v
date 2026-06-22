'use client';

import Link from 'next/link';

export type ProjectStatus = 'queued' | 'processing' | 'completed' | 'failed';

interface ProjectCardProps {
  id: string;
  title: string;
  status: ProjectStatus;
  thumbnailUrl?: string;
  duration?: string;
  createdAt: string;
  progress?: number;
  onDelete?: (id: string) => void;
}

const statusConfig: Record<ProjectStatus, { label: string; className: string }> = {
  queued: { label: 'En attente', className: 'badge-queued' },
  processing: { label: 'En cours', className: 'badge-processing' },
  completed: { label: 'Terminé', className: 'badge-completed' },
  failed: { label: 'Erreur', className: 'badge-failed' },
};

export default function ProjectCard({
  id,
  title,
  status,
  thumbnailUrl,
  duration,
  createdAt,
  progress,
  onDelete,
}: ProjectCardProps) {
  const { label, className } = statusConfig[status];

  return (
    <Link href={`/project/${id}`} style={{ textDecoration: 'none' }}>
      <div className="project-card">
        <div className="project-card-thumbnail">
          {thumbnailUrl ? (
            <img src={thumbnailUrl} alt={title} />
          ) : (
            <div
              style={{
                width: '100%',
                height: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'linear-gradient(135deg, var(--bg-tertiary) 0%, var(--bg-elevated) 100%)',
                fontSize: '40px',
              }}
            >
              🎬
            </div>
          )}

          <div className="project-card-thumbnail-overlay">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="white" opacity="0.9">
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
          </div>

          {duration && <div className="project-card-duration">{duration}</div>}

          {/* Delete button */}
          {onDelete && (
            <button
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                if (confirm('Supprimer ce projet ?')) onDelete(id);
              }}
              style={{
                position: 'absolute',
                top: 8,
                right: 8,
                width: 28,
                height: 28,
                borderRadius: '50%',
                background: 'rgba(239, 68, 68, 0.85)',
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                opacity: 0,
                transition: 'opacity 0.2s',
                zIndex: 5,
              }}
              className="project-card-delete-btn"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              </svg>
            </button>
          )}
        </div>

        <div className="project-card-body">
          <h4 className="project-card-title">{title}</h4>

          {status === 'processing' && progress !== undefined && (
            <div className="progress-bar" style={{ marginBottom: 'var(--space-3)' }}>
              <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
            </div>
          )}

          <div className="project-card-meta">
            <span className="project-card-date">{createdAt}</span>
            <span className={`badge ${className}`}>
              <span className="badge-dot" />
              {label}
            </span>
          </div>
        </div>
      </div>
    </Link>
  );
}
