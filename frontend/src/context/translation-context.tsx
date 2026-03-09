'use client';

import React, { createContext, useContext, useState, useEffect, useRef, ReactNode } from 'react';
import { toast } from 'sonner';
import { useUser } from '@/context/user-context';
import { saveBlob, loadBlob, deleteBlob } from '@/lib/pdf-storage';
import { translatePDF } from '@/lib/api/translation';

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
    docxUrl?: string;
}

interface TranslationContextType {
    files: TranslationFile[];
    addFiles: (fileList: File[], sourceLang: string, targetLang: string, debug?: boolean) => void;
    removeFile: (fileId: string) => void;
}

const TranslationContext = createContext<TranslationContextType | undefined>(undefined);

export function TranslationProvider({ children }: { children: ReactNode }) {
    const { user } = useUser();
    const storageKey = `translation_files_${user?.username ?? 'guest'}`;

    const [files, setFiles] = useState<TranslationFile[]>(() => {
        // Initialize metadata from localStorage (blob URLs are NOT stored here)
        if (typeof window === 'undefined') return [];
        const saved = localStorage.getItem(`translation_files_${user?.username ?? 'guest'}`);
        if (!saved) return [];
        try {
            const parsed = JSON.parse(saved);
            return parsed.map((f: any) => ({
                ...f,
                uploadedAt: new Date(f.uploadedAt),
                originalUrl: undefined,  // will be restored from IndexedDB below
                downloadUrl: undefined,   // will be restored from IndexedDB below
                docxUrl: undefined        // will be restored from IndexedDB below
            }));
        } catch {
            return [];
        }
    });

    // ─── Restore blob URLs from IndexedDB on mount ───────────────────────────────
    // On page refresh, files are loaded from localStorage without blob URLs.
    // We look up the actual PDF binaries from IndexedDB and create fresh blob URLs.
    useEffect(() => {
        (async () => {
            const updates: { id: string; changes: Partial<TranslationFile> }[] = [];

            for (const f of files) {
                const changes: Partial<TranslationFile> = {};

                // Restore original (source) PDF
                const origBlob = await loadBlob(`${f.id}_original`);
                if (origBlob) changes.originalUrl = URL.createObjectURL(origBlob);

                // Restore translated PDF (only for completed records)
                if (f.status === 'completed') {
                    const transBlob = await loadBlob(`${f.id}_translated`);
                    if (transBlob) changes.downloadUrl = URL.createObjectURL(transBlob);

                    const docxBlob = await loadBlob(`${f.id}_translated_docx`);
                    if (docxBlob) changes.docxUrl = URL.createObjectURL(docxBlob);
                }

                if (Object.keys(changes).length > 0) {
                    updates.push({ id: f.id, changes });
                }
            }

            if (updates.length > 0) {
                setFiles(prev =>
                    prev.map(f => {
                        const update = updates.find(u => u.id === f.id);
                        return update ? { ...f, ...update.changes } : f;
                    })
                );
            }
        })();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []); // Run once on mount; `files` is stable from useState initializer

    // ─── Persist metadata to localStorage on file changes ────────────────────────
    // useRef avoids the race condition where a storageKey change fires the save
    // effect with empty files, overwriting the new user's saved records.
    const storageKeyRef = useRef(storageKey);
    useEffect(() => { storageKeyRef.current = storageKey; });

    useEffect(() => {
        // Strip blob URLs before saving (they are session-only; IndexedDB holds the binaries)
        const serializable = files.map(f => ({
            ...f,
            originalUrl: undefined,
            downloadUrl: undefined,
            docxUrl: undefined,
        }));
        localStorage.setItem(storageKeyRef.current, JSON.stringify(serializable));
    }, [files]); // eslint-disable-line react-hooks/exhaustive-deps

    // ─── Reload records when user changes ────────────────────────────────────────
    useEffect(() => {
        if (typeof window === 'undefined') return;
        const saved = localStorage.getItem(storageKey);
        if (!saved) { setFiles([]); return; }
        try {
            const parsed = JSON.parse(saved);
            const newFiles = parsed.map((f: any) => ({
                ...f,
                uploadedAt: new Date(f.uploadedAt),
                originalUrl: undefined,
                downloadUrl: undefined,
                docxUrl: undefined
            }));
            setFiles(newFiles);

            // Restore blob URLs for the newly loaded user's records
            (async () => {
                const updates: { id: string; changes: Partial<TranslationFile> }[] = [];
                for (const f of newFiles) {
                    const changes: Partial<TranslationFile> = {};
                    const origBlob = await loadBlob(`${f.id}_original`);
                    if (origBlob) changes.originalUrl = URL.createObjectURL(origBlob);
                    if (f.status === 'completed') {
                        const transBlob = await loadBlob(`${f.id}_translated`);
                        if (transBlob) changes.downloadUrl = URL.createObjectURL(transBlob);
                        
                        const docxBlob = await loadBlob(`${f.id}_translated_docx`);
                        if (docxBlob) changes.docxUrl = URL.createObjectURL(docxBlob);
                    }
                    if (Object.keys(changes).length > 0) updates.push({ id: f.id, changes });
                }
                if (updates.length > 0) {
                    setFiles(prev => prev.map(f => {
                        const u = updates.find(x => x.id === f.id);
                        return u ? { ...f, ...u.changes } : f;
                    }));
                }
            })();
        } catch {
            setFiles([]);
        }
    }, [storageKey]); // eslint-disable-line react-hooks/exhaustive-deps

    // ─── Helpers ─────────────────────────────────────────────────────────────────
    const updateFileStatus = (id: string, updates: Partial<TranslationFile>) => {
        setFiles(prev => prev.map(f => f.id === id ? { ...f, ...updates } : f));
    };

    const uploadAndTranslate = async (fileRecord: TranslationFile, fileObj: File, debug: boolean = false) => {
        updateFileStatus(fileRecord.id, { status: 'uploading', progress: 30 });

        try {
            updateFileStatus(fileRecord.id, { status: 'processing', progress: 60 });

            // Delegate API call to lib/api/translation.ts (browser-side, direct backend)
            const { pdfBlob, docxBlob } = await translatePDF(fileObj, fileRecord.targetLang, debug);

            // Persist translated PDF to IndexedDB so it survives page refresh
            await saveBlob(`${fileRecord.id}_translated`, pdfBlob);
            
            let docxUrl = undefined;
            if (docxBlob) {
                await saveBlob(`${fileRecord.id}_translated_docx`, docxBlob);
                docxUrl = URL.createObjectURL(docxBlob);
            }

            const url = URL.createObjectURL(pdfBlob);
            updateFileStatus(fileRecord.id, {
                status: 'completed',
                progress: 100,
                downloadUrl: url,
                docxUrl: docxUrl
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
            const id = Date.now().toString() + Math.random();

            const newFile: TranslationFile = {
                id,
                name: file.name,
                size: file.size,
                sourceLang,
                targetLang,
                status: 'uploading',
                progress: 0,
                uploadedAt: new Date(),
                originalUrl
            };

            // Persist original PDF to IndexedDB so preview survives refresh
            saveBlob(`${id}_original`, file).catch(console.error);

            setFiles(prev => [newFile, ...prev]);
            uploadAndTranslate(newFile, file, debug);
        });
    };

    const removeFile = (fileId: string) => {
        setFiles(prev => {
            const file = prev.find(f => f.id === fileId);
            if (file) {
                if (file.originalUrl) URL.revokeObjectURL(file.originalUrl);
                if (file.downloadUrl) URL.revokeObjectURL(file.downloadUrl);
                if (file.docxUrl) URL.revokeObjectURL(file.docxUrl);
            }
            return prev.filter(f => f.id !== fileId);
        });
        // Also clean up IndexedDB blobs
        deleteBlob(`${fileId}_original`).catch(console.error);
        deleteBlob(`${fileId}_translated`).catch(console.error);
        deleteBlob(`${fileId}_translated_docx`).catch(console.error);
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
