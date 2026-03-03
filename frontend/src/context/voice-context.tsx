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
    downloadUrl?: string;
}

interface VoiceContextType {
    isProcessing: boolean;
    processingFilename: string | null;
    records: ProcessedRecord[];
    processAudio: (file: File) => Promise<void>;
    removeRecord: (id: string) => void;
}

const VoiceContext = createContext<VoiceContextType | undefined>(undefined);

/** IndexedDB key for a record's Word document blob */
const docxKey = (id: string) => `${id}_docx`;

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
                downloadUrl: undefined,   // blob URLs are session-only; restored from IndexedDB below
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
        // Strip downloadUrl before saving (session-only blob URL; binary lives in IndexedDB)
        const serializable = records.map(r => ({ ...r, downloadUrl: undefined }));
        localStorage.setItem(storageKeyRef.current, JSON.stringify(serializable));
    }, [records]); // eslint-disable-line react-hooks/exhaustive-deps

    // ─── Restore Word blob URLs from IndexedDB on mount ──────────────────────────
    useEffect(() => {
        (async () => {
            const updates: { id: string; downloadUrl: string }[] = [];
            for (const r of records) {
                const blob = await loadBlob(docxKey(r.id));
                if (blob) {
                    updates.push({ id: r.id, downloadUrl: URL.createObjectURL(blob) });
                }
            }
            if (updates.length > 0) {
                setRecords(prev =>
                    prev.map(r => {
                        const u = updates.find(x => x.id === r.id);
                        return u ? { ...r, downloadUrl: u.downloadUrl } : r;
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
            }));
            setRecords(newRecords);

            // Restore Word blobs for newly loaded user's records
            (async () => {
                const updates: { id: string; downloadUrl: string }[] = [];
                for (const r of newRecords) {
                    const blob = await loadBlob(docxKey(r.id));
                    if (blob) {
                        updates.push({ id: r.id, downloadUrl: URL.createObjectURL(blob) });
                    }
                }
                if (updates.length > 0) {
                    setRecords(prev =>
                        prev.map(r => {
                            const u = updates.find(x => x.id === r.id);
                            return u ? { ...r, downloadUrl: u.downloadUrl } : r;
                        })
                    );
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

            // Decode Base64 Word document and persist to IndexedDB
            let downloadUrl = '';
            const recordId = Date.now().toString();

            if (data.file_download?.content_base64) {
                const binaryString = window.atob(data.file_download.content_base64);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }
                const blob = new Blob([bytes], {
                    type: data.file_download.mime_type ||
                        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                });

                // Persist Word blob to IndexedDB so download survives page refresh
                await saveBlob(docxKey(recordId), blob);
                downloadUrl = URL.createObjectURL(blob);
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
            };

            setRecords(prev => [newRecord, ...prev]);
            toast.success('會議分析完成');
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
            // Revoke the session blob URL to avoid memory leaks
            if (record?.downloadUrl) {
                URL.revokeObjectURL(record.downloadUrl);
            }
            return prev.filter(r => r.id !== id);
        });
        // Clean up the Word document binary from IndexedDB
        deleteBlob(docxKey(id)).catch(console.error);
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
