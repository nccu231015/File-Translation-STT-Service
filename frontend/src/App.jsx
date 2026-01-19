import React, { useState } from 'react';
import MessageList from './components/Chat/MessageList';
import InputArea from './components/Chat/InputArea';

function App() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  const addMessage = (content, role, type = 'text') => {
    setMessages(prev => [...prev, { content, role, type }]);
  };

  const handleSendMessage = async (text) => {
    addMessage(text, 'user');
    setIsLoading(true);

    try {
      const response = await fetch('/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ text }),
      });

      if (!response.ok) throw new Error('Network response was not ok');

      const data = await response.json();
      addMessage(data.llm_response, 'system');
    } catch (error) {
      console.error("Chat error:", error);
      addMessage("Sorry, I encountered an error.", 'system');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendAudio = async (audioFile, mode = 'chat') => {
    console.log(`Sending audio to backend (Mode: ${mode})...`, audioFile);
    setIsLoading(true);

    // Create form data
    const formData = new FormData();
    formData.append('file', audioFile);
    formData.append('mode', mode);

    try {
      const response = await fetch('/stt', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Error: ${response.statusText}`);
      }

      const data = await response.json();

      // 1. Show what the user said (Transcription)
      addMessage(data.transcription.text, 'user', 'audio');

      // 2. Handle Response based on Mode
      if (mode === 'chat') {
        addMessage(data.llm_response, 'system');
      } else if (mode === 'meeting') {
        // Meeting Mode: Show Summary and trigger download
        const analysis = data.analysis;
        const downloadInfo = data.file_download;

        // Format for Chat Display
        const displayContent = `
📋 **會議重點摘要**
${analysis.summary}

✅ **決策事項**
${analysis.decisions.map(d => `- ${d}`).join('\n')}

⚡ **待辦清單**
${analysis.action_items.map(a => `- ${a}`).join('\n')}
          `.trim();

        addMessage(displayContent, 'system', 'meeting-result');

        // Trigger Download
        if (downloadInfo) {
          const blob = new Blob([downloadInfo.content], { type: 'text/plain' });
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = downloadInfo.filename;
          document.body.appendChild(a);
          a.click();
          window.URL.revokeObjectURL(url);
          document.body.removeChild(a);
          addMessage(`📥 會議記錄已自動下載: ${downloadInfo.filename}`, 'system');
        }
      }

    } catch (error) {
      console.error("Transcription error:", error);
      addMessage("Error processing audio. Please try again.", 'system');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendFile = async (file) => {
    setIsLoading(true);

    // Check if Audio File -> Route to Meeting Mode
    if (file.type.startsWith('audio/')) {
      addMessage(`Uploading Audio for Meeting Analysis: ${file.name}...`, 'user');
      // Retrieve explicit mode? For file upload, we can assume 'meeting' mode is the primary intent for uploading long audio
      // or we could inspect the 'mode' state if we passed it up, but usually uploading a file implies full processing.
      // Let's force 'meeting' mode for uploaded audio files as requested.
      await handleSendAudio(file, 'meeting');
      return;
    }

    // PDF Flow
    addMessage(`Uploading PDF: ${file.name}...`, 'user');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('/pdf-translation', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) throw new Error('PDF processing failed');
      const data = await response.json();
      const translatedText = data.content;
      const summary = data.summary;
      const filename = data.filename;

      console.log("[App.jsx] Full Response Data:", data);
      console.log("[App.jsx] Extracted Summary:", summary);

      // 1. Show Summary as a separate chat message (if exists)
      if (summary) {
        addMessage(`📄 **文件摘要**：\n\n${summary}`, 'system');
      } else {
        addMessage("📄 文件翻譯完成（未能生成摘要）。", 'system');
      }

      // 2. Show Translation Result as a "file-result" block
      const fileDisplayHeader = `【翻譯內容預覽】\n\n`;
      addMessage(fileDisplayHeader + translatedText, 'system', 'file-result');

      // 3. Prepare content for download (Translation ONLY)
      let downloadContent = translatedText;

      // Trigger Download automatically
      const blob = new Blob([downloadContent], { type: 'text/plain' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

    } catch (error) {
      console.error("PDF Translate Error:", error);
      addMessage("Failed to translate PDF.", 'system');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50 text-gray-900 font-sans">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between shadow-sm z-10">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold">A</div>
          <h1 className="font-semibold text-lg tracking-tight">AI Assistant v2.0 (Meeting Mode)</h1>
        </div>
        <div>
          {isLoading && <span className="text-sm text-blue-600 animate-pulse font-medium">Processing...</span>}
        </div>
      </header>

      {/* Chat Area */}
      <MessageList messages={messages} isLoading={isLoading} />

      {/* Input Area */}
      <InputArea
        onSendMessage={handleSendMessage}
        onSendAudio={handleSendAudio}
        onSendFile={handleSendFile}
      />
    </div>
  );
}

export default App;
