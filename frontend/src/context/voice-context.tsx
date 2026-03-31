'use client';

import React, { createContext, useContext, useState, useEffect, useRef, ReactNode } from 'react';
import { toast } from 'sonner';
import { analyzeMeetingAudio } from '@/lib/api/stt';
import { useUser } from '@/context/user-context';
import { saveBlob, loadBlob, deleteBlob } from '@/lib/pdf-storage';

export interface ActionItem {
    task: string;
    owner?: string;
    deadline?: string;
}

export interface ProcessedRecord {
    id: string;
    fileName: string;
    duration: string;
    processedAt: Date;
    transcript: string;
    summary: string;
    decisions: string[];
    actionItems: (string | ActionItem)[];
    downloadUrl?: string;     // Meeting minutes docx (blob URL)
    transcriptUrl?: string;   // Bilingual transcript docx (blob URL)
    translatedSegments?: { start: number, end: number, original: string, translated: string }[];
}

interface VoiceContextType {
    isProcessing: boolean;
    processingFilename: string | null;
    records: ProcessedRecord[];
    processAudio: (file: File) => Promise<void>;
    removeRecord: (id: string) => void;
}

const VoiceContext = createContext<VoiceContextType | undefined>(undefined);

export function VoiceProvider({ children }: { children: ReactNode }) {
    const { user } = useUser();
    const storageKey = `meeting_records_${user?.username ?? 'guest'}`;

    const [isProcessing, setIsProcessing] = useState(false);
    const [processingFilename, setProcessingFilename] = useState<string | null>(null);

    // Always start with empty array to prevent SSR/CSR hydration mismatch (React #418).
    // localStorage is only available in the browser, so we load it in useEffect after mount.
    const [records, setRecords] = useState<ProcessedRecord[]>([]);
    const [hydrated, setHydrated] = useState(false);

    // ─── Load records from localStorage after first client-side mount ─────────
    useEffect(() => {
        if (typeof window === 'undefined') return;
        const saved = localStorage.getItem(`meeting_records_${user?.username ?? 'guest'}`);
        if (saved) {
            try {
                const parsed = JSON.parse(saved);
                setRecords(parsed.map((r: any) => ({
                    ...r,
                    processedAt: new Date(r.processedAt),
                    downloadUrl: undefined,
                    transcriptUrl: undefined,
                })));
            } catch {
                // Corrupt data — silently reset
            }
        }
        setHydrated(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []); // Run once on mount only

    // ─── Persist metadata to localStorage on record changes ──────────────────────
    // useRef avoids race condition where storageKey change fires the save effect
    // with empty records, overwriting the new user's saved data.
    const storageKeyRef = useRef(storageKey);
    useEffect(() => { storageKeyRef.current = storageKey; });

    useEffect(() => {
        // Skip the initial empty render before hydration is complete
        if (!hydrated) return;
        const serializable = records.map(r => ({ ...r, downloadUrl: undefined, transcriptUrl: undefined }));
        localStorage.setItem(storageKeyRef.current, JSON.stringify(serializable));
    }, [records, hydrated]); // eslint-disable-line react-hooks/exhaustive-deps

    // ─── Reload records when user switches ────────────────────────────────────────
    useEffect(() => {
        if (typeof window === 'undefined') return;
        const saved = localStorage.getItem(storageKey);
        if (!saved) { setRecords([]); return; }
        try {
            const parsed = JSON.parse(saved);
            const newRecords: ProcessedRecord[] = parsed.map((r: any) => ({
                ...r,
                processedAt: new Date(r.processedAt),
                downloadUrl: undefined,
                transcriptUrl: undefined,
            }));
            setRecords(newRecords);
        } catch {
            setRecords([]);
        }
    }, [storageKey]); // eslint-disable-line react-hooks/exhaustive-deps

    // ─── Process audio file ───────────────────────────────────────────────────────
    const processAudio = async (file: File) => {
        setIsProcessing(true);
        setProcessingFilename(file.name);
        try {
            // analyzeMeetingAudio now returns N8nSTTResponse (via n8n microservice)
            const data = await analyzeMeetingAudio(file);
            const recordId = Date.now().toString();

            // n8n Microservice Version: Results are directly at the top level
            // (No docx download or bilingual transcript URL management needed)
            const newRecord: ProcessedRecord = {
                id: recordId,
                fileName: file.name,
                duration: data.processing_time ? `${data.processing_time.toFixed(1)}s` : 'Unknown',
                processedAt: new Date(),
                transcript: data.transcript ?? '',
                summary: data.summary ?? '',
                decisions: data.decisions ?? [],
                actionItems: data.action_items ?? [],
                downloadUrl: '',
                transcriptUrl: '',
                translatedSegments: [],
            };

            setRecords(prev => [newRecord, ...prev]);
            toast.success('Meeting analysis complete');

            // ── Push metadata to backend for manager preview (non-blocking) ──
            if (user?.username) {
                const decisionsText = Array.isArray(data.decisions)
                    ? data.decisions.join('\n')
                    : String(data.decisions ?? '');
                const actionText = Array.isArray(data.action_items)
                    ? data.action_items.map((a: any) =>
                        typeof a === 'object'
                            ? `[${a.owner ?? ''}] ${a.task ?? ''}${a.deadline ? ` (${a.deadline})` : ''}`
                            : String(a)
                    ).join('\n')
                    : String(data.action_items ?? '');

                fetch(`/api/employee-records`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true' },
                    body: JSON.stringify({
                        empid: user.username,
                        type: 'voice',
                        file_name: file.name,
                        summary: data.summary ?? '',
                        decisions: decisionsText,
                        action_items: actionText,
                    }),
                }).catch(e => console.warn('[VoiceContext] Failed to sync record to backend:', e));
            }
        } catch (error) {
            console.error(error);
            toast.error('處理失敗');
        } finally {
            setIsProcessing(false);
            setProcessingFilename(null);
        }
    };


    // ─── Remove a record ─────────────────────────────────────────────────────────
    const removeRecord = (id: string) => {
        setRecords(prev => prev.filter(r => r.id !== id));
    };

    return (
        <VoiceContext.Provider value={{ isProcessing, processingFilename, records, processAudio, removeRecord }}>
            {children}
        </VoiceContext.Provider>
    );
}

export function useVoice() {
    const context = useContext(VoiceContext);
    if (context === undefined) {
        throw new Error('useVoice must be used within a VoiceProvider');
    }
    return context;
}
