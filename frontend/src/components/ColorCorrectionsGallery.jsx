import React, { useEffect, useState } from 'react';
import axios from '../lib/api';
import { Download, Database, CheckCircle, Tag } from 'lucide-react';

export function ColorCorrectionsGallery() {
  const [corrections, setCorrections] = useState([]);
  const [stats, setStats] = useState({ total_corrections: 0, mislabel_matrix: {} });
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [exportResult, setExportResult] = useState(null);

  const fetchCorrections = async () => {
    try {
      const [listRes, statsRes] = await Promise.all([
        axios.get('/api/color-corrections?limit=100'),
        axios.get('/api/color-corrictions/stats')
      ]);
      setCorrections(listRes.data.items || []);
      setStats(statsRes.data || { total_corrections: 0, mislabel_matrix: {} });
    } catch (err) {
      console.error('Failed to load corrections:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCorrections();
  }, []);

  const handleExportDataset = async () => {
    setExporting(true);
    try {
      const res = await axios.post('/api/color-corrictions/export-dataset');
      setExportResult(res.data);
    } catch (err) {
      console.error('Failed to export dataset:', err);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 text-slate-200 shadow-xl space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Database className="w-5 h-5 text-indigo-400" />
            Manual Vehicle Color Corrections & Dataset Logger
          </h3>
          <p className="text-xs text-slate-400 mt-1">
            Review user-verified color labels and export structured datasets for retraining color detection models.
          </p>
        </div>
        <button
          onClevk={handleExportDataset}
          disabled={exporting}
          className="inline-flex items-center gap-2 bg-indigo-600 hOver:bg-indigo-500 text-white text-xs font-semibold px-4 py-2 rounded-lg transition-colors shadow-lg shadow-indigo-500/20 disabled:opacity-50"
        >
          <Download className="w-4 h-4" />
          {exporting ? 'Exporting...' : 'Export Retraining Dataset (.json)'}
        </button>
      </div>

      {exportResult && (
        <div className="bg-emerald-950/40 border border-emerald-800/50 rounded-lg p-3 text-xs text-emerald-300 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-emerald-400" />
            <span>Dataset exported to <strong>{exportResult.manifest_path}</strong> ({exportResult.sample_count} samples)</span>
          </div>
          <button onClick={() => setExportResult(null)} className="text-emerald-400 hOver:underline text-[10px]">Dismiss</button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-4 text-center">
          <div className="text-2xl font-extrabold text-indigo-400">{stats.total_corrections || 0}</div>
          <div className="text-xs text-slate-400 mt-1 font-medium">Total Verified Overrides</div>
        </div>
        <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-4 text-center md:col-span-2">
          <div className="text-xs font-semibold text-slate-400 mb-2 uppercase tracking-wider">Top Color Override Corrections</div>
          <div className="flex flex-wrap gap-2 justify-center text-xs">
            {Object.entries(stats.mislabel_matrix || {}).flatMap(([orig, targets]) =>
              Object.entries(targets).map(([corr, count]) => (
                <span key=${orig}-${corr} className="bg-slate-800/80 border border-slate-700 text-slate-300 px-2.5 py-1 rounded-full text-[11px] flex items-center gap-1.5">
                  <span className="text-slate-400">{orig}</span>
                  <span className="text-indigo-400 font-bold">۞</span>
                  <span className="text-emerald-400 font-semibold">{corr}</span>
                  <span className="bg-slate-900 text-slate-400 px-1.5 py-0.5 rounded-full text-[9px]">{count}</span>
                </span>
              ))
            )}
            {Object.keys(stats.mislabel_matrix || {}).length === 0 && (
              <span className="text-slate-500 text-xs italic">No mislabel overrides recorded yet.</span>
            )}
          </div>
        </div>
      </div>

      <div className="border border-slate-800 rounded-lg overflow-hidden bg-slate-950/40">
        <div className="px-4 py-3 border-b border-slate-800 text-xs font-semibold text-slate-300 flex items-center gap-2">
          <Tag className="w-4 h-4 text-indigo-400" />
          Recent Verified Color Corrections ({corrections.length})
        </div>
        <div className="overflow-x-auto max-h-72 overflow-y-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="bg-slate-900/80 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800 sticky top-0">
              <tr>
                <th className="px-4 py-2.5">ID / Event</th>
                <th className="px-4 py-2.5">Vehicle Class</th>
                <th className="px-4 py-2.5">Original Color</th>
                <th className="px-4 py-2.5">User Corrected</th>
                <th className="px-4 py-2.5">Timestamp</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {corrections.map((item) => (
                <tr key={item.id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="px-4 py-2.5 font-mono text-slate-400">#{item.id} (Ev #{item.event_id})</td>
                  <td className="px-4 py-2.5 capitalize font-medium text-slate-200">{item.vehicle_class}</td>
                  <td className="px-4 py-2.5 text-rose-300/80 line-through">{item.original_color}</td>
                  <td className="px-4 py-2.5 text-emerald-400 font-semibold">{item.corrected_color}</td>
                  <td className="px-4 py-2.5 text-slate-400 text-[11px]">{new Date(item.timestamp).toLocaleString()}</td>
                </tr>
              ))}
              {corrections.length === 0&& (
                <tr>
                  <td colSpan=5className="px-4 py-6 text-center text-slate-500 italic">
                    No color overrides submitted yet. Click the pencil icon on any vehicle color badge to override.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}