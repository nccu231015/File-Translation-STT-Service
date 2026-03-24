
import { useState, useRef } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Progress } from '@/components/ui/progress';
import {
    Upload,
    FileText,
    Languages,
    Download,
    Loader2,
    CheckCircle2,
    AlertCircle,
    X,
    Trash2,
    FileCheck,
    Maximize2,
    Bug,
    LayoutGrid
} from 'lucide-react';
import { Switch } from '@/components/ui/switch'; // Import Switch
import { Alert, AlertDescription } from '@/components/ui/alert';
import { toast } from 'sonner';
import { useTranslation } from '@/context/translation-context';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"

export function DocumentTranslation() {
    const { files, addFiles, removeFile } = useTranslation();
    const [sourceLang, setSourceLang] = useState('');
    const [targetLang, setTargetLang] = useState('');
    const [isDragging, setIsDragging] = useState(false);
    const [debugMode, setDebugMode] = useState(false);
    const [isComplexTable, setIsComplexTable] = useState(false);
    const [showPasswordDialog, setShowPasswordDialog] = useState(false);
    const [password, setPassword] = useState('');
    // Files staged before the user has picked a target language
    const [pendingFiles, setPendingFiles] = useState<File[]>([]);
    const fileInputRef = useRef<HTMLInputElement>(null);
    // Word 下載前提醒對話框
    const [showWordWarning, setShowWordWarning] = useState(false);
    const [pendingDocxInfo, setPendingDocxInfo] = useState<{ url: string; filename: string } | null>(null);

    const handleDebugToggle = (checked: boolean) => {
        if (checked) {
            setShowPasswordDialog(true);
        } else {
            setDebugMode(false);
        }
    };

    const verifyPassword = () => {
        if (password === '123') {
            setDebugMode(true);
            setShowPasswordDialog(false);
            setPassword('');
            toast.success("Debug 模式已啟用");
        } else {
            toast.error("密碼錯誤");
            setPassword('');
        }
    };

    const languages = [
        { value: 'zh-TW', label: '繁體中文' },
        { value: 'en', label: '英文' }
    ];

    const handleDragOver = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(true);
    };

    const handleDragLeave = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        const droppedFiles = Array.from(e.dataTransfer.files);
        processFiles(droppedFiles);
    };

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files) {
            const selectedFiles = Array.from(e.target.files);
            processFiles(selectedFiles);
        }
    };

    const processFiles = (fileList: File[]) => {
        const pdfFiles = fileList.filter(file => file.type === 'application/pdf');
        if (pdfFiles.length === 0 && fileList.length > 0) {
            toast.error('僅支援 PDF 檔案');
            return;
        }
        if (pdfFiles.length === 0) return;

        if (!targetLang) {
            // Language not yet selected — stage the files and prompt the user
            setPendingFiles(prev => [...prev, ...pdfFiles]);
            toast.info(`已暫存 ${pdfFiles.length} 個檔案，請選擇目標語言後自動開始翻譯`);
            return;
        }

        addFiles(pdfFiles, sourceLang, targetLang, debugMode, isComplexTable);
    };

    // When the user finally picks a target language, flush any pending files
    const handleTargetLangChange = (lang: string) => {
        setTargetLang(lang);
        if (pendingFiles.length > 0) {
            addFiles(pendingFiles, sourceLang, lang, debugMode, isComplexTable);
            setPendingFiles([]);
            toast.success(`開始翻譯 ${pendingFiles.length} 個已暫存的檔案`);
        }
    };

    const formatFileSize = (bytes: number) => {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    };

    return (
        <div className="space-y-6">
            <Alert>
                <AlertCircle className="size-4" />
                <AlertDescription>
                    文件翻譯功能基於地端部署的翻譯模型，所有文件均在內部處理，確保資料安全不外流。
                </AlertDescription>
            </Alert>

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Languages className="size-5" />
                        翻譯設定
                    </CardTitle>
                    <CardDescription>選擇源語言與目標語言 (目前後端支援自動偵測與翻譯)</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="grid md:grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label htmlFor="sourceLang">源語言 (自動偵測)</Label>
                            <Select value={sourceLang} onValueChange={setSourceLang}>
                                <SelectTrigger id="sourceLang">
                                    <SelectValue placeholder="選擇源語言" />
                                </SelectTrigger>
                                <SelectContent>
                                    {languages.map((lang) => (
                                        <SelectItem key={lang.value} value={lang.value}>
                                            {lang.label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="targetLang">目標語言</Label>
                            <Select value={targetLang} onValueChange={handleTargetLangChange}>
                                <SelectTrigger id="targetLang">
                                    <SelectValue placeholder="選擇目標語言" />
                                </SelectTrigger>
                                <SelectContent>
                                    {languages.map((lang) => (
                                        <SelectItem key={lang.value} value={lang.value}>
                                            {lang.label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    </div>

                    <div className="pt-6 border-t mt-4 space-y-3">
                        <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1">
                            <Maximize2 className="size-3" />
                            進階功能設定
                        </div>

                        {/* Complex Table Mode Option */}
                        <div className="group flex items-center justify-between p-3 rounded-xl border border-slate-100 bg-slate-50/50 hover:bg-white hover:border-blue-200 transition-all duration-200">
                            <div className="flex gap-3 items-start">
                                <div className="p-2 rounded-lg bg-blue-100/50 text-blue-600 group-hover:bg-blue-600 group-hover:text-white transition-colors">
                                    <LayoutGrid className="size-4" />
                                </div>
                                <Label htmlFor="complex-table" className="flex flex-col gap-1 cursor-pointer">
                                    <span className="text-sm font-semibold text-slate-900 leading-tight">使用 Word 表格解析模式</span>
                                    <span className="text-[11px] text-slate-500 font-normal leading-relaxed">
                                        建議複雜/巢狀表格使用。開啟後將採用 Word 二次轉譯機制，能更精準對應儲存格內容。
                                    </span>
                                </Label>
                            </div>
                            <Switch
                                id="complex-table"
                                checked={isComplexTable}
                                onCheckedChange={setIsComplexTable}
                                className="ml-4"
                            />
                        </div>

                        {/* Debug Mode Option */}
                        <div className="group flex items-center justify-between p-3 rounded-xl border border-slate-100 bg-slate-50/50 hover:bg-white hover:border-orange-200 transition-all duration-200">
                            <div className="flex gap-3 items-start">
                                <div className="p-2 rounded-lg bg-orange-100/50 text-orange-600 group-hover:bg-orange-600 group-hover:text-white transition-colors">
                                    <Bug className="size-4" />
                                </div>
                                <Label htmlFor="debug-mode" className="flex flex-col gap-1 cursor-pointer">
                                    <span className="text-sm font-semibold text-slate-900 leading-tight">開啟排版偵測預覽模式</span>
                                    <span className="text-[11px] text-slate-500 font-normal leading-relaxed">
                                        僅標記 YOLO 偵測到的區塊 (Figure/Table) 供診斷使用，不會實際扣除翻譯額度。
                                    </span>
                                </Label>
                            </div>
                            <Switch
                                id="debug-mode"
                                checked={debugMode}
                                onCheckedChange={handleDebugToggle}
                                className="ml-4"
                            />
                        </div>
                    </div>

                    <Dialog open={showPasswordDialog} onOpenChange={setShowPasswordDialog}>
                        <DialogContent>
                            <DialogHeader>
                                <DialogTitle>開啟 Debug 模式</DialogTitle>
                                <DialogDescription>
                                    請輸入密碼以啟用開發者預覽模式。
                                </DialogDescription>
                            </DialogHeader>
                            <div className="space-y-4 py-4">
                                <div className="space-y-2">
                                    <Label htmlFor="password">密碼</Label>
                                    <Input
                                        id="password"
                                        type="password"
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        onKeyDown={(e) => {
                                            if (e.key === 'Enter') {
                                                verifyPassword();
                                            }
                                        }}
                                    />
                                </div>
                            </div>
                            <DialogFooter>
                                <Button variant="outline" onClick={() => setShowPasswordDialog(false)}>取消</Button>
                                <Button onClick={verifyPassword}>確認</Button>
                            </DialogFooter>
                        </DialogContent>
                    </Dialog>
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Upload className="size-5" />
                        上傳 PDF 文件
                    </CardTitle>
                    <CardDescription>支援拖放上傳，系統將自動翻譯並保留原始排版格式</CardDescription>
                </CardHeader>
                <CardContent>
                    <div
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                        className={`
              border-2 border-dashed rounded-lg p-12 text-center transition-all cursor-pointer
              ${isDragging
                                ? 'border-blue-600 bg-blue-50'
                                : 'border-slate-300 hover:border-blue-400 hover:bg-slate-50'
                            }
            `}
                        onClick={(e) => {
                            e.stopPropagation();
                            fileInputRef.current?.click();
                        }}
                    >
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept=".pdf"
                            multiple
                            className="hidden"
                            onChange={(e) => {
                                handleFileSelect(e);
                                e.target.value = '';
                            }}
                        />

                        <Upload className="size-12 mx-auto mb-4 text-slate-400" />

                        <div className="space-y-2">
                            <p className="font-medium text-slate-900">拖放 PDF 文件到此處</p>
                            <p className="text-sm text-slate-500">或點擊選擇文件上傳</p>
                            {!targetLang && pendingFiles.length === 0 && (
                                <p className="text-xs text-amber-600 mt-2">⚠ 請選擇目標語言（可先上傳，選完語言後自動翻譯）</p>
                            )}
                            {pendingFiles.length > 0 && (
                                <p className="text-xs text-blue-600 mt-2">⏳ 已暫存 {pendingFiles.length} 個檔案，選擇目標語言即開始翻譯</p>
                            )}
                        </div>
                    </div>
                </CardContent>
            </Card>

            {files.length > 0 && (
                <div className="space-y-4">
                    <h3 className="text-lg font-semibold flex items-center gap-2">
                        <FileCheck className="size-5" />
                        翻譯任務列表
                    </h3>
                    <div className="space-y-6">
                        {files.map((file) => (
                            <Card key={file.id} className="overflow-hidden">
                                <CardHeader className="bg-slate-50 border-b py-3 px-4">
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-3">
                                            <div className={`p-2 rounded-full ${file.status === 'completed' ? 'bg-green-100' : 'bg-blue-100'}`}>
                                                <FileText className={`size-4 ${file.status === 'completed' ? 'text-green-600' : 'text-blue-600'}`} />
                                            </div>
                                            <div>
                                                <h4 className="font-medium text-sm">{file.name}</h4>
                                                <div className="flex gap-2 text-xs mt-0.5">
                                                    <Badge variant="outline" className="text-[10px] h-5">{formatFileSize(file.size)}</Badge>
                                                    <Badge variant={file.status === 'completed' ? 'default' : 'secondary'} className="text-[10px] h-5">
                                                        {file.status === 'uploading' ? '上傳中' :
                                                            file.status === 'processing' ? '翻譯處理中' :
                                                                file.status === 'completed' ? '翻譯完成' : '失敗'}
                                                    </Badge>
                                                </div>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            {file.status === 'completed' && file.downloadUrl && (
                                                <a href={file.downloadUrl} download={`translated_${file.name}`}>
                                                    <Button size="sm" variant="outline" className="h-8">
                                                        <Download className="size-3.5 mr-2" />
                                                        下載 PDF
                                                    </Button>
                                                </a>
                                            )}
                                            {file.status === 'completed' && file.docxUrl && (
                                                <Button
                                                    size="sm"
                                                    variant="outline"
                                                    className="h-8 border-blue-200 text-blue-600 hover:bg-blue-50"
                                                    onClick={() => {
                                                        setPendingDocxInfo({
                                                            url: file.docxUrl!,
                                                            filename: `translated_${file.name.replace(/\.pdf$/i, '.docx')}`
                                                        });
                                                        setShowWordWarning(true);
                                                    }}
                                                >
                                                    <FileText className="size-3.5 mr-2" />
                                                    下載 Word
                                                </Button>
                                            )}
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                className="h-8 w-8 text-slate-400 hover:text-red-600 hover:bg-red-50"
                                                onClick={() => {
                                                    if (confirm('確定要刪除此筆翻譯記錄嗎？')) {
                                                        removeFile(file.id);
                                                    }
                                                }}
                                            >
                                                <Trash2 className="size-4" />
                                            </Button>
                                        </div>
                                    </div>
                                    {(file.status === 'uploading' || file.status === 'processing') && (
                                        <div className="flex items-center justify-center p-4 text-slate-500">
                                            <Loader2 className="animate-spin mr-2 h-4 w-4" />
                                            <span className="text-sm">
                                                {file.status === 'uploading' ? '正在上傳...' : '正在翻譯中，這可能需要幾分鐘...'}
                                            </span>
                                        </div>
                                    )}
                                </CardHeader>

                                {file.status === 'completed' && (
                                    <CardContent className="p-0">
                                        <div className="grid grid-cols-2 h-[600px] divide-x">
                                            {/* Left: Original */}
                                            <div className="flex flex-col h-full bg-slate-100">
                                                <div className="p-2 text-xs font-medium text-center bg-white border-b sticky top-0 z-10 text-slate-500">
                                                    原始文件
                                                </div>
                                                <div className="flex-1 w-full h-full relative">
                                                    {file.originalUrl ? (
                                                        <iframe
                                                            src={`${file.originalUrl}#toolbar=0&view=FitH`}
                                                            className="w-full h-full border-none"
                                                            title="Original PDF"
                                                        />
                                                    ) : (
                                                        <div className="flex items-center justify-center h-full text-slate-400">無法預覽</div>
                                                    )}
                                                </div>
                                            </div>

                                            {/* Right: Translated */}
                                            <div className="flex flex-col h-full bg-slate-100">
                                                <div className="p-2 text-xs font-medium text-center bg-white border-b sticky top-0 z-10 text-blue-600">
                                                    翻譯結果
                                                </div>
                                                <div className="flex-1 w-full h-full relative">
                                                    {file.downloadUrl ? (
                                                        <iframe
                                                            src={`${file.downloadUrl}#toolbar=0&view=FitH`}
                                                            className="w-full h-full border-none"
                                                            title="Translated PDF"
                                                        />
                                                    ) : (
                                                        <div className="flex items-center justify-center h-full text-slate-400">無法預覽</div>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    </CardContent>
                                )}
                            </Card>
                        ))}
                    </div>
                </div>
            )}

            {/* Word 下載前の温馨提醒 Dialog */}
            <Dialog open={showWordWarning} onOpenChange={setShowWordWarning}>
                <DialogContent className="sm:max-w-sm p-0 overflow-hidden rounded-2xl">
                    <div className="flex flex-col items-center px-6 pt-8 pb-6 gap-5">
                        {/* 雲端下載圖示 */}
                        <div className="w-20 h-20 rounded-2xl bg-green-50 flex items-center justify-center">
                            <Download className="size-9 text-green-500" strokeWidth={2} />
                        </div>

                        {/* 標題 */}
                        <h2 className="text-xl font-bold text-slate-800 text-center">
                            下載後再檢查一下吧！
                        </h2>

                        {/* 提示卡片區 */}
                        <div className="w-full space-y-3">
                            {/* 術語核對建議 */}
                            <div className="flex items-start gap-3 rounded-xl border border-slate-100 bg-slate-50 p-4">
                                <div className="mt-0.5 flex-shrink-0 w-8 h-8 rounded-lg bg-purple-100 flex items-center justify-center">
                                    <span className="text-xs font-bold text-purple-600">AB</span>
                                </div>
                                <div>
                                    <p className="text-sm font-semibold text-slate-800">術語核對建議</p>
                                    <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
                                        AI 翻譯可能對「專有名詞」理解有誤，建議進行最終確認。
                                    </p>
                                </div>
                            </div>

                            {/* 排版檢查提示 */}
                            <div className="flex items-start gap-3 rounded-xl border border-slate-100 bg-slate-50 p-4">
                                <div className="mt-0.5 flex-shrink-0 w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center">
                                    <LayoutGrid className="size-4 text-blue-600" />
                                </div>
                                <div>
                                    <p className="text-sm font-semibold text-slate-800">排版檢查提示</p>
                                    <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
                                        複雜的圖表或跑位是正常現象，您只需微調 Word 檔案即可恢復完美外觀。
                                    </p>
                                </div>
                            </div>
                        </div>

                        {/* 確認下載按鈕 */}
                        <button
                            className="w-full bg-green-500 hover:bg-green-600 active:bg-green-700 transition-colors text-white font-semibold rounded-xl py-3.5 flex items-center justify-center gap-2 shadow-md shadow-green-200"
                            onClick={() => {
                                if (pendingDocxInfo) {
                                    const a = document.createElement('a');
                                    a.href = pendingDocxInfo.url;
                                    a.download = pendingDocxInfo.filename;
                                    a.click();
                                }
                                setShowWordWarning(false);
                                setPendingDocxInfo(null);
                            }}
                        >
                            <CheckCircle2 className="size-5" />
                            沒問題，立即下載
                        </button>

                        {/* 取消連結 */}
                        <button
                            className="text-sm text-slate-400 hover:text-slate-600 transition-colors"
                            onClick={() => {
                                setShowWordWarning(false);
                                setPendingDocxInfo(null);
                            }}
                        >
                            取消
                        </button>
                    </div>
                </DialogContent>
            </Dialog>
        </div>
    );
}
