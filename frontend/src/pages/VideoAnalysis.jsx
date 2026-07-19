import { useState, useEffect, useCallback, useRef } from 'react'
import {
  FileVideo,
  UploadCloud,
  Trash2,
  Download,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
  XCircle,
  Radio,
  ArrowDown,
  ArrowUp,
  X,
} from 'lucide-react'
import {
  PieChart,
  Pie,
  Cell,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { useApi } from '../hooks/useApi'
import api from '../lib/api'

// ─── Config ───────────────────────────────────────────────────────────────────
const STREAM_BASE =
  import.meta.env.VITE_STREAM_BASE_URL ||
  `${window.location.protocol}//${window.location.hostname}:8001`

const ACCEPTED_EXTENSIONS = ['.mp4', '.avi', '.mov', '.mkv', '.webm']
const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(',')
const LIST_POLL_MS = 4000

const CLASS_COLORS = {
  car: 'var(--chart-car)',
  van: 'var(--chart-car)',
  motorcycle: 'var(--chart-bike)',
  bike: 'var(--chart-bike)',
  truck: 'var(--chart-heavy)',
  heavy: 'var(--chart-heavy)',
  bus: 'var(--chart-bus)',
  bicycle: 'var(--chart-bicycle)',
}
const FALLBACK_COLORS = [
  'var(--accent-cyan)',
  'var(--accent-purple)',
  'var(--accent-amber)',
  'var(--accent-green)',
  'var(--accent-blue)',
  'var(--accent-red)',
]

const STATUS_CONFIG = {
  pending: {
    label: 'Queued',
    icon: Clock,
    badge: 'bg-accent-amber/10 text-accent-amber border-accent-amber/30',
    dot: 'bg-accent-amber',
  },
  processing: {
    label: 'Processing',
    icon: Loader2,
    badge: 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/30',
    dot: 'bg-accent-cyan',
  },
  completed: {
    label: 'Completed',
    icon: CheckCircle2,
    badge: 'bg-accent-green/10 text-accent-green border-accent-green/30',
    dot: 'bg-accent-green',
  },
  failed: {
    label: 'Failed',
    icon: XCircle,
    badge: 'bg-accent-red/10 text-accent-red border-accent-red/30',
    dot: 'bg-accent-red',
  },
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function formatBytes(bytes) {
  const n = Number(bytes)
  if (!Number.isFinite(n) || n <= 0) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), units.length - 1)
  const value = n / Math.pow(1024, i)
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

function formatTimestamp(ts) {
  if (!ts) return '—'
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return String(ts)
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(d)
}

function formatClockTick(ts) {
  if (ts === null || ts === undefined) return ''
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return String(ts)
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(d)
}

function getExtension(filename = '') {
  const idx = filename.lastIndexOf('.')
  return idx === -1 ? '' : filename.slice(idx).toLowerCase()
}

/** Normalise FastAPI / proxy error payloads into a readable single line. */
function apiErrorMessage(err, fallback = 'Something went wrong.') {
  const status = err?.response?.status
  if (status === 413) {
    return 'That file is too large for the server to accept. Try a shorter clip or a lower resolution.'
  }
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const msgs = detail.map((d) => d?.msg || (typeof d === 'string' ? d : null)).filter(Boolean)
    if (msgs.length) return msgs.join('; ')
  }
  if (detail && typeof detail === 'object' && detail.msg) return detail.msg
  if (status === 400) return 'The server rejected this file. Check that it is a supported video format.'
  if (typeof err?.response?.data === 'string' && err.response.data.length < 200) {
    return err.response.data
  }
  return err?.message || fallback
}

function classColor(name, index) {
  return CLASS_COLORS[String(name).toLowerCase()] ?? FALLBACK_COLORS[index % FALLBACK_COLORS.length]
}

