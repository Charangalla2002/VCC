import { useState, useEffect } from 'react'
import { RefreshCw, AlertCircle, Radio, Ruler } from 'lucide-react'
import { useApi } from '../hooks/useApi'
import api from '../lib/api'
import CountingLineEditor from './CountingLineEditor'

const STREAM_BASE = import.meta.env.VITE_STREAM_BASE_URL || `${window.location.protocol}//${window.location.hostname}:8001`

export default function LiveFeedPanel({ lastMessage }) {
  const { data: camerasResp, loading: camsLoading } = useApi('/api/cameras')
  const cameras = camerasResp?.items ?? []
  const [selectedId, setSelectedId] = useState(null)
  const [imgError, setImgError] = useState(false)
  const [imgKey, setImgKey] = useState(0)
  const [liveStats, setLiveStats] = useState(null)
  const [showLineEditor, setShowLineEditor] = useState(false)

  // Pick first camera by default
  useEffect(() => {
    if (cameras?.length && selectedId === null) {
      setSelectedId(cameras[0]?.id ?? cameras[0]?.camera_id)
    }
  }, [cameras, selectedId])

  // Fetch initial stats for selected camera from events history
  useEffect(() => {
    if (!selectedId) return
    setLiveStats(null) // reset stats while loading
    api.get('/api/events', { params: { camera_id: selectedId, limit: 1000 } })
      .then((res) => {
        const items = res.data?.items ?? []
        const stats = { car: 0, bike: 0, heavy: 0, bus: 0 }
        items.forEach((evt) => {
          const cls = evt.vehicle_class
          if (cls === 'car') stats.car += 1
          else if (cls === 'motorcycle' || cls === 'bicycle') stats.bike += 1
          else if (cls === 'truck') stats.heavy += 1
          else if (cls === 'bus') stats.bus += 1
        })
        setLiveStats(stats)
      })
      .catch((err) => {
        console.error("Failed to fetch camera stats:", err)
        setLiveStats({ car: 0, bike: 0, heavy: 0, bus: 0 })
      })
  }, [selectedId])

  // Update live stats & recent events from WebSocket
  const [recentEvents, setRecentEvents] = useState([])

  useEffect(() => {
    if (!lastMessage) return
    if (lastMessage.type === 'new_event') {
      const evt = lastMessage.event
      if (String(evt.camera_id) === String(selectedId)) {
        setRecentEvents((prev) => [evt, ...prev.slice(0, 4)])
        setLiveStats((prev) => {
          const next = prev ? { ...prev } : { car: 0, bike: 0, heavy: 0, bus: 0 }
          const cls = evt.vehicle_class
          if (cls === 'car') next.car += 1
          else if (cls === 'motorcycle' || cls === 'bicycle') next.bike += 1
          else if (cls === 'truck') next.heavy += 1
          else if (cls === 'bus') next.bus += 1
          return next
        })
      }
    }
  }, [lastMessage, selectedId])

  const COLOR_BADGE_STYLES = {
    Red: 'bg-red-500/20 text-red-300 border-red-500/40',
    Orange: 'bg-orange-500/20 text-orange-300 border-orange-500/40',
    Yellow: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40',
    Green: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
    Cyan: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40',
    Blue: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
    Purple: 'bg-purple-500/20 text-purple-300 border-purple-500/40',
    Pink: 'bg-pink-500/20 text-pink-300 border-pink-500/40',
    White: 'bg-slate-100/20 text-slate-100 border-slate-300/40',
    Black: 'bg-zinc-800 text-zinc-300 border-zinc-700',
    Silver: 'bg-slate-400/20 text-slate-300 border-slate-400/40',
    Unknown: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  }

  const selectedCam = cameras?.find((c) => (c.id ?? c.camera_id) === selectedId)
  const streamSrc = selectedId ? `${STREAM_BASE}/stream/${selectedId}` : null

  const handleCameraChange = (e) => {
    setSelectedId(e.target.value)
    setImgError(false)
    setImgKey((k) => k + 1)
  }

  const handleRetry = () => {
    setImgError(false)
    setImgKey((k) => k + 1)
  }

  return (
    <div className="flex flex-col gap-3 h-full">
      {/* ── Camera selector ── */}
      <div className="flex items-center gap-3">
        <label className="text-text-muted text-xs font-medium uppercase tracking-widest whitespace-nowrap">
          Camera
        </label>
        <div className="relative flex-1 max-w-[260px]">
          <select
            value={selectedId ?? ''}
            onChange={handleCameraChange}
            disabled={camsLoading}
            className="w-full bg-bg border border-bg-border rounded-lg px-3 py-2 text-text-primary text-sm
                       appearance-none cursor-pointer hover:border-accent-cyan/40 transition-colors"
          >
            {camsLoading && <option value="">Loading cameras…</option>}
            {!camsLoading && !cameras?.length && <option value="">No cameras found</option>}
            {cameras?.map((cam) => {
              const id = cam.id ?? cam.camera_id
              return (
                <option key={id} value={id}>
                  {cam.name ?? `Camera ${id}`} — {cam.location ?? ''}
                </option>
              )
            })}
          </select>
          <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-text-muted text-xs">▾</div>
        </div>
        {/* Configure Lines button */}
        {selectedCam && (
          <button
            onClick={() => setShowLineEditor(true)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-bg border border-bg-border text-text-secondary text-xs hover:border-accent-cyan/40 hover:text-accent-cyan transition-all"
          >
            <Ruler size={13} />
            Configure Lines
          </button>
        )}
      </div>

      {/* ── Stream container ── */}
      <div className="relative flex-1 min-h-[360px] rounded-xl overflow-hidden bg-black border border-bg-border flex items-center justify-center">
        {/* MJPEG stream */}
        {streamSrc && !imgError && (
          <img
            key={imgKey}
            src={streamSrc}
            alt="Live camera feed"
            className="w-full h-full object-contain max-h-[520px]"
            onError={() => setImgError(true)}
          />
        )}

        {/* Offline state */}
        {(imgError || !streamSrc) && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-bg">
            <AlertCircle size={36} className="text-text-muted" />
            <p className="text-text-muted text-sm">
              {!streamSrc ? 'No camera selected' : 'Camera offline or stream unavailable'}
            </p>
            {imgError && (
              <button
                onClick={handleRetry}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-bg-hover border border-bg-border
                           text-text-secondary text-xs hover:border-accent-cyan/40 hover:text-accent-cyan transition-all"
              >
                <RefreshCw size={13} />
                Retry
              </button>
            )}
          </div>
        )}

        {/* Top-left: camera info */}
        {selectedCam && (
          <div className="absolute top-3 left-3 flex items-center gap-2 px-3 py-1.5 rounded-full glass text-xs">
            <span className="w-2 h-2 rounded-full bg-accent-red live-pulse" />
            <span className="text-text-primary font-medium">{selectedCam.name ?? `Camera ${selectedId}`}</span>
            <span className="text-text-muted">·</span>
            <span className="text-text-muted">{selectedCam.location ?? '—'}</span>
          </div>
        )}

        {/* Bottom-left: LIVE label */}
        {streamSrc && !imgError && (
          <div className="absolute bottom-3 left-3 flex items-center gap-1.5 text-xs">
            <Radio size={11} className="text-accent-red live-pulse" />
            <span className="text-text-secondary font-semibold uppercase tracking-wide">LIVE</span>
          </div>
        )}
      </div>

      {/* Live Detections Ticker */}
      {recentEvents.length > 0 && (
        <div className="bg-bg-card border border-bg-border rounded-xl p-3 space-y-2">
          <div className="text-xs font-semibold text-text-muted uppercase tracking-wider">Live Detections</div>
          <div className="flex flex-wrap gap-2">
            {recentEvents.map((evt, idx) => {
              const colorName = evt.vehicle_color || 'Unknown'
              const badgeStyle = COLOR_BADGE_STYLES[colorName] || COLOR_BADGE_STYLES.Unknown
              const clsLabel = evt.vehicle_class ? evt.vehicle_class.replace('_', ' ').toUpperCase() : 'VEHICLE'

              return (
                <div key={idx} className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-bg border border-bg-border text-xs">
                  <span className={`px-1.5 py-0.5 rounded border text-[10px] font-semibold ${badgeStyle}`}>
                    {colorName}
                  </span>
                  <span className="font-bold text-text-primary">{clsLabel}</span>
                  <span className="text-text-muted">#{evt.track_id}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Counting Line Editor Modal */}
      {showLineEditor && selectedCam && (
        <CountingLineEditor
          camera={selectedCam}
          onClose={() => setShowLineEditor(false)}
          onSaved={() => {
            setShowLineEditor(false)
            setImgKey(k => k + 1)
          }}
        />
      )}
    </div>
  )
}
