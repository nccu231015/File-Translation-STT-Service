
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
        content?: string; // Legacy text content
        content_base64?: string; // Base64 encoded binary content
        mime_type?: string; // MIME type for download
    };
}

export const analyzeMeetingAudio = async (file: File): Promise<STTResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('mode', 'meeting');

    // Bypass Next.js API route to avoid Node.js fetch timeout
    // Using direct backend URL
    const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    try {
        const response = await fetch(`${API_URL}/stt`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`STT Processing failed: ${response.status} ${errorText}`);
        }

        return response.json();
    } catch (error) {
        console.error("Direct backend call failed:", error);
        throw error;
    }
};
