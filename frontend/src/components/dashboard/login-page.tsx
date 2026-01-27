
import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Brain, Lock, Mail, User, AlertCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';

interface User {
    username: string;
    email: string;
}

interface LoginPageProps {
    onLogin: (user: User) => void;
}

export function LoginPage({ onLogin }: LoginPageProps) {
    const [loginEmail, setLoginEmail] = useState('');
    const [loginPassword, setLoginPassword] = useState('');
    const [signupName, setSignupName] = useState('');
    const [signupEmail, setSignupEmail] = useState('');
    const [signupPassword, setSignupPassword] = useState('');
    const [signupConfirmPassword, setSignupConfirmPassword] = useState('');
    const [error, setError] = useState('');
    const [activeTab, setActiveTab] = useState('login');

    const handleLogin = (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        if (!loginEmail || !loginPassword) {
            setError('請填寫所有欄位');
            return;
        }

        // Mock login - in real system this would call backend API
        if (loginPassword.length < 6) {
            setError('密碼錯誤');
            return;
        }

        // Simulate successful login
        onLogin({
            username: loginEmail.split('@')[0],
            email: loginEmail
        });
    };

    const handleSignup = (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        if (!signupName || !signupEmail || !signupPassword || !signupConfirmPassword) {
            setError('請填寫所有欄位');
            return;
        }

        if (signupPassword.length < 6) {
            setError('密碼長度至少需要 6 個字元');
            return;
        }

        if (signupPassword !== signupConfirmPassword) {
            setError('密碼與確認密碼不符');
            return;
        }

        // Mock signup - in real system this would call backend API
        onLogin({
            username: signupName,
            email: signupEmail
        });
    };

    const handleDemoLogin = () => {
        // Quick demo login
        onLogin({
            username: 'demo_user',
            email: 'demo@company.com'
        });
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

                {/* Login/Signup Card */}
                <Card className="shadow-xl border-2">
                    <CardHeader>
                        <CardTitle>歡迎使用</CardTitle>
                        <CardDescription>登入或註冊以開始使用 AI 工具系統</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Tabs value={activeTab} onValueChange={setActiveTab}>
                            <TabsList className="grid w-full grid-cols-2 mb-6">
                                <TabsTrigger value="login">登入</TabsTrigger>
                                <TabsTrigger value="signup">註冊</TabsTrigger>
                            </TabsList>

                            {/* Login Tab */}
                            <TabsContent value="login">
                                <form onSubmit={handleLogin} className="space-y-4">
                                    <div className="space-y-2">
                                        <Label htmlFor="login-email">電子郵件</Label>
                                        <div className="relative">
                                            <Mail className="absolute left-3 top-3 size-4 text-slate-400" />
                                            <Input
                                                id="login-email"
                                                type="email"
                                                placeholder="your.email@company.com"
                                                value={loginEmail}
                                                onChange={(e) => setLoginEmail(e.target.value)}
                                                className="pl-10"
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
                                                value={loginPassword}
                                                onChange={(e) => setLoginPassword(e.target.value)}
                                                className="pl-10"
                                            />
                                        </div>
                                    </div>

                                    {error && (
                                        <Alert variant="destructive">
                                            <AlertCircle className="size-4" />
                                            <AlertDescription>{error}</AlertDescription>
                                        </Alert>
                                    )}

                                    <Button type="submit" className="w-full" size="lg">
                                        登入
                                    </Button>
                                </form>
                            </TabsContent>

                            {/* Signup Tab */}
                            <TabsContent value="signup">
                                <form onSubmit={handleSignup} className="space-y-4">
                                    <div className="space-y-2">
                                        <Label htmlFor="signup-name">姓名</Label>
                                        <div className="relative">
                                            <User className="absolute left-3 top-3 size-4 text-slate-400" />
                                            <Input
                                                id="signup-name"
                                                type="text"
                                                placeholder="王小明"
                                                value={signupName}
                                                onChange={(e) => setSignupName(e.target.value)}
                                                className="pl-10"
                                            />
                                        </div>
                                    </div>

                                    <div className="space-y-2">
                                        <Label htmlFor="signup-email">電子郵件</Label>
                                        <div className="relative">
                                            <Mail className="absolute left-3 top-3 size-4 text-slate-400" />
                                            <Input
                                                id="signup-email"
                                                type="email"
                                                placeholder="your.email@company.com"
                                                value={signupEmail}
                                                onChange={(e) => setSignupEmail(e.target.value)}
                                                className="pl-10"
                                            />
                                        </div>
                                    </div>

                                    <div className="space-y-2">
                                        <Label htmlFor="signup-password">密碼</Label>
                                        <div className="relative">
                                            <Lock className="absolute left-3 top-3 size-4 text-slate-400" />
                                            <Input
                                                id="signup-password"
                                                type="password"
                                                placeholder="至少 6 個字元"
                                                value={signupPassword}
                                                onChange={(e) => setSignupPassword(e.target.value)}
                                                className="pl-10"
                                            />
                                        </div>
                                    </div>

                                    <div className="space-y-2">
                                        <Label htmlFor="signup-confirm-password">確認密碼</Label>
                                        <div className="relative">
                                            <Lock className="absolute left-3 top-3 size-4 text-slate-400" />
                                            <Input
                                                id="signup-confirm-password"
                                                type="password"
                                                placeholder="再次輸入密碼"
                                                value={signupConfirmPassword}
                                                onChange={(e) => setSignupConfirmPassword(e.target.value)}
                                                className="pl-10"
                                            />
                                        </div>
                                    </div>

                                    {error && (
                                        <Alert variant="destructive">
                                            <AlertCircle className="size-4" />
                                            <AlertDescription>{error}</AlertDescription>
                                        </Alert>
                                    )}

                                    <Button type="submit" className="w-full" size="lg">
                                        註冊
                                    </Button>
                                </form>
                            </TabsContent>
                        </Tabs>

                        {/* Demo Login */}
                        <div className="mt-6 pt-6 border-t">
                            <Button
                                onClick={handleDemoLogin}
                                variant="outline"
                                className="w-full"
                            >
                                使用展示帳號登入
                            </Button>
                            <p className="text-xs text-slate-500 text-center mt-2">
                                快速體驗系統功能，無需註冊
                            </p>
                        </div>
                    </CardContent>
                </Card>

                {/* Footer Note */}
                <div className="mt-6 text-center text-sm text-slate-600">
                    <p>🔒 本系統採用地端部署，資料完全不外流</p>
                </div>
            </div>
        </div>
    );
}
