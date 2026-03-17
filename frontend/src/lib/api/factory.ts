/**
 * factory.ts
 *
 * Client-side API utility for Factory Smart Q&A.
 * Uses relative paths — Next.js rewrites in next.config.ts proxy the request
 * to the backend, so no CORS issues and no hardcoded IPs needed.
 */

export interface FactoryResponse {
    response: string;
    session_id: string;
}

export interface SessionSummary {
    session_id: string;
    title: string;
    created_at: string;
    updated_at: string;
    message_count: number;
}

export interface SessionMessage {
    role: 'user' | 'assistant';
    content: string;
    ts: string;
}

export interface SessionDetail {
    session_id: string;
    title: string;
    messages: SessionMessage[];
    created_at: string;
    updated_at: string;
}

export const askFactory = async (text: string, session_id?: string): Promise<FactoryResponse> => {
    const response = await fetch(`/factory-chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, session_id }),
    });

    if (!response.ok) {
        const errText = await response.text();
        throw new Error(`Factory API failed: ${response.status} ${errText}`);
    }

    return response.json();
};

export const listFactorySessions = async (): Promise<SessionSummary[]> => {
    const res = await fetch(`/factory-sessions`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.sessions ?? [];
};

export const getFactorySession = async (session_id: string): Promise<SessionDetail | null> => {
    const res = await fetch(`/factory-sessions/${session_id}`);
    if (!res.ok) return null;
    return res.json();
};

export const deleteFactorySession = async (session_id: string): Promise<boolean> => {
    const res = await fetch(`/factory-sessions/${session_id}`, { method: 'DELETE' });
    return res.ok;
};
