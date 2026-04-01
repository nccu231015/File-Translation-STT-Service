'use client';

/**
 * ChartBlock.tsx
 *
 * Renders a chart from a `chart_config` object returned by the backend API.
 * Supports two chart types:
 *   - 'bar_line_combo' : dual-Y-axis (Bar = quantity, Line = defect rate) for Q5
 *   - 'multi_line'    : multiple lines, one per model/line  for Q7
 *
 * This component is intentionally *backend-agnostic*:
 * it only depends on the ChartConfig interface, not on how the data was fetched.
 * When the backend migrates to n8n the chart_config JSON structure stays the same.
 */

import {
    ComposedChart,
    LineChart,
    Bar,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
} from 'recharts';
import { ChartConfig } from '@/lib/api/factory';

// ── Colour palette ────────────────────────────────────────────────────────────
const PALETTE = [
    '#6366f1', // indigo-500
    '#f59e0b', // amber-500
    '#10b981', // emerald-500
    '#ef4444', // red-500
    '#3b82f6', // blue-500
    '#8b5cf6', // violet-500
    '#ec4899', // pink-500
    '#14b8a6', // teal-500
    '#f97316', // orange-500
    '#84cc16', // lime-500
];

function colour(i: number) {
    return PALETTE[i % PALETTE.length];
}

// ── Convert datasets array → recharts row-based format ────────────────────────
function toRows(labels: string[], datasets: ChartConfig['datasets']) {
    return labels.map((label, i) => {
        const row: Record<string, string | number | null> = { label };
        datasets.forEach(ds => {
            row[ds.label] = ds.data[i] ?? null;
        });
        return row;
    });
}

// ── Custom Tooltip ────────────────────────────────────────────────────────────
function CustomTooltip({ active, payload, label }: any) {
    if (!active || !payload?.length) return null;
    return (
        <div className="bg-white border border-slate-200 rounded-xl shadow-lg px-4 py-3 text-xs space-y-1">
            <p className="font-semibold text-slate-600 mb-1">{label}</p>
            {payload.map((p: any) => (
                <div key={p.name} className="flex items-center gap-2">
                    <span className="size-2.5 rounded-full flex-shrink-0" style={{ background: p.color }} />
                    <span className="text-slate-500">{p.name}：</span>
                    <span className="font-bold text-slate-800">
                        {p.value == null ? '—' : typeof p.value === 'number' && p.value < 5 && p.name.includes('%')
                            ? `${p.value.toFixed(4)}%`
                            : p.value.toLocaleString()}
                    </span>
                </div>
            ))}
        </div>
    );
}

// ── Main component ────────────────────────────────────────────────────────────
interface ChartBlockProps {
    config: ChartConfig;
}

export function ChartBlock({ config }: ChartBlockProps) {
    const rows = toRows(config.labels, config.datasets);

    // Detect which datasets are bars vs lines for ComposedChart
    const barDatasets  = config.datasets.filter(ds => ds.type === 'bar');
    const lineDatasets = config.datasets.filter(ds => ds.type === 'line');

    // Left Y-axis key (quantity), right Y-axis key (defect rate)
    const leftAxisId  = barDatasets[0]?.yAxisID  ?? 'y_quantity';
    const rightAxisId = lineDatasets[0]?.yAxisID ?? 'y_defect_rate';

    return (
        <div className="mt-4 rounded-2xl border border-slate-100 bg-slate-50/60 p-4 shadow-sm">
            <p className="text-sm font-semibold text-slate-700 mb-3">{config.title}</p>

            <ResponsiveContainer width="100%" height={300}>
                {config.chart_type === 'bar_line_combo' ? (
                    /* ── Q5: Bar (quantity) + Line (defect rate), dual Y-axis ── */
                    <ComposedChart data={rows} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                        <XAxis
                            dataKey="label"
                            tick={{ fontSize: 11, fill: '#94a3b8' }}
                            axisLine={{ stroke: '#e2e8f0' }}
                            tickLine={false}
                        />
                        {/* Left Y – quantity */}
                        <YAxis
                            yAxisId={leftAxisId}
                            orientation="left"
                            tick={{ fontSize: 11, fill: '#94a3b8' }}
                            axisLine={false}
                            tickLine={false}
                            label={{
                                value: config.yAxes?.[leftAxisId]?.label ?? '產量',
                                angle: -90, position: 'insideLeft',
                                style: { fontSize: 10, fill: '#94a3b8' },
                            }}
                        />
                        {/* Right Y – defect rate */}
                        <YAxis
                            yAxisId={rightAxisId}
                            orientation="right"
                            tickFormatter={(v: number) => `${v.toFixed(2)}%`}
                            tick={{ fontSize: 11, fill: '#94a3b8' }}
                            axisLine={false}
                            tickLine={false}
                            label={{
                                value: config.yAxes?.[rightAxisId]?.label ?? '不良率',
                                angle: 90, position: 'insideRight',
                                style: { fontSize: 10, fill: '#94a3b8' },
                            }}
                        />
                        <Tooltip content={<CustomTooltip />} />
                        <Legend wrapperStyle={{ fontSize: 12 }} />
                        {barDatasets.map((ds, i) => (
                            <Bar
                                key={ds.label}
                                dataKey={ds.label}
                                yAxisId={ds.yAxisID ?? leftAxisId}
                                fill={ds.backgroundColor ?? colour(i)}
                                radius={[4, 4, 0, 0]}
                                maxBarSize={40}
                                hide={(ds as any).hide}
                                legendType={(ds as any).hideInLegend ? 'none' : 'rect'}
                            />
                        ))}
                        {lineDatasets.map((ds, i) => (
                            <Line
                                key={ds.label}
                                type="monotone"
                                dataKey={ds.label}
                                yAxisId={ds.yAxisID ?? rightAxisId}
                                stroke={ds.borderColor ?? colour(barDatasets.length + i)}
                                strokeWidth={2}
                                dot={{ r: 3 }}
                                activeDot={{ r: 5 }}
                                connectNulls
                                legendType={(ds as any).hideInLegend ? 'none' : 'line'}
                            />
                        ))}
                    </ComposedChart>
                ) : (
                    /* ── Q7: Multi-line (one per model / production line) ── */
                    <LineChart data={rows} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                        <XAxis
                            dataKey="label"
                            tick={{ fontSize: 11, fill: '#94a3b8' }}
                            axisLine={{ stroke: '#e2e8f0' }}
                            tickLine={false}
                        />
                        <YAxis
                            tickFormatter={(v: number) => `${v.toFixed(2)}%`}
                            tick={{ fontSize: 11, fill: '#94a3b8' }}
                            axisLine={false}
                            tickLine={false}
                        />
                        <Tooltip content={<CustomTooltip />} />
                        <Legend wrapperStyle={{ fontSize: 12 }} />
                        {config.datasets.map((ds, i) => (
                            <Line
                                key={ds.label}
                                type="monotone"
                                dataKey={ds.label}
                                stroke={ds.borderColor ?? colour(i)}
                                strokeWidth={2}
                                dot={{ r: 3 }}
                                activeDot={{ r: 5 }}
                                connectNulls
                            />
                        ))}
                    </LineChart>
                )}
            </ResponsiveContainer>

            <p className="text-[10px] text-slate-400 text-right mt-2">
                資料由 AI 助手即時查詢，僅供參考
            </p>
        </div>
    );
}
