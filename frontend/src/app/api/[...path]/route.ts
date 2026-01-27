
import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

async function handler(
    req: NextRequest,
    { params }: { params: Promise<{ path: string[] }> }
) {
    const { path } = await params;
    const pathString = path.join('/');
    const url = `${BACKEND_URL}/${pathString}`;
    const method = req.method;

    console.log(`[API Proxy] ${method} -> ${url}`);

    try {
        const headers = new Headers(req.headers);
        headers.delete('host');
        headers.delete('connection');
        headers.delete('upgrade-insecure-requests');

        // Forward body for non-GET/HEAD methods
        const body = ['GET', 'HEAD'].includes(method) ? undefined : await req.blob();

        const backendRes = await fetch(url, {
            method,
            headers,
            body,
            // @ts-ignore: Next.js extended fetch requires duplex for streaming bodies
            duplex: 'half',
        });

        const resHeaders = new Headers(backendRes.headers);
        // Be careful with CORS or other restricted headers if needed

        return new NextResponse(backendRes.body, {
            status: backendRes.status,
            statusText: backendRes.statusText,
            headers: resHeaders,
        });
    } catch (error) {
        console.error(`[API Proxy] Error:`, error);
        return NextResponse.json(
            { error: 'Backend connection failed' },
            { status: 502 }
        );
    }
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const DELETE = handler;
export const PATCH = handler;
