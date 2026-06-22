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
