/**
 * doc-qa.ts
 *
 * Client-side API utility for Document Knowledge (RAG) Q&A.
 * Calls backend /document-chat, which proxies to the n8n PDF RAG webhook.
 *
 * Contract:
 *   POST   /document-chat                  →  { response: string, session_id: string }
 *   GET    /document-sessions              →  { sessions: SessionSummary[] }
 *   GET    /document-sessions/:id          →  SessionDetail
 *   DELETE /document-sessions/:id          →  { message: string }
 *   POST   /document-ingest (multipart + optional session_id) →  { status, filename, session_id }
 *   GET    /document-files?session_id=     →  { files }
 *   DELETE /document-files/:name?session_id=
 */

const getBackendUrl = () => {
    if (typeof window !== 'undefined') {
        return `http://${window.location.hostname}:8000`;
    }
    return 'http://172.16.2.68:8000';
};

export interface DocQAResponse {
    response: string;
    session_id: string;
}

export interface DocIngestResponse {
    status: string;
    filename: string;
    message?: string;
    /** Present when backend created a session for this upload, or echoed for an existing session */
    session_id?: string;
}

export interface DocSessionSummary {
    session_id: string;
    title: string;
    created_at: string;
    updated_at: string;
    message_count: number;
}

export interface DocSessionMessage {
    role: 'user' | 'assistant';
    content: string;
    ts: string;
}

export interface DocSessionDetail {
    session_id: string;
    title: string;
    messages: DocSessionMessage[];
    created_at: string;
    updated_at: string;
}

/**
 * Send a question to the document KM agent with optional session continuation.
 */
export async function askDocumentQA(question: string, session_id?: string): Promise<DocQAResponse> {
    const resp = await fetch(`${getBackendUrl()}/document-chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, session_id }),
    });
    if (!resp.ok) throw new Error(`Document chat API error: ${resp.status}`);
    return resp.json();
}

/** List all document KM sessions, newest first. */
export async function listDocSessions(): Promise<DocSessionSummary[]> {
    const res = await fetch(`${getBackendUrl()}/document-sessions`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.sessions ?? [];
}

/** Get a specific session with full message history. */
export async function getDocSession(session_id: string): Promise<DocSessionDetail | null> {
    const res = await fetch(`${getBackendUrl()}/document-sessions/${session_id}`);
    if (!res.ok) return null;
    return res.json();
}

/** Delete a session by ID. */
export async function deleteDocSession(session_id: string): Promise<boolean> {
    const res = await fetch(`${getBackendUrl()}/document-sessions/${session_id}`, { method: 'DELETE' });
    return res.ok;
}

/**
 * Upload a PDF file to be ingested into the ChromaDB knowledge base via n8n.
 * Uses multipart/form-data – do NOT set Content-Type manually (browser handles boundary).
 * When `session_id` is omitted, the backend creates a new chat session for this upload.
 */
export async function uploadDocument(file: File, session_id?: string | null): Promise<DocIngestResponse> {
    const formData = new FormData();
    formData.append('file', file);
    if (session_id) {
        formData.append('session_id', session_id);
    }
    const resp = await fetch(`${getBackendUrl()}/document-ingest`, {
        method: 'POST',
        body: formData,
    });
    if (!resp.ok) throw new Error(`Document ingest API error: ${resp.status}`);
    return resp.json();
}

export interface DocFileRecord {
    filename: string;
    size: number;
    uploaded_at: string;
}

/** List ingested file records for one document-KM chat session. */
export async function listDocFiles(session_id: string | null): Promise<DocFileRecord[]> {
    if (!session_id) return [];
    const q = new URLSearchParams({ session_id });
    const res = await fetch(`${getBackendUrl()}/document-files?${q.toString()}`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.files ?? [];
}

/** Remove a file record for a session from Redis (does not delete from ChromaDB). */
export async function deleteDocFile(filename: string, session_id: string): Promise<boolean> {
    const q = new URLSearchParams({ session_id });
    const res = await fetch(
        `${getBackendUrl()}/document-files/${encodeURIComponent(filename)}?${q.toString()}`,
        { method: 'DELETE' },
    );
    return res.ok;
}

