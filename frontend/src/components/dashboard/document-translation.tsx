
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
    FileCheck
} from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert'; // Import from shadcn equivalent
import { toast } from 'sonner';
import ReactMarkdown from 'react-markdown';

interface TranslationFile {
    id: string;
    name: string;
    size: number;
    sourceLang: string;
    targetLang: string;
    status: 'uploading' | 'processing' | 'completed' | 'error';
    progress: number;
    uploadedAt: Date;
    downloadUrl?: string; // Add download URL
    summary?: string;     // Add summary
    content?: string;     // Add full content
}

export function DocumentTranslation() {
    const [files, setFiles] = useState<TranslationFile[]>([]);
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
        // Only require targetLang. Source lang is optional (auto-detect).
        if (!targetLang) {
            toast.warning("請先選擇目標語言");
            return;
        }

        // Filter PDF
        const pdfFiles = fileList.filter(file => file.type === 'application/pdf');
        if (pdfFiles.length === 0 && fileList.length > 0) {
            toast.error("僅支援 PDF 檔案");
        }

        pdfFiles.forEach(file => {
            const newFile: TranslationFile = {
                id: Date.now().toString() + Math.random(),
                name: file.name,
                size: file.size,
                sourceLang,
                targetLang,
                status: 'uploading',
                progress: 0,
                uploadedAt: new Date()
            };

            setFiles(prev => [newFile, ...prev]);
            uploadAndTranslate(newFile, file);
        });
    };

    const uploadAndTranslate = async (fileRecord: TranslationFile, fileObj: File) => {
        // 1. Uploading
        updateFileStatus(fileRecord.id, { status: 'uploading', progress: 30 });

        const formData = new FormData();
        formData.append('file', fileObj);
        // Pass selected target language to backend if backend supports it
        formData.append('target_lang', fileRecord.targetLang);
        // formData.append('sourceLang', fileRecord.sourceLang); // Backend currently auto-detects
        // formData.append('targetLang', fileRecord.targetLang); 

        try {
            updateFileStatus(fileRecord.id, { status: 'processing', progress: 60 });

            const res = await fetch('/api/pdf-translation', {
                method: 'POST',
                body: formData
            });

            if (!res.ok) throw new Error('Translation failed');

            const data = await res.json();

            // Blob for download
            const blob = new Blob([data.content], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);

            updateFileStatus(fileRecord.id, {
                status: 'completed',
                progress: 100,
                downloadUrl: url,
                summary: data.summary,
                content: data.content
            });
            toast.success(`${fileRecord.name} 翻譯完成`);

        } catch (error) {
            console.error(error);
            updateFileStatus(fileRecord.id, { status: 'error', progress: 0 });
            toast.error(`${fileRecord.name} 翻譯失敗`);
        }
    };

    const updateFileStatus = (id: string, updates: Partial<TranslationFile>) => {
        setFiles(prev => prev.map(f => f.id === id ? { ...f, ...updates } : f));
    };

    const removeFile = (fileId: string) => {
        setFiles(prev => prev.filter(f => f.id !== fileId));
    };

    const formatFileSize = (bytes: number) => {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    };

    const getLanguageLabel = (code: string) => {
        return languages.find(l => l.value === code)?.label || code;
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
                    <CardDescription>支援拖放上傳</CardDescription>
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
                            // Prevent triggering if clicking on the actual input (if it wasn't hidden)
                            // or distinct logic
                            e.stopPropagation();
                            if (targetLang) {
                                console.log("Triggering file input click");
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
                                console.log("File input changed", e.target.files);
                                handleFileSelect(e);
                                // Reset value to allow selecting same file again
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
                <Card>
                    <CardHeader>
                        <CardTitle>翻譯任務列表</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-3">
                            {files.map((file) => (
                                <div key={file.id} className="p-4 border rounded-lg space-y-3">
                                    <div className="flex items-start justify-between">
                                        <div className="flex items-start gap-3 flex-1">
                                            <div className={`p-2 rounded-lg ${file.status === 'completed' ? 'bg-green-100' :
                                                file.status === 'error' ? 'bg-red-100' : 'bg-blue-100'
                                                }`}>
                                                <FileText className={`size-5 ${file.status === 'completed' ? 'text-green-600' :
                                                    file.status === 'error' ? 'text-red-600' : 'text-blue-600'
                                                    }`} />
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <h4 className="font-semibold truncate">{file.name}</h4>
                                                {/* Status Badges */}
                                                <div className="flex gap-2 text-xs mt-1">
                                                    <Badge variant="outline">{formatFileSize(file.size)}</Badge>
                                                    <Badge variant="secondary">{file.status}</Badge>
                                                </div>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            {file.status === 'completed' && file.downloadUrl && (
                                                <a href={file.downloadUrl} download={`translated_${file.name.replace('.pdf', '.txt')}`}>
                                                    <Button variant="outline" size="sm">
                                                        <Download className="size-4 mr-2" />
                                                        下載
                                                    </Button>
                                                </a>
                                            )}
                                            {file.status !== 'processing' && (
                                                <Button variant="ghost" size="sm" onClick={() => removeFile(file.id)}>
                                                    <X className="size-4" />
                                                </Button>
                                            )}
                                        </div>
                                    </div>

                                    {(file.status === 'uploading' || file.status === 'processing') && (
                                        <div className="space-y-2">
                                            <div className="flex justify-between text-xs text-slate-500">
                                                <span>{file.status === 'uploading' ? '上傳中' : '翻譯處理中 (這可能需要幾分鐘)...'}</span>
                                                <span>{file.progress}%</span>
                                            </div>
                                            <Progress value={file.progress} className="h-2" />
                                        </div>
                                    )}

                                    {file.status === 'completed' && (
                                        <div className="mt-4 space-y-4">
                                            {file.summary && (
                                                <div className="bg-slate-50 p-4 rounded-lg text-sm border border-slate-200">
                                                    <h5 className="font-semibold mb-2 flex items-center gap-2">
                                                        <FileText className="size-4" />
                                                        文件摘要
                                                    </h5>
                                                    <div className="prose prose-sm max-w-none text-slate-700">
                                                        <ReactMarkdown>{file.summary}</ReactMarkdown>
                                                    </div>
                                                </div>
                                            )}

                                            {file.content && (
                                                <details className="group">
                                                    <summary className="flex items-center gap-2 cursor-pointer font-medium text-blue-600 hover:text-blue-700 p-2 hover:bg-blue-50 rounded select-none">
                                                        <span>查看完整翻譯內容</span>
                                                        <span className="text-xs text-slate-500 font-normal ml-auto transition-transform group-open:rotate-180">▼</span>
                                                    </summary>
                                                    <div className="mt-2 p-4 bg-white border rounded-lg shadow-inner max-h-96 overflow-y-auto">
                                                        <article className="prose prose-slate max-w-none prose-sm prose-headings:font-bold prose-h1:text-xl prose-h2:text-lg prose-p:leading-relaxed">
                                                            <ReactMarkdown>{file.content}</ReactMarkdown>
                                                        </article>
                                                    </div>
                                                </details>
                                            )}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
