'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
    Send, Loader2, Database, Bot, User as UserIcon,
    PlusCircle, Trash2, MessageSquare, ChevronRight
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { motion, AnimatePresence } from 'framer-motion';
import {
    askFactory, listFactorySessions, getFactorySession, deleteFactorySession,
    SessionSummary
} from '@/lib/api/factory';

interface Message {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date;
}

const WELCOME_MSG = (date: string): Message => ({
    id: 'welcome',
    role: 'assistant',
    content: '您好！我是 **工廠數據智慧助手**。您可以直接詢問關於 **產線開工、工單進度、不良品分析 (Pareto)** 或 **設備運行狀態** 等問題。',
    timestamp: new Date(),
});

const QUICK_QUESTIONS = (date: string) => [
    `今日 (${date}) 產線開工與工單狀況？`,
    '分析目前正在生產業績最好與最差的機種',
    '哪些設備現在處於停機 (DOWN) 狀態？',
    '分析上週設備故障的主要趨勢',
];

export function QAInterface() {
    const [mounted, setMounted] = useState(false);
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

    // ── Init ─────────────────────────────────────────────────────────────────
    useEffect(() => {
        setMounted(true);
        const today = new Date().toISOString().split('T')[0];
        setMessages([WELCOME_MSG(today)]);
        setQuickQuestions(QUICK_QUESTIONS(today));
        loadSessions();
    }, []);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages, isLoading]);

    if (!mounted) return null;

    // ── Session Helpers ──────────────────────────────────────────────────────
    const loadSessions = async () => {
        const list = await listFactorySessions();
        setSessions(list);
    };

    const startNewChat = () => {
        const today = new Date().toISOString().split('T')[0];
        setCurrentSessionId(null);
        setMessages([WELCOME_MSG(today)]);
        setInput('');
        inputRef.current?.focus();
    };

    const loadSession = async (session_id: string) => {
        const detail = await getFactorySession(session_id);
        if (!detail) return;

        const restored: Message[] = detail.messages.map((m, i) => ({
            id: `${m.role}-${i}`,
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
        await deleteFactorySession(session_id);
        if (currentSessionId === session_id) startNewChat();
        await loadSessions();
    };

    // ── Send Message ─────────────────────────────────────────────────────────
    const handleSend = async (text: string = input) => {
        if (!text.trim() || isLoading) return;

        const userText = text;
        setInput('');

        const userMsg: Message = {
            id: Date.now().toString(),
            role: 'user',
            content: userText,
            timestamp: new Date(),
        };
        setMessages(prev => [...prev.filter(m => m.id !== 'welcome'), ...prev.filter(m => m.id === 'welcome'), userMsg]);
        setMessages(prev => [...prev, userMsg].filter((m, i, arr) => arr.findIndex(x => x.id === m.id) === i));

        // Simpler: just append
        setMessages(prev => {
            const without = prev.filter(m => m.id !== userMsg.id);
            return [...without, userMsg];
        });
        setIsLoading(true);

        try {
            const data = await askFactory(userText, currentSessionId ?? undefined);

            if (!currentSessionId) {
                setCurrentSessionId(data.session_id);
                await loadSessions(); // refresh sidebar
            }

            const aiMsg: Message = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: data.response,
                timestamp: new Date(),
            };
            setMessages(prev => [...prev, aiMsg]);

        } catch {
            setMessages(prev => [...prev, {
                id: (Date.now() + 1).toString(),
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

    const formatDate = (iso: string) => {
        const d = new Date(iso);
        return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
    };

    // ── Render ───────────────────────────────────────────────────────────────
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
                        {/* Sidebar header */}
                        <div className="p-3 border-b border-slate-200">
                            <Button
                                onClick={startNewChat}
                                className="w-full flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm h-9"
                            >
                                <PlusCircle className="size-4" />
                                新對話
                            </Button>
                        </div>

                        {/* Session list */}
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
                                        className={`group flex items-start gap-2 rounded-lg px-3 py-2 cursor-pointer transition-colors ${
                                            currentSessionId === s.session_id
                                                ? 'bg-indigo-50 border border-indigo-200'
                                                : 'hover:bg-slate-100'
                                        }`}
                                    >
                                        <MessageSquare className="size-3.5 mt-0.5 flex-shrink-0 text-slate-400" />
                                        <div className="flex-1 min-w-0">
                                            <p className="text-xs font-medium text-slate-700 truncate">{s.title}</p>
                                            <p className="text-[10px] text-slate-400 mt-0.5">
                                                {formatDate(s.updated_at)} · {s.message_count / 2 | 0}輪
                                            </p>
                                        </div>
                                        <Button
                                            variant="ghost" size="icon"
                                            onClick={(e) => removeSession(e, s.session_id)}
                                            className="size-6 opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-500 flex-shrink-0"
                                        >
                                            <Trash2 className="size-3" />
                                        </Button>
                                    </motion.div>
                                ))
                            )}
                        </div>

                        {/* Footer */}
                        <div className="p-3 border-t border-slate-200">
                            <p className="text-[10px] text-slate-400 text-center">對話保留 24 小時</p>
                        </div>
                    </motion.aside>
                )}
            </AnimatePresence>

            {/* ── Main Chat Area ───────────────────────────────────────────── */}
            <div className="flex flex-col flex-1 min-w-0">
                {/* Header */}
                <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-100 bg-white">
                    <Button
                        variant="ghost" size="icon"
                        onClick={() => setSidebarOpen(o => !o)}
                        className="size-8 text-slate-500"
                    >
                        <ChevronRight className={`size-4 transition-transform ${sidebarOpen ? 'rotate-180' : ''}`} />
                    </Button>
                    <Database className="size-5 text-indigo-600" />
                    <div>
                        <h2 className="text-sm font-semibold text-slate-800">工廠數據智慧問答</h2>
                        {currentSessionId && (
                            <p className="text-[10px] text-slate-400">
                                Session: {currentSessionId.slice(0, 8)}…
                            </p>
                        )}
                    </div>
                    <div className="ml-auto">
                        <Badge variant="outline" className="text-xs gap-1 text-indigo-600 border-indigo-200">
                            <span className="size-1.5 rounded-full bg-green-400 inline-block" />
                            AI 連線中
                        </Badge>
                    </div>
                </div>

                {/* Messages */}
                <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
                    {/* Quick question pills (show only for new session) */}
                    {messages.length === 1 && messages[0].id === 'welcome' && (
                        <div className="flex flex-wrap gap-2 mb-2">
                            {quickQuestions.map((q, i) => (
                                <button
                                    key={i}
                                    onClick={() => handleSend(q)}
                                    className="text-xs bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 px-3 py-1.5 rounded-full transition-colors"
                                >
                                    {q}
                                </button>
                            ))}
                        </div>
                    )}

                    <AnimatePresence initial={false}>
                        {messages.map(msg => (
                            <motion.div
                                key={msg.id}
                                initial={{ opacity: 0, y: 8 }}
                                animate={{ opacity: 1, y: 0 }}
                                className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
                            >
                                {/* Avatar */}
                                <div className={`size-8 rounded-full flex-shrink-0 flex items-center justify-center ${
                                    msg.role === 'user'
                                        ? 'bg-indigo-600 text-white'
                                        : 'bg-slate-100 text-slate-600'
                                }`}>
                                    {msg.role === 'user'
                                        ? <UserIcon className="size-4" />
                                        : <Bot className="size-4" />}
                                </div>

                                {/* Bubble */}
                                <div className={`max-w-[78%] rounded-2xl px-4 py-3 text-sm shadow-sm ${
                                    msg.role === 'user'
                                        ? 'bg-indigo-600 text-white rounded-tr-sm'
                                        : 'bg-slate-50 border border-slate-100 text-slate-800 rounded-tl-sm'
                                }`}>
                                    {msg.role === 'assistant' ? (
                                        <div className="prose prose-sm max-w-none prose-headings:text-slate-800 prose-code:text-indigo-700 prose-table:text-xs">
                                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                                {msg.content}
                                            </ReactMarkdown>
                                        </div>
                                    ) : (
                                        <p className="whitespace-pre-wrap">{msg.content}</p>
                                    )}
                                    <p className={`text-[10px] mt-1.5 ${msg.role === 'user' ? 'text-indigo-200' : 'text-slate-400'}`}>
                                        {msg.timestamp.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })}
                                    </p>
                                </div>
                            </motion.div>
                        ))}
                    </AnimatePresence>

                    {/* Loading bubble */}
                    {isLoading && (
                        <motion.div
                            initial={{ opacity: 0, y: 8 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="flex gap-3"
                        >
                            <div className="size-8 rounded-full bg-slate-100 flex items-center justify-center">
                                <Bot className="size-4 text-slate-600" />
                            </div>
                            <div className="bg-slate-50 border border-slate-100 rounded-2xl rounded-tl-sm px-4 py-3">
                                <Loader2 className="size-4 animate-spin text-indigo-500" />
                            </div>
                        </motion.div>
                    )}
                </div>

                {/* Input area */}
                <div className="px-4 py-3 border-t border-slate-100 bg-white">
                    <div className="flex gap-2 items-end">
                        <Textarea
                            ref={inputRef}
                            value={input}
                            onChange={e => setInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="輸入問題... (Shift+Enter 換行，Enter 送出)"
                            rows={2}
                            className="flex-1 resize-none text-sm rounded-xl border-slate-200 focus:border-indigo-400 focus:ring-indigo-300"
                            disabled={isLoading}
                        />
                        <Button
                            onClick={() => handleSend()}
                            disabled={isLoading || !input.trim()}
                            className="h-10 w-10 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white p-0 flex-shrink-0"
                        >
                            {isLoading
                                ? <Loader2 className="size-4 animate-spin" />
                                : <Send className="size-4" />}
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    );
}
