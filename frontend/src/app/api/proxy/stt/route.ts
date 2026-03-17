import { NextRequest, NextResponse } from 'next/server';

// 停用 Next.js 的 body parser，讓原始 stream 直接透傳
export const config = {
    api: {
        bodyParser: false,
    },
};

const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

export async function POST(request: NextRequest) {
    try {
        // 直接將原始的 FormData stream 轉送給後端
        const formData = await request.formData();

        const backendResponse = await fetch(`${BACKEND_URL}/stt`, {
            method: 'POST',
            body: formData,
            // 注意：讓 fetch 自動設定帶有 boundary 的 Content-Type
            // 不要手動設定 Content-Type！
        });

        const data = await backendResponse.json();

        return NextResponse.json(data, { status: backendResponse.status });
    } catch (error: unknown) {
        console.error('[/api/proxy/stt] Error:', error);
        const message = error instanceof Error ? error.message : String(error);
        return NextResponse.json(
            { error: 'STT proxy failed', detail: message },
            { status: 500 }
        );
    }
}
