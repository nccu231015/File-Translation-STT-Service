
import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';
export const maxDuration = 1800; // 30 minutes

export async function POST(req: NextRequest) {
    try {
        const formData = await req.formData();

        // Forward to Backend
        // Using environment variable or default to localhost
        const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

        console.log(`[STT API] Forwarding request to ${BACKEND_URL}/stt`);

        const response = await fetch(`${BACKEND_URL}/stt`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            console.error(`[STT API] Backend error: ${response.status} ${response.statusText}`);
            const errorText = await response.text();
            return NextResponse.json(
                { error: `Backend processing failed: ${errorText}` },
                { status: response.status }
            );
        }

        const data = await response.json();
        return NextResponse.json(data);

    } catch (error: any) {
        console.error('[STT API] Forwarding failed:', error);
        return NextResponse.json(
            { error: 'Internal Server Error during STT forwarding', details: error.message },
            { status: 500 }
        );
    }
}
