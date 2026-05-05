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
    FileText,
    ListTodo,
    AlertCircle,
    Trash2
} from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useVoice } from '@/context/voice-context';
import { toast } from 'sonner';

const AUDIO_EXTENSIONS = ['mp3', 'wav', 'm4a', 'ogg', 'flac', 'aac', 'webm'];

function isAudioFile(file: File): boolean {
    const ext = file.name.split('.').pop()?.toLowerCase();
    const okByMime = file.type.startsWith('audio/');
    const okByExt = ext ? AUDIO_EXTENSIONS.includes(ext) : false;
    return okByMime || okByExt;
}

export function VoiceInterface() {
    const { isProcessing, activeJobs, records, processAudio, removeRecord } = useVoice();
    const [isDragging, setIsDragging] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const runParallelForFiles = (fileList: File[]) => {
        const audios = fileList.filter(isAudioFile);
        if (audios.length === 0 && fileList.length > 0) {
            toast.error('請上傳音訊檔案（WAV, MP3, M4A, AAC 等）');
            return;
        }
        for (const f of audios) {
            void processAudio(f);
        }
    };

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const list = e.target.files;
        if (!list?.length) return;
        runParallelForFiles(Array.from(list));
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

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
        const dropped = Array.from(e.dataTransfer.files);
        if (!dropped.length) return;
        runParallelForFiles(dropped);
    };

    const deleteRecord = (id: string) => {
        if (confirm('確定要刪除此筆會議記錄嗎？')) {
            removeRecord(id);
        }
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
                    <CardDescription>支援 WAV, MP3, M4A, AAC, OGG, FLAC, WEBM（可多選，會同時分析）</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                        onClick={() => fileInputRef.current?.click()}
                        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer
                            ${isDragging
                                ? 'border-blue-500 bg-blue-50'
                                : 'border-slate-300 hover:border-blue-400 hover:bg-slate-50'
                            }`}
                    >
                        <input
                            ref={fileInputRef}
                            type="file"
                            multiple
                            accept=".mp3,.wav,.m4a,.aac,.ogg,.flac,.webm,audio/*,audio/aac,audio/x-aac"
                            onChange={handleFileSelect}
                            className="hidden"
                            id="audio-upload"
                        />
                        <FileAudio className={`size-12 mx-auto mb-3 ${isDragging ? 'text-blue-500' : 'text-slate-400'}`} />
                        <p className="font-medium mb-1">點擊上傳或拖放音訊檔案</p>
                        <p className="text-xs text-slate-400 mt-1">WAV &bull; MP3 &bull; M4A &bull; AAC &bull; OGG &bull; FLAC（可一次多個）</p>
                        {isProcessing && (
                            <p className="text-xs text-amber-800 mt-3 font-medium">
                                目前正同時處理 {activeJobs.length} 個檔案；仍可繼續加入，與文件翻譯等其他功能並行、互不影響
                            </p>
                        )}
                    </div>

                    {/* Active parallel jobs */}
                    {isProcessing && activeJobs.length > 0 && (
                        <div className="space-y-2">
                            {activeJobs.map(job => (
                                <div
                                    key={job.id}
                                    className="p-4 bg-blue-50 border border-blue-200 rounded-lg flex justify-between items-center"
                                >
                                    <div className="flex items-center gap-3 min-w-0">
                                        <FileAudio className="size-6 text-blue-600 shrink-0" />
                                        <div className="flex flex-col min-w-0">
                                            <span className="font-medium truncate">{job.fileName}</span>
                                            <span className="text-xs text-slate-500">進行 AI 會議分析…</span>
                                        </div>
                                    </div>
                                    <Button disabled className="shrink-0">
                                        <Loader2 className="animate-spin mr-2 size-4" />
                                        處理中
                                    </Button>
                                </div>
                            ))}
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
                                {/* Meeting minutes download */}
                                {record.downloadUrl && (
                                    <a href={record.downloadUrl} download={`meeting_minutes_${record.fileName}.docx`}>
                                        <Button variant="outline" size="sm" className="gap-2">
                                            <Download className="size-4" />
                                            摘要 (.docx)
                                        </Button>
                                    </a>
                                )}
                                {/* Bilingual transcript download */}
                                {record.transcriptUrl && (
                                    <a href={record.transcriptUrl} download={`bilingual_transcript_${record.fileName}.docx`}>
                                        <Button variant="outline" size="sm" className="gap-2 border-emerald-300 text-emerald-700 hover:bg-emerald-50">
                                            <FileText className="size-4" />
                                            逐字稿 (.docx)
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
                            <p className="text-slate-700 leading-relaxed pl-6 text-sm whitespace-pre-line">
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
                                            <span className="whitespace-pre-line leading-relaxed">{typeof d === 'string' ? d : JSON.stringify(d)}</span>
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
                                            <div className="text-sm text-slate-700 whitespace-pre-line leading-relaxed">
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

                        {/* Translation / Original Transcript Viewer */}
                        <div className="mt-6 border-t border-slate-100 pt-4">
                            <details className="text-sm group">
                                <summary className="font-bold cursor-pointer text-slate-700 hover:text-blue-600 transition-colors list-none flex items-center gap-2">
                                    <FileText className="size-4" />
                                    <span>展開全文逐字稿與翻譯</span>
                                    <span className="text-xs font-normal text-slate-400 ml-2">(點擊展開)</span>
                                </summary>
                                <div className="mt-4 bg-slate-50 border border-slate-200 rounded-lg p-4 max-h-80 overflow-y-auto space-y-4">
                                    {record.translatedSegments && record.translatedSegments.length > 0 ? (
                                        record.translatedSegments.map((seg: any, idx: number) => (
                                            <div key={idx} className="pb-3 border-b border-slate-200 last:border-0 last:pb-0">
                                                <div className="text-xs text-slate-400 font-mono mb-1">
                                                    {new Date(seg.start * 1000).toISOString().substr(11, 8)} → {new Date(seg.end * 1000).toISOString().substr(11, 8)}
                                                </div>
                                                <p className="text-slate-800 font-medium mb-1 relative pl-3 before:content-[''] before:absolute before:left-0 before:top-1.5 before:bottom-1.5 before:w-1 before:bg-blue-400 before:rounded">
                                                    {seg.original}
                                                </p>
                                                <p className="text-slate-600 pl-3">
                                                    {seg.translated}
                                                </p>
                                            </div>
                                        ))
                                    ) : (
                                        <div className="text-slate-600 leading-relaxed whitespace-pre-wrap">
                                            {record.transcript}
                                        </div>
                                    )}
                                </div>
                            </details>
                        </div>
                    </CardContent>
                </Card>
            ))}
        </div>
    );
}
