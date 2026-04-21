'use client';

import { useState } from 'react';
import { Database, BookOpen, ArrowLeft, Factory, FileSearch } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { QAInterface } from './qa-interface';
import { DocQAInterface } from './doc-qa-interface';

type KMSubView = 'landing' | 'factory' | 'doc';

export function KMHub() {
    const [subView, setSubView] = useState<KMSubView>('landing');

    if (subView === 'factory') {
        return (
            <div className="flex flex-col gap-3 h-full">
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSubView('landing')}
                    className="self-start gap-2 text-slate-500 hover:text-slate-800 hover:bg-slate-100 -ml-1"
                >
                    <ArrowLeft className="size-4" />
                    返回 KM 助理
                </Button>
                <QAInterface />
            </div>
        );
    }

    if (subView === 'doc') {
        return (
            <div className="flex flex-col gap-3 h-full">
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSubView('landing')}
                    className="self-start gap-2 text-slate-500 hover:text-slate-800 hover:bg-slate-100 -ml-1"
                >
                    <ArrowLeft className="size-4" />
                    返回 KM 助理
                </Button>
                <DocQAInterface />
            </div>
        );
    }

    // Landing page
    return (
        <div className="flex flex-col items-center justify-center min-h-[60vh] gap-10 px-4">
            {/* Header */}
            <div className="text-center space-y-2">
                <div className="flex items-center justify-center gap-3 mb-4">
                    <div className="p-3 bg-gradient-to-br from-violet-500 to-indigo-600 rounded-2xl shadow-lg">
                        <BookOpen className="size-8 text-white" />
                    </div>
                </div>
                <h2 className="text-2xl font-bold text-slate-800">KM 助理</h2>
                <p className="text-slate-500 text-sm max-w-md">
                    請選擇要使用的問答功能
                </p>
            </div>

            {/* Two choice cards */}
            <div className="grid md:grid-cols-2 gap-6 w-full max-w-3xl">
                {/* Factory Q&A */}
                <button
                    onClick={() => setSubView('factory')}
                    className="group relative bg-white hover:bg-indigo-50 border-2 border-slate-200 hover:border-indigo-400 rounded-2xl p-8 text-left transition-all duration-200 shadow-sm hover:shadow-md active:scale-[0.98]"
                >
                    <div className="flex flex-col gap-5">
                        <div className="size-14 rounded-xl bg-gradient-to-br from-indigo-500 to-blue-600 flex items-center justify-center shadow-md group-hover:scale-105 transition-transform">
                            <Factory className="size-7 text-white" />
                        </div>
                        <div>
                            <h3 className="text-lg font-bold text-slate-800 mb-2">工廠智慧問答</h3>
                            <p className="text-sm text-slate-500 leading-relaxed">
                                查詢產線稼動狀態、工單進度、不良率分析、設備停機原因等工廠即時與歷史資料。
                            </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                            {['產線開工狀況', '工單落後', '設備稼動率', '不良率趨勢'].map(tag => (
                                <span key={tag} className="text-[11px] bg-indigo-100 text-indigo-700 px-2.5 py-1 rounded-full font-medium">
                                    {tag}
                                </span>
                            ))}
                        </div>
                    </div>
                    <div className="absolute bottom-6 right-6 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Database className="size-5 text-indigo-400" />
                    </div>
                </button>

                {/* Document Q&A */}
                <button
                    onClick={() => setSubView('doc')}
                    className="group relative bg-white hover:bg-emerald-50 border-2 border-slate-200 hover:border-emerald-400 rounded-2xl p-8 text-left transition-all duration-200 shadow-sm hover:shadow-md active:scale-[0.98]"
                >
                    <div className="flex flex-col gap-5">
                        <div className="size-14 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-md group-hover:scale-105 transition-transform">
                            <FileSearch className="size-7 text-white" />
                        </div>
                        <div>
                            <h3 className="text-lg font-bold text-slate-800 mb-2">文件智慧問答</h3>
                            <p className="text-sm text-slate-500 leading-relaxed">
                                從企業知識庫（PDF 文件、SOP、手冊、規範）中提取答案，並標示來源檔案。
                            </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                            {['SOP 查詢', '規範手冊', '作業標準', '文件搜尋'].map(tag => (
                                <span key={tag} className="text-[11px] bg-emerald-100 text-emerald-700 px-2.5 py-1 rounded-full font-medium">
                                    {tag}
                                </span>
                            ))}
                        </div>
                    </div>
                    <div className="absolute bottom-6 right-6 opacity-0 group-hover:opacity-100 transition-opacity">
                        <BookOpen className="size-5 text-emerald-400" />
                    </div>
                </button>
            </div>
        </div>
    );
}
