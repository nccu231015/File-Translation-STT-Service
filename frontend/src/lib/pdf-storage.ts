/**
 * pdf-storage.ts
 *
 * IndexedDB helper for persisting PDF blobs across page refreshes.
 * localStorage can only hold strings and has a ~5MB limit.
 * IndexedDB can store binary Blobs directly with no practical size limit.
 *
 * Key convention:
 *   `${recordId}_original`   → the user-uploaded source PDF
 *   `${recordId}_translated` → the translated PDF returned by the backend
 */

const DB_NAME = 'pdf_blob_store';
const STORE_NAME = 'blobs';
const DB_VERSION = 1;

function openDB(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION);

        request.onupgradeneeded = (e) => {
            const db = (e.target as IDBOpenDBRequest).result;
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                db.createObjectStore(STORE_NAME);
            }
        };

        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

/** Save a Blob/File under `key`. Overwrites if the key already exists. */
export async function saveBlob(key: string, blob: Blob): Promise<void> {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        tx.objectStore(STORE_NAME).put(blob, key);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

/** Load a Blob by `key`. Returns null if not found. */
export async function loadBlob(key: string): Promise<Blob | null> {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readonly');
        const req = tx.objectStore(STORE_NAME).get(key);
        req.onsuccess = () => resolve((req.result as Blob) ?? null);
        req.onerror = () => reject(req.error);
    });
}

/** Delete a Blob by `key`. No-op if not found. */
export async function deleteBlob(key: string): Promise<void> {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        tx.objectStore(STORE_NAME).delete(key);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}
