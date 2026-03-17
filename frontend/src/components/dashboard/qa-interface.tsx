'use client';

import { useState, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
    Send, Loader2, Database, Bot, User as UserIcon,
    PlusCircle, Trash2, MessageSquare, ChevronRight
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import { motion, AnimatePresence } from 'framer-motion';
import {
    askFactory, listFactorySessions, getFactorySession, deleteFactorySession,
    SessionSummary
} from '@/lib/api/factory';

interface Message {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date | null; // 改為可為空，避免 Hydration 衝突
}

export function QAInterface() {
    const [mounted, setMounted] = useState(false);
    // ... (其餘狀態保持不變)
    const [messages, setMessages] = useState<Message[]>([]);
    const [quickQuestions, setQuickQuestions] = useState<string[]>([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    // Session state
    const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
    const [sessions, setSessions] = useState<SessionSummary[]>([]);
    const [sidebarOpen, setSidebarOpen] = useState(true);

    const scrollRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);
    // ── Date Formatting (Hydration Safe) ───────────────────────────────────
    const [timeStrings, setTimeStrings] = useState<Record<string, string>>({});

    useEffect(() => {
        const newTimes: Record<string, string> = {};
        messages.forEach(m => {
            if (m.timestamp) {
                newTimes[m.id] = m.timestamp.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' });
            }
        });
        setTimeStrings(newTimes);
    }, [messages]);

    const formatSessionDate = (iso: string) => {
        if (!mounted) return "";
        const d = new Date(iso);
        return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
    };

    // ── Init ─────────────────────────────────────────────────────────────────
    useEffect(() => {
        setMounted(true);
        const today = new Date().toISOString().split('T')[0];
        
        // 1. 初始化歡迎訊息
        setMessages([{
            id: 'welcome',
            role: 'assistant' as const,
            content: '您好！我是 **工廠數據智慧助手**。您可以直接詢問關於 **產線開工、工單進度、不良品分析 (Pareto)** 或 **設備運行狀態** 等問題。',
            timestamp: new Date(),
        }]);

        // 2. 初始化快速問題
        setQuickQuestions([
            `今日 (${today}) 產線開工與工單狀況？`,
            '分析目前正在生產業績最好與最差的機種',
            '哪些設備現在處於停機 (DOWN) 狀態？',
            '分析上週設備故障的主要趨勢',
        ]);
        
        // 3. 載入對話歷史 (只在 mount 時載入一次)
        listFactorySessions()
            .then(list => setSessions(list))
            .catch(e => console.error("Failed to load sessions", e));

    }, []); // 將依賴改為空陣列，防止重新渲染導致的無限迴圈

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages, isLoading]);

    // ── Session Helpers ──────────────────────────────────────────────────────
    const loadSessions = async () => {
        try {
            const list = await listFactorySessions();
            setSessions(list);
        } catch (e) {
            console.error("Failed to load sessions", e);
        }
    };

    const startNewChat = () => {
        setCurrentSessionId(null);
        setMessages([{
            id: 'welcome',
            role: 'assistant' as const,
            content: '您好！我是 **工廠數據智慧助手**。您可以直接詢問關於 **產線開工、工單進度、不良品分析 (Pareto)** 或 **設備運行狀態** 等問題。',
            timestamp: new Date(),
        }]);
        setInput('');
        setTimeout(() => inputRef.current?.focus(), 10);
    };

    const loadSession = async (session_id: string) => {
        const detail = await getFactorySession(session_id);
        if (!detail) return;

        const restored: Message[] = detail.messages.map((m, i) => ({
            id: `${m.role}-${i}-${Date.now()}`,
            role: m.role as 'user' | 'assistant',
            content: m.content,
            timestamp: new Date(m.ts),
        }));

        setCurrentSessionId(session_id);
        setMessages(restored);
        setInput('');
    };

    const removeSession = async (e: React.MouseEvent, session_id: string) => {
        e.stopPropagation();
        if (!window.confirm("確定要刪除這段對話嗎？資料刪除後無法復原。")) return;

        try {
            await deleteFactorySession(session_id);
            if (currentSessionId === session_id) startNewChat();
            await loadSessions();
        } catch (err) {
            console.error("Delete failed", err);
            alert("刪除失敗，請稍後再試。");
        }
    };

    // ── Send Message ─────────────────────────────────────────────────────────
    const handleSend = async (text: string = input) => {
        if (!text.trim() || isLoading) return;

        const userText = text;
        const msgId = `user-${Date.now()}`;
        setInput('');

        const userMsg: Message = {
            id: msgId,
            role: 'user',
            content: userText,
            timestamp: new Date(),
        };

        // UI Update (Filter welcome if it's the first real question)
        setMessages(prev => {
            const filtered = prev.filter(m => m.id !== 'welcome');
            return [...filtered, userMsg];
        });

        setIsLoading(true);

        try {
            const data = await askFactory(userText, currentSessionId ?? undefined);

            if (!currentSessionId) {
                setCurrentSessionId(data.session_id);
                loadSessions();
            }

            const aiMsg: Message = {
                id: `ai-${Date.now()}`,
                role: 'assistant',
                content: data.response,
                timestamp: new Date(),
            };
            setMessages(prev => [...prev, aiMsg]);

        } catch {
            setMessages(prev => [...prev, {
                id: `error-${Date.now()}`,
                role: 'assistant',
                content: '⚠️ 抱歉，工廠數據後端連線異常，請稍後再試。',
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
        <div className="flex h-[calc(100vh-8rem)] gap-0 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">

            {/* ── Sidebar ─────────────────────────────────────────────────── */}
            <AnimatePresence initial={false}>
                {sidebarOpen && (
                    <motion.aside
                        initial={{ width: 0, opacity: 0 }}
                        animate={{ width: 260, opacity: 1 }}
                        exit={{ width: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="flex-shrink-0 border-r border-slate-100 bg-slate-50 flex flex-col overflow-hidden"
                    >
                        <div className="p-3 border-b border-slate-200">
                            <Button
                                onClick={startNewChat}
                                className="w-full flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm h-9 shadow-md transition-all active:scale-95"
                            >
                                <PlusCircle className="size-4" />
                                新對話
                            </Button>
                        </div>

                        <div className="flex-1 overflow-y-auto p-2 space-y-1">
                            {sessions.length === 0 ? (
                                <p className="text-xs text-slate-400 text-center pt-6">尚無對話紀錄</p>
                            ) : (
                                sessions.map(s => (
                                    <motion.div
                                        key={s.session_id}
                                        initial={{ opacity: 0, x: -10 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        onClick={() => loadSession(s.session_id)}
                                        className={`group flex items-start gap-2 rounded-lg px-3 py-2 cursor-pointer transition-all ${currentSessionId === s.session_id
                                                ? 'bg-indigo-50 border border-indigo-200 shadow-sm'
                                                : 'hover:bg-slate-100 active:bg-slate-200'
                                            }`}
                                    >
                                        <MessageSquare className="size-3.5 mt-0.5 flex-shrink-0 text-slate-400" />
                                        <div className="flex-1 min-w-0">
                                            <p className="text-xs font-medium text-slate-700 truncate">{s.title}</p>
                                            <p className="text-[10px] text-slate-400 mt-0.5">
                                                {formatSessionDate(s.updated_at)} · {Math.floor(s.message_count / 2)}輪
                                            </p>
                                        </div>
                                        <Button
                                            variant="ghost" size="icon"
                                            onClick={(e) => removeSession(e, s.session_id)}
                                            className="size-6 opacity-30 group-hover:opacity-100 text-slate-400 hover:text-red-500 flex-shrink-0 transition-opacity"
                                        >
                                            <Trash2 className="size-3" />
                                        </Button>
                                    </motion.div>
                                ))
                            )}
                        </div>

                        <div className="p-3 border-t border-slate-200 bg-slate-100/50">
                            <p className="text-[10px] text-slate-400 text-center">對話保留 24 小時</p>
                        </div>
                    </motion.aside>
                )}
            </AnimatePresence>

            {/* ── Main Chat Area ───────────────────────────────────────────── */}
            <div className="flex flex-col flex-1 min-w-0 bg-slate-50/10">
                {/* Header */}
                <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-100 bg-white z-10 shadow-sm">
                    <Button
                        variant="ghost" size="icon"
                        onClick={() => setSidebarOpen(o => !o)}
                        className="size-8 text-slate-500 hover:bg-slate-100"
                    >
                        <ChevronRight className={`size-4 transition-transform ${sidebarOpen ? 'rotate-180' : ''}`} />
                    </Button>
                    <Database className="size-5 text-indigo-600" />
                    <div>
                        <h2 className="text-sm font-semibold text-slate-800">工廠數據智慧問答</h2>
                        {currentSessionId && (
                            <p className="text-[10px] text-slate-400 font-mono">
                                ID: {currentSessionId.slice(0, 8)}…
                            </p>
                        )}
                    </div>
                    <div className="ml-auto">
                        <Badge variant="outline" className="text-xs gap-1 text-indigo-600 border-indigo-200 bg-indigo-50/50">
                            <span className="size-1.5 rounded-full bg-green-500 animate-pulse inline-block" />
                            AI 連線中
                        </Badge>
                    </div>
                </div>

                {/* Messages */}
                <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-6 scroll-smooth">
                    {/* Quick question pills */}
                    {messages.length === 1 && messages[0].id === 'welcome' && (
                        <div className="flex flex-wrap gap-2 mb-4">
                            {quickQuestions.map((q, i) => (
                                <motion.button
                                    key={i}
                                    whileHover={{ scale: 1.02 }}
                                    whileTap={{ scale: 0.98 }}
                                    onClick={() => handleSend(q)}
                                    className="text-xs bg-white hover:bg-indigo-50 text-slate-700 hover:text-indigo-700 border border-slate-200 hover:border-indigo-200 px-4 py-2 rounded-full transition-all shadow-sm"
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
                                <div className={`size-9 rounded-xl flex-shrink-0 flex items-center justify-center shadow-sm ${msg.role === 'user'
                                        ? 'bg-indigo-600 text-white'
                                        : 'bg-white border border-slate-200 text-indigo-600'
                                    }`}>
                                    {msg.role === 'user' ? <UserIcon className="size-5" /> : <Bot className="size-5" />}
                                </div>

                                <div className={`group relative max-w-[85%] sm:max-w-[75%] rounded-2xl px-4 py-3 text-sm shadow-sm transition-all ${msg.role === 'user'
                                        ? 'bg-indigo-600 text-white rounded-tr-none'
                                        : 'bg-white border border-slate-100 text-slate-800 rounded-tl-none'
                                    }`}>
                                    {msg.role === 'assistant' ? (
                                        <div className="prose prose-sm max-w-none prose-indigo prose-headings:text-indigo-900 prose-code:bg-indigo-50 prose-code:px-1 prose-code:rounded prose-table:border prose-table:border-slate-200 prose-th:bg-slate-50 prose-th:px-2 prose-td:px-2">
                                            <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                                                {msg.content}
                                            </ReactMarkdown>
                                        </div>
                                    ) : (
                                        <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                                    )}
                                    <div className={`flex items-center gap-2 mt-2 pt-1 border-t opacity-60 ${msg.role === 'user' ? 'border-white/10 text-white' : 'border-slate-100 text-slate-400'
                                        }`}>
                                        <p className="text-[10px]">
                                            {timeStrings[msg.id] || "--:--"}
                                        </p>
                                    </div>
                                </div>
                            </motion.div>
                        ))}
                    </AnimatePresence>

                    {isLoading && (
                        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-3">
                            <div className="size-9 rounded-xl bg-white border border-slate-200 flex items-center justify-center shadow-sm">
                                <Bot className="size-5 text-indigo-500 animate-pulse" />
                            </div>
                            <div className="bg-white border border-slate-100 rounded-2xl rounded-tl-none px-5 py-3 shadow-sm flex items-center gap-3">
                                <div className="flex gap-1">
                                    <span className="size-1.5 bg-indigo-400 rounded-full animate-bounce [animation-delay:-0.3s]" />
                                    <span className="size-1.5 bg-indigo-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
                                    <span className="size-1.5 bg-indigo-400 rounded-full animate-bounce" />
                                </div>
                                <span className="text-xs text-slate-400 font-medium whitespace-nowrap">AI 正在思考中...</span>
                            </div>
                        </motion.div>
                    )}
                </div>

                {/* Input area */}
                <div className="p-4 bg-white border-t border-slate-100">
                    <div className="max-w-4xl mx-auto flex gap-3 items-end bg-slate-50 p-2 rounded-2xl border border-slate-200 focus-within:border-indigo-400 focus-within:ring-2 focus-within:ring-indigo-100 transition-all shadow-inner">
                        <Textarea
                            ref={inputRef}
                            value={input}
                            onChange={e => setInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="在這裡輸入問題... (Shift+Enter 換行)"
                            rows={1}
                            className="flex-1 min-h-[44px] max-h-32 resize-none bg-transparent border-none text-sm focus-visible:ring-0 focus-visible:ring-offset-0 px-3 py-3"
                            disabled={isLoading}
                        />
                        <Button
                            onClick={() => handleSend()}
                            disabled={isLoading || !input.trim()}
                            className="size-10 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white p-0 flex-shrink-0 shadow-lg active:scale-90 transition-all disabled:bg-slate-300"
                        >
                            {isLoading ? <Loader2 className="size-5 animate-spin" /> : <Send className="size-5" />}
                        </Button>
                    </div>
                    <p className="text-[10px] text-center text-slate-400 mt-2">
                        使用此助手即代表您同意由 AI 自動查詢生產數據。所有的分析結果僅供參考。
                    </p>
                </div>
            </div>
        </div>
    );
}
