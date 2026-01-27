
import { useState, useRef } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
    Mic,
    Upload,
    Loader2,
    FileAudio,
    CheckCircle2,
    Download,
    Play,
    Pause,
    AlertCircle
} from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { toast } from 'sonner';
import { analyzeMeetingAudio } from '@/lib/api/stt';

interface ProcessedRecord {
    id: string;
    fileName: string;
    duration: string;
    processedAt: Date;
    transcript: string;
    summary: string;
    decisions: string[];
    actionItems: string[];
    downloadUrl?: string;
}

export function VoiceInterface() {
    const [isRecording, setIsRecording] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [records, setRecords] = useState<ProcessedRecord[]>([]);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) setSelectedFile(file);
    };

    const handleUploadAndProcess = async () => {
        if (!selectedFile) return;

        setIsProcessing(true);

        try {
            const data = await analyzeMeetingAudio(selectedFile);
            const analysis = data.analysis;

            // Handle file download for meeting minutes
            let downloadUrl = '';
            if (data.file_download) {
                const blob = new Blob([data.file_download.content], { type: 'text/plain' });
                downloadUrl = URL.createObjectURL(blob);
            }

            const newRecord: ProcessedRecord = {
                id: Date.now().toString(),
                fileName: selectedFile.name,
                duration: 'Unknown',
                processedAt: new Date(),
                transcript: data.transcription.text,
                summary: analysis.summary,
                decisions: analysis.decisions,
                actionItems: analysis.action_items,
                downloadUrl: downloadUrl
            };

            setRecords(prev => [newRecord, ...prev]);
            toast.success('會議分析完成');
            setSelectedFile(null);

        } catch (error) {
            console.error(error);
            toast.error('處理失敗');
        } finally {
            setIsProcessing(false);
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

            <Tabs defaultValue="upload" className="space-y-4">
                <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="upload">上傳錄音檔</TabsTrigger>
                    <TabsTrigger value="realtime" disabled>即時錄音 (暫未開放)</TabsTrigger>
                </TabsList>

                <TabsContent value="upload">
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

                            {selectedFile && (
                                <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg flex justify-between items-center">
                                    <div className="flex items-center gap-3">
                                        <FileAudio className="size-6 text-blue-600" />
                                        <span className="font-medium">{selectedFile.name}</span>
                                    </div>
                                    <Button onClick={handleUploadAndProcess} disabled={isProcessing}>
                                        {isProcessing ? <Loader2 className="animate-spin mr-2" /> : '開始分析'}
                                    </Button>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>

            {/* Results */}
            {records.map((record) => (
                <Card key={record.id} className="mt-6">
                    <CardHeader>
                        <CardTitle>{record.fileName}</CardTitle>
                        <CardDescription>{record.processedAt.toLocaleString()}</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        {record.downloadUrl && (
                            <div className="flex justify-end">
                                <a href={record.downloadUrl} download={`meeting_minutes_${record.fileName}.txt`}>
                                    <Button variant="outline" size="sm">
                                        <Download className="mr-2 size-4" />
                                        下載會議記錄 (.txt)
                                    </Button>
                                </a>
                            </div>
                        )}
                        <div className="bg-slate-50 p-4 rounded">
                            <h4 className="font-bold mb-2">摘要</h4>
                            <p>{record.summary}</p>
                        </div>

                        <div className="grid md:grid-cols-2 gap-4">
                            <div>
                                <h4 className="font-bold mb-2 text-green-700">決策事項</h4>
                                <ul className="list-disc pl-5">
                                    {record.decisions.map((d, i) => <li key={i}>{d}</li>)}
                                </ul>
                            </div>
                            <div>
                                <h4 className="font-bold mb-2 text-blue-700">待辦事項</h4>
                                <ul className="list-disc pl-5">
                                    {record.actionItems.map((a, i) => <li key={i}>{a}</li>)}
                                </ul>
                            </div>
                        </div>

                        <details className="text-sm border-t pt-4">
                            <summary className="cursor-pointer font-semibold mb-2">
                                🗣️ 完整逐字稿
                            </summary>
                            <div className="bg-slate-50 p-3 rounded max-h-40 overflow-y-auto whitespace-pre-wrap">
                                {record.transcript}
                            </div>
                        </details>
                    </CardContent>
                </Card>
            ))}
        </div>
    );
}
