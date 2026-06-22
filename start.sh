#!/bin/bash
# ── Nabi AI — Script de démarrage ──
# Lance le backend Python et le frontend Next.js

set -e

echo "🚀 Démarrage de Nabi AI..."
echo ""

# Configure pyenv
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)" 2>/dev/null || true

# Configure NVM
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Configure local bin (FFmpeg, etc.)
export PATH="$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Check prerequisites
echo "🔍 Vérification des prérequis..."

if ! command -v ffmpeg &> /dev/null; then
    echo "❌ FFmpeg non trouvé. Installe-le avec: brew install ffmpeg"
    exit 1
fi
echo "  ✅ FFmpeg"

if ! command -v node &> /dev/null; then
    echo "❌ Node.js non trouvé."
    exit 1
fi
echo "  ✅ Node.js $(node --version)"

if [ ! -d "$SCRIPT_DIR/backend/.venv" ]; then
    echo "❌ Virtual environment Python non trouvé. Lance: python -m venv backend/.venv && pip install -r backend/requirements.txt"
    exit 1
fi
echo "  ✅ Python venv"

echo ""

# Start backend
echo "🐍 Lancement du backend Python (port 8000)..."
cd "$SCRIPT_DIR/backend"
source .venv/bin/activate
python main.py &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"

# Wait for backend to be ready
sleep 2

# Start frontend
echo "🌐 Lancement du frontend Next.js (port 3000)..."
cd "$SCRIPT_DIR"
npm run dev &
FRONTEND_PID=$!
echo "  Frontend PID: $FRONTEND_PID"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ Nabi AI est prêt !"
echo ""
echo "  🌐 Frontend : http://localhost:3000"
echo "  🐍 Backend  : http://localhost:8000"
echo "  📚 API Docs : http://localhost:8000/docs"
echo ""
echo "  Appuie sur Ctrl+C pour arrêter."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Handle cleanup
cleanup() {
    echo ""
    echo "🛑 Arrêt de Nabi AI..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID 2>/dev/null
    wait $FRONTEND_PID 2>/dev/null
    echo "👋 À bientôt !"
    exit 0
}

trap cleanup INT TERM

# Wait for both processes
wait
