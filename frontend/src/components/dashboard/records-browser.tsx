'use client';

import { useState, useEffect, useCallback } from 'react';
import { useUser } from '@/context/user-context';
import {
    Search, Users, FileText, Mic, ChevronRight,
    UserCircle, Building2, Briefcase, Clock, RefreshCw, AlertCircle,
    ListChecks, MessageSquare,
} from 'lucide-react';
import { Button } from '@/components/ui/button';

// ── Types ──────────────────────────────────────────────────────────────────

interface Employee {
    EMPID: string;
    EMPNAME: string;
    DEPTNAME: string;
    DUTYNAME: string;
    rank?: number | null;
}

interface EmployeeRecord {
    id: number;
    empid: string;
    type: 'voice' | 'translation';
    file_name: string;
    summary: string;
    decisions: string;
    action_items: string;
    processed_at: string;
}

// ── Constants ──────────────────────────────────────────────────────────────

// Uses relative paths — Next.js rewrites in next.config.ts proxy to backend.

const HEADERS = { 'ngrok-skip-browser-warning': 'true' };

const RANK_BADGE: Record<number, { label: string; color: string }> = {
    1: { label: '最高管理層', color: 'bg-purple-100 text-purple-700' },
    2: { label: '最高管理層', color: 'bg-purple-100 text-purple-700' },
    3: { label: '管理層', color: 'bg-blue-100 text-blue-700' },
    4: { label: '管理層', color: 'bg-blue-100 text-blue-700' },
    5: { label: '專業層', color: 'bg-green-100 text-green-700' },
    6: { label: '專業層', color: 'bg-green-100 text-green-700' },
    7: { label: '專業層', color: 'bg-green-100 text-green-700' },
    8: { label: '基層', color: 'bg-amber-100 text-amber-700' },
    9: { label: '支援層', color: 'bg-gray-100 text-gray-600' },
};

// ── Sub-components ─────────────────────────────────────────────────────────

