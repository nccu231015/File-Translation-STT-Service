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

/** IndexedDB key for a record's meeting-minutes Word document */
const docxKey = (id: string) => `${id}_docx`;
/** IndexedDB key for a record's bilingual transcript Word document */
const transcriptKey = (id: string) => `${id}_transcript`;

/** Decode a base64 string into a Blob. */
function _base64ToBlob(base64: string, mimeType?: string): Blob {
    const mime = mimeType || 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
    const binary = window.atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return new Blob([bytes], { type: mime });
}

export function VoiceProvider({ children }: { children: ReactNode }) {
    const { user } = useUser();
    const storageKey = `meeting_records_${user?.username ?? 'guest'}`;

    const [isProcessing, setIsProcessing] = useState(false);
    const [processingFilename, setProcessingFilename] = useState<string | null>(null);

    const [records, setRecords] = useState<ProcessedRecord[]>(() => {
        if (typeof window === 'undefined') return [];
        const saved = localStorage.getItem(`meeting_records_${user?.username ?? 'guest'}`);
        if (!saved) return [];
        try {
            const parsed = JSON.parse(saved);
            return parsed.map((r: any) => ({
                ...r,
                processedAt: new Date(r.processedAt),
                downloadUrl: undefined,    // blob URLs are session-only; restored from IndexedDB
                transcriptUrl: undefined,  // restored from IndexedDB
            }));
        } catch {
            return [];
        }
    });

    // ─── Persist metadata to localStorage on record changes ──────────────────────
    // useRef avoids race condition where storageKey change fires the save effect
    // with empty records, overwriting the new user's saved data.
    const storageKeyRef = useRef(storageKey);
    useEffect(() => { storageKeyRef.current = storageKey; });

    useEffect(() => {
        // Strip blob URLs before saving (session-only; binaries live in IndexedDB)
        const serializable = records.map(r => ({ ...r, downloadUrl: undefined, transcriptUrl: undefined }));
        localStorage.setItem(storageKeyRef.current, JSON.stringify(serializable));
    }, [records]); // eslint-disable-line react-hooks/exhaustive-deps

    // ─── Restore Word blob URLs from IndexedDB on mount ──────────────────────────
    useEffect(() => {
        (async () => {
            const updates: { id: string; downloadUrl?: string; transcriptUrl?: string }[] = [];
            for (const r of records) {
                const upd: { id: string; downloadUrl?: string; transcriptUrl?: string } = { id: r.id };
                const blob = await loadBlob(docxKey(r.id));
                if (blob) upd.downloadUrl = URL.createObjectURL(blob);
                const tBlob = await loadBlob(transcriptKey(r.id));
                if (tBlob) upd.transcriptUrl = URL.createObjectURL(tBlob);
                if (upd.downloadUrl || upd.transcriptUrl) updates.push(upd);
            }
            if (updates.length > 0) {
                setRecords(prev =>
                    prev.map(r => {
                        const u = updates.find(x => x.id === r.id);
                        return u ? { ...r, ...u } : r;
                    })
                );
            }
        })();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []); // Run once on mount; `records` is stable from useState initializer

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

            // Restore blobs for newly loaded user's records
            (async () => {
                const updates: { id: string; downloadUrl?: string; transcriptUrl?: string }[] = [];
                for (const r of newRecords) {
                    const upd: { id: string; downloadUrl?: string; transcriptUrl?: string } = { id: r.id };
                    const blob = await loadBlob(docxKey(r.id));
                    if (blob) upd.downloadUrl = URL.createObjectURL(blob);
                    const tBlob = await loadBlob(transcriptKey(r.id));
                    if (tBlob) upd.transcriptUrl = URL.createObjectURL(tBlob);
                    if (upd.downloadUrl || upd.transcriptUrl) updates.push(upd);
                }
                if (updates.length > 0) {
                    setRecords(prev => prev.map(r => {
                        const u = updates.find(x => x.id === r.id);
                        return u ? { ...r, ...u } : r;
                    }));
                }
            })();
        } catch {
            setRecords([]);
        }
    }, [storageKey]); // eslint-disable-line react-hooks/exhaustive-deps

    // ─── Process audio file ───────────────────────────────────────────────────────
    const processAudio = async (file: File) => {
        setIsProcessing(true);
        setProcessingFilename(file.name);
        try {
            const data = await analyzeMeetingAudio(file);
            const analysis = data.analysis;

            // Decode & persist meeting minutes docx
            let downloadUrl = '';
            const recordId = Date.now().toString();

            if (data.file_download?.content_base64) {
                const blob = _base64ToBlob(
                    data.file_download.content_base64,
                    data.file_download.mime_type,
                );
                await saveBlob(docxKey(recordId), blob);
                downloadUrl = URL.createObjectURL(blob);
            }

            // Decode & persist bilingual transcript docx
            let transcriptUrl = '';
            if (data.transcript_download?.content_base64) {
                const tBlob = _base64ToBlob(
                    data.transcript_download.content_base64,
                    data.transcript_download.mime_type,
                );
                await saveBlob(transcriptKey(recordId), tBlob);
                transcriptUrl = URL.createObjectURL(tBlob);
            }

            const newRecord: ProcessedRecord = {
                id: recordId,
                fileName: file.name,
                duration: 'Unknown',
                processedAt: new Date(),
                transcript: data.transcription.text,
                summary: analysis.summary,
                decisions: analysis.decisions,
                actionItems: analysis.action_items,
                downloadUrl,
                transcriptUrl,
                translatedSegments: data.translated_segments || [],
            };

            setRecords(prev => [newRecord, ...prev]);
            toast.success('會議分析完成');

            // ── Push metadata to backend for manager preview (non-blocking) ──
            if (user?.username) {
                const decisionsText = Array.isArray(analysis.decisions)
                    ? analysis.decisions.join('\n')
                    : String(analysis.decisions ?? '');
                const actionText = Array.isArray(analysis.action_items)
                    ? analysis.action_items.map((a: any) =>
                        typeof a === 'object'
                            ? `[${a.owner ?? ''}] ${a.task ?? ''}${a.deadline ? ` (${a.deadline})` : ''}`
                            : String(a)
                    ).join('\n')
                    : String(analysis.action_items ?? '');

                fetch(`/api/employee-records`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true' },
                    body: JSON.stringify({
                        empid: user.username,
                        type: 'voice',
                        file_name: file.name,
                        summary: analysis.summary ?? '',
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

    // ─── Remove a record and clean up all associated resources ───────────────────
    const removeRecord = (id: string) => {
        setRecords(prev => {
            const record = prev.find(r => r.id === id);
            if (record?.downloadUrl) URL.revokeObjectURL(record.downloadUrl);
            if (record?.transcriptUrl) URL.revokeObjectURL(record.transcriptUrl);
            return prev.filter(r => r.id !== id);
        });
        deleteBlob(docxKey(id)).catch(console.error);
        deleteBlob(transcriptKey(id)).catch(console.error);
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
