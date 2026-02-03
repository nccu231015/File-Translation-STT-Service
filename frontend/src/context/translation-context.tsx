'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { toast } from 'sonner';

export interface TranslationFile {
    id: string;
    name: string;
    size: number;
    sourceLang: string;
    targetLang: string;
    status: 'uploading' | 'processing' | 'completed' | 'error';
    progress: number;
    uploadedAt: Date;
    originalUrl?: string;
    downloadUrl?: string;
}

interface TranslationContextType {
    files: TranslationFile[];
    addFiles: (fileList: File[], sourceLang: string, targetLang: string, debug?: boolean) => void;
    removeFile: (fileId: string) => void;
}

const TranslationContext = createContext<TranslationContextType | undefined>(undefined);

const STORAGE_KEY = 'translation_files';

export function TranslationProvider({ children }: { children: ReactNode }) {
    const [files, setFiles] = useState<TranslationFile[]>(() => {
        // Initialize from localStorage
        if (typeof window === 'undefined') return [];
        const saved = localStorage.getItem(STORAGE_KEY);
        if (!saved) return [];
        try {
            const parsed = JSON.parse(saved);
            // Convert date strings back to Date objects
            // Note: blob URLs (originalUrl, downloadUrl) cannot be persisted
            return parsed.map((f: any) => ({
                ...f,
                uploadedAt: new Date(f.uploadedAt),
                originalUrl: undefined, // Blob URLs don't survive refresh
                downloadUrl: undefined
            }));
        } catch {
            return [];
        }
    });

    // Save to localStorage whenever files change
    useEffect(() => {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(files));
    }, [files]);

    const updateFileStatus = (id: string, updates: Partial<TranslationFile>) => {
        setFiles(prev => prev.map(f => f.id === id ? { ...f, ...updates } : f));
    };

    const uploadAndTranslate = async (fileRecord: TranslationFile, fileObj: File, debug: boolean = false) => {
        updateFileStatus(fileRecord.id, { status: 'uploading', progress: 30 });

        const formData = new FormData();
        formData.append('file', fileObj);
        formData.append('target_lang', fileRecord.targetLang);
        formData.append('debug', debug.toString());

        try {
            updateFileStatus(fileRecord.id, { status: 'processing', progress: 60 });
            // ... (rest of function)
            const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

            const res = await fetch(`${API_URL}/pdf-translation`, {
                method: 'POST',
                body: formData
            });

            if (!res.ok) throw new Error('Translation failed');

            const blob = await res.blob();
            const pdfBlob = new Blob([blob], { type: 'application/pdf' });
            const url = URL.createObjectURL(pdfBlob);

            updateFileStatus(fileRecord.id, {
                status: 'completed',
                progress: 100,
                downloadUrl: url
            });
            toast.success(`${fileRecord.name} ${debug ? 'Debug 預覽' : '翻譯'}完成`);

        } catch (error) {
            console.error(error);
            updateFileStatus(fileRecord.id, { status: 'error', progress: 0 });
            toast.error(`${fileRecord.name} 翻譯失敗`);
        }
    };

    const addFiles = (fileList: File[], sourceLang: string, targetLang: string, debug: boolean = false) => {
        const pdfFiles = fileList.filter(file => file.type === 'application/pdf');

        pdfFiles.forEach(file => {
            const originalUrl = URL.createObjectURL(file);

            const newFile: TranslationFile = {
                id: Date.now().toString() + Math.random(),
                name: file.name,
                size: file.size,
                sourceLang,
                targetLang,
                status: 'uploading',
                progress: 0,
                uploadedAt: new Date(),
                originalUrl: originalUrl
            };

            setFiles(prev => [newFile, ...prev]);
            // Fire and forget
            uploadAndTranslate(newFile, file, debug);
        });
    };

    const removeFile = (fileId: string) => {
        setFiles(prev => {
            const file = prev.find(f => f.id === fileId);
            if (file) {
                if (file.originalUrl) URL.revokeObjectURL(file.originalUrl);
                if (file.downloadUrl) URL.revokeObjectURL(file.downloadUrl);
            }
            return prev.filter(f => f.id !== fileId);
        });
    };

    return (
        <TranslationContext.Provider value={{ files, addFiles, removeFile }}>
            {children}
        </TranslationContext.Provider>
    );
}

export function useTranslation() {
    const context = useContext(TranslationContext);
    if (context === undefined) {
        throw new Error('useTranslation must be used within a TranslationProvider');
    }
    return context;
}
