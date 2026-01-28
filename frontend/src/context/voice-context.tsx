'use client';

import React, { createContext, useContext, useState, useEffect, Dispatch, SetStateAction, ReactNode } from 'react';
import { toast } from 'sonner';
import { analyzeMeetingAudio } from '@/lib/api/stt';

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
    setRecords: Dispatch<SetStateAction<ProcessedRecord[]>>;
    processAudio: (file: File) => Promise<void>;
}

const VoiceContext = createContext<VoiceContextType | undefined>(undefined);

const STORAGE_KEY = 'meeting_records';

export function VoiceProvider({ children }: { children: ReactNode }) {
    const [isProcessing, setIsProcessing] = useState(false);
    const [processingFilename, setProcessingFilename] = useState<string | null>(null);

    const [records, setRecords] = useState<ProcessedRecord[]>(() => {
        // Initialize from localStorage
        if (typeof window === 'undefined') return [];
        const saved = localStorage.getItem(STORAGE_KEY);
        if (!saved) return [];
        try {
            const parsed = JSON.parse(saved);
            return parsed.map((r: any) => ({
                ...r,
                processedAt: new Date(r.processedAt)
            }));
        } catch {
            return [];
        }
    });

    // Persistence
    useEffect(() => {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(records));
    }, [records]);

    const processAudio = async (file: File) => {
        setIsProcessing(true);
        setProcessingFilename(file.name);
        try {
            const data = await analyzeMeetingAudio(file);
            const analysis = data.analysis;

            // Handle Word document download
            let downloadUrl = '';
            if (data.file_download && data.file_download.content_base64) {
                const binaryString = window.atob(data.file_download.content_base64);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }
                const blob = new Blob([bytes], {
                    type: data.file_download.mime_type || 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                });
                downloadUrl = URL.createObjectURL(blob);
            }

            const newRecord: ProcessedRecord = {
                id: Date.now().toString(),
                fileName: file.name,
                duration: 'Unknown',
                processedAt: new Date(),
                transcript: data.transcription.text,
                summary: analysis.summary,
                decisions: analysis.decisions,
                actionItems: analysis.action_items,
                downloadUrl: downloadUrl
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

    return (
        <VoiceContext.Provider value={{ isProcessing, processingFilename, records, setRecords, processAudio }}>
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
