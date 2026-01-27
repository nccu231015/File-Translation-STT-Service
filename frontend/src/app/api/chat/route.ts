
import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';
export const maxDuration = 1800; // 30 minutes

export async function POST(req: NextRequest) {
    try {
        const body = await req.json();

        // Forward to Backend
        const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

        console.log(`[Chat API] Forwarding request to ${BACKEND_URL}/chat`);

        const response = await fetch(`${BACKEND_URL}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(body),
        });

        if (!response.ok) {
            const errorText = await response.text();
            return NextResponse.json(
                { error: `Backend processing failed: ${errorText}` },
                { status: response.status }
            );
        }

        const data = await response.json();
        return NextResponse.json(data);

    } catch (error: any) {
        console.error('[Chat API] Forwarding failed:', error);
        return NextResponse.json(
            { error: 'Internal Server Error during Chat forwarding', details: error.message },
            { status: 500 }
        );
    }
}
