
import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Brain, Lock, User, AlertCircle, Loader2 } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useUser } from '@/context/user-context';

interface LoginPageProps {
    onLogin: () => void;
}

export function LoginPage({ onLogin }: LoginPageProps) {
    const { login } = useUser();
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        if (!username.trim() || !password) {
            setError('請填寫工號與密碼');
            return;
        }

        setLoading(true);
        try {
            const res = await fetch(`/api/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: username.trim(), password }),
            });

            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                setError(data.detail || '工號或密碼錯誤，請重試');
                return;
            }

            const userData = await res.json();
            login(userData);
            onLogin();
        } catch {
            setError('無法連線至伺服器，請確認網路後重試');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 flex items-center justify-center p-4">
            <div className="w-full max-w-md">
                {/* Logo and Title */}
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center p-4 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-2xl shadow-lg mb-4">
                        <Brain className="size-12 text-white" />
                    </div>
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent mb-2">
                        全一電子 AI 助手
                    </h1>
                    <p className="text-slate-600">智能問答 · 報表生成 · 語音處理</p>
                </div>

                {/* Login Card */}
                <Card className="shadow-xl border-2">
                    <CardHeader>
                        <CardTitle>員工登入</CardTitle>
                        <CardDescription>請輸入您的工號與密碼</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <form onSubmit={handleLogin} className="space-y-4">
                            <div className="space-y-2">
                                <Label htmlFor="login-username">工號</Label>
                                <div className="relative">
                                    <User className="absolute left-3 top-3 size-4 text-slate-400" />
                                    <Input
                                        id="login-username"
                                        type="text"
                                        placeholder="請輸入工號"
                                        value={username}
                                        onChange={(e) => setUsername(e.target.value)}
                                        className="pl-10"
                                        autoComplete="username"
                                    />
                                </div>
                            </div>

                            <div className="space-y-2">
                                <Label htmlFor="login-password">密碼</Label>
                                <div className="relative">
                                    <Lock className="absolute left-3 top-3 size-4 text-slate-400" />
                                    <Input
                                        id="login-password"
                                        type="password"
                                        placeholder="••••••••"
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        className="pl-10"
                                        autoComplete="current-password"
                                    />
                                </div>
                            </div>

                            {error && (
                                <Alert variant="destructive">
                                    <AlertCircle className="size-4" />
                                    <AlertDescription>{error}</AlertDescription>
                                </Alert>
                            )}

                            <Button type="submit" className="w-full" size="lg" disabled={loading}>
                                {loading ? (
                                    <>
                                        <Loader2 className="size-4 mr-2 animate-spin" />
                                        驗證中...
                                    </>
                                ) : '登入'}
                            </Button>
                        </form>
                    </CardContent>
                </Card>

                <div className="mt-6 text-center text-sm text-slate-600">
                    <p>🔒 本系統採用地端部署，資料完全不外流</p>
                </div>
            </div>
        </div>
    );
}
