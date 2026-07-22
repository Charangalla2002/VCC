import React, { useState } from 'react';
import axios from '../lib/api';
import { Pencil, Check } from 'lucide-react';

const PREDEFINED_COLORS = [
  'White', 'Black', 'Silver', 'Grey', 'Red', 
  'Blue', 'Green', 'Yellow', 'Orange', 'Cyan', 'Purple', 'Pink'
];

export function EditableColorBadge({ eventId, initialColor, onColorUpdated }) {
  const [color, setColor] = useState(initialColor || 'Unknown');
  const [isOpen, setIsOpen] = useState(false);
  const [customColor, setCustomColor] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSelectColor = async (newColor) => {
    if (!eventId) return;
    setSaving(true);
    try {
      await axios.post('/api/color-corrections/events/' + eventId + '/correct', {
        corrected_color: newColor,
        notes: 'Manual override from UI'
      });
      setColor(newColor);
      setIsOpen(false);
      if (onColorUpdated) onColorUpdated(newColor);
    } catch (err) {
      console.error('Failed to correct color:', err);
    } finally {
      setSaving(false);
    }
  };

  const badgeColorClass = (c) => {
    const lc = (c || '').toLowerCase();
    if (lc === 'red') return 'bg-red-500/20 text-red-400 border-red-500/30';
    if (lc === 'blue') return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
    if (lc === 'green') return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
    if (lc === 'yellow') return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
    if (lc === 'white') return 'bg-slate-100/20 text-slate-200 border-slate-300/30';
    if (lc === 'black') return 'bg-slate-900/40 text-slate-300 border-slate-700/50';
    if (lc === 'orange') return 'bg-orange-500/20 text-orange-400 border-orange-500/30';
    if (lc === 'purple') return 'bg-purple-500/20 text-purple-400 border-purple-500/30';
    return 'bg-slate-700/40 text-slate-300 border-slate-600/30';
  };

  return (
    <div className="relative inline-block text-left">
      <div 
        onClick={() => setIsOpen(!isOpen)}
        className={"group cursor-pointer inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border transition-all hover:scale-105 " + badgeColorClass(color)}
        title="Click to manually correct vehicle color"
      >
        <span>{color}</span>
        <Pencil className="w-3 h-3 opacity-60 group-hover:opacity-100 transition-opacity" />
      </div>

      {isOpen && (
        <div className="absolute z-50 mt-1.5 w-44 rounded-xl bg-slate-900 border border-slate-800 shadow-2xl p-2 text-slate-200 text-xs backdrop-blur-md">
          <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider px-2 py-1 mb-1">
            Correct Vehicle Color
          </div>
          <div className="grid grid-cols-2 gap-1 max-h-36 overflow-y-auto mb-2 pr-1">
            {PREDEFINED_COLORS.map((c) => (
              <button
                key={c}
                disabled={saving}
                onClick={() => handleSelectColor(c)}
                className={"text-left px-2 py-1 rounded-md transition-colors hover:bg-slate-800 flex items-center justify-between " + (c === color ? 'bg-indigo-600/30 text-indigo-300 font-semibold' : '')}
              >
                <span>{c}</span>
                {c === color && <Check className="w-3 h-3 text-indigo-400" />}
              </button>
            ))}
          </div>
          <div className="border-t border-slate-800 pt-1.5 flex gap-1">
            <input
              type="text"
              placeholder="Custom..."
              value={customColor}
              onChange={(e) => setCustomColor(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && customColor.trim() && handleSelectColor(customColor.trim())}
              className="w-full bg-slate-950 border border-slate-800 rounded px-1.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
            />
            <button
              onClick={() => customColor.trim() && handleSelectColor(customColor.trim())}
              className="bg-indigo-600 hover:bg-indigo-500 text-white rounded px-2 text-[10px] font-medium transition-colors"
            >
              Save
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
