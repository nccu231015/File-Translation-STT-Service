
export interface STTResponse {
    transcription: {
        text: string;
        segments?: any[]; // Keep flexible if we add segments later
        language?: string;
    };
    analysis: {
        summary: string;
        decisions: string[];
        action_items: string[];
    };
    llm_response?: string; // For chat mode
    file_download?: {
        filename: string;
        content: string;
    };
}

export const analyzeMeetingAudio = async (file: File): Promise<STTResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('mode', 'meeting');

    const response = await fetch('/api/stt', {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        throw new Error('STT Processing failed');
    }

    return response.json();
};
