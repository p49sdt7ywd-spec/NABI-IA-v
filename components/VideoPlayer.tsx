'use client';

import { useRef, useState } from 'react';

interface VideoPlayerProps {
  src?: string;
  poster?: string;
}

export default function VideoPlayer({ src, poster }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);

  const togglePlay = () => {
    if (!videoRef.current || !src) return;
    if (videoRef.current.paused) {
      videoRef.current.play();
      setIsPlaying(true);
    } else {
      videoRef.current.pause();
      setIsPlaying(false);
    }
  };

  if (!src) {
    return (
      <div className="video-player-container">
        <div className="video-player-placeholder">
          <div className="video-player-placeholder-icon">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--accent-violet)' }}>
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
          </div>
          <div>
            <p style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>Aucune vidéo</p>
            <p style={{ fontSize: 'var(--text-xs)', marginTop: 'var(--space-1)' }}>
              La vidéo apparaîtra ici une fois le montage terminé
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="video-player-container" onClick={togglePlay} style={{ cursor: 'pointer' }}>
      <video
        ref={videoRef}
        src={src}
        poster={poster}
        onEnded={() => setIsPlaying(false)}
        style={{ width: '100%', height: '100%', objectFit: 'contain' }}
      />
      {!isPlaying && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(0,0,0,0.3)',
            transition: 'opacity var(--transition-fast)',
          }}
        >
          <div
            style={{
              width: 64,
              height: 64,
              borderRadius: '50%',
              background: 'rgba(139, 92, 246, 0.9)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: 'var(--shadow-glow-violet)',
            }}
          >
            <svg width="28" height="28" viewBox="0 0 24 24" fill="white">
              <polygon points="6 3 20 12 6 21 6 3" />
            </svg>
          </div>
        </div>
      )}
    </div>
  );
}
