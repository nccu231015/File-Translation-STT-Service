/**
 * factory.ts
 *
 * Client-side API utility for Factory Smart Q&A.
 * Uses relative paths — Next.js rewrites in next.config.ts proxy the request
 * to the backend, so no CORS issues and no hardcoded IPs needed.
 */

export interface FactoryResponse {
    response: string;
}

export const askFactory = async (text: string): Promise<FactoryResponse> => {
    const response = await fetch(`/factory-chat`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ text }),
    });

    if (!response.ok) {
        const errText = await response.text();
        throw new Error(`Factory API failed: ${response.status} ${errText}`);
    }

    return response.json();
};
