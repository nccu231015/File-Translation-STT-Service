
import { NextRequest, NextResponse } from 'next/server';

// Prevent Next.js from caching this route
export const dynamic = 'force-dynamic';

// Adjust max duration if deployed on Vercel/etc. (not needed for local/docker usually but good practice)
export const maxDuration = 1800; // 30 minutes

export async function POST(req: NextRequest) {
    try {
        const formData = await req.formData();

        // Forward to Backend
        // Using 127.0.0.1:8000 assuming backend is reachable there. 
        // In Docker-compose, if frontend is in container, it should be 'http://app:8000'
        // But since you are running 'npm run dev', localhost 8000 is correct.
        const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

        console.log(`[API Route] Forwarding request to ${BACKEND_URL}/pdf-translation`);

        const response = await fetch(`${BACKEND_URL}/pdf-translation`, {
            method: 'POST',
            body: formData,
            // No headers needed, fetch automatically sets multipart/form-data boundary
        });

        if (!response.ok) {
            console.error(`[API Route] Backend error: ${response.status} ${response.statusText}`);
            const errorText = await response.text();
            return NextResponse.json(
                { error: `Backend processing failed: ${errorText}` },
                { status: response.status }
            );
        }

        // Backend now returns a PDF file (binary), not JSON
        // Get the blob and forward it to the client
        const blob = await response.blob();

        // Get the filename from Content-Disposition header if available
        const contentDisposition = response.headers.get('content-disposition');
        let filename = 'translated.pdf';
        if (contentDisposition) {
            const match = contentDisposition.match(/filename="?(.+?)"?$/);
            if (match) filename = match[1];
        }

        return new NextResponse(blob, {
            status: 200,
            headers: {
                'Content-Type': 'application/pdf',
                'Content-Disposition': `attachment; filename="${filename}"`,
            },
        });

    } catch (error: any) {
        console.error('[API Route] Forwarding failed:', error);
        return NextResponse.json(
            { error: 'Internal Server Error during forwarding', details: error.message },
            { status: 500 }
        );
    }
}