// ─── Status badge ─────────────────────────────────────────────────────────────
function StatusBadge({ status, size = 'sm' }) {
  const cfg = STATUS_CONFIG[status] ?? {
    label: status || 'Unknown',
    icon: AlertCircle,
    badge: 'bg-text-muted/10 text-text-muted border-bg-border',
  }
  const Icon = cfg.icon
  const spin = status === 'processing'
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-semibold uppercase tracking-wide
        ${size === 'sm' ? 'px-2.5 py-1 text-[10px]' : 'px-3 py-1.5 text-xs'} ${cfg.badge}`}
    >
      <Icon size={size === 'sm' ? 11 : 13} className={spin ? 'animate-spin' : ''} />
      {cfg.label}
    </span>
  )
}

// ─── Inline error / notice strip ──────────────────────────────────────────────
function InlineMessage({ tone = 'error', children, onDismiss }) {
  const tones = {
    error: 'bg-accent-red/10 border-accent-red/30 text-accent-red',
    success: 'bg-accent-green/10 border-accent-green/30 text-accent-green',
    info: 'bg-accent-cyan/10 border-accent-cyan/30 text-accent-cyan',
  }
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={`flex items-start gap-2 rounded-lg border px-3 py-2.5 text-xs leading-relaxed ${tones[tone]}`}
    >
      {tone === 'error' ? (
        <AlertCircle size={14} className="mt-px flex-shrink-0" />
      ) : (
        <CheckCircle2 size={14} className="mt-px flex-shrink-0" />
      )}
      <span className="min-w-0 flex-1 break-words">{children}</span>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="flex-shrink-0 opacity-70 transition-opacity hover:opacity-100"
          aria-label="Dismiss message"
        >
          <X size={13} />
        </button>
      )}
    </div>
  )
}

// ─── Upload panel ─────────────────────────────────────────────────────────────
function UploadPanel({ onUploaded }) {
  const inputRef = useRef(null)
  const [dragActive, setDragActive] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const dragDepth = useRef(0)

  const upload = useCallback(
    async (file) => {
      setError(null)
      setSuccess(null)

      if (!file) return

      const ext = getExtension(file.name)
      if (!ACCEPTED_EXTENSIONS.includes(ext)) {
        setError(
          `"${file.name}" is not a supported video file${ext ? ` (${ext})` : ''}. ` +
            `Accepted formats: ${ACCEPTED_EXTENSIONS.join(', ')}.`,
        )
        return
      }
      if (file.size === 0) {
        setError(`"${file.name}" is empty (0 bytes).`)
        return
      }

      const form = new FormData()
      form.append('file', file)
      form.append('name', file.name.replace(/\.[^.]+$/, ''))

      setUploading(true)
      setProgress(0)
      try {
        const res = await api.post('/api/videos/upload', form, {
          headers: { 'Content-Type': 'multipart/form-data' },
          onUploadProgress: (evt) => {
            if (evt.total) {
              setProgress(Math.round((evt.loaded * 100) / evt.total))
            } else if (evt.loaded) {
              // Total unknown (e.g. chunked) — show indeterminate-ish progress
              setProgress((p) => (p < 90 ? p + 5 : p))
            }
          },
        })
        setSuccess(`"${res.data?.name || file.name}" uploaded. Processing will begin shortly.`)
        onUploaded?.(res.data)
      } catch (err) {
        setError(apiErrorMessage(err, 'Upload failed. Please try again.'))
      } finally {
        setUploading(false)
        setProgress(0)
        if (inputRef.current) inputRef.current.value = ''
      }
    },
    [onUploaded],
  )

  const handleDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    dragDepth.current = 0
    setDragActive(false)
    if (uploading) return
    const file = e.dataTransfer?.files?.[0]
    upload(file)
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    e.stopPropagation()
  }

  const handleDragEnter = (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (uploading) return
    dragDepth.current += 1
    setDragActive(true)
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    e.stopPropagation()
    dragDepth.current = Math.max(0, dragDepth.current - 1)
    if (dragDepth.current === 0) setDragActive(false)
  }

  const openPicker = () => {
    if (uploading) return
    inputRef.current?.click()
  }

  return (
    <div className="space-y-3">
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onClick={openPicker}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            openPicker()
          }
        }}
        role="button"
        tabIndex={uploading ? -1 : 0}
        aria-disabled={uploading}
        aria-label="Upload a traffic video"
        className={`relative flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed
          px-6 py-10 text-center transition-all duration-200
          ${uploading
            ? 'cursor-not-allowed border-bg-border bg-bg-card/60 opacity-80'
            : dragActive
              ? 'cursor-pointer border-accent-cyan bg-accent-cyan/5 shadow-glow-cyan'
              : 'cursor-pointer border-bg-border bg-bg-card hover:border-accent-cyan/50 hover:bg-bg-hover'
          }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT_ATTR}
          className="hidden"
          disabled={uploading}
          onChange={(e) => upload(e.target.files?.[0])}
        />

        {uploading ? (
          <>
            <Loader2 size={34} className="animate-spin text-accent-cyan" />
            <div className="w-full max-w-sm space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-text-secondary">
                  {progress >= 100 ? 'Finalising upload…' : 'Uploading…'}
                </span>
                <span className="font-semibold text-accent-cyan">{progress}%</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-bg">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-accent-cyan to-accent-purple transition-all duration-200"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          </>
        ) : (
          <>
            <div
              className={`flex h-14 w-14 items-center justify-center rounded-xl transition-colors duration-200
                ${dragActive ? 'bg-accent-cyan/20' : 'bg-bg-hover'}`}
            >
              <UploadCloud
                size={26}
                className={dragActive ? 'text-accent-cyan' : 'text-text-secondary'}
              />
            </div>
            <div>
              <p className="text-sm font-semibold text-text-primary">
                {dragActive ? 'Drop the video to upload' : 'Drag & drop a traffic video here'}
              </p>
              <p className="mt-1 text-xs text-text-secondary">
                or <span className="font-medium text-accent-cyan">browse your files</span>
              </p>
            </div>
            <p className="text-[11px] uppercase tracking-widest text-text-muted">
              {ACCEPTED_EXTENSIONS.join(' · ').replace(/\./g, '')}
            </p>
          </>
        )}
      </div>

      {error && (
        <InlineMessage tone="error" onDismiss={() => setError(null)}>
          {error}
        </InlineMessage>
      )}
      {success && (
        <InlineMessage tone="success" onDismiss={() => setSuccess(null)}>
          {success}
        </InlineMessage>
      )}
    </div>
  )
}

