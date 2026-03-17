/**
 * translation.ts
 *
 * Client-side (browser) API utility for PDF translation.
 * Runs in the browser — calls the backend directly via NEXT_PUBLIC_API_URL.
 * No Next.js Route Handler involved → no timeout risk.
 *
 * Mirrors the pattern used by lib/api/stt.ts for voice processing.
 */

// Uses relative path — Next.js rewrites in next.config.ts proxy to backend.

export interface TranslationResponse {
    pdfBlob: Blob;
    docxBlob: Blob | null;
}

function _base64ToBlob(base64: string, mimeType: string): Blob {
    const binary = window.atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return new Blob([bytes], { type: mimeType });
}

export const translatePDF = async (
    file: File,
    targetLang: string = 'zh-TW',
    debug: boolean = false,
): Promise<TranslationResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('target_lang', targetLang);
    formData.append('debug', debug.toString());

    // DIRECT CALL to backend to bypass Next.js proxy/body-size issues
    const BACKEND_URL = "http://172.16.2.68:8000";
    const response = await fetch(`${BACKEND_URL}/pdf-translation`, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const errText = await response.text();
        throw new Error(`PDF Translation failed: ${response.status} ${errText}`);
    }

    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
        const data = await response.json();
        const pdfBlob = _base64ToBlob(data.pdf_base64, 'application/pdf');
        const docxBlob = data.docx_base64 ? _base64ToBlob(data.docx_base64, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') : null;
        return { pdfBlob, docxBlob };
    } else {
        // Fallback for direct PDF returning
        const blob = await response.blob();
        return { pdfBlob: new Blob([blob], { type: 'application/pdf' }), docxBlob: null };
    }
};
