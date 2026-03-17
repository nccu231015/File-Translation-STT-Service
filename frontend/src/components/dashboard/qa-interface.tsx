
import { useState, useRef, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Send, Loader2, Database, Bot, User as UserIconAlt } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { motion, AnimatePresence } from 'framer-motion';
import { askFactory } from '@/lib/api/factory';

interface Message {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date;
}

export function QAInterface() {
    const [mounted, setMounted] = useState(false);
    const [messages, setMessages] = useState<Message[]>([]);
    const [quickQuestions, setQuickQuestions] = useState<string[]>([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const scrollRef = useRef<HTMLDivElement>(null);

    // Initial setup (Client side only to avoid Hydration Error)
    useEffect(() => {
        setMounted(true);
        const today = new Date();
        const todayStr = today.toISOString().split('T')[0];
        setMessages([
            {
                id: 'welcome',
                role: 'assistant',
                content: '您好！我是 **工廠數據智慧助手**。您可以直接詢問關於 **產線開工、工單進度、不良品分析 (Pareto)** 或 **設備運行狀態** 等問題。',
                timestamp: new Date()
            }
        ]);
        setQuickQuestions([
            `今日 (${todayStr}) 產線開工與工單狀況？`,
            '分析目前正在生產業績最好與最差的機種',
            `查詢特定工單在 ${todayStr} 的良率與生產進度`,
            '哪些設備現在處於停機 (DOWN) 狀態？'
        ]);
    }, []);

    // 自動捲動置底
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages, isLoading]);

    if (!mounted) return null;

    const handleSend = async (text: string = input) => {
        if (!text.trim() || isLoading) return;

        const userText = text;
        setInput('');

        const userMsg: Message = { id: Date.now().toString(), role: 'user', content: userText, timestamp: new Date() };
        setMessages(prev => [...prev, userMsg]);
        setIsLoading(true);

        try {
            const data = await askFactory(userText);

            const aiMsg: Message = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: data.response,
                timestamp: new Date()
            };
            setMessages(prev => [...prev, aiMsg]);

        } catch (error) {
            console.error(error);
            setMessages(prev => [...prev, { id: 'error', role: 'assistant', content: '抱歉，工廠數據後端連線異常，請稍後再試。', timestamp: new Date() }]);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="flex flex-col gap-4 h-[calc(100vh-13rem)] min-h-[500px]">
            <Alert className="bg-blue-50 border-blue-200">
                <Database className="size-4 text-blue-600" />
                <AlertDescription className="text-blue-700">
                    本系統即時串接 **MSSQL (產線)** 與 **Postgres (設備)** 資料庫，數據均為現場預計與實際值。
                </AlertDescription>
            </Alert>

            {/* Messages Area */}
            <Card className="flex-1 flex flex-col shadow-inner bg-slate-50/50 overflow-hidden">
                <CardContent 
                    ref={scrollRef}
                    className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6 scroll-smooth"
                >
                    <AnimatePresence initial={false}>
                        {messages.map((msg) => (
                            <motion.div 
                                key={msg.id}
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} gap-3`}
                            >
                                {msg.role === 'assistant' && (
                                    <div className="size-8 rounded-full bg-blue-600 flex items-center justify-center text-white shrink-0 shadow-sm">
                                        <Bot className="size-5" />
                                    </div>
                                )}
                                <div className={`max-w-[85%] md:max-w-[75%] rounded-2xl px-4 py-3 shadow-sm ${
                                    msg.role === 'user' 
                                        ? 'bg-blue-600 text-white rounded-tr-none' 
                                        : 'bg-white text-slate-900 border border-slate-200 rounded-tl-none'
                                }`}>
                                    <div className={`prose prose-sm max-w-none ${msg.role === 'user' ? 'prose-invert' : 'prose-slate'}`}>
                                        <ReactMarkdown 
                                            remarkPlugins={[remarkGfm]}
                                            components={{
                                                table: ({node, ...props}) => <div className="overflow-x-auto my-2"><table className="border-collapse border border-slate-300 w-full text-xs" {...props} /></div>,
                                                th: ({node, ...props}) => <th className="border border-slate-300 bg-slate-100 p-2 font-bold" {...props} />,
                                                td: ({node, ...props}) => <td className="border border-slate-300 p-2" {...props} />,
                                            }}
                                        >
                                            {msg.content}
                                        </ReactMarkdown>
                                    </div>
                                    <div className={`text-[10px] mt-1.5 opacity-50 ${msg.role === 'user' ? 'text-right' : 'text-left'}`}>
                                        {msg.timestamp.toLocaleTimeString()}
                                    </div>
                                </div>
                                {msg.role === 'user' && (
                                    <div className="size-8 rounded-full bg-slate-200 flex items-center justify-center text-slate-600 shrink-0 shadow-sm border border-slate-300">
                                        <UserIconAlt className="size-5" />
                                    </div>
                                )}
                            </motion.div>
                        ))}
                    </AnimatePresence>
                    
                    {isLoading && (
                        <div className="flex justify-start gap-3">
                            <div className="size-8 rounded-full bg-blue-600 flex items-center justify-center text-white shrink-0 animate-pulse">
                                <Bot className="size-5" />
                            </div>
                            <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-none px-4 py-4 shadow-sm flex items-center gap-3">
                                <div className="flex gap-1.5">
                                    <span className="w-1.5 h-1.5 bg-blue-600 rounded-full animate-bounce [animation-delay:-0.3s]"></span>
                                    <span className="w-1.5 h-1.5 bg-blue-600 rounded-full animate-bounce [animation-delay:-0.15s]"></span>
                                    <span className="w-1.5 h-1.5 bg-blue-600 rounded-full animate-bounce"></span>
                                </div>
                                <span className="text-xs text-slate-500 font-medium">資料庫分析中...</span>
                            </div>
                        </div>
                    )}
                </CardContent>

                {/* Quick Selection Footer */}
                <div className="px-4 pb-2 flex gap-2 overflow-x-auto no-scrollbar">
                    {messages.length < 3 && quickQuestions.map((q, i) => (
                        <Button 
                            key={i} 
                            variant="outline" 
                            size="sm" 
                            className="whitespace-nowrap rounded-full bg-white text-xs hover:border-blue-400 hover:text-blue-600 transition-colors"
                            onClick={() => handleSend(q)}
                        >
                            {q}
                        </Button>
                    ))}
                </div>

                <div className="p-4 bg-white border-t">
                    <div className="flex gap-3 items-end">
                        <Textarea
                            placeholder="請輸入問題，例如：查詢工單目標數..."
                            value={input}
                            onChange={e => setInput(e.target.value)}
                            className="min-h-[50px] max-h-[150px] resize-none border-slate-200 focus:border-blue-400 focus:ring-blue-100 rounded-xl"
                            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                        />
                        <Button 
                            onClick={() => handleSend()} 
                            disabled={isLoading || !input.trim()} 
                            size="icon" 
                            className="size-[50px] rounded-xl shadow-lg shadow-blue-200 shrink-0"
                        >
                            <Send className="size-5" />
                        </Button>
                    </div>
                    <p className="text-[10px] text-slate-400 mt-2 text-center">
                        AI 回答僅供參考，關鍵決策請務必核對原始報表系統。
                    </p>
                </div>
            </Card>
        </div>
    );
}
