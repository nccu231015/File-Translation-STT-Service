
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
    Maximize2
} from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { toast } from 'sonner';
import { useTranslation } from '@/context/translation-context';

export function DocumentTranslation() {
    const { files, addFiles, removeFile } = useTranslation();
    const [sourceLang, setSourceLang] = useState('');
    const [targetLang, setTargetLang] = useState('');
    const [isDragging, setIsDragging] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

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
        if (!targetLang) {
            toast.warning("請先選擇目標語言");
            return;
        }

        const pdfFiles = fileList.filter(file => file.type === 'application/pdf');
        if (pdfFiles.length === 0 && fileList.length > 0) {
            toast.error("僅支援 PDF 檔案");
            return;
        }

        addFiles(pdfFiles, sourceLang, targetLang);
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
                            <Select value={targetLang} onValueChange={setTargetLang}>
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
              border-2 border-dashed rounded-lg p-12 text-center transition-all
              ${isDragging
                                ? 'border-blue-600 bg-blue-50'
                                : 'border-slate-300 hover:border-slate-400'
                            }
              ${!targetLang
                                ? 'opacity-50 cursor-not-allowed'
                                : 'cursor-pointer'
                            }
            `}
                        onClick={(e) => {
                            e.stopPropagation();
                            if (targetLang) {
                                fileInputRef.current?.click();
                            } else {
                                toast.warning("請先選擇目標語言");
                            }
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
                            disabled={!targetLang}
                        />

                        <Upload className="size-12 mx-auto mb-4 text-slate-400" />

                        {!targetLang ? (
                            <div className="space-y-2">
                                <p className="font-medium text-slate-600">請先選擇目標語言</p>
                            </div>
                        ) : (
                            <div className="space-y-2">
                                <p className="font-medium text-slate-900">拖放 PDF 文件到此處</p>
                                <p className="text-sm text-slate-500">或點擊選擇文件上傳</p>
                            </div>
                        )}
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
                                                        下載翻譯檔
                                                    </Button>
                                                </a>
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
        </div>
    );
}