// ─── Video list row ───────────────────────────────────────────────────────────
function VideoRow({ video, selected, onSelect, onDeleted }) {
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState(null)
  const resetTimer = useRef(null)

  useEffect(() => () => clearTimeout(resetTimer.current), [])

  const askConfirm = (e) => {
    e.stopPropagation()
    setError(null)
    setConfirming(true)
    clearTimeout(resetTimer.current)
    resetTimer.current = setTimeout(() => setConfirming(false), 5000)
  }

  const cancelConfirm = (e) => {
    e.stopPropagation()
    clearTimeout(resetTimer.current)
    setConfirming(false)
  }

  const doDelete = async (e) => {
    e.stopPropagation()
    clearTimeout(resetTimer.current)
    setDeleting(true)
    setError(null)
    try {
      await api.delete(`/api/videos/${video.id}`)
      setConfirming(false)
      onDeleted?.(video.id)
    } catch (err) {
      setError(apiErrorMessage(err, 'Failed to delete this video.'))
      setDeleting(false)
      setConfirming(false)
    }
  }

  return (
    <div
      onClick={() => onSelect(video.id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect(video.id)
        }
      }}
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      className={`cursor-pointer rounded-xl border p-4 transition-all duration-200
        ${selected
          ? 'border-accent-cyan/50 bg-bg-hover shadow-glow-cyan'
          : 'border-bg-border bg-bg-card hover:border-accent-cyan/30 hover:bg-bg-hover'
        }`}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-bg">
          <FileVideo size={16} className={selected ? 'text-accent-cyan' : 'text-text-muted'} />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="min-w-0 flex-1 truncate text-sm font-semibold text-text-primary">
              {video.name || video.video_filename || `Video ${video.id}`}
            </p>
            <StatusBadge status={video.processing_status} />
          </div>

          <p className="mt-0.5 truncate text-xs text-text-muted">{video.video_filename || '—'}</p>

          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-secondary">
            <span>{formatBytes(video.video_size_bytes)}</span>
            <span className="text-text-muted">·</span>
            <span>
              <span className="font-semibold text-text-primary">
                {Number(video.event_count ?? 0).toLocaleString()}
              </span>{' '}
              events
            </span>
            {video.processed_at && (
              <>
                <span className="text-text-muted">·</span>
                <span>{formatTimestamp(video.processed_at)}</span>
              </>
            )}
          </div>
        </div>

        {/* Delete with two-step confirm */}
        <div className="flex flex-shrink-0 items-center gap-1.5">
          {confirming ? (
            <>
              <button
                onClick={doDelete}
                disabled={deleting}
                className="rounded-lg border border-accent-red/40 bg-accent-red/10 px-2.5 py-1.5 text-[11px]
                           font-semibold text-accent-red transition-colors hover:bg-accent-red/20
                           disabled:cursor-not-allowed disabled:opacity-60"
              >
                {deleting ? 'Deleting…' : 'Confirm'}
              </button>
              <button
                onClick={cancelConfirm}
                disabled={deleting}
                className="rounded-lg border border-bg-border px-2.5 py-1.5 text-[11px] font-medium
                           text-text-secondary transition-colors hover:bg-bg-hover disabled:opacity-60"
              >
                Cancel
              </button>
            </>
          ) : (
            <button
              onClick={askConfirm}
              title="Delete video"
              aria-label={`Delete ${video.name || 'video'}`}
              className="rounded-lg border border-bg-border p-2 text-text-muted transition-all
                         hover:border-accent-red/40 hover:text-accent-red"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="mt-3">
          <InlineMessage tone="error" onDismiss={() => setError(null)}>
            {error}
          </InlineMessage>
        </div>
      )}
    </div>
  )
}

