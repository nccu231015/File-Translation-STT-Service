/**
 * factory.ts
 *
 * Client-side API utility for Factory Smart Q&A.
 * Follows the pattern used by translation.ts and stt.ts.
 */

const getApiUrl = () => process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface FactoryResponse {
    response: string;
}

export const askFactory = async (text: string): Promise<FactoryResponse> => {
    const response = await fetch(`${getApiUrl()}/factory-chat`, {
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
