'use client';

export type StepStatus = 'pending' | 'active' | 'completed' | 'failed';

interface Step {
  id: string;
  title: string;
  subtitle?: string;
  status: StepStatus;
}

interface ProgressTrackerProps {
  steps: Step[];
  vertical?: boolean;
}

export default function ProgressTracker({ steps, vertical = false }: ProgressTrackerProps) {
  const getStepIcon = (status: StepStatus, index: number) => {
    switch (status) {
      case 'completed':
        return (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        );
      case 'failed':
        return (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        );
      case 'active':
        return (
          <div style={{ width: 12, height: 12, border: '2px solid currentColor', borderTop: '2px solid transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
        );
      default:
        return <span>{index + 1}</span>;
    }
  };

  if (vertical) {
    return (
      <div className="flex flex-col gap-2">
        {steps.map((step, index) => (
          <div key={step.id}>
            <div className={`progress-step ${step.status}`} style={{ padding: 'var(--space-3) 0' }}>
              <div className="progress-step-indicator">
                {getStepIcon(step.status, index)}
              </div>
              <div className="progress-step-content">
                <div className="progress-step-title">{step.title}</div>
                {step.subtitle && <div className="progress-step-subtitle">{step.subtitle}</div>}
              </div>
            </div>
            {index < steps.length - 1 && (
              <div
                style={{
                  width: 2,
                  height: 24,
                  marginLeft: 17,
                  borderRadius: 'var(--radius-full)',
                  background: step.status === 'completed' ? 'var(--accent-green)' : 'var(--border-default)',
                  transition: 'background var(--transition-base)',
                }}
              />
            )}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="progress-tracker">
      {steps.map((step, index) => (
        <div key={step.id} style={{ display: 'contents' }}>
          <div className={`progress-step ${step.status}`}>
            <div className="progress-step-indicator">
              {getStepIcon(step.status, index)}
            </div>
            <div className="progress-step-content">
              <div className="progress-step-title">{step.title}</div>
              {step.subtitle && <div className="progress-step-subtitle">{step.subtitle}</div>}
            </div>
          </div>
          {index < steps.length - 1 && (
            <div className={`progress-step-connector ${step.status === 'completed' ? 'completed' : ''}`} />
          )}
        </div>
      ))}
    </div>
  );
}
