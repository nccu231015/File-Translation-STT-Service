
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    MessageSquare,
    FileBarChart,
    Mic,
    Languages,
    TrendingUp,
    CheckCircle2,
    ArrowRight,
    Activity,
    Database
} from 'lucide-react';

interface DashboardHomeProps {
    user: {
        username: string;
        email: string;
    };
    onNavigate: (view: 'qa' | 'report' | 'translation' | 'voice') => void;
}

export function DashboardHome({ user, onNavigate }: DashboardHomeProps) {
    const features = [
        {
            id: 'qa' as const,
            title: '智能問答',
            description: '基於企業資料與專業知識的 AI 問答系統',
            icon: MessageSquare,
            color: 'from-blue-500 to-cyan-500',
            stats: { label: '本月查詢', value: '1,247' },
            features: ['自然語言查詢', '多語言支援', '資料來源可追溯']
        },
        {
            id: 'report' as const,
            title: '報表生成',
            description: '自動化資料分析與視覺化報表產出',
            icon: FileBarChart,
            color: 'from-green-500 to-emerald-500',
            stats: { label: '已生成報表', value: '384' },
            features: ['一鍵生成', '多種圖表', '遵循語義層定義']
        },
        {
            id: 'translation' as const,
            title: '文件翻譯',
            description: '專業文件翻譯與多語言轉換服務',
            icon: Languages,
            color: 'from-orange-500 to-red-500',
            stats: { label: '已翻譯文件', value: '128' },
            features: ['PDF 支援', '專業術語庫', '地端處理']
        },
        {
            id: 'voice' as const,
            title: '語音處理',
            description: '語音轉文字與智能會議紀錄整理',
            icon: Mic,
            color: 'from-purple-500 to-pink-500',
            stats: { label: '處理時數', value: '156' },
            features: ['中文辨識', '說話人分離', '自動摘要']
        }
    ];

    const systemStats = [
        {
            label: '系統狀態',
            value: '正常運行',
            icon: Activity,
            color: 'text-green-600'
        },
        {
            label: '資料庫連線',
            value: '已連接',
            icon: Database,
            color: 'text-blue-600'
        },
        {
            label: 'AI 模型',
            value: '就緒',
            icon: CheckCircle2,
            color: 'text-green-600'
        }
    ];

    return (
        <div className="space-y-6">
            {/* Welcome Section */}
            <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-xl p-8 text-white shadow-lg">
                <h2 className="text-3xl font-bold mb-2">歡迎回來，{user.username}！</h2>
                <p className="text-blue-100">開始使用企業級 AI 工具，提升工作效率</p>
            </div>

            {/* System Status */}
            <div className="grid md:grid-cols-3 gap-4">
                {systemStats.map((stat, idx) => {
                    const Icon = stat.icon;
                    return (
                        <Card key={idx}>
                            <CardContent className="p-6">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-sm text-slate-600 mb-1">{stat.label}</p>
                                        <p className={`text-xl font-semibold ${stat.color}`}>{stat.value}</p>
                                    </div>
                                    <Icon className={`size-10 ${stat.color}`} />
                                </div>
                            </CardContent>
                        </Card>
                    );
                })}
            </div>

            {/* Main Features */}
            <div>
                <h3 className="text-xl font-semibold mb-4">核心功能</h3>
                <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
                    {features.map((feature) => {
                        const Icon = feature.icon;
                        return (
                            <Card
                                key={feature.id}
                                className="hover:shadow-xl transition-shadow cursor-pointer group"
                                onClick={() => onNavigate(feature.id)}
                            >
                                <CardHeader>
                                    <div className={`w-12 h-12 rounded-lg bg-gradient-to-br ${feature.color} flex items-center justify-center mb-3`}>
                                        <Icon className="size-6 text-white" />
                                    </div>
                                    <CardTitle className="flex items-center justify-between">
                                        {feature.title}
                                        <Badge variant="secondary">{feature.stats.label}</Badge>
                                    </CardTitle>
                                    <CardDescription>{feature.description}</CardDescription>
                                </CardHeader>
                                <CardContent>
                                    <div className="space-y-3 mb-4">
                                        <div className="text-2xl font-bold text-slate-900">
                                            {feature.stats.value}
                                        </div>
                                        <div className="space-y-1.5">
                                            {feature.features.map((item, idx) => (
                                                <div key={idx} className="flex items-center gap-2 text-sm text-slate-600">
                                                    <CheckCircle2 className="size-3.5 text-green-600" />
                                                    <span>{item}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                    <Button
                                        variant="ghost"
                                        className="w-full group-hover:bg-gradient-to-r group-hover:from-blue-600 group-hover:to-indigo-600 group-hover:text-white"
                                    >
                                        開始使用
                                        <ArrowRight className="size-4 ml-2" />
                                    </Button>
                                </CardContent>
                            </Card>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