// ─── Live annotated stream (while processing) ─────────────────────────────────
function LiveProcessingStream({ videoId, name }) {
  const [imgError, setImgError] = useState(false)
  const [imgKey, setImgKey] = useState(0)

  useEffect(() => {
    setImgError(false)
    setImgKey((k) => k + 1)
  }, [videoId])

  const src = `${STREAM_BASE}/stream/${videoId}`

  return (
    <div className="relative min-h-[280px] overflow-hidden rounded-xl border border-bg-border bg-bg">
      {!imgError && (
        <img
          key={imgKey}
          src={src}
          alt={`Annotated processing stream for ${name || `video ${videoId}`}`}
          className="max-h-[520px] w-full object-contain"
          onError={() => setImgError(true)}
        />
      )}

      {imgError && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center">
          <AlertCircle size={34} className="text-text-muted" />
          <p className="text-sm text-text-muted">
            Annotated stream unavailable. Processing may still be running in the background.
          </p>
          <button
            onClick={() => {
              setImgError(false)
              setImgKey((k) => k + 1)
            }}
            className="flex items-center gap-2 rounded-lg border border-bg-border bg-bg-hover px-4 py-2
                       text-xs text-text-secondary transition-all hover:border-accent-cyan/40 hover:text-accent-cyan"
          >
            <RefreshCw size={13} />
            Retry
          </button>
        </div>
      )}

      {!imgError && (
        <div className="absolute left-3 top-3 flex items-center gap-1.5 rounded-full glass px-3 py-1.5 text-xs">
          <Radio size={11} className="text-accent-red live-pulse" />
          <span className="font-semibold uppercase tracking-wide text-text-secondary">
            Analysing
          </span>
        </div>
      )}
    </div>
  )
}

// ─── Report charts ────────────────────────────────────────────────────────────
function ClassTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const { name, value, payload: p } = payload[0]
  const total = p?.total || 1
  return (
    <div className="rounded-xl border border-bg-border bg-bg-card p-3 shadow-card">
      <p className="text-sm font-semibold capitalize text-text-primary">{name}</p>
      <p className="mt-1 text-xs text-text-secondary">
        {Number(value).toLocaleString()}{' '}
        <span className="font-medium text-accent-cyan">
          ({((value / total) * 100).toFixed(1)}%)
        </span>
      </p>
    </div>
  )
}

function TimelineTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="min-w-[150px] rounded-xl border border-bg-border bg-bg-card p-3 shadow-card">
      <p className="mb-1.5 text-xs text-text-muted">{formatClockTick(label)}</p>
      <div className="flex items-center justify-between gap-4">
        <span className="text-xs text-text-secondary">Vehicles</span>
        <span className="text-xs font-semibold text-text-primary">
          {Number(payload[0].value).toLocaleString()}
        </span>
      </div>
    </div>
  )
}

