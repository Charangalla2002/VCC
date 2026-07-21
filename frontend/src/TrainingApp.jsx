import { useState, useEffect } from 'react'
import { Cpu, ExternalLink, ShieldCheck } from 'lucide-react'
import TrainingStudio from './pages/TrainingStudio'
import { refreshAccessToken } from './lib/auth'

export default function TrainingApp() {
  const [initializing, setInitializing] = useState(true)

  useEffect(() => {
    const initAuth = async () => {
      try {
        const params = new URLSearchParams(window.location.search)
        const urlToken = params.get('token')
        if (urlToken) {
          localStorage.setItem('vcc_access_token', urlToken)
        }
        await refreshAccessToken()
      } catch (err) {
        console.log("Session init check complete.")
      } finally {
        setInitializing(false)
      }
    }
    initAuth()
  }, [])

  if (initializing) {
    return (
      <div className="min-h-screen bg-bg flex flex-col items-center justify-center gap-3">
        <span className="w-10 h-10 border-4 border-accent-purple border-t-transparent rounded-full animate-spin"></span>
        <span className="text-text-secondary text-sm font-semibold tracking-wide">Initializing Training Studio Session...</span>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-bg flex flex-col overflow-x-hidden">
      {/* Top Navigation Header for Isolated Training App */}
      <header className="bg-bg-card border-b border-bg-border px-6 py-4 flex items-center justify-between shadow-card sticky top-0 z-30">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-accent-purple to-accent-cyan flex items-center justify-center shadow-glow-cyan">
            <Cpu size={20} className="text-white" />
          </div>
          <div>
            <h1 className="text-base font-bold bg-gradient-to-r from-accent-purple to-accent-cyan bg-clip-text text-transparent leading-tight">
              VCC Model Training Studio
            </h1>
            <p className="text-xs text-text-muted">Dedicated Isolated Workspace — Port 5174</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-accent-purple/10 border border-accent-purple/20 text-accent-purple text-xs font-semibold">
            <ShieldCheck size={14} />
            <span>Isolated Training Mode</span>
          </div>
          <a
            href="http://localhost:5173"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-bg-hover border border-bg-border text-text-secondary hover:text-accent-cyan hover:border-accent-cyan/30 text-xs font-medium transition-all"
          >
            <span>Back to Dashboard (5173)</span>
            <ExternalLink size={13} />
          </a>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 p-6 max-w-7xl mx-auto w-full">
        <TrainingStudio />
      </main>
    </div>
  )
}
