
export const translatePDF = async (file: File, sourceLang: string, targetLang: string) => {
    const formData = new FormData();
    formData.append('file', file);
    // Backend relies on internal logic or defaults, but if we need to pass languages:
    // formData.append('source_lang', sourceLang);
    // formData.append('target_lang', targetLang); 

    // In our current backend implementation (from memory), /upload path handles everything.
    // But our proxy is set to /api/* -> Backend /*
    // So we call /api/pdf-translation which maps to Backend /pdf-translation ideally.
    // Wait, let's check backend routes.
    // Assuming the backend has a specific endpoint. 
    // Based on "File Translation" task, it likely expects a file upload.

    const response = await fetch('/api/pdf-translation', {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        throw new Error('PDF Translation failed');
    }

    return response.json();
};
