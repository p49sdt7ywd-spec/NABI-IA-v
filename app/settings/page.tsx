'use client';

import { useState, useEffect } from 'react';
import Sidebar from '@/components/Sidebar';
import { fetchSettings, saveSettings, type Settings } from '@/lib/api';

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings>({
    pexels_api_key: '',
    ollama_model: 'qwen3:4b',
    whisper_model: 'mlx-community/whisper-large-v3-turbo',
    motion_mode: 'hyperframes',
    da_primary: '#FF7820',
    da_secondary: '#1E1E28',
    da_background: '#FFFFFF',
    da_accent_2: '#326FA8',
    output_resolution: '1080p',
    output_dir: '~/nabi-ai/projects',
    pip_enabled: 'true',
    remove_silences: 'true',
  });
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const data = await fetchSettings();
      setSettings(data);
      setLoading(false);
    } catch {
      setLoading(false);
      setError('Backend non connecté. Les paramètres seront sauvegardés une fois le backend lancé.');
    }
  };

  const handleSave = async () => {
    try {
      await saveSettings(settings);
      setSaved(true);
      setError('');
      setTimeout(() => setSaved(false), 2000);
    } catch {
      setError('Impossible de sauvegarder. Vérifie que le backend est lancé.');
    }
  };

  const update = (key: keyof Settings, value: string) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  const toggleBool = (key: keyof Settings) => {
    setSettings((prev) => ({
      ...prev,
      [key]: prev[key] === 'true' ? 'false' : 'true',
    }));
  };

  return (
    <div className="app-layout">
      <Sidebar />
      <main className="main-content">
        <div className="page-container" style={{ maxWidth: 800 }}>
          {/* Header */}
          <div className="page-header animate-fade-in">
            <h1 className="page-title">Configuration</h1>
            <p className="page-subtitle">Paramètres de Nabi AI — API keys, modèles, préférences</p>
          </div>

          {/* Error banner */}
          {error && (
            <div
              className="card section animate-fade-in"
              style={{ borderColor: 'rgba(249, 115, 22, 0.3)', background: 'rgba(249, 115, 22, 0.05)' }}
            >
              <p className="text-sm" style={{ color: 'var(--accent-orange-light)' }}>⚠️ {error}</p>
            </div>
          )}

          {/* API Keys */}
          <div className="card section animate-fade-in stagger-1">
            <h3 className="section-title" style={{ marginBottom: 'var(--space-5)' }}>
              🔑 Clés API
            </h3>

            <div className="form-group">
              <label className="form-label">Pexels API Key</label>
              <input
                type="password"
                className="form-input"
                placeholder="Colle ta clé API Pexels ici..."
                value={settings.pexels_api_key}
                onChange={(e) => update('pexels_api_key', e.target.value)}
              />
              <p className="form-hint">
                Gratuit — Obtiens ta clé sur{' '}
                <a href="https://www.pexels.com/api/" target="_blank" rel="noopener" style={{ color: 'var(--accent-violet-light)' }}>
                  pexels.com/api
                </a>
              </p>
            </div>
          </div>

          {/* AI Models */}
          <div className="card section animate-fade-in stagger-2">
            <h3 className="section-title" style={{ marginBottom: 'var(--space-5)' }}>
              🤖 Modèles IA
            </h3>

            <div className="form-group">
              <label className="form-label">Modèle Ollama (Orchestrateur)</label>
              <select
                className="form-select"
                value={settings.ollama_model}
                onChange={(e) => update('ollama_model', e.target.value)}
              >
                <option value="qwen3:4b">Qwen 3 4B (Recommandé — 18GB RAM)</option>
                <option value="gemma4:12b">Gemma 4 12B</option>
                <option value="llama3.2:8b">Llama 3.2 8B</option>
                <option value="deepseek-r1:7b">DeepSeek R1 7B</option>
              </select>
              <p className="form-hint">Le LLM qui analyse ton script et prend les décisions de montage</p>
            </div>

            <div className="form-group">
              <label className="form-label">Modèle Whisper (Transcription)</label>
              <select
                className="form-select"
                value={settings.whisper_model}
                onChange={(e) => update('whisper_model', e.target.value)}
              >
                <option value="mlx-community/whisper-large-v3-turbo">Large V3 Turbo (Recommandé)</option>
                <option value="mlx-community/whisper-large-v3">Large V3 (Plus précis, plus lent)</option>
                <option value="mlx-community/whisper-medium">Medium (Plus rapide)</option>
                <option value="mlx-community/whisper-small">Small (Le plus rapide)</option>
              </select>
              <p className="form-hint">Optimisé pour Apple Silicon via MLX</p>
            </div>

            <div className="form-group">
              <label className="form-label">Mode Motion Design</label>
              <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
                <button
                  className={`btn ${settings.motion_mode === 'hyperframes' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => update('motion_mode', 'hyperframes')}
                  style={{ flex: 1 }}
                >
                  🎬 HyperFrames
                  <span style={{ fontSize: 'var(--text-xs)', opacity: 0.7, display: 'block', fontWeight: 400 }}>
                    Motion design animé (recommandé)
                  </span>
                </button>
                <button
                  className={`btn ${settings.motion_mode === 'pillow' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => update('motion_mode', 'pillow')}
                  style={{ flex: 1 }}
                >
                  🖼️ Pillow
                  <span style={{ fontSize: 'var(--text-xs)', opacity: 0.7, display: 'block', fontWeight: 400 }}>
                    Images statiques (fallback)
                  </span>
                </button>
              </div>
              <p className="form-hint">
                HyperFrames crée des clips motion design animés (HTML/CSS/GSAP → MP4).
                L'IA orchestrateur génère le HTML adapté au contenu de la transcription.
              </p>
            </div>

            {/* DA Color Palette */}
            <div className="form-group">
              <label className="form-label">Palette DA (Direction Artistique)</label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                  <input
                    type="color"
                    value={settings.da_primary}
                    onChange={(e) => update('da_primary', e.target.value)}
                    style={{ width: 40, height: 40, border: 'none', borderRadius: 8, cursor: 'pointer', background: 'none' }}
                  />
                  <div>
                    <div className="text-sm font-semibold">Primaire</div>
                    <div className="text-xs text-tertiary">Accents, icônes</div>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                  <input
                    type="color"
                    value={settings.da_secondary}
                    onChange={(e) => update('da_secondary', e.target.value)}
                    style={{ width: 40, height: 40, border: 'none', borderRadius: 8, cursor: 'pointer', background: 'none' }}
                  />
                  <div>
                    <div className="text-sm font-semibold">Secondaire</div>
                    <div className="text-xs text-tertiary">Texte principal</div>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                  <input
                    type="color"
                    value={settings.da_background}
                    onChange={(e) => update('da_background', e.target.value)}
                    style={{ width: 40, height: 40, border: 'none', borderRadius: 8, cursor: 'pointer', background: 'none' }}
                  />
                  <div>
                    <div className="text-sm font-semibold">Fond</div>
                    <div className="text-xs text-tertiary">Arrière-plan</div>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                  <input
                    type="color"
                    value={settings.da_accent_2}
                    onChange={(e) => update('da_accent_2', e.target.value)}
                    style={{ width: 40, height: 40, border: 'none', borderRadius: 8, cursor: 'pointer', background: 'none' }}
                  />
                  <div>
                    <div className="text-sm font-semibold">Accent 2</div>
                    <div className="text-xs text-tertiary">Données, graphiques</div>
                  </div>
                </div>
              </div>
              <p className="form-hint" style={{ marginTop: 'var(--space-2)' }}>
                Ces couleurs sont utilisées par l'IA pour générer les motion designs.
              </p>
            </div>
          </div>

          {/* Export Settings */}
          <div className="card section animate-fade-in stagger-3">
            <h3 className="section-title" style={{ marginBottom: 'var(--space-5)' }}>
              🎬 Export & Rendu
            </h3>

            <div className="form-group">
              <label className="form-label">Résolution de sortie</label>
              <select
                className="form-select"
                value={settings.output_resolution}
                onChange={(e) => update('output_resolution', e.target.value)}
              >
                <option value="1080p">1080p (Full HD) — Recommandé</option>
                <option value="720p">720p (HD) — Plus rapide</option>
                <option value="4k">4K (Ultra HD) — Plus lent</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Dossier de sortie</label>
              <input
                type="text"
                className="form-input"
                value={settings.output_dir}
                onChange={(e) => update('output_dir', e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label" style={{ marginBottom: 'var(--space-3)' }}>Options de montage</label>
              <div className="flex flex-col gap-4">
                <div className="form-toggle" onClick={() => toggleBool('pip_enabled')}>
                  <div className={`form-toggle-track ${settings.pip_enabled === 'true' ? 'active' : ''}`}>
                    <div className="form-toggle-thumb" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold">Picture-in-Picture (PiP)</div>
                    <div className="text-xs text-tertiary">Afficher le speaker pendant les B-rolls</div>
                  </div>
                </div>

                <div className="form-toggle" onClick={() => toggleBool('remove_silences')}>
                  <div className={`form-toggle-track ${settings.remove_silences === 'true' ? 'active' : ''}`}>
                    <div className="form-toggle-thumb" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold">Supprimer les silences</div>
                    <div className="text-xs text-tertiary">Couper automatiquement les pauses et temps morts</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Save Button */}
          <div className="animate-fade-in stagger-4" style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-3)' }}>
            {saved && (
              <span className="badge badge-completed animate-scale-in" style={{ alignSelf: 'center' }}>
                ✓ Sauvegardé
              </span>
            )}
            <button className="btn btn-primary btn-lg" onClick={handleSave}>
              Sauvegarder les paramètres
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
