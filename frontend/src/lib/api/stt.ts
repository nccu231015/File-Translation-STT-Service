
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
    /** Bilingual segments for the viewer */
    translated_segments?: Array<{
        start: number;
        end: number;
        original: string;
        translated: string;
    }>;
}

export const analyzeMeetingAudio = async (file: File): Promise<STTResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('mode', 'meeting');

    // DIRECT CALL to backend to bypass Next.js proxy/body-size issues
    const BACKEND_URL = "http://172.16.2.68:8000";
    try {
        const response = await fetch(`${BACKEND_URL}/stt`, {
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

export const transcribeAudio = async (file: File): Promise<{transcription: {text: string}}> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('mode', 'stt_only');

    const BACKEND_URL = "http://172.16.2.68:8000";
    try {
        const response = await fetch(`${BACKEND_URL}/stt`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`STT Transcription failed: ${response.status} ${errorText}`);
        }

        return response.json();
    } catch (error) {
        console.error("Transcription call failed:", error);
        throw error;
    }
};