function ClassBreakdown({ byClass }) {
  const entries = Object.entries(byClass || {}).filter(([, v]) => Number(v) > 0)
  const total = entries.reduce((sum, [, v]) => sum + Number(v), 0)

  if (!entries.length) {
    return (
      <div className="flex h-56 items-center justify-center text-sm text-text-muted">
        No class data available
      </div>
    )
  }

  const chartData = entries
    .map(([name, value], i) => ({ name, value: Number(value), total, hex: classColor(name, i) }))
    .sort((a, b) => b.value - a.value)

  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
      <div className="h-56 w-full lg:w-1/2">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius={55}
              outerRadius={80}
              paddingAngle={3}
              dataKey="value"
              nameKey="name"
              isAnimationActive
              animationDuration={800}
            >
              {chartData.map((entry) => (
                <Cell key={entry.name} fill={entry.hex} stroke="transparent" />
              ))}
            </Pie>
            <Tooltip content={<ClassTooltip />} />
          </PieChart>
        </ResponsiveContainer>
      </div>

      <div className="w-full space-y-2.5 lg:w-1/2">
        {chartData.map((entry) => {
          const pct = total > 0 ? (entry.value / total) * 100 : 0
          return (
            <div key={entry.name}>
              <div className="mb-1 flex items-center gap-2">
                <span
                  className="h-2.5 w-2.5 flex-shrink-0 rounded-sm"
                  style={{ background: entry.hex }}
                />
                <span className="flex-1 truncate text-xs capitalize text-text-secondary">
                  {entry.name}
                </span>
                <span className="text-xs font-semibold text-text-primary">
                  {entry.value.toLocaleString()}
                </span>
                <span className="w-11 text-right text-xs text-text-muted">{pct.toFixed(1)}%</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{ width: `${pct}%`, background: entry.hex }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function DirectionSplit({ byDirection }) {
  const down = Number(byDirection?.down ?? 0)
  const up = Number(byDirection?.up ?? 0)
  const total = down + up
  const rows = [
    { key: 'down', label: 'Downstream', value: down, icon: ArrowDown, hex: 'var(--accent-cyan)' },
    { key: 'up', label: 'Upstream', value: up, icon: ArrowUp, hex: 'var(--accent-purple)' },
  ]

  return (
    <div className="space-y-4">
      {rows.map((row) => {
        const pct = total > 0 ? (row.value / total) * 100 : 0
        const Icon = row.icon
        return (
          <div key={row.key}>
            <div className="mb-1.5 flex items-center gap-2">
              <Icon size={14} style={{ color: row.hex }} className="flex-shrink-0" />
              <span className="flex-1 text-xs font-medium text-text-secondary">{row.label}</span>
              <span className="text-sm font-bold text-text-primary">
                {row.value.toLocaleString()}
              </span>
              <span className="w-11 text-right text-xs text-text-muted">{pct.toFixed(1)}%</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-bg">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${pct}%`, background: row.hex }}
              />
            </div>
          </div>
        )
      })}
      {total === 0 && <p className="text-xs text-text-muted">No directional data recorded.</p>}
    </div>
  )
}

function Timeline({ timeline }) {
  const data = Array.isArray(timeline) ? timeline : []
  if (!data.length) {
    return (
      <div className="flex h-56 items-center justify-center text-sm text-text-muted">
        No timeline data available
      </div>
    )
  }
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 16, left: -12, bottom: 0 }}>
          <defs>
            <linearGradient id="va-timeline-grad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="var(--accent-cyan)" stopOpacity={0.28} />
              <stop offset="95%" stopColor="var(--accent-cyan)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="var(--bg-border)"
            strokeOpacity={0.5}
            vertical={false}
          />
          <XAxis
            dataKey="ts"
            tickFormatter={formatClockTick}
            tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
            axisLine={false}
            tickLine={false}
            minTickGap={50}
          />
          <YAxis
            tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
            axisLine={false}
            tickLine={false}
            width={36}
            allowDecimals={false}
          />
          <Tooltip content={<TimelineTooltip />} />
          <Area
            type="monotone"
            dataKey="count"
            stroke="var(--accent-cyan)"
            strokeWidth={2}
            fill="url(#va-timeline-grad)"
            dot={false}
            activeDot={{ r: 4, strokeWidth: 0, fill: 'var(--accent-cyan)' }}
            isAnimationActive
            animationDuration={800}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

// ─── CSV export ───────────────────────────────────────────────────────────────
function csvEscape(value) {
  const s = value === null || value === undefined ? '' : String(value)
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

function buildReportCsv(report, video) {
  const rows = []
  rows.push(['Section', 'Key', 'Value'])
  rows.push(['Summary', 'Video name', video?.name ?? ''])
  rows.push(['Summary', 'Source file', video?.video_filename ?? ''])
  rows.push(['Summary', 'Processing status', report?.processing_status ?? ''])
  rows.push(['Summary', 'Processed at', report?.processed_at ?? ''])
  rows.push(['Summary', 'First event at', report?.first_event_at ?? ''])
  rows.push(['Summary', 'Last event at', report?.last_event_at ?? ''])
  rows.push(['Summary', 'Total vehicles', report?.total_vehicles ?? 0])

  Object.entries(report?.by_class || {}).forEach(([k, v]) => rows.push(['By class', k, v]))

  rows.push(['By direction', 'down', report?.by_direction?.down ?? 0])
  rows.push(['By direction', 'up', report?.by_direction?.up ?? 0])

  ;(Array.isArray(report?.timeline) ? report.timeline : []).forEach((p) =>
    rows.push(['Timeline', p?.ts ?? '', p?.count ?? 0]),
  )

  return rows.map((r) => r.map(csvEscape).join(',')).join('\r\n')
}

function downloadCsv(report, video) {
  const csv = buildReportCsv(report, video)
  // Leading BOM so Excel reads it as UTF-8
  const blob = new Blob(['\ufeff', csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  const safeName = String(video?.name || `video-${video?.id ?? 'report'}`)
    .replace(/[^a-z0-9-_]+/gi, '_')
    .slice(0, 60)
  link.href = url
  link.download = `${safeName}_report.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

// ─── Report view (mounted only for completed videos) ──────────────────────────
function StatTile({ label, value, accent = 'cyan' }) {
  const map = {
    cyan: 'text-accent-cyan',
    purple: 'text-accent-purple',
    green: 'text-accent-green',
    amber: 'text-accent-amber',
  }
  return (
    <div className="rounded-xl border border-bg-border bg-bg-card p-4">
      <p className="text-[11px] uppercase tracking-widest text-text-muted">{label}</p>
      <p className={`mt-1.5 text-2xl font-black ${map[accent] ?? map.cyan}`}>{value}</p>
    </div>
  )
}

function VideoReport({ video }) {
  // useApi is a polling GET hook — mounted only once the video is completed,
  // so the (slow) poll is harmless and it re-fetches if the report is amended.
  const { data: report, loading, error, refetch } = useApi(`/api/videos/${video.id}/report`)

  if (loading && !report) {
    return (
      <div className="space-y-4">
        <div className="skeleton h-24 w-full rounded-xl" />
        <div className="skeleton h-56 w-full rounded-xl" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-3">
        <InlineMessage tone="error">
          Could not load the report for this video:{' '}
          {typeof error === 'string' ? error : 'unexpected server response.'}
        </InlineMessage>
        <button
          onClick={refetch}
          className="flex items-center gap-2 rounded-lg border border-bg-border bg-bg-card px-4 py-2
                     text-xs text-text-secondary transition-all hover:border-accent-cyan/40 hover:text-accent-cyan"
        >
          <RefreshCw size={13} />
          Retry
        </button>
      </div>
    )
  }

  if (!report) {
    return <p className="text-sm text-text-muted">No report data available for this video.</p>
  }

  const byDirection = report.by_direction || {}
  const classCount = Object.keys(report.by_class || {}).length

  return (
    <div className="space-y-5">
      {/* Export */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-text-muted">
          Processed {formatTimestamp(report.processed_at || video.processed_at)}
          {report.first_event_at && report.last_event_at && (
            <>
              {' · '}
              {formatClockTick(report.first_event_at)} → {formatClockTick(report.last_event_at)}
            </>
          )}
        </p>
        <button
          onClick={() => downloadCsv(report, video)}
          className="flex items-center gap-2 rounded-lg border border-bg-border bg-bg-card px-4 py-2
                     text-sm font-medium transition-colors hover:bg-bg-border"
        >
          <Download size={16} className="text-accent-cyan" />
          Export CSV
        </button>
      </div>

      {/* Stat tiles */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="Total Vehicles"
          value={Number(report.total_vehicles ?? 0).toLocaleString()}
          accent="cyan"
        />
        <StatTile
          label="Downstream"
          value={Number(byDirection.down ?? 0).toLocaleString()}
          accent="green"
        />
        <StatTile
          label="Upstream"
          value={Number(byDirection.up ?? 0).toLocaleString()}
          accent="purple"
        />
        <StatTile label="Vehicle Classes" value={classCount} accent="amber" />
      </div>

      {/* Class + direction */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="rounded-xl border border-bg-border bg-bg-card p-5 xl:col-span-2">
          <h3 className="mb-4 text-sm font-bold text-text-primary">Class Distribution</h3>
          <ClassBreakdown byClass={report.by_class} />
        </div>
        <div className="rounded-xl border border-bg-border bg-bg-card p-5">
          <h3 className="mb-4 text-sm font-bold text-text-primary">Direction Split</h3>
          <DirectionSplit byDirection={byDirection} />
        </div>
      </div>

      {/* Timeline */}
      <div className="rounded-xl border border-bg-border bg-bg-card p-5">
        <h3 className="mb-4 text-sm font-bold text-text-primary">Detection Timeline</h3>
        <Timeline timeline={report.timeline} />
      </div>
    </div>
  )
}

// ─── Detail panel ─────────────────────────────────────────────────────────────
function DetailPanel({ video }) {
  if (!video) {
    return (
      <div className="flex min-h-[320px] flex-col items-center justify-center gap-3 rounded-xl
                      border border-bg-border bg-bg-card p-8 text-center">
        <FileVideo size={34} className="text-text-muted" />
        <p className="text-sm text-text-secondary">Select a video to view its analysis</p>
        <p className="max-w-xs text-xs text-text-muted">
          The annotated stream appears here while a video is processing, and the full report once
          it has completed.
        </p>
      </div>
    )
  }

  const status = video.processing_status

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-lg font-bold text-text-primary">
            {video.name || video.video_filename || `Video ${video.id}`}
          </h2>
          <p className="mt-0.5 truncate text-xs text-text-muted">
            {video.video_filename} · {formatBytes(video.video_size_bytes)}
          </p>
        </div>
        <StatusBadge status={status} size="md" />
      </div>

      {status === 'pending' && (
        <div className="flex min-h-[280px] flex-col items-center justify-center gap-3 rounded-xl
                        border border-bg-border bg-bg-card p-8 text-center">
          <Clock size={34} className="text-accent-amber" />
          <p className="text-sm font-medium text-text-primary">Queued for processing</p>
          <p className="max-w-sm text-xs text-text-muted">
            This video is waiting for the detection pipeline to pick it up. The status updates
            automatically.
          </p>
        </div>
      )}

      {status === 'processing' && (
        <>
          <LiveProcessingStream videoId={video.id} name={video.name} />
          <p className="text-xs text-text-muted">
            Live annotated output from the detection pipeline. The full report becomes available
            once processing completes.
          </p>
        </>
      )}

      {status === 'completed' && <VideoReport key={video.id} video={video} />}

      {status === 'failed' && (
        <div className="flex min-h-[280px] flex-col items-center justify-center gap-3 rounded-xl
                        border border-accent-red/30 bg-accent-red/5 p-8 text-center">
          <XCircle size={34} className="text-accent-red" />
          <p className="text-sm font-medium text-text-primary">Processing failed</p>
          <p className="max-w-sm text-xs text-text-muted">
            {video.error_message ||
              'The detection pipeline could not process this video. Check that the file is a valid, readable video and try uploading it again.'}
          </p>
        </div>
      )}

      {!STATUS_CONFIG[status] && (
        <InlineMessage tone="error">
          Unrecognised processing status: {String(status)}
        </InlineMessage>
      )}
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function VideoAnalysis() {
  const [videos, setVideos] = useState([])
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const abortRef = useRef(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      abortRef.current?.abort()
    }
  }, [])

  const fetchVideos = useCallback(async ({ showSpinner = false } = {}) => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    if (showSpinner) setLoading(true)
    try {
      const res = await api.get('/api/videos', { signal: controller.signal })
      if (!mountedRef.current) return
      setVideos(Array.isArray(res.data) ? res.data : (res.data?.items ?? []))
      setListError(null)
    } catch (err) {
      if (err?.name === 'CanceledError' || err?.name === 'AbortError') return
      if (!mountedRef.current) return
      setListError(apiErrorMessage(err, 'Could not load the video list.'))
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [])

  // Initial load
  useEffect(() => {
    fetchVideos({ showSpinner: true })
  }, [fetchVideos])

  // Conditional polling — only while something is actually in flight.
  const hasWorkInFlight = videos.some(
    (v) => v.processing_status === 'pending' || v.processing_status === 'processing',
  )

  useEffect(() => {
    if (!hasWorkInFlight) return undefined
    const id = setInterval(() => fetchVideos(), LIST_POLL_MS)
    return () => clearInterval(id)
  }, [hasWorkInFlight, fetchVideos])

  const handleUploaded = useCallback(
    (created) => {
      if (created?.id !== undefined && created?.id !== null) {
        setSelectedId(created.id)
        // Optimistically show it so polling kicks in immediately
        setVideos((prev) => (prev.some((v) => v.id === created.id) ? prev : [created, ...prev]))
      }
      fetchVideos()
    },
    [fetchVideos],
  )

  const handleDeleted = useCallback(
    (id) => {
      setVideos((prev) => prev.filter((v) => v.id !== id))
      setSelectedId((cur) => (cur === id ? null : cur))
      fetchVideos()
    },
    [fetchVideos],
  )

  const selectedVideo = videos.find((v) => v.id === selectedId) ?? null

  return (
    <div className="page-mount mx-auto max-w-7xl space-y-6 p-6">
      {/* Header */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="bg-gradient-to-r from-accent-cyan to-accent-purple bg-clip-text text-3xl font-black text-transparent">
            Video Analysis
          </h1>
          <p className="mt-1 text-text-secondary">
            Upload recorded traffic footage and run it through the detection pipeline
          </p>
        </div>
        <div className="flex items-center gap-2">
          {hasWorkInFlight && (
            <span className="flex items-center gap-1.5 text-xs text-accent-cyan">
              <span className="h-1.5 w-1.5 rounded-full bg-accent-cyan live-pulse" />
              Live updates
            </span>
          )}
          <button
            onClick={() => fetchVideos({ showSpinner: true })}
            className="flex items-center gap-2 rounded-lg border border-bg-border bg-bg-card px-4 py-2
                       text-sm font-medium transition-colors hover:bg-bg-border"
          >
            <RefreshCw size={16} className={`text-accent-cyan ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Upload */}
      <UploadPanel onUploaded={handleUploaded} />

      {listError && <InlineMessage tone="error">{listError}</InlineMessage>}

      {/* List + detail */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-12">
        {/* List */}
        <div className="space-y-3 xl:col-span-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold uppercase tracking-widest text-text-muted">
              Uploaded Videos
            </h2>
            {videos.length > 0 && (
              <span className="text-xs text-text-muted">{videos.length}</span>
            )}
          </div>

          {loading && videos.length === 0 && (
            <div className="space-y-3">
              <div className="skeleton h-24 w-full rounded-xl" />
              <div className="skeleton h-24 w-full rounded-xl" />
              <div className="skeleton h-24 w-full rounded-xl" />
            </div>
          )}

          {!loading && videos.length === 0 && !listError && (
            <div className="flex flex-col items-center justify-center gap-3 rounded-xl border
                            border-dashed border-bg-border bg-bg-card p-8 text-center">
              <FileVideo size={30} className="text-text-muted" />
              <p className="text-sm font-medium text-text-primary">No videos yet</p>
              <p className="max-w-xs text-xs text-text-muted">
                Upload a traffic video above to run vehicle detection and generate a report.
              </p>
            </div>
          )}

          {videos.map((video) => (
            <VideoRow
              key={video.id}
              video={video}
              selected={video.id === selectedId}
              onSelect={setSelectedId}
              onDeleted={handleDeleted}
            />
          ))}
        </div>

        {/* Detail */}
        <div className="xl:col-span-8">
          <DetailPanel video={selectedVideo} />
        </div>
      </div>
    </div>
  )
}
