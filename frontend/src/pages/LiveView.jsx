import { useState, useEffect } from 'react'
import { useOutletContext } from 'react-router-dom'
import { Activity } from 'lucide-react'
import LiveFeedPanel from '../components/LiveFeedPanel'
import { useApi } from '../hooks/useApi'
import { EditableColorBadge } from '../components/EditableColorBadge'

export default function LiveView() {
  const { lastMessage, connectionStatus } = useOutletContext()
  const [events, setEvents] = useState([])
  const { data: camerasResp, loading: camerasLoading } = useApi('/api/cameras')
  const cameras = camerasResp?.items ?? []

  useEffect(() => {
    if (lastMessage && lastMessage.type === 'new_event') {
      setEvents(prev => [lastMessage.event, ...prev].slice(0, 20)) // Keep last 20 events
    }
  }, [lastMessage])

  return (
    <div className="p-6 h-full flex flex-col gap-6 overflow-y-auto custom-scrollbar">
      {/* Header Bar */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-black bg-gradient-to-r from-accent-red to-accent-amber bg-clip-text text-transparent flex items-center gap-3">
            <Activity className="text-accent-red animate-pulse" />
            Live View
          </h1>
          <p className="text-text-secondary mt-1">Real-time camera feed and event stream</p>
        </div>
        <div className="flex items-center gap-3 bg-bg-card border border-bg-border px-4 py-2 rounded-full shadow-md">
          <div className={`w-3 h-3 rounded-full ${connectionStatus === 'connected' ? 'bg-accent-green animate-pulse' : 'bg-accent-red'}`}></div>
          <span className="text-sm font-medium text-text-primary uppercase tracking-wide">
            {connectionStatus}
          </span>
        </div>
      </div>

      {/* Main Full-Width Camera Feed Card */}
      <div className="w-full bg-bg-card rounded-2xl border border-bg-border shadow-2xl p-5">
        <LiveFeedPanel lastMessage={lastMessage} />
      </div>

      {/* Full-Width Recent Events Section Below */}
      <div className="w-full bg-bg-card rounded-2xl border border-bg-border shadow-2xl p-5 flex flex-col">
        <h2 className="text-text-secondary uppercase tracking-widest text-xs font-bold flex items-center gap-2 mb-4 pb-2 border-b border-bg-border">
          <span className="w-2.5 h-2.5 rounded-full bg-accent-cyan animate-pulse"></span>
          Recent Events
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {events.length === 0 ? (
            <div className="col-span-full text-center text-text-muted py-8 text-sm">
              Waiting for real-time events...
            </div>
          ) : (
            events.map((evt, idx) => (
              <div key={idx} className="bg-slate-900/80 border border-slate-800 rounded-xl p-3 text-sm shadow-md flex flex-col justify-between">
                <div className="flex justify-between items-start mb-2">
                  <span className="font-bold text-slate-100 capitalize">{evt.vehicle_class}</span>
                  <span className="text-[11px] text-slate-400 font-mono">
                    {new Intl.DateTimeFormat(undefined, { timeStyle: 'medium' }).format(new Date(evt.timestamp || Date.now()))}
                  </span>
                </div>
                <div className="text-xs text-slate-400 flex justify-between items-center mt-2 pt-2 border-t border-slate-800/80">
                  <span>Cam: {evt.camera_id}</span>
                  <EditableColorBadge eventId={evt.id} initialColor={evt.vehicle_color || 'Unknown'} />
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
