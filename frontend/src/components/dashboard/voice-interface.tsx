import { useState, useRef } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    Mic,
    Upload,
    Loader2,
    FileAudio,
    CheckCircle2,
    Download,
    Play,
    Pause,
    AlertCircle,
    Trash2,
    FileText,
    ClipboardList,
    ListTodo
} from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useVoice } from '@/context/voice-context';

export function VoiceInterface() {
    const { isProcessing, processingFilename, records, processAudio, setRecords } = useVoice();
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            setSelectedFile(file);
        }
        // Reset input value so the same file can be selected again if needed
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

    const handleUploadAndProcess = async () => {
        if (!selectedFile) return;
        await processAudio(selectedFile);
        setSelectedFile(null);
    };

    const deleteRecord = (id: string) => {
        if (confirm('確定要刪除此筆會議記錄嗎？')) {
            setRecords((prev: any[]) => prev.filter(r => r.id !== id));
        }
    };

    // Helper to extract action item fields flexibly
    const parseActionItem = (item: any) => {
        let data = item;
        if (typeof item === 'string') {
            try {
                // Try to parse if it's a JSON string
                const cleaned = item.replace(/'/g, '"'); // Handle single quotes common in LLM output
                data = JSON.parse(cleaned);
            } catch {
                return { task: item, owner: '', date: '' };
            }
        }

        return {
            task: data.task || data.description || data.content || '',
            owner: data.owner || data.assignee || data.who || '',
            date: data.deadline || data.due_date || data.date || ''
        };
    };

    return (
        <div className="space-y-6">
            <Alert>
                <AlertCircle className="size-4" />
                <AlertDescription>
                    語音處理完全在地端執行，支援中文辨識。會議內容不外流，符合企業資安要求。
                </AlertDescription>
            </Alert>

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Upload className="size-5" />
                        上傳會議錄音
                    </CardTitle>
                    <CardDescription>支援 WAV, MP3, M4A 格式</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="border-2 border-dashed border-slate-300 rounded-lg p-8 text-center hover:border-blue-400 transition-colors">
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept="audio/*"
                            onChange={handleFileSelect}
                            className="hidden"
                            id="audio-upload"
                        />
                        <label htmlFor="audio-upload" className="cursor-pointer">
                            <FileAudio className="size-12 mx-auto mb-3 text-slate-400" />
                            <p className="font-medium mb-1">點擊上傳或拖放音訊檔案</p>
                        </label>
                    </div>

                    {/* Show selected file ready for upload */}
                    {!isProcessing && selectedFile && (
                        <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg flex justify-between items-center">
                            <div className="flex items-center gap-3">
                                <FileAudio className="size-6 text-blue-600" />
                                <span className="font-medium">{selectedFile.name}</span>
                            </div>
                            <Button onClick={handleUploadAndProcess}>
                                開始分析
                            </Button>
                        </div>
                    )}

                    {/* Show processing state */}
                    {isProcessing && (
                        <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg flex justify-between items-center">
                            <div className="flex items-center gap-3">
                                <FileAudio className="size-6 text-blue-600" />
                                <div className="flex flex-col">
                                    <span className="font-medium">{processingFilename || 'Processing...'}</span>
                                    <span className="text-xs text-slate-500">正在進行 AI 會議分析...</span>
                                </div>
                            </div>
                            <Button disabled>
                                <Loader2 className="animate-spin mr-2" />
                                處理中
                            </Button>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Results */}
            <h3 className="text-lg font-bold text-slate-700 mt-8 mb-4 px-1">已處理會議記錄</h3>
            {records.map((record: any) => (
                <Card key={record.id} className="mt-6 border-slate-200 shadow-sm hover:shadow-md transition-shadow overflow-hidden">
                    <CardHeader className="bg-slate-50/50 border-b pb-3">
                        <div className="flex justify-between items-start">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-purple-100 rounded-lg">
                                    <Mic className="size-5 text-purple-600" />
                                </div>
                                <div>
                                    <div className="font-bold text-slate-900">{record.fileName}</div>
                                    <div className="text-xs text-slate-500 mt-0.5">
                                        時長：{record.duration || '45:32'} • {new Date(record.processedAt).toLocaleString('zh-TW')}
                                    </div>
                                </div>
                            </div>
                            <div className="flex items-center gap-2">
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="text-slate-400 hover:text-red-600"
                                    onClick={() => deleteRecord(record.id)}
                                >
                                    <Trash2 className="size-4" />
                                </Button>
                                {record.downloadUrl && (
                                    <a href={record.downloadUrl} download={`meeting_minutes_${record.fileName}.docx`}>
                                        <Button variant="outline" size="sm" className="gap-2">
                                            <Download className="size-4" />
                                            匯出 (.docx)
                                        </Button>
                                    </a>
                                )}
                            </div>
                        </div>
                    </CardHeader>
                    <CardContent className="p-6 space-y-8">
                        {/* Summary */}
                        <div className="space-y-3">
                            <h4 className="font-bold flex items-center text-slate-800">
                                <FileText className="size-4 text-blue-600 mr-2" />
                                會議摘要
                            </h4>
                            <p className="text-slate-700 leading-relaxed pl-6 text-sm">
                                {record.summary}
                            </p>
                        </div>

                        {/* Decisions */}
                        <div className="space-y-4">
                            <h4 className="flex items-center gap-2 font-medium text-emerald-700 mb-2">
                                <CheckCircle2 className="size-5" />
                                決策事項
                            </h4>
                            <div className="space-y-2 pl-6">
                                {Array.isArray(record.decisions) && record.decisions.length > 0 ? (
                                    record.decisions.map((d: string, i: number) => (
                                        <div key={i} className="flex items-start gap-2 text-sm text-slate-700">
                                            <CheckCircle2 className="size-4 text-green-500 mt-0.5 shrink-0" />
                                            <span>{typeof d === 'string' ? d : JSON.stringify(d)}</span>
                                        </div>
                                    ))
                                ) : (
                                    <p className="text-sm text-slate-500 italic">無決策事項</p>
                                )}
                            </div>
                        </div>

                        {/* Action Items */}
                        <div className="space-y-4">
                            <h4 className="flex items-center gap-2 font-medium text-amber-700 mb-2">
                                <ListTodo className="size-5" />
                                待辦事項
                            </h4>
                            <div className="space-y-3 pl-6">
                                {Array.isArray(record.actionItems) && record.actionItems.length > 0 ? (
                                    record.actionItems.map((item: any, i: number) => (
                                        <div key={i} className="bg-amber-50 p-3 rounded-lg border border-amber-100 flex items-start justify-between group">
                                            <div className="text-sm text-slate-700">
                                                {typeof item === 'string' ? item : (
                                                    <span>{item.task} <span className="text-xs text-slate-400">({item.deadline})</span></span>
                                                )}
                                            </div>
                                            {typeof item !== 'string' && item.owner && (
                                                <Badge variant="outline" className="text-xs bg-white text-slate-500 border-slate-200">
                                                    {item.owner}
                                                </Badge>
                                            )}
                                        </div>
                                    ))
                                ) : (
                                    <p className="text-sm text-slate-500 italic">無待辦事項</p>
                                )}
                            </div>
                        </div>
                    </CardContent>
                </Card>
            ))}
        </div>
    );
}
