
export interface STTResponse {
    transcription: {
        text: string;
        segments?: any[];
        language?: string;
    };
    analysis: {
        summary: string;
        decisions: string[];
        action_items: string[];
    };
    llm_response?: string;
    file_download?: {
        filename: string;
        content?: string;
        content_base64?: string;
        mime_type?: string;
    };
    /** Bilingual transcript Word document (base64 encoded) */
    transcript_download?: {
        filename: string;
        content_base64?: string;
        mime_type?: string;
    };
}

export const analyzeMeetingAudio = async (file: File): Promise<STTResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('mode', 'meeting');

    // Uses relative path — Next.js rewrites in next.config.ts proxy to backend
    try {
        const response = await fetch(`/stt`, {
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
