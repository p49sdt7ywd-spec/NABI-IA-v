'use client';

import { useState, useRef, useCallback } from 'react';

interface UploadZoneProps {
  onFileSelect: (file: File) => void;
  isUploading?: boolean;
  uploadProgress?: number;
  uploadedFileName?: string;
}

export default function UploadZone({
  onFileSelect,
  isUploading = false,
  uploadProgress = 0,
  uploadedFileName,
}: UploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const acceptedFormats = ['MP4', 'MOV', 'MKV', 'AVI', 'WEBM'];
  const acceptedMimes = 'video/mp4,video/quicktime,video/x-matroska,video/avi,video/webm';

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);

      const files = e.dataTransfer.files;
      if (files.length > 0 && files[0].type.startsWith('video/')) {
        onFileSelect(files[0]);
      }
    },
    [onFileSelect]
  );

  const handleClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      onFileSelect(files[0]);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  };

  if (isUploading) {
    return (
      <div className="upload-progress-container animate-scale-in">
        <div className="upload-progress-info">
          <div className="upload-progress-filename">
            <span style={{ fontSize: '20px' }}>🎬</span>
            {uploadedFileName}
          </div>
          <span className="upload-progress-percent">{Math.round(uploadProgress)}%</span>
        </div>
        <div className="progress-bar">
          <div className="progress-bar-fill" style={{ width: `${uploadProgress}%` }} />
        </div>
        <p className="form-hint mt-2">Copie du fichier en cours...</p>
      </div>
    );
  }

  return (
    <>
      <div
        className={`upload-zone ${isDragging ? 'dragging' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleClick}
      >
        <div className="upload-zone-icon">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--accent-violet-light)' }}>
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </div>
        <h3 className="upload-zone-title">
          {isDragging ? 'Dépose ta vidéo ici !' : 'Glisse ta vidéo ici'}
        </h3>
        <p className="upload-zone-subtitle">
          ou <span style={{ color: 'var(--accent-violet-light)', fontWeight: 600 }}>clique pour parcourir</span>
        </p>
        <div className="upload-zone-formats">
          {acceptedFormats.map((format) => (
            <span key={format} className="upload-zone-format-tag">{format}</span>
          ))}
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept={acceptedMimes}
        onChange={handleFileChange}
        style={{ display: 'none' }}
      />
    </>
  );
}
