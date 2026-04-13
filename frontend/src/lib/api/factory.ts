/**
 * factory.ts
 *
 * Client-side API utility for Factory Smart Q&A.
 * DIRECT CALL to backend to bypass Next.js proxy timeout issues (60s limit).
 *
 * ─── API Contract (stable, backend-agnostic) ───────────────────────────────
 * POST /factory-chat  →  FactoryResponse
 *   { response: string, session_id: string, chart_config?: ChartConfig }
 *
 * When the backend migrates to n8n, only `getBackendUrl()` needs to change.
 * The ChartConfig schema is the same whether emitted by Python or n8n.
 * ────────────────────────────────────────────────────────────────────────────
 */

// Helper to determine the backend URL dynamically (direct port 8000 bypass)
// ⚠️  n8n migration: replace the return values below with your n8n webhook URL
const getBackendUrl = () => {
    if (typeof window !== 'undefined') {
        return `http://${window.location.hostname}:8000`;
    }
    return "http://172.16.2.68:8000";
};

// ── Chart config types (Recharts-compatible) ─────────────────────────────────

export interface ChartDataset {
    type: 'bar' | 'line' | 'heatmap';
    label: string;
    cate?: string;          // heatmap: fault category
    data: (number | null)[];
    yAxisID?: string;       // 'y_quantity' | 'y_defect_rate'
    backgroundColor?: string;
    borderColor?: string;
    borderWidth?: number;
    fill?: boolean;
    tension?: number;       // line smoothing 0–1
}

export interface YAxisConfig {
    label: string;
    position: 'left' | 'right';
}

export interface ChartConfig {
    chart_type: 'bar_line_combo' | 'multi_line' | 'heatmap';
    title: string;
    labels: string[];       // X-axis labels (time periods or equipment names)
    datasets: ChartDataset[];
    yAxes?: Record<string, YAxisConfig>; // only for bar_line_combo
    max_value?: number;                  // heatmap: normalisation ceiling
}

export interface FactoryResponse {
    response: string;
    session_id: string;
    chart_config?: ChartConfig;  // optional – present only for Q5 / Q7 queries
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
    const response = await fetch(`${getBackendUrl()}/factory-chat`, {
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
    const res = await fetch(`${getBackendUrl()}/factory-sessions`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.sessions ?? [];
};

export const getFactorySession = async (session_id: string): Promise<SessionDetail | null> => {
    const res = await fetch(`${getBackendUrl()}/factory-sessions/${session_id}`);
    if (!res.ok) return null;
    return res.json();
};

export const deleteFactorySession = async (session_id: string): Promise<boolean> => {
    const res = await fetch(`${getBackendUrl()}/factory-sessions/${session_id}`, { method: 'DELETE' });
    return res.ok;
};
