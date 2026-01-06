import React, { useState, useRef } from 'react';

const InputArea = ({ onSendMessage, onSendAudio, onSendFile }) => {
    const [inputText, setInputText] = useState('');
    const [isRecording, setIsRecording] = useState(false);
    const mediaRecorderRef = useRef(null);
    const audioChunksRef = useRef([]);

    const handleSendText = () => {
        if (!inputText.trim()) return;
        onSendMessage(inputText);
        setInputText('');
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSendText();
        }
    };

    const toggleRecording = async () => {
        if (isRecording) {
            // Stop recording
            if (mediaRecorderRef.current) {
                mediaRecorderRef.current.stop();
                setIsRecording(false);
            }
        } else {
            // Start recording
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                const mediaRecorder = new MediaRecorder(stream);
                mediaRecorderRef.current = mediaRecorder;
                audioChunksRef.current = [];

                mediaRecorder.ondataavailable = (event) => {
                    console.log("Data available:", event.data.size);
                    if (event.data.size > 0) {
                        audioChunksRef.current.push(event.data);
                    }
                };

                mediaRecorder.onstop = () => {
                    console.log("Recorder stopped. Chunks:", audioChunksRef.current.length);
                    const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
                    console.log("Audio Blob size:", audioBlob.size);

                    if (audioBlob.size === 0) {
                        console.error("Recorded audio is empty!");
                        alert("Recording failed: Audio is empty.");
                        return;
                    }

                    const audioFile = new File([audioBlob], "recording.webm", { type: 'audio/webm' });
                    onSendAudio(audioFile);

                    stream.getTracks().forEach(track => track.stop());
                };

                mediaRecorder.start();
                console.log("MediaRecorder started");
                setIsRecording(true);
            } catch (error) {
                console.error("Error accessing microphone:", error);
                alert("Could not access microphone. Please allow permissions.");
            }
        }
    };

    const fileInputRef = useRef(null);

    const handleFileChange = (e) => {
        const file = e.target.files[0];
        if (file) {
            // Check if PDF
            if (file.type === "application/pdf") {
                // Propagate up to App.jsx to handle the upload API call
                // We reuse a new prop or existing one? 
                // Let's create a new prop onSendFile
                if (onSendFile) onSendFile(file);
            } else {
                alert("Please upload a PDF file.");
            }
        }
    };

    return (
        <div className="border-t border-gray-100 bg-white p-4">
            <div className="max-w-3xl mx-auto flex items-end gap-2">
                {/* File Upload Hidden Input */}
                <input
                    type="file"
                    ref={fileInputRef}
                    className="hidden"
                    accept=".pdf"
                    onChange={handleFileChange}
                />

                {/* File Upload Button */}
                <button
                    onClick={() => fileInputRef.current.click()}
                    className="p-3 text-gray-400 hover:text-gray-600 rounded-full hover:bg-gray-100 transition-colors"
                    title="Upload PDF for Translation"
                >
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" /></svg>
                </button>

                <div className="flex-1 bg-gray-100 rounded-2xl flex items-center px-4 py-2 focus-within:ring-2 ring-blue-100 transition-all">
                    <textarea
                        value={inputText}
                        onChange={(e) => setInputText(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Type a message..."
                        className="w-full bg-transparent border-none focus:outline-none resize-none max-h-32 py-2"
                        rows={1}
                    />
                </div>

                {/* Record / Send Button */}
                {inputText.trim() ? (
                    <button
                        onClick={handleSendText}
                        className="p-3 bg-blue-600 text-white rounded-full hover:bg-blue-700 transition-colors shadow-md"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" /></svg>
                    </button>
                ) : (
                    <button
                        onClick={toggleRecording}
                        className={`p-3 rounded-full transition-all shadow-md ${isRecording
                            ? 'bg-red-500 text-white ring-4 ring-red-200'
                            : 'bg-gray-900 text-white hover:bg-gray-700'
                            }`}
                        title={isRecording ? "Click to Stop" : "Click to Record"}
                    >
                        {isRecording ? (
                            <div className="w-5 h-5 flex items-center justify-center">
                                <div className="w-3 h-3 bg-white rounded-sm animate-pulse" />
                            </div>
                        ) : (
                            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" /><path d="M19 10v2a7 7 0 0 1-14 0v-2" /><line x1="12" y1="19" x2="12" y2="23" /><line x1="8" y1="23" x2="16" y2="23" /></svg>
                        )}
                    </button>
                )}
            </div>
            <div className="max-w-3xl mx-auto text-center mt-2">
                <span className="text-xs text-gray-400">
                    {isRecording ? "Recording... Click stop to send." : "Click microphone to start recording"}
                </span>
            </div>
        </div>
    );
};

export default InputArea;
