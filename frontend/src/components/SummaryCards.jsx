import { useEffect, useRef, useState } from 'react'
import {
  Car, Bike, Bus, Truck, TrendingUp, TrendingDown, Minus,
} from 'lucide-react'

// ─── Animated number counter ──────────────────────────────────────────────────
function useCountUp(target, duration = 1200) {
  const [value, setValue] = useState(0)
  const frameRef = useRef(null)
  const startTimeRef = useRef(null)
  const startValueRef = useRef(0)

  useEffect(() => {
    if (target === undefined || target === null) return
    startValueRef.current = 0
    startTimeRef.current = null

    const animate = (timestamp) => {
      if (!startTimeRef.current) startTimeRef.current = timestamp
      const elapsed = timestamp - startTimeRef.current
      const progress = Math.min(elapsed / duration, 1)
      const ease = 1 - Math.pow(1 - progress, 3)
      setValue(Math.round(startValueRef.current + (target - startValueRef.current) * ease))
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(animate)
      }
    }

    frameRef.current = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(frameRef.current)
  }, [target, duration])

  return value
}

// ─── Card config ──────────────────────────────────────────────────────────────
const CARD_CONFIGS = [
  {
    key: 'total',
    label: 'Total Vehicles',
    icon: Car,
    gradient: 'from-cyan-400 via-sky-300 to-indigo-400',
    glow: 'hover:border-cyan-500/40 hover:shadow-cyan-500/10',
    iconBg: 'from-cyan-500/20 to-blue-600/10 border-cyan-500/30',
    iconColor: 'text-cyan-400',
    progressColor: 'bg-cyan-400',
  },
  {
    key: 'car',
    label: 'Car / Jeep / Van',
    icon: Car,
    gradient: 'from-indigo-400 via-violet-300 to-cyan-400',
    glow: 'hover:border-indigo-500/40 hover:shadow-indigo-500/10',
    iconBg: 'from-indigo-500/20 to-violet-600/10 border-indigo-500/30',
    iconColor: 'text-indigo-400',
    progressColor: 'bg-indigo-400',
  },
  {
    key: 'bike',
    label: 'Two Wheelers',
    icon: Bike,
    gradient: 'from-purple-400 via-fuchsia-300 to-indigo-400',
    glow: 'hover:border-purple-500/40 hover:shadow-purple-500/10',
    iconBg: 'from-purple-500/20 to-fuchsia-600/10 border-purple-500/30',
    iconColor: 'text-purple-400',
    progressColor: 'bg-purple-400',
  },
  {
    key: 'heavy',
    label: 'Heavy Vehicles',
    icon: Truck,
    gradient: 'from-amber-400 via-orange-300 to-rose-400',
    glow: 'hover:border-amber-500/40 hover:shadow-amber-500/10',
    iconBg: 'from-amber-500/20 to-orange-600/10 border-amber-500/30',
    iconColor: 'text-amber-400',
    progressColor: 'bg-amber-400',
  },
  {
    key: 'bus',
    label: 'Buses',
    icon: Bus,
    gradient: 'from-emerald-400 via-teal-300 to-cyan-400',
    glow: 'hover:border-emerald-500/40 hover:shadow-emerald-500/10',
    iconBg: 'from-emerald-500/20 to-teal-600/10 border-emerald-500/30',
    iconColor: 'text-emerald-400',
    progressColor: 'bg-emerald-400',
  },
]

// ─── Delta badge ──────────────────────────────────────────────────────────────
function DeltaBadge({ delta }) {
  if (delta === undefined || delta === null) return null
  const isUp = delta >= 0
  const isNeutral = delta === 0

  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full border shadow-sm backdrop-blur-md transition-all
        ${isNeutral
          ? 'bg-slate-800/40 border-slate-700/50 text-slate-400'
          : isUp
            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
            : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
        }`}
    >
      {isNeutral ? <Minus size={11} /> : isUp ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
      {Math.abs(delta).toFixed(1)}%
    </span>
  )
}

// ─── Single summary card ──────────────────────────────────────────────────────
function SummaryCard({ config, count, percentage, delta, isLoading }) {
  const animated = useCountUp(isLoading ? 0 : (count ?? 0))
  const Icon = config.icon
  const pct = percentage ?? 0

  return (
    <div
      className={`relative bg-slate-900/60 backdrop-blur-xl border border-slate-800/80 rounded-2xl p-5 shadow-xl
                  transition-all duration-300 hover:scale-[1.02] hover:shadow-2xl cursor-default group overflow-hidden
                  ${config.glow} flex flex-col gap-3 min-w-0`}
    >
      {/* Background Subtle Gradient Overlay */}
      <div className="absolute -right-8 -top-8 w-28 h-28 bg-gradient-to-br from-indigo-500/5 to-cyan-500/0 rounded-full blur-2xl group-hover:scale-150 transition-transform duration-500 pointer-events-none" />

      {/* Header row */}
      <div className="flex items-start justify-between gap-2 relative z-10">
        <div className={`w-11 h-11 rounded-2xl bg-gradient-to-br ${config.iconBg} border flex items-center justify-center flex-shrink-0 shadow-inner group-hover:scale-110 transition-transform`}>
          <Icon size={22} className={config.iconColor} />
        </div>
        <DeltaBadge delta={delta} />
      </div>

      {/* Count */}
      {isLoading ? (
        <div className="space-y-2 relative z-10">
          <div className="skeleton h-8 w-24 rounded-lg" />
          <div className="skeleton h-4 w-16 rounded-md" />
        </div>
      ) : (
        <div className="count-up-animate relative z-10">
          <p className={`text-3xl lg:text-4xl font-black bg-gradient-to-r ${config.gradient}
                         bg-clip-text text-transparent leading-none tracking-tight`}>
            {animated.toLocaleString()}
          </p>
        </div>
      )}

      {/* Label */}
      <p className="text-slate-400 text-xs font-semibold uppercase tracking-wider relative z-10">
        {config.label}
      </p>

      {/* Progress bar */}
      {config.key !== 'total' && !isLoading && (
        <div className="space-y-1.5 relative z-10 mt-auto pt-1">
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-slate-500 font-medium">% of total</span>
            <span className="font-bold text-slate-300">
              {pct.toFixed(1)}%
            </span>
          </div>
          <div className="h-1.5 bg-slate-950/80 rounded-full overflow-hidden border border-slate-800/50 p-[1px]">
            <div
              className={`h-full ${config.progressColor} rounded-full transition-all duration-1000 shadow-sm`}
              style={{ width: `${Math.min(pct, 100)}%` }}
            />
          </div>
        </div>
      )}

      {config.key === 'total' && !isLoading && (
        <div className="text-[11px] text-slate-500 font-medium relative z-10 mt-auto pt-1 flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
          Live counting active today
        </div>
      )}
    </div>
  )
}

// ─── SummaryCards ─────────────────────────────────────────────────────────────
export default function SummaryCards({ data, isLoading }) {
  const total = data?.total ?? 0
  const safeData = {
    total,
    car:   data?.car   ?? 0,
    bike:  data?.bike  ?? 0,
    heavy: data?.heavy ?? 0,
    bus:   data?.bus   ?? 0,
  }

  const pct = (val) => total > 0 ? (val / total) * 100 : 0

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
      {CARD_CONFIGS.map((config) => (
        <SummaryCard
          key={config.key}
          config={config}
          count={safeData[config.key]}
          percentage={pct(safeData[config.key])}
          delta={data?.deltas?.[config.key]}
          isLoading={isLoading}
        />
      ))}
    </div>
  )
}
