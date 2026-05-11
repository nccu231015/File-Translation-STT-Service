'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
    Send, Loader2, Bot, User as UserIcon,
    FileSearch, Mic, Square, UploadCloud,
    FileText, CheckCircle2, XCircle, Trash2, X,
    PlusCircle, MessageSquare, ChevronRight
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'framer-motion';
import {
    askDocumentQA, uploadDocument,
    listDocSessions, getDocSession, deleteDocSession,
    listDocFiles, deleteDocFile,
    DocSessionSummary, DocSessionMessage, DocFileRecord
} from '@/lib/api/doc-qa';

interface Message {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date | null;
}

type FileStatus = 'uploading' | 'done' | 'error';

// Local tracking for in-progress uploads (not yet confirmed by backend)
interface UploadingFile {
    id: string;
    name: string;
    size: number;
    status: FileStatus;
    errorMsg?: string;
}

const WELCOME_MSG: Message = {
    id: 'welcome',
    role: 'assistant',
    content: '您好！我是 **文件知識助理 (KM)**。您可以詢問關於公司 **SOP、規範手冊、作業標準、教育訓練** 等文件內容。\n\n請先在左側上傳 PDF 文件建立知識庫，再開始提問。',
    timestamp: new Date(),
};

export function DocQAInterface() {
    const [mounted, setMounted] = useState(false);
    const [messages, setMessages] = useState<Message[]>([WELCOME_MSG]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    // Session state
    const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
    const [sessions, setSessions] = useState<DocSessionSummary[]>([]);

    // Persistent file records loaded from backend (survive page refresh)
    const [persistedFiles, setPersistedFiles] = useState<DocFileRecord[]>([]);
    // In-progress uploads tracked locally only
    const [uploadingFiles, setUploadingFiles] = useState<UploadingFile[]>([]);
    const [isDragging, setIsDragging] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // ── System load indicator ─────────────────────────────────────────────────
    const [systemBusy, setSystemBusy] = useState(false);
    useEffect(() => {
        const backendUrl = `http://${window.location.hostname}:8000`;
        const check = async () => {
            try {
                const res = await fetch(`${backendUrl}/system-status`);
                if (res.ok) {
                    const data = await res.json();
                    setSystemBusy(!!data.busy);
                }
            } catch { /* ignore network errors */ }
        };
        check();
        const timer = setInterval(check, 15000); // poll every 15s
        return () => clearInterval(timer);
    }, []);

    // Voice Input
    const [isRecording, setIsRecording] = useState(false);
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const audioChunksRef = useRef<Blob[]>([]);

    const scrollRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);

    // Hydration-safe time display
    const [timeStrings, setTimeStrings] = useState<Record<string, string>>({});
    useEffect(() => {
        const t: Record<string, string> = {};
        messages.forEach(m => {
            if (m.timestamp) {
                t[m.id] = m.timestamp.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' });
            }
        });
        setTimeStrings(t);
    }, [messages]);

    // ── Init: load session list and restore latest session (files load per session_id below) ──
    useEffect(() => {
        setMounted(true);
        listDocSessions()
            .then(async (list: DocSessionSummary[]) => {
                setSessions(list);
                if (list.length > 0) {
                    const sid = list[0].session_id;
                    setCurrentSessionId(sid);
                    try {
                        const detail = await getDocSession(sid);
                        if (detail && detail.messages.length > 0) {
                            const restored: Message[] = detail.messages.map((m: DocSessionMessage, i: number) => ({
                                id: `${m.role}-${i}-restored`,
                                role: m.role as 'user' | 'assistant',
                                content: m.content,
                                timestamp: new Date(m.ts),
                            }));
                            setMessages(restored);
                        }
                    } catch (e) {
                        console.warn('Failed to restore last doc session', e);
                    }
                }
            })
            .catch((e: unknown) => console.error('Failed to load doc sessions', e));
    }, []);

    // Reload per-session file list when the active chat session changes
    useEffect(() => {
        if (!mounted) return;
        if (!currentSessionId) {
            setPersistedFiles([]);
            return;
        }
        listDocFiles(currentSessionId).then(setPersistedFiles).catch(() => setPersistedFiles([]));
    }, [mounted, currentSessionId]);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages, isLoading]);

    // ── Session Helpers ──────────────────────────────────────────────────────
    const loadSessions = async () => {
        try {
            setSessions(await listDocSessions());
        } catch (e) {
            console.error('Failed to load doc sessions', e);
        }
    };

    const startNewChat = () => {
        setCurrentSessionId(null);
        setPersistedFiles([]);
        setMessages([WELCOME_MSG]);
        setInput('');
        setTimeout(() => inputRef.current?.focus(), 10);
    };

    const loadSession = async (session_id: string) => {
        const detail = await getDocSession(session_id);
        if (!detail) return;
        const restored: Message[] = detail.messages.map((m: DocSessionMessage, i: number) => ({
            id: `${m.role}-${i}-${Date.now()}`,
            role: m.role as 'user' | 'assistant',
            content: m.content,
            timestamp: new Date(m.ts),
        }));
        setCurrentSessionId(session_id);
        setMessages(restored.length > 0 ? restored : [WELCOME_MSG]);
        setInput('');
    };

    const removeSession = async (e: React.MouseEvent, session_id: string) => {
        e.stopPropagation();
        if (!window.confirm('確定要刪除這段對話嗎？資料刪除後無法復原。')) return;
        try {
            await deleteDocSession(session_id);
            if (currentSessionId === session_id) startNewChat();
            await loadSessions();
        } catch {
            alert('刪除失敗，請稍後再試。');
        }
    };

    const formatSessionDate = (iso: string) => {
        if (!mounted) return '';
        const d = new Date(iso);
        return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
    };

    // ── File Helpers ─────────────────────────────────────────────────────────
    const loadFiles = async () => {
        if (!currentSessionId) {
            setPersistedFiles([]);
            return;
        }
        try {
            setPersistedFiles(await listDocFiles(currentSessionId));
        } catch (e) {
            console.error('Failed to load doc files', e);
        }
    };

    const handleDeleteFile = async (e: React.MouseEvent, filename: string) => {
        e.stopPropagation();
        if (!currentSessionId) return;
        if (!window.confirm(`確定要從本對話的知識庫清單中移除「${filename}」嗎？`)) return;
        try {
            await deleteDocFile(filename, currentSessionId);
            await loadFiles();
            toast.success(`${filename} 已從清單中移除`);
        } catch {
            toast.error('移除失敗，請稍後再試。');
        }
    };

    // ── File Upload ──────────────────────────────────────────────────────────
    const processFiles = useCallback(async (files: File[]) => {
        const pdfs = files.filter(f => f.name.toLowerCase().endsWith('.pdf'));
        if (pdfs.length === 0) { toast.error('請上傳 PDF 格式的文件'); return; }

        // Use a local variable to track the session ID across sequential uploads,
        // because the React state (currentSessionId) won't update mid-loop.
        let activeSessionId = currentSessionId;

        // 1. Immediately add all selected files to the uploading UI state
        const filesWithIds = pdfs.map(f => ({
            file: f,
            id: `${f.name}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
        }));
        
        setUploadingFiles(prev => [
            ...prev,
            ...filesWithIds.map(({ file, id }) => ({
                id,
                name: file.name,
                size: file.size,
                status: 'uploading' as FileStatus
            }))
        ]);

        // 2. Process them sequentially
        for (const { file, id } of filesWithIds) {
            try {
                const data = await uploadDocument(file, activeSessionId);
                // Remove from uploading list upon success
                setUploadingFiles(prev => prev.filter(u => u.id !== id));
                if (data.session_id) {
                    activeSessionId = data.session_id;
                    setCurrentSessionId(data.session_id);
                }
                toast.success(`${file.name} 已成功寫入知識庫`);
            } catch (err: unknown) {
                const msg = err instanceof Error ? err.message : '未知錯誤';
                // Mark as error
                setUploadingFiles(prev => prev.map(u => u.id === id ? { ...u, status: 'error', errorMsg: msg } : u));
                toast.error(`${file.name} 上傳失敗`);
            }
        }

        // 3. Refresh both session list and file list once after all uploads complete
        await loadSessions();
        if (activeSessionId) {
            try {
                setPersistedFiles(await listDocFiles(activeSessionId));
            } catch (e) {
                console.error('Failed to reload doc files after upload', e);
            }
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [currentSessionId]);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files) processFiles(Array.from(e.target.files));
        e.target.value = '';
    };
    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault(); setIsDragging(false);
        if (e.dataTransfer.files) processFiles(Array.from(e.dataTransfer.files));
    }, [processFiles]);
    const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); };
    const handleDragLeave = () => setIsDragging(false);
    const removeUploadingFile = (id: string) => setUploadingFiles(prev => prev.filter(f => f.id !== id));
    const formatSize = (bytes: number) => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    // ── Voice Input ──────────────────────────────────────────────────────────
    const startRecording = async () => {
        try {
            if (!navigator.mediaDevices?.getUserMedia) {
                toast.error('無法存取麥克風：請確認連線為 https 或 localhost'); return;
            }
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mediaRecorder = new MediaRecorder(stream);
            mediaRecorderRef.current = mediaRecorder;
            audioChunksRef.current = [];
            mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
            mediaRecorder.onstop = async () => {
                const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
                stream.getTracks().forEach(t => t.stop());
                const file = new File([blob], 'voice_input.webm', { type: 'audio/webm' });
                setIsLoading(true);
                toast.info('正在辨識語音...');
                try {
                    const { transcribeAudio } = await import('@/lib/api/stt');
                    const result = await transcribeAudio(file);
                    if (result.transcription?.text) {
                        setInput(prev => (prev + ' ' + result.transcription.text.trim()).trim());
                        toast.success('語音辨識完成');
                    }
                } catch { toast.error('語音辨識失敗，請稍後再試'); }
                finally { setIsLoading(false); }
            };
            mediaRecorder.start();
            setIsRecording(true);
        } catch (error: any) {
            if (error.name === 'NotFoundError') toast.error('找不到麥克風設備');
            else if (error.name === 'NotAllowedError') toast.error('麥克風存取被拒絕');
            else toast.error(`無法存取麥克風: ${error.message || '未知錯誤'}`);
        }
    };
    const stopRecording = () => {
        if (mediaRecorderRef.current && isRecording) { mediaRecorderRef.current.stop(); setIsRecording(false); }
    };

    // ── Send Message ─────────────────────────────────────────────────────────
    const handleSend = async (text: string = input) => {
        if (!text.trim() || isLoading) return;
        const finalText = text.trim();
        setInput('');
        const userMsg: Message = { id: `user-${Date.now()}`, role: 'user', content: finalText, timestamp: new Date() };
        setMessages(prev => [...prev.filter(m => m.id !== 'welcome'), userMsg]);
        setIsLoading(true);
        try {
            const data = await askDocumentQA(finalText, currentSessionId ?? undefined);
            if (!currentSessionId) {
                setCurrentSessionId(data.session_id);
            }
            setMessages(prev => [...prev, {
                id: `ai-${Date.now()}`, role: 'assistant', content: data.response, timestamp: new Date(),
            }]);
        } catch {
            setMessages(prev => [...prev, {
                id: `error-${Date.now()}`, role: 'assistant',
                content: '⚠️ 抱歉，知識庫查詢服務連線異常，請稍後再試。', timestamp: new Date(),
            }]);
        } finally {
            setIsLoading(false);
            // Always refresh session list after any send attempt
            loadSessions();
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
    };

    if (!mounted) return null;

    return (
        <div className="flex h-[calc(100vh-8rem)] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">

            {/* ── Left Panel ──────────────────────────────────────────────── */}
            <div className="w-72 flex-shrink-0 border-r border-slate-100 bg-slate-50 flex flex-col">

                {/* New chat button */}
                <div className="px-3 pt-3 pb-2">
                    <Button
                        onClick={startNewChat}
                        className="w-full gap-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm h-9"
                    >
                        <PlusCircle className="size-4" /> 新對話
                    </Button>
                </div>

                {/* Session list */}
                <div className="flex-1 overflow-y-auto px-2 space-y-1 min-h-0">
                    {sessions.length === 0 ? (
                        <p className="text-[11px] text-slate-400 text-center pt-3 px-2">尚無對話紀錄</p>
                    ) : sessions.map(s => (
                        <button
                            key={s.session_id}
                            onClick={() => loadSession(s.session_id)}
                            className={`group w-full text-left px-3 py-2.5 rounded-xl transition-all flex items-start gap-2 ${
                                currentSessionId === s.session_id
                                    ? 'bg-emerald-50 border border-emerald-200'
                                    : 'hover:bg-white hover:shadow-sm border border-transparent'
                            }`}
                        >
                            <MessageSquare className={`size-4 flex-shrink-0 mt-0.5 ${
                                currentSessionId === s.session_id ? 'text-emerald-600' : 'text-slate-400'
                            }`} />
                            <div className="flex-1 min-w-0">
                                <p className={`text-xs font-medium truncate ${
                                    currentSessionId === s.session_id ? 'text-emerald-800' : 'text-slate-700'
                                }`}>{s.title}</p>
                                <p className="text-[10px] text-slate-400">{formatSessionDate(s.updated_at)}</p>
                            </div>
                            <button
                                onClick={(e) => removeSession(e, s.session_id)}
                                className="group-hover:opacity-100 text-slate-300 hover:text-red-500 transition-all flex-shrink-0 mt-0.5 px-1"
                                title="刪除對話"
                            >
                                <Trash2 className="size-3.5" />
                            </button>
                        </button>
                    ))}
                </div>

                {/* Divider */}
                <div className="mx-3 border-t border-slate-200 my-2" />

                {/* Per-session knowledge base file list (same Chroma collection; UI scoped to this chat) */}
                <div className="px-4 pb-1 flex items-center gap-2">
                    <FileSearch className="size-3.5 text-emerald-600" />
                    <span className="text-xs font-semibold text-slate-600">本對話上傳</span>
                    <Badge variant="outline" className="ml-auto text-[10px] text-emerald-600 border-emerald-200 bg-emerald-50">
                        {persistedFiles.length} 份
                    </Badge>
                </div>

                {/* Drop Zone */}
                <div
                    onDrop={handleDrop} onDragOver={handleDragOver} onDragLeave={handleDragLeave}
                    onClick={() => fileInputRef.current?.click()}
                    className={`mx-3 mb-1 rounded-xl border-2 border-dashed cursor-pointer transition-all px-3 py-3 flex flex-col items-center gap-1 ${
                        isDragging ? 'border-emerald-400 bg-emerald-50 scale-[1.01]' : 'border-slate-300 hover:border-emerald-300 hover:bg-emerald-50/50'
                    }`}
                >
                    <UploadCloud className={`size-6 transition-colors ${isDragging ? 'text-emerald-500' : 'text-slate-400'}`} />
                    <p className="text-[11px] text-slate-500 text-center">
                        拖放 PDF 或<span className="text-emerald-600 font-semibold">點擊上傳</span>
                    </p>
                </div>
                <input ref={fileInputRef} type="file" accept=".pdf" multiple className="hidden" onChange={handleFileChange} />

                {/* System busy warning */}
                {systemBusy && (
                    <div className="mx-3 mb-1 flex items-start gap-1.5 rounded-lg bg-amber-50 border border-amber-200 px-2.5 py-1.5">
                        <span className="text-amber-500 mt-0.5 text-xs">⚠</span>
                        <p className="text-[11px] text-amber-700 leading-snug">
                            系統目前運算負載較高，文件處理可能需要較長時間，請耐心等候。
                        </p>
                    </div>
                )}

                {/* File list */}
                <div className="overflow-y-auto px-3 pb-2 space-y-1 max-h-48">
                    {/* In-progress uploads */}
                    <AnimatePresence>
                        {uploadingFiles.map(f => (
                            <motion.div
                                key={f.id}
                                initial={{ opacity: 0, y: -4 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, x: -16 }}
                                className="flex items-center gap-1.5 bg-white rounded-lg px-2 py-1.5 border border-slate-100 shadow-sm group"
                            >
                                <div className="flex-shrink-0">
                                    {f.status === 'uploading' && <Loader2 className="size-3.5 text-emerald-500 animate-spin" />}
                                    {f.status === 'error' && <XCircle className="size-3.5 text-red-500" />}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <p className="text-[11px] font-medium text-slate-700 truncate">{f.name}</p>
                                    <p className="text-[10px] text-slate-400">{f.status === 'uploading' ? '上傳中...' : '上傳失敗'}</p>
                                </div>
                                {f.status === 'error' && (
                                    <button onClick={() => removeUploadingFile(f.id)} className="text-slate-400 hover:text-red-500 flex-shrink-0 transition-opacity">
                                        <X className="size-3" />
                                    </button>
                                )}
                            </motion.div>
                        ))}
                    </AnimatePresence>
                    {/* Persisted files from backend */}
                    {persistedFiles.length === 0 && uploadingFiles.length === 0 ? (
                        <p className="text-[10px] text-slate-400 text-center py-1">尚未上傳任何文件</p>
                    ) : (
                        <AnimatePresence>
                            {persistedFiles.map(f => (
                                <motion.div
                                    key={f.filename}
                                    initial={{ opacity: 0, y: -4 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, x: -16 }}
                                    className="flex items-center gap-1.5 bg-white rounded-lg px-2 py-1.5 border border-slate-100 shadow-sm group"
                                >
                                    <CheckCircle2 className="size-3.5 text-emerald-500 flex-shrink-0" />
                                    <div className="flex-1 min-w-0">
                                        <p className="text-[11px] font-medium text-slate-700 truncate">{f.filename}</p>
                                        <p className="text-[10px] text-slate-400">{formatSize(f.size)}</p>
                                    </div>
                                    <button
                                        onClick={(e) => handleDeleteFile(e, f.filename)}
                                        className="opacity-0 group-hover:opacity-60 hover:!opacity-100 text-slate-400 hover:text-red-500 flex-shrink-0 transition-opacity"
                                        title="從清單移除"
                                    >
                                        <Trash2 className="size-3" />
                                    </button>
                                </motion.div>
                            ))}
                        </AnimatePresence>
                    )}
                </div>
            </div>

            {/* ── Right Panel: Chat Area ────────────────────────────────────── */}
            <div className="flex flex-col flex-1 min-w-0 bg-slate-50/10">
                {/* Header */}
                <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-100 bg-white z-10 shadow-sm">
                    <FileText className="size-5 text-emerald-600" />
                    <div>
                        <h2 className="text-sm font-semibold text-slate-800">文件知識智慧問答</h2>
                        <p className="text-[10px] text-slate-400">由企業知識庫（KM）驅動</p>
                    </div>
                    <div className="ml-auto">
                        <Badge variant="outline" className="text-xs gap-1 text-emerald-600 border-emerald-200 bg-emerald-50/50">
                            <span className="size-1.5 rounded-full bg-green-500 animate-pulse inline-block" />
                            AI 連線中
                        </Badge>
                    </div>
                </div>

                {/* Messages */}
                <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-6 scroll-smooth">
                    <AnimatePresence initial={false}>
                        {messages.map(msg => (
                            <motion.div
                                key={msg.id}
                                layout
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
                            >
                                <div className={`size-9 rounded-xl flex-shrink-0 flex items-center justify-center shadow-sm ${
                                    msg.role === 'user' ? 'bg-emerald-600 text-white' : 'bg-white border border-slate-200 text-emerald-600'
                                }`}>
                                    {msg.role === 'user' ? <UserIcon className="size-5" /> : <Bot className="size-5" />}
                                </div>
                                <div className={`group relative max-w-[85%] sm:max-w-[75%] rounded-2xl px-4 py-3 text-sm shadow-sm transition-all ${
                                    msg.role === 'user'
                                        ? 'bg-emerald-600 text-white rounded-tr-none'
                                        : 'bg-white border border-slate-100 text-slate-800 rounded-tl-none'
                                }`}>
                                    {msg.role === 'assistant' ? (
                                        <div className="prose prose-sm max-w-none prose-emerald prose-headings:text-emerald-900 prose-code:bg-emerald-50 prose-code:px-1 prose-code:rounded prose-table:border prose-table:border-slate-200 prose-th:bg-slate-50 prose-th:px-2 prose-td:px-2">
                                            <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                                                {msg.content}
                                            </ReactMarkdown>
                                        </div>
                                    ) : (
                                        <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                                    )}
                                    <div className={`flex items-center gap-2 mt-2 pt-1 border-t opacity-60 ${
                                        msg.role === 'user' ? 'border-white/10 text-white' : 'border-slate-100 text-slate-400'
                                    }`}>
                                        <p className="text-[10px]">{timeStrings[msg.id] || '--:--'}</p>
                                    </div>
                                </div>
                            </motion.div>
                        ))}
                    </AnimatePresence>

                    {isLoading && (
                        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-3">
                            <div className="size-9 rounded-xl bg-white border border-slate-200 flex items-center justify-center shadow-sm">
                                <Bot className="size-5 text-emerald-500 animate-pulse" />
                            </div>
                            <div className="bg-white border border-slate-100 rounded-2xl rounded-tl-none px-5 py-3 shadow-sm flex items-center gap-3">
                                <div className="flex gap-1">
                                    <span className="size-1.5 bg-emerald-400 rounded-full animate-bounce [animation-delay:-0.3s]" />
                                    <span className="size-1.5 bg-emerald-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
                                    <span className="size-1.5 bg-emerald-400 rounded-full animate-bounce" />
                                </div>
                                <span className="text-xs text-slate-400 font-medium whitespace-nowrap">正在搜尋知識庫...</span>
                            </div>
                        </motion.div>
                    )}
                </div>

                {/* Input area */}
                <div className="p-4 bg-white border-t border-slate-100 flex flex-col gap-3">
                    <div className="max-w-4xl mx-auto w-full flex gap-3 items-end bg-slate-50 p-2 rounded-2xl border border-slate-200 focus-within:border-emerald-400 focus-within:ring-2 focus-within:ring-emerald-100 transition-all shadow-inner">
                        <Textarea
                            ref={inputRef}
                            value={input}
                            onChange={e => setInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="詢問關於文件內容的問題... (Shift+Enter 換行)"
                            rows={1}
                            className="flex-1 min-h-[44px] max-h-32 resize-none bg-transparent border-none text-sm focus-visible:ring-0 focus-visible:ring-offset-0 px-3 py-3"
                            disabled={isLoading || isRecording}
                        />
                        <Button
                            onClick={isRecording ? stopRecording : startRecording}
                            disabled={isLoading}
                            variant="outline"
                            className={`size-10 rounded-xl p-0 flex-shrink-0 shadow-sm transition-all ${
                                isRecording
                                    ? 'bg-red-50 hover:bg-red-100 text-red-500 border-red-200 animate-pulse'
                                    : 'bg-white text-slate-500 hover:text-emerald-600 border-slate-200 hover:border-emerald-200'
                            }`}
                        >
                            {isRecording ? <Square className="size-4" /> : <Mic className="size-5" />}
                        </Button>
                        <Button
                            onClick={() => handleSend()}
                            disabled={isLoading || isRecording || !input.trim()}
                            className="size-10 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white p-0 flex-shrink-0 shadow-lg active:scale-90 transition-all disabled:bg-slate-300"
                        >
                            {isLoading ? <Loader2 className="size-5 animate-spin" /> : <Send className="size-5" />}
                        </Button>
                    </div>
                    <p className="text-[10px] text-center text-slate-400 mt-2">
                        回答內容僅供參考，請以正式文件為準。所有查詢均在地端進行，資料不會外傳。
                    </p>
                </div>
            </div>
        </div>
    );
}