function RankBadge({ rank }: { rank?: number | null }) {
    if (!rank) return null;
    const info = RANK_BADGE[rank];
    if (!info) return null;
    return (
        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${info.color}`}>
            {info.label}
        </span>
    );
}

function RecordCard({ record }: { record: EmployeeRecord }) {
    const isVoice = record.type === 'voice';
    const Icon = isVoice ? Mic : FileText;
    const iconBg = isVoice ? 'bg-purple-50' : 'bg-blue-50';
    const iconColor = isVoice ? 'text-purple-500' : 'text-blue-500';
    const typeBg = isVoice ? 'bg-purple-100 text-purple-600' : 'bg-blue-100 text-blue-600';

    const dateStr = record.processed_at
        ? new Date(record.processed_at).toLocaleString('zh-TW', {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit',
        })
        : '—';

    const decisions = record.decisions
        ? record.decisions.split('\n').filter(Boolean)
        : [];
    const actionItems = record.action_items
        ? record.action_items.split('\n').filter(Boolean)
        : [];

    return (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 hover:shadow-md transition-shadow">
            {/* Header */}
            <div className="flex items-start gap-3">
                <div className={`size-10 rounded-xl ${iconBg} flex items-center justify-center flex-shrink-0`}>
                    <Icon className={`size-5 ${iconColor}`} />
                </div>
                <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                        <p className="font-semibold text-slate-800 text-sm truncate">{record.file_name}</p>
                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium flex-shrink-0 ${typeBg}`}>
                            {isVoice ? '語音處理' : '文件翻譯'}
                        </span>
                    </div>
                    <div className="flex items-center gap-1.5 mt-0.5 text-xs text-slate-400">
                        <Clock className="size-3" />
                        <span>{dateStr}</span>
                    </div>
                </div>
            </div>

            {/* Summary */}
            {record.summary && (
                <div className="mt-3 bg-slate-50 rounded-lg p-3">
                    <div className="flex items-center gap-1.5 mb-1 text-xs font-semibold text-slate-500">
                        <MessageSquare className="size-3" /> 摘要
                    </div>
                    <p className="text-xs text-slate-700 leading-relaxed whitespace-pre-wrap">
                        {record.summary}
                    </p>
                </div>
            )}

            {/* Decisions */}
            {decisions.length > 0 && (
                <div className="mt-2 bg-blue-50 rounded-lg p-3">
                    <div className="flex items-center gap-1.5 mb-1.5 text-xs font-semibold text-blue-600">
                        <ListChecks className="size-3" /> 決策事項
                    </div>
                    <ul className="space-y-0.5">
                        {decisions.map((d, i) => (
                            <li key={i} className="text-xs text-slate-700 flex gap-1.5">
                                <span className="text-blue-400 font-bold mt-0.5">·</span>
                                <span>{d}</span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Action items */}
            {actionItems.length > 0 && (
                <div className="mt-2 bg-amber-50 rounded-lg p-3">
                    <div className="flex items-center gap-1.5 mb-1.5 text-xs font-semibold text-amber-600">
                        <ListChecks className="size-3" /> 待辦事項
                    </div>
                    <ul className="space-y-0.5">
                        {actionItems.map((a, i) => (
                            <li key={i} className="text-xs text-slate-700 flex gap-1.5">
                                <span className="text-amber-400 font-bold mt-0.5">·</span>
                                <span>{a}</span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {/* No content fallback — guaranteed previewable */}
            {!record.summary && decisions.length === 0 && actionItems.length === 0 && (
                <p className="mt-3 text-xs text-slate-400 italic">此筆紀錄尚無詳細內容</p>
            )}
        </div>
    );
}

// ── Main Component ─────────────────────────────────────────────────────────

export function RecordsBrowser() {
    const { user } = useUser();

    const [employees, setEmployees] = useState<Employee[]>([]);
    const [empLoading, setEmpLoading] = useState(true);
    const [empError, setEmpError] = useState<string | null>(null);
    const [search, setSearch] = useState('');

    const [selectedEmp, setSelectedEmp] = useState<Employee | null>(null);
    const [records, setRecords] = useState<EmployeeRecord[]>([]);
    const [recLoading, setRecLoading] = useState(false);
    const [recError, setRecError] = useState<string | null>(null);

    // ── Fetch employee list ────────────────────────────────────────────────
    const fetchEmployees = useCallback(async () => {
        if (!user?.username) return;
        setEmpLoading(true);
        setEmpError(null);
        try {
            const res = await fetch(`/api/records/${user.username}`, { headers: HEADERS });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            setEmployees(data.employees ?? []);
        } catch (e: any) {
            setEmpError(e.message ?? '無法載入員工資料');
        } finally {
            setEmpLoading(false);
        }
    }, [user?.username]);

    useEffect(() => { fetchEmployees(); }, [fetchEmployees]);

    // ── Fetch selected employee's records from backend ─────────────────────
    const selectEmployee = async (emp: Employee) => {
        setSelectedEmp(emp);
        setRecords([]);
        setRecError(null);
        setRecLoading(true);
        try {
            const res = await fetch(`/api/employee-records/${emp.EMPID}`, { headers: HEADERS });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            setRecords(data.records ?? []);
        } catch (e: any) {
            setRecError(e.message ?? '無法載入紀錄');
        } finally {
            setRecLoading(false);
        }
    };

    const filtered = employees.filter(
        e =>
            e.EMPNAME.includes(search) ||
            e.EMPID.includes(search) ||
            e.DUTYNAME.includes(search)
    );

    // ── Render ─────────────────────────────────────────────────────────────
    return (
        <div className="flex gap-5 h-[calc(100vh-160px)]">

            {/* Left: employee list */}
            <aside className="w-72 flex-shrink-0 flex flex-col bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
                <div className="px-4 py-4 border-b bg-gradient-to-br from-blue-600 to-indigo-600">
                    <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2 text-white">
                            <Users className="size-4" />
                            <span className="font-semibold text-sm">部門員工</span>
                        </div>
                        <Button
                            variant="ghost" size="icon"
                            className="size-7 text-white/70 hover:text-white hover:bg-white/10"
                            onClick={fetchEmployees}
                        >
                            <RefreshCw className={`size-3.5 ${empLoading ? 'animate-spin' : ''}`} />
                        </Button>
                    </div>
                    <div className="relative">
                        <Search className="absolute left-2.5 top-2.5 size-3.5 text-white/60" />
                        <input
                            type="text"
                            placeholder="搜尋姓名、工號、職稱..."
                            value={search}
                            onChange={e => setSearch(e.target.value)}
                            className="w-full pl-8 pr-3 py-2 text-xs rounded-lg bg-white/15 text-white placeholder:text-white/50 border border-white/20 focus:outline-none focus:ring-1 focus:ring-white/40"
                        />
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
                    {empLoading && (
                        <div className="flex items-center justify-center py-12 text-slate-400 gap-2">
                            <RefreshCw className="size-4 animate-spin" /><span className="text-sm">載入中...</span>
                        </div>
                    )}
                    {empError && (
                        <div className="p-4 text-center">
                            <AlertCircle className="size-6 text-red-400 mx-auto mb-2" />
                            <p className="text-xs text-red-500">{empError}</p>
                        </div>
                    )}
                    {!empLoading && !empError && filtered.length === 0 && (
                        <div className="p-6 text-center text-slate-400">
                            <Users className="size-8 mx-auto mb-2 opacity-30" />
                            <p className="text-sm">找不到符合的員工</p>
                        </div>
                    )}
                    {filtered.map(emp => {
                        const isSelected = selectedEmp?.EMPID === emp.EMPID;
                        return (
                            <button
                                key={emp.EMPID}
                                onClick={() => selectEmployee(emp)}
                                className={`w-full text-left px-4 py-3 flex items-center gap-3 transition-colors border-l-2 ${isSelected
                                    ? 'bg-blue-50 border-blue-500'
                                    : 'hover:bg-slate-50 border-transparent'}`}
                            >
                                <div className={`size-9 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0 ${isSelected ? 'bg-blue-500 text-white' : 'bg-slate-100 text-slate-600'}`}>
                                    {emp.EMPNAME.charAt(0)}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center justify-between">
                                        <span className="text-sm font-semibold text-slate-800 truncate">{emp.EMPNAME}</span>
                                        <ChevronRight className={`size-3.5 flex-shrink-0 ${isSelected ? 'text-blue-500' : 'text-slate-300'}`} />
                                    </div>
                                    <p className="text-xs text-slate-500 truncate">{emp.DUTYNAME}</p>
                                    <div className="mt-0.5"><RankBadge rank={emp.rank} /></div>
                                </div>
                            </button>
                        );
                    })}
                </div>

                <div className="px-4 py-2 border-t bg-slate-50 text-[11px] text-slate-400">
                    共 {filtered.length} 位員工
                </div>
            </aside>

            {/* Right: records */}
            <main className="flex-1 flex flex-col gap-4 overflow-hidden">
                {!selectedEmp ? (
                    <div className="flex-1 flex items-center justify-center bg-white rounded-2xl border border-slate-200 shadow-sm">
                        <div className="text-center text-slate-400 max-w-xs">
                            <UserCircle className="size-16 mx-auto mb-4 opacity-20" />
                            <p className="text-base font-medium text-slate-600">選擇左側員工</p>
                            <p className="text-sm mt-1">點擊員工以查看其翻譯與語音紀錄</p>
                        </div>
                    </div>
                ) : (
                    <>
                        {/* Employee info */}
                        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm px-6 py-4 flex items-center gap-5 flex-shrink-0">
                            <div className="size-14 rounded-full bg-gradient-to-br from-blue-500 to-indigo-500 flex items-center justify-center text-white text-2xl font-bold shadow">
                                {selectedEmp.EMPNAME.charAt(0)}
                            </div>
                            <div className="flex-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <h2 className="text-xl font-bold text-slate-900">{selectedEmp.EMPNAME}</h2>
                                    <RankBadge rank={selectedEmp.rank} />
                                </div>
                                <div className="flex items-center gap-4 mt-1 text-sm text-slate-500 flex-wrap">
                                    <span className="flex items-center gap-1"><Briefcase className="size-3.5" />{selectedEmp.DUTYNAME}</span>
                                    <span className="flex items-center gap-1"><Building2 className="size-3.5" />{selectedEmp.DEPTNAME}</span>
                                    <span className="flex items-center gap-1 font-mono text-xs bg-slate-100 px-2 py-0.5 rounded">#{selectedEmp.EMPID}</span>
                                </div>
                            </div>
                            <div className="text-right text-sm text-slate-400">
                                <p className="font-medium text-slate-700">{records.length}</p>
                                <p className="text-xs">筆紀錄</p>
                            </div>
                        </div>

                        {/* Records */}
                        <div className="flex-1 overflow-y-auto space-y-3 pb-2">
                            {recLoading && (
                                <div className="flex items-center justify-center py-12 bg-white rounded-2xl border border-slate-200 gap-2 text-slate-400">
                                    <RefreshCw className="size-4 animate-spin" /><span className="text-sm">載入紀錄...</span>
                                </div>
                            )}
                            {recError && (
                                <div className="flex items-center justify-center py-12 bg-white rounded-2xl border border-slate-200">
                                    <div className="text-center">
                                        <AlertCircle className="size-6 text-red-400 mx-auto mb-2" />
                                        <p className="text-sm text-red-500">{recError}</p>
                                        <Button variant="outline" size="sm" className="mt-3" onClick={() => selectEmployee(selectedEmp)}>
                                            重試
                                        </Button>
                                    </div>
                                </div>
                            )}
                            {!recLoading && !recError && records.length === 0 && (
                                <div className="flex items-center justify-center min-h-48 bg-white rounded-2xl border border-slate-200 shadow-sm">
                                    <div className="text-center text-slate-400">
                                        <FileText className="size-10 mx-auto mb-3 opacity-20" />
                                        <p className="text-sm">此員工目前沒有任何紀錄</p>
                                    </div>
                                </div>
                            )}
                            {!recLoading && !recError && records.map(record => (
                                <RecordCard key={record.id} record={record} />
                            ))}
                        </div>
                    </>
                )}
            </main>
        </div>
    );
}
