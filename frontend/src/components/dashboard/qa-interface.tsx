
import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Send, Loader2, Database, AlertCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';

interface Message {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date;
}

export function QAInterface() {
    const [messages, setMessages] = useState<Message[]>([
        {
            id: 'welcome',
            role: 'assistant',
            content: '您好！我是企業 AI 助手。您可以詢問關於生產數據、產線狀況、異常事件等問題。',
            timestamp: new Date()
        }
    ]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    const quickQuestions = [
        '今日生產良率如何？',
        '哪條產線進度落後？',
        '本月異常事件統計',
        '停機時間最長的設備'
        // These might yield generic LLM answers unless backend has RAG
    ];

    const handleSend = async () => {
        if (!input.trim() || isLoading) return;

        const userText = input;
        setInput('');

        const userMsg: Message = { id: Date.now().toString(), role: 'user', content: userText, timestamp: new Date() };
        setMessages(prev => [...prev, userMsg]);
        setIsLoading(true);

        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: userText })
            });

            if (!res.ok) throw new Error('Chat API failed');
            const data = await res.json();

            const aiMsg: Message = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: data.llm_response,
                timestamp: new Date()
            };
            setMessages(prev => [...prev, aiMsg]);

        } catch (error) {
            console.error(error);
            setMessages(prev => [...prev, { id: 'error', role: 'assistant', content: '抱歉，系統暫時無法回應。', timestamp: new Date() }]);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="flex flex-col gap-4 h-[calc(100vh-13rem)] min-h-[500px]">
            <Alert>
                <AlertCircle className="size-4" />
                <AlertDescription>
                    本系統基於企業內部資料與語義層定義，所有回答均可追溯資料來源。
                </AlertDescription>
            </Alert>

            {/* Quick Questions */}
            {messages.length === 1 && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">快速提問</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid md:grid-cols-2 gap-2">
                            {quickQuestions.map((q, i) => (
                                <Button key={i} variant="outline" className="justify-start" onClick={() => setInput(q)}>
                                    {q}
                                </Button>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Messages */}
            <Card className="flex-1 flex flex-col">
                <CardContent className="flex-1 overflow-y-auto p-6 space-y-4">
                    {messages.map((msg) => (
                        <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                            <div className={`max-w-[80%] rounded-lg p-4 ${msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-900'}`}>
                                <div className="whitespace-pre-wrap">{msg.content}</div>
                                <div className="text-xs opacity-70 mt-2 text-right">{msg.timestamp.toLocaleTimeString()}</div>
                            </div>
                        </div>
                    ))}
                    {isLoading && (
                        <div className="flex justify-start">
                            <div className="bg-slate-100 rounded-lg p-4 flex items-center gap-2">
                                <Loader2 className="animate-spin size-4" />
                                <span className="text-sm">AI 思考中...</span>
                            </div>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Input */}
            <Card>
                <CardContent className="p-4 flex gap-3">
                    <Textarea
                        placeholder="輸入您的問題..."
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        className="min-h-[60px] resize-none"
                        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                    />
                    <Button onClick={handleSend} disabled={isLoading || !input.trim()} size="lg" className="px-8 h-auto">
                        <Send className="size-5" />
                    </Button>
                </CardContent>
            </Card>
        </div>
    );
}
