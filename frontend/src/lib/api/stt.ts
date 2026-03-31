
/** n8n 微服務回傳格式（對應 POST /api/v1/stt/process） */

/** N8N Microservice response format (corresponds to POST /api/v1/stt/process) */
export interface N8nSTTResponse {
    status: string;
    mode: string;
    transcript: string;
    language?: string;
    processing_time?: number;
    summary?: string;
    meeting_objective?: string;
    decisions?: string[];
    action_items?: any[];
    attendees?: string[];
    llm_options_used?: Record<string, number>;
}

export const analyzeMeetingAudio = async (file: File): Promise<N8nSTTResponse> => {
    // ─── Route to n8n Microservice Webhook ─────────────────────────────────────
    // n8n forwards the file to Python /api/v1/stt/process, 
    // and the Respond to Webhook node returns the processed result.
    const N8N_WEBHOOK_URL = "http://172.16.2.68:5678/webhook/ff6bacb9-5b6e-486e-9929-5a735090b28d";

    const formData = new FormData();
    formData.append('file', file);
    // Note: mode/temperature/num_predict are pre-configured in the n8n HTTP Request node.
    // The frontend only needs to send the file (client tunes params via n8n).

    try {
        const response = await fetch(N8N_WEBHOOK_URL, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`STT Processing failed: ${response.status} ${errorText}`);
        }

        return response.json();
    } catch (error) {
        console.error("n8n STT call failed:", error);
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
