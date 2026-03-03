/**
 * translation.ts
 *
 * Client-side (browser) API utility for PDF translation.
 * Runs in the browser — calls the backend directly via NEXT_PUBLIC_API_URL.
 * No Next.js Route Handler involved → no timeout risk.
 *
 * Mirrors the pattern used by lib/api/stt.ts for voice processing.
 */

const getApiUrl = () =>
    process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const translatePDF = async (
    file: File,
    targetLang: string = 'zh-TW',
    debug: boolean = false,
): Promise<Blob> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('target_lang', targetLang);
    formData.append('debug', debug.toString());

    const response = await fetch(`${getApiUrl()}/pdf-translation`, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const errText = await response.text();
        throw new Error(`PDF Translation failed: ${response.status} ${errText}`);
    }

    const blob = await response.blob();
    return new Blob([blob], { type: 'application/pdf' });
};
