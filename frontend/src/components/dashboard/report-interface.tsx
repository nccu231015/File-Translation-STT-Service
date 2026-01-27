
import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { FileBarChart, Download, Loader2, TrendingUp, AlertCircle, BarChart3 } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer
} from 'recharts';
import { generateReport, ReportData } from '@/lib/api/report';

export function ReportInterface() {
    const [reportType, setReportType] = useState('');
    const [timeRange, setTimeRange] = useState('');
    const [isGenerating, setIsGenerating] = useState(false);
    const [reports, setReports] = useState<ReportData[]>([
        {
            id: '1',
            title: '本月生產分析報表',
            type: '生產分析',
            createdAt: new Date(Date.now() - 3600000),
            status: 'completed'
        },
        {
            id: '2',
            title: '異常事件統計報表',
            type: '異常分析',
            createdAt: new Date(Date.now() - 7200000),
            status: 'completed'
        }
    ]);

    const reportTypes = [
        { value: 'production', label: '生產分析報表', description: '良率、產量、稼動率等生產指標' },
        { value: 'quality', label: '品質分析報表', description: '異常事件、缺陷率、檢驗結果' },
        { value: 'equipment', label: '設備效能報表', description: 'OEE、停機時間、維護記錄' },
        { value: 'cost', label: '成本分析報表', description: '原料成本、人力成本、單位成本' }
    ];

    const timeRanges = [
        { value: 'today', label: '今日' },
        { value: 'week', label: '本週' },
        { value: 'month', label: '本月' },
        { value: 'quarter', label: '本季' },
        { value: 'custom', label: '自訂區間' }
    ];

    const handleGenerate = async () => {
        if (!reportType || !timeRange) {
            return;
        }

        setIsGenerating(true);

        try {
            const newReport = await generateReport(reportType, timeRange);
            setReports(prev => [newReport, ...prev]);
            setReportType('');
            setTimeRange('');
        } catch (error) {
            console.error("Report generation failed", error);
        } finally {
            setIsGenerating(false);
        }
    };

    const yieldTrendData = [
        { date: '1/1', 良率: 94.5, 目標: 96 },
        { date: '1/3', 良率: 95.2, 目標: 96 },
        { date: '1/5', 良率: 93.8, 目標: 96 },
        { date: '1/7', 良率: 96.1, 目標: 96 },
        { date: '1/9', 良率: 95.7, 目標: 96 },
        { date: '1/11', 良率: 97.2, 目標: 96 },
        { date: '1/13', 良率: 96.8, 目標: 96 },
        { date: '1/15', 良率: 96.3, 目標: 96 },
    ];

    return (
        <div className="space-y-6">
            <Alert>
                <AlertCircle className="size-4" />
                <AlertDescription>
                    報表生成基於語義層定義的指標,確保跨部門數據一致性。所有計算邏輯可追溯。
                </AlertDescription>
            </Alert>

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <FileBarChart className="size-5" />
                        生成新報表
                    </CardTitle>
                    <CardDescription>選擇報表類型與時間範圍，系統將自動取得資料並生成分析報表</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                    <div className="space-y-3">
                        <Label>報表類型</Label>
                        <div className="grid md:grid-cols-2 gap-3">
                            {reportTypes.map((type) => (
                                <button
                                    key={type.value}
                                    onClick={() => setReportType(type.value)}
                                    className={`p-4 border-2 rounded-lg text-left transition-all ${reportType === type.value
                                        ? 'border-blue-600 bg-blue-50'
                                        : 'border-slate-200 hover:border-slate-300'
                                        }`}
                                >
                                    <div className="font-semibold mb-1">{type.label}</div>
                                    <div className="text-xs text-slate-600">{type.description}</div>
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="timeRange">時間範圍</Label>
                        <Select value={timeRange} onValueChange={setTimeRange}>
                            <SelectTrigger id="timeRange">
                                <SelectValue placeholder="選擇時間範圍" />
                            </SelectTrigger>
                            <SelectContent>
                                {timeRanges.map((range) => (
                                    <SelectItem key={range.value} value={range.value}>
                                        {range.label}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    <Button
                        onClick={handleGenerate}
                        disabled={!reportType || !timeRange || isGenerating}
                        size="lg"
                        className="w-full"
                    >
                        {isGenerating ? (
                            <>
                                <Loader2 className="size-5 mr-2 animate-spin" />
                                生成中...（分析資料、計算指標、產生圖表）
                            </>
                        ) : (
                            <>
                                <FileBarChart className="size-5 mr-2" />
                                生成報表
                            </>
                        )}
                    </Button>

                    {isGenerating && (
                        <Alert>
                            <TrendingUp className="size-4" />
                            <AlertDescription>
                                正在執行：資料取得 → 語義層驗證 → 指標計算 → 視覺化生成
                            </AlertDescription>
                        </Alert>
                    )}
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle>已生成報表</CardTitle>
                    <CardDescription>點擊報表查看詳細內容或下載</CardDescription>
                </CardHeader>
                <CardContent>
                    {reports.length === 0 ? (
                        <div className="text-center py-12 text-slate-500">
                            <FileBarChart className="size-12 mx-auto mb-3 opacity-50" />
                            <p>尚未生成任何報表</p>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {reports.map((report) => (
                                <div
                                    key={report.id}
                                    className="flex items-center justify-between p-4 border rounded-lg hover:bg-slate-50 transition-colors"
                                >
                                    <div className="flex items-start gap-3 flex-1">
                                        <div className="p-2 bg-blue-100 rounded-lg">
                                            <FileBarChart className="size-5 text-blue-600" />
                                        </div>
                                        <div className="flex-1">
                                            <h4 className="font-semibold">{report.title}</h4>
                                            <div className="flex items-center gap-2 mt-1">
                                                <Badge variant="outline">{report.type}</Badge>
                                                <span className="text-xs text-slate-500">
                                                    {report.createdAt.toLocaleString('zh-TW')}
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        {report.status === 'completed' && (
                                            <>
                                                <Button variant="outline" size="sm">
                                                    <BarChart3 className="size-4 mr-2" />
                                                    查看
                                                </Button>
                                                <Button variant="outline" size="sm">
                                                    <Download className="size-4 mr-2" />
                                                    下載
                                                </Button>
                                            </>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>

            {reports.length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle>報表預覽 - {reports[0].title}</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-6">
                            <div className="grid md:grid-cols-4 gap-4">
                                <Card>
                                    <CardContent className="p-4">
                                        <div className="text-sm text-slate-600 mb-1">整體良率</div>
                                        <div className="text-2xl font-bold text-green-600">96.3%</div>
                                        <div className="text-xs text-slate-500 mt-1">↑ 較上月 +1.2%</div>
                                    </CardContent>
                                </Card>
                                <Card>
                                    <CardContent className="p-4">
                                        <div className="text-sm text-slate-600 mb-1">異常事件</div>
                                        <div className="text-2xl font-bold text-amber-600">156</div>
                                        <div className="text-xs text-slate-500 mt-1">需關注</div>
                                    </CardContent>
                                </Card>
                            </div>

                            <div className="grid md:grid-cols-2 gap-6">
                                <Card>
                                    <CardHeader>
                                        <CardTitle className="text-base">良率趨勢分析</CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        <ResponsiveContainer width="100%" height={250}>
                                            <AreaChart data={yieldTrendData}>
                                                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                                                <XAxis dataKey="date" stroke="#64748b" fontSize={12} />
                                                <YAxis stroke="#64748b" fontSize={12} domain={[92, 100]} />
                                                <Tooltip
                                                    contentStyle={{ backgroundColor: '#fff', border: '1px solid #e2e8f0', borderRadius: '8px' }}
                                                />
                                                <Legend />
                                                <Area
                                                    type="monotone"
                                                    dataKey="良率"
                                                    stroke="#10b981"
                                                    fill="#86efac"
                                                    strokeWidth={2}
                                                />
                                                <Area
                                                    type="monotone"
                                                    dataKey="目標"
                                                    stroke="#ef4444"
                                                    fill="transparent"
                                                    strokeWidth={2}
                                                    strokeDasharray="5 5"
                                                />
                                            </AreaChart>
                                        </ResponsiveContainer>
                                    </CardContent>
                                </Card>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
