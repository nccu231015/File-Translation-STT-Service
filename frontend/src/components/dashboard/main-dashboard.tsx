
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
    Brain,
    MessageSquare,
    FileBarChart,
    Mic,
    LogOut,
    User,
    Home,
    Settings,
    HelpCircle,
    Languages
} from 'lucide-react';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

import { QAInterface } from './qa-interface';
import { ReportInterface } from './report-interface';
import { VoiceInterface } from './voice-interface';
import { DocumentTranslation } from './document-translation';
import { DashboardHome } from './dashboard-home';

// Types
export interface User {
    username: string;
    email: string;
}

interface MainDashboardProps {
    user: User;
    onLogout: () => void;
}

type ActiveView = 'home' | 'qa' | 'report' | 'translation' | 'voice';

export function MainDashboard({ user, onLogout }: MainDashboardProps) {
    const [activeView, setActiveView] = useState<ActiveView>('home');

    const navigationItems = [
        { id: 'home' as const, label: '首頁', icon: Home },
        { id: 'qa' as const, label: '智能問答', icon: MessageSquare },
        { id: 'report' as const, label: '報表生成', icon: FileBarChart },
        { id: 'translation' as const, label: '文件翻譯', icon: Languages },
        { id: 'voice' as const, label: '語音處理', icon: Mic },
    ];

    return (
        <div className="min-h-screen bg-slate-50 flex flex-col">
            {/* Top Navigation Bar */}
            <header className="bg-white border-b sticky top-0 z-50 shadow-sm">
                <div className="flex items-center justify-between px-6 py-3">
                    {/* Logo and Title */}
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-lg shadow-md">
                            <Brain className="size-6 text-white" />
                        </div>
                        <div>
                            <h1 className="text-xl font-bold text-slate-900 tracking-tight">全一電子 AI 助手</h1>
                            <p className="text-xs text-slate-500 font-medium">On-Premise AI Platform</p>
                        </div>
                    </div>

                    {/* Right Side Actions */}
                    <div className="flex items-center gap-3">
                        {/* User Menu */}
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <Button variant="ghost" className="gap-2 hover:bg-slate-100 rounded-full px-2">
                                    <div className="size-8 rounded-full bg-gradient-to-br from-blue-500 to-indigo-500 flex items-center justify-center text-white font-semibold shadow-sm">
                                        {user.username.charAt(0).toUpperCase()}
                                    </div>
                                    <span className="hidden md:inline font-medium text-slate-700">{user.username}</span>
                                </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-56">
                                <DropdownMenuLabel>
                                    <div className="py-1">
                                        <p className="font-semibold text-sm">{user.username}</p>
                                        <p className="text-xs text-slate-500 truncate">{user.email}</p>
                                    </div>
                                </DropdownMenuLabel>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem className="cursor-pointer">
                                    <User className="size-4 mr-2 text-slate-500" />
                                    個人資料
                                </DropdownMenuItem>
                                <DropdownMenuItem className="cursor-pointer">
                                    <Settings className="size-4 mr-2 text-slate-500" />
                                    系統設定
                                </DropdownMenuItem>
                                <DropdownMenuItem className="cursor-pointer">
                                    <HelpCircle className="size-4 mr-2 text-slate-500" />
                                    使用說明
                                </DropdownMenuItem>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem onClick={onLogout} className="text-red-600 cursor-pointer focus:text-red-600 focus:bg-red-50">
                                    <LogOut className="size-4 mr-2" />
                                    登出
                                </DropdownMenuItem>
                            </DropdownMenuContent>
                        </DropdownMenu>
                    </div>
                </div>

                {/* Main Navigation Tabs */}
                <div className="border-t bg-slate-50/50 backdrop-blur supports-[backdrop-filter]:bg-slate-50/50">
                    <nav className="flex gap-1 px-6 overflow-x-auto no-scrollbar">
                        {navigationItems.map((item) => {
                            const Icon = item.icon;
                            const isActive = activeView === item.id;
                            return (
                                <button
                                    key={item.id}
                                    onClick={() => setActiveView(item.id)}
                                    className={`
                    flex items-center gap-2 px-4 py-3 border-b-2 transition-all duration-200 outline-none
                    whitespace-nowrap text-sm
                    ${isActive
                                            ? 'border-blue-600 text-blue-600 bg-white shadow-sm font-semibold'
                                            : 'border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-100/80 font-medium'
                                        }
                  `}
                                >
                                    <Icon className={`size-4 ${isActive ? 'text-blue-600' : 'text-slate-500'}`} />
                                    <span>{item.label}</span>
                                </button>
                            );
                        })}
                    </nav>
                </div>
            </header>

            {/* Main Content Area */}
            <main className="container mx-auto p-4 md:p-6 flex-1 max-w-7xl animate-in fade-in duration-300">
                {activeView === 'home' && <DashboardHome user={user} onNavigate={setActiveView} />}
                {activeView === 'qa' && <QAInterface />}
                {activeView === 'report' && <ReportInterface />}
                {activeView === 'translation' && <DocumentTranslation />}
                {activeView === 'voice' && <VoiceInterface />}
            </main>

            {/* Footer */}
            <footer className="border-t bg-white mt-auto">
                <div className="container mx-auto px-6 py-4">
                    <div className="flex flex-col md:flex-row justify-between items-center text-sm text-slate-500 gap-2">
                        <p>© 2026 全一電子 AI 助手 - 地端部署版本 v1.0.0</p>
                        <div className="flex items-center gap-4">
                            <span>當前使用者：<span className="font-medium text-slate-700">{user.username}</span></span>
                            <span className="hidden md:inline text-slate-300">|</span>
                            <span>系統狀態：<span className="text-green-600 font-medium">正常</span></span>
                        </div>
                    </div>
                </div>
            </footer>
        </div>
    );
}
