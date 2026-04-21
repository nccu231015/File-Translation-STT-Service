'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
    Send, Loader2, Bot, User as UserIcon,
    FileSearch, Mic, Square, UploadCloud,
    FileText, CheckCircle2, XCircle, Trash2, X
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'framer-motion';
import { askDocumentQA, uploadDocument } from '@/lib/api/doc-qa';

interface Message {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date | null;
}

type FileStatus = 'uploading' | 'done' | 'error';

interface UploadedFile {
    id: string;
    name: string;
    size: number;
    status: FileStatus;
    errorMsg?: string;
}

export function DocQAInterface() {
    const [mounted, setMounted] = useState(false);
    const [messages, setMessages] = useState<Message[]>([]);
    const [quickQuestions] = useState<string[]>([
        '請說明本公司的電焊作業安全規範',
        '設備點檢的 SOP 是什麼？',
        '新人訓練的流程與注意事項',
        '品質異常處理程序',
    ]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    // Uploaded file records (client-side tracking only)
    const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
    const [isDragging, setIsDragging] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

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

    useEffect(() => {
        setMounted(true);
        setMessages([{
            id: 'welcome',
            role: 'assistant',
            content: '您好！我是 **文件知識助理 (KM)**。您可以詢問關於公司 **SOP、規範手冊、作業標準、教育訓練** 等文件內容。\n\n請先在左側上傳 PDF 文件建立知識庫，再開始提問。',
            timestamp: new Date(),
        }]);
    }, []);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages, isLoading]);

    // ── File Upload ──────────────────────────────────────────────────────────
    const processFiles = useCallback(async (files: File[]) => {
        const pdfs = files.filter(f => f.name.toLowerCase().endsWith('.pdf'));
        if (pdfs.length === 0) {
            toast.error('請上傳 PDF 格式的文件');
            return;
        }

        for (const f of pdfs) {
            const id = `${f.name}-${Date.now()}`;
            // Add to list with uploading status
            setUploadedFiles(prev => [...prev, {
                id,
                name: f.name,
                size: f.size,
                status: 'uploading',
            }]);

            try {
                await uploadDocument(f);
                setUploadedFiles(prev =>
                    prev.map(u => u.id === id ? { ...u, status: 'done' } : u)
                );
                toast.success(`${f.name} 已成功寫入知識庫`);
            } catch (err: any) {
                setUploadedFiles(prev =>
                    prev.map(u => u.id === id ? { ...u, status: 'error', errorMsg: err.message } : u)
                );
                toast.error(`${f.name} 上傳失敗`);
            }
        }
    }, []);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files) processFiles(Array.from(e.target.files));
        e.target.value = '';
    };

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        if (e.dataTransfer.files) processFiles(Array.from(e.dataTransfer.files));
    }, [processFiles]);

    const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); };
    const handleDragLeave = () => setIsDragging(false);

    const removeFile = (id: string) => {
        setUploadedFiles(prev => prev.filter(f => f.id !== id));
    };

    const formatSize = (bytes: number) => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    // ── Voice Input ──────────────────────────────────────────────────────────
    const startRecording = async () => {
        try {
            if (!navigator.mediaDevices?.getUserMedia) {
                toast.error('無法存取麥克風：請確認連線為 https 或 localhost');
                return;
            }
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mediaRecorder = new MediaRecorder(stream);
            mediaRecorderRef.current = mediaRecorder;
            audioChunksRef.current = [];
            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) audioChunksRef.current.push(e.data);
            };
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
                } catch {
                    toast.error('語音辨識失敗，請稍後再試');
                } finally {
                    setIsLoading(false);
                }
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
        if (mediaRecorderRef.current && isRecording) {
            mediaRecorderRef.current.stop();
            setIsRecording(false);
        }
    };

    // ── Send Message ─────────────────────────────────────────────────────────
    const handleSend = async (text: string = input) => {
        if (!text.trim() || isLoading) return;
        const finalText = text.trim();
        setInput('');
        const userMsg: Message = {
            id: `user-${Date.now()}`,
            role: 'user',
            content: finalText,
            timestamp: new Date(),
        };
        setMessages(prev => {
            const filtered = prev.filter(m => m.id !== 'welcome');
            return [...filtered, userMsg];
        });
        setIsLoading(true);
        try {
            const data = await askDocumentQA(finalText);
            setMessages(prev => [...prev, {
                id: `ai-${Date.now()}`,
                role: 'assistant',
                content: data.response,
                timestamp: new Date(),
            }]);
        } catch {
            setMessages(prev => [...prev, {
                id: `error-${Date.now()}`,
                role: 'assistant',
                content: '⚠️ 抱歉，知識庫查詢服務連線異常，請稍後再試。',
                timestamp: new Date(),
            }]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    if (!mounted) return null;

    return (
        <div className="flex h-[calc(100vh-8rem)] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">

            {/* ── Left Panel: Knowledge Base Manager ──────────────────────── */}
            <div className="w-72 flex-shrink-0 border-r border-slate-100 bg-slate-50 flex flex-col">
                <div className="px-4 py-3 border-b border-slate-200 flex items-center gap-2">
                    <FileSearch className="size-4 text-emerald-600" />
                    <span className="text-sm font-semibold text-slate-700">知識庫文件</span>
                    <Badge variant="outline" className="ml-auto text-[10px] text-emerald-600 border-emerald-200 bg-emerald-50">
                        {uploadedFiles.filter(f => f.status === 'done').length} 份
                    </Badge>
                </div>

                {/* Drop Zone */}
                <div
                    onDrop={handleDrop}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onClick={() => fileInputRef.current?.click()}
                    className={`mx-3 mt-3 rounded-xl border-2 border-dashed cursor-pointer transition-all px-4 py-5 flex flex-col items-center gap-2 ${
                        isDragging
                            ? 'border-emerald-400 bg-emerald-50 scale-[1.01]'
                            : 'border-slate-300 hover:border-emerald-300 hover:bg-emerald-50/50'
                    }`}
                >
                    <UploadCloud className={`size-8 transition-colors ${isDragging ? 'text-emerald-500' : 'text-slate-400'}`} />
                    <p className="text-xs text-slate-500 text-center leading-relaxed">
                        拖放 PDF 至此，或<span className="text-emerald-600 font-semibold">點擊選擇</span>
                    </p>
                    <p className="text-[10px] text-slate-400">僅支援 .pdf 格式</p>
                </div>
                <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf"
                    multiple
                    className="hidden"
                    onChange={handleFileChange}
                />

                {/* File List */}
                <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2 mt-1">
                    {uploadedFiles.length === 0 ? (
                        <p className="text-[11px] text-slate-400 text-center pt-4">尚未上傳任何文件</p>
                    ) : (
                        <AnimatePresence>
                            {uploadedFiles.map(f => (
                                <motion.div
                                    key={f.id}
                                    initial={{ opacity: 0, y: -6 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, x: -20 }}
                                    className="flex items-start gap-2 bg-white rounded-lg px-3 py-2 border border-slate-100 shadow-sm group"
                                >
                                    {/* Status icon */}
                                    <div className="mt-0.5 flex-shrink-0">
                                        {f.status === 'uploading' && (
                                            <Loader2 className="size-4 text-emerald-500 animate-spin" />
                                        )}
                                        {f.status === 'done' && (
                                            <CheckCircle2 className="size-4 text-emerald-500" />
                                        )}
                                        {f.status === 'error' && (
                                            <XCircle className="size-4 text-red-500" />
                                        )}
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <p className="text-xs font-medium text-slate-700 truncate">{f.name}</p>
                                        <p className="text-[10px] text-slate-400">
                                            {formatSize(f.size)} ·{' '}
                                            {f.status === 'uploading' && <span className="text-emerald-500">上傳中...</span>}
                                            {f.status === 'done' && <span className="text-emerald-600">已寫入知識庫</span>}
                                            {f.status === 'error' && <span className="text-red-500">上傳失敗</span>}
                                        </p>
                                    </div>
                                    <Button
                                        variant="ghost" size="icon"
                                        onClick={() => removeFile(f.id)}
                                        className="size-5 opacity-0 group-hover:opacity-60 hover:!opacity-100 text-slate-400 hover:text-red-500 flex-shrink-0 transition-opacity"
                                    >
                                        <X className="size-3" />
                                    </Button>
                                </motion.div>
                            ))}
                        </AnimatePresence>
                    )}
                </div>

                {/* Clear all */}
                {uploadedFiles.length > 0 && (
                    <div className="p-3 border-t border-slate-200">
                        <Button
                            variant="ghost" size="sm"
                            onClick={() => setUploadedFiles([])}
                            className="w-full text-xs text-slate-400 hover:text-red-500 gap-1.5"
                        >
                            <Trash2 className="size-3" /> 清除清單
                        </Button>
                    </div>
                )}
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
                    {messages.length === 1 && messages[0].id === 'welcome' && (
                        <div className="flex flex-wrap gap-2 mb-4">
                            {quickQuestions.map((q, i) => (
                                <motion.button
                                    key={i}
                                    whileHover={{ scale: 1.02 }}
                                    whileTap={{ scale: 0.98 }}
                                    onClick={() => handleSend(q)}
                                    className="text-xs bg-white hover:bg-emerald-50 text-slate-700 hover:text-emerald-700 border border-slate-200 hover:border-emerald-200 px-4 py-2 rounded-full transition-all shadow-sm"
                                >
                                    {q}
                                </motion.button>
                            ))}
                        </div>
                    )}

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
                                    msg.role === 'user'
                                        ? 'bg-emerald-600 text-white'
                                        : 'bg-white border border-slate-200 text-emerald-600'
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
