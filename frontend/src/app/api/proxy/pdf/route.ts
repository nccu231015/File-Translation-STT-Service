import { NextRequest, NextResponse } from 'next/server';

export const config = {
    api: {
        bodyParser: false,
    },
};

const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

export async function POST(request: NextRequest) {
    try {
        const formData = await request.formData();

        const backendResponse = await fetch(`${BACKEND_URL}/pdf-translation`, {
            method: 'POST',
            body: formData,
            // 讓 fetch 自動加入帶有 boundary 的 Content-Type
        });

        const data = await backendResponse.json();

        return NextResponse.json(data, { status: backendResponse.status });
    } catch (error: unknown) {
        console.error('[/api/proxy/pdf] Error:', error);
        const message = error instanceof Error ? error.message : String(error);
        return NextResponse.json(
            { error: 'PDF proxy failed', detail: message },
            { status: 500 }
        );
    }
}
