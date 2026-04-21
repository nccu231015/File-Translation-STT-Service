/**
 * doc-qa.ts
 *
 * Client-side API utility for Document Knowledge (RAG) Q&A.
 * Calls backend /document-chat, which proxies to the n8n PDF RAG webhook.
 *
 * Contract:
 *   POST /document-chat  →  { response: string }
 */

const getBackendUrl = () => {
    if (typeof window !== 'undefined') {
        return `http://${window.location.hostname}:8000`;
    }
    return 'http://172.16.2.68:8000';
};

export interface DocQAResponse {
    response: string;
}

export interface DocIngestResponse {
    status: string;
    filename: string;
    message?: string;
}

/**
 * Send a question to the document KM agent.
 * Returns the cleaned answer text from the PDF RAG pipeline.
 */
export async function askDocumentQA(question: string): Promise<DocQAResponse> {
    const url = `${getBackendUrl()}/document-chat`;
    const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
    });
    if (!resp.ok) {
        throw new Error(`Document chat API error: ${resp.status}`);
    }
    return resp.json();
}

/**
 * Upload a PDF file to be ingested into the ChromaDB knowledge base via n8n.
 * Uses multipart/form-data – do NOT set Content-Type manually (browser handles boundary).
 */
export async function uploadDocument(file: File): Promise<DocIngestResponse> {
    const url = `${getBackendUrl()}/document-ingest`;
    const formData = new FormData();
    formData.append('file', file);
    const resp = await fetch(url, {
        method: 'POST',
        body: formData,
    });
    if (!resp.ok) {
        throw new Error(`Document ingest API error: ${resp.status}`);
    }
    return resp.json();
}
