
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
    translated_segments?: Array<{start: number; end: number; original: string; translated: string}>;
    llm_options_used?: Record<string, number>;
    /** Bilingual meeting minutes Word document */
    file_download?: {
        filename: string;
        content_base64: string;
        mime_type: string;
    };
    /** Bilingual transcript Word document */
    transcript_download?: {
        filename: string;
        content_base64: string;
        mime_type: string;
    };
}

export const analyzeMeetingAudio = async (file: File): Promise<N8nSTTResponse> => {
    // ─── Route to n8n Microservice Webhook ─────────────────────────────────────
    // n8n forwards the file to Python /api/v1/stt/process,
    // and the Respond to Webhook node returns the processed result.
    // mode / temperature / num_predict / model are hardcoded in the n8n HTTP Request node.
    // The frontend only sends the audio file.
    const N8N_WEBHOOK_URL = "http://172.16.2.68:5678/webhook/ff6bacb9-5b6e-486e-9929-5a735090b28d";

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(N8N_WEBHOOK_URL, {
            method: 'POST',
            body: formData,
        });

        // Read body as text first to avoid "Unexpected end of JSON" crash
        const rawText = await response.text();

        if (!response.ok) {
            throw new Error(`n8n STT failed [${response.status}]: ${rawText || '(empty response)'}`);
        }

        // Guard against empty body (e.g. n8n workflow not active or misconfigured node)
        if (!rawText || rawText.trim() === '') {
            throw new Error(
                'n8n returned an empty response. ' +
                'Check: (1) Workflow is Active, (2) HTTP Request node "Input Data Field Name" is set to "file".'
            );
        }

        try {
            return JSON.parse(rawText) as N8nSTTResponse;
        } catch {
            throw new Error(`n8n response is not valid JSON: ${rawText.slice(0, 300)}`);
        }
    } catch (error) {
        console.error("n8n STT call failed:", error);
        throw error;
    }
};

export const transcribeAudio = async (file: File): Promise<{transcription: {text: string}}> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('mode', 'stt_only');

    // Direct call to backend for short assistant transcription (bypasses n8n for speed)
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
