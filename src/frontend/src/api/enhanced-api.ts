/**
 * Enhanced API module with better error handling and type safety
 */

import { fetchEventSource } from '@microsoft/fetch-event-source';
import type { 
    ChatRequest, 
    IndexListResponse, 
    UploadResponse,
    ProcessDocumentRequest,
    ProcessDocumentResponse,
    StreamMessageHandler,
    StreamErrorHandler
} from '@/types/api';
import type { SearchConfig } from '@/types/config';
import { ApiError, logError } from '@/utils/errors';
import { API_ENDPOINTS, TIMEOUTS } from '@/constants';

/**
 * Base API configuration
 */
const API_CONFIG = {
    headers: {
        'Content-Type': 'application/json',
    },
    credentials: 'same-origin' as RequestCredentials,
};

/**
 * Enhanced fetch wrapper with error handling and timeout
 */
async function apiRequest<T>(
    endpoint: string, 
    options: RequestInit = {},
    timeout = TIMEOUTS.API_REQUEST
): Promise<T> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
        const response = await fetch(endpoint, {
            ...API_CONFIG,
            ...options,
            signal: controller.signal,
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
            const errorText = await response.text();
            let errorData: unknown = {};
            
            try {
                errorData = errorText ? JSON.parse(errorText) : {};
            } catch {
                errorData = { error: errorText };
            }

            throw new ApiError(
                `API request failed: ${response.statusText}`,
                response.status,
                `HTTP_${response.status}`,
                errorData
            );
        }

        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            return await response.json();
        }

        return await response.text() as unknown as T;
    } catch (error) {
        clearTimeout(timeoutId);
        
        if (error instanceof ApiError) {
            throw error;
        }

        if (error instanceof DOMException && error.name === 'AbortError') {
            throw new ApiError('Request timeout', 408, 'TIMEOUT');
        }

        throw new ApiError(
            error instanceof Error ? error.message : 'Network error',
            0,
            'NETWORK_ERROR',
            error
        );
    }
}

/**
 * Send chat message with streaming response
 */
export async function sendChatApi(
    message: string,
    requestId: string,
    chatThread: Array<{
        role: string;
        content: Array<{ text: string; type: string }>;
    }>,
    config: SearchConfig,
    onMessage: StreamMessageHandler,
    onError?: StreamErrorHandler
): Promise<void> {
    const request: Omit<ChatRequest, 'query' | 'request_id' | 'chat_history'> = { config };
    
    try {
        await fetchEventSource(API_ENDPOINTS.CHAT, {
            openWhenHidden: true,
            method: 'POST',
            headers: API_CONFIG.headers,
            body: JSON.stringify({
                query: message,
                request_id: requestId,
                chatThread,
                ...request
            }),
            onmessage: onMessage,
            onerror: (error) => {
                logError(error, 'Chat API Stream');
                onError?.(new Error('Chat stream error'));
            },
        });
    } catch (error) {
        logError(error, 'Chat API');
        throw new ApiError(
            'Failed to send chat message',
            0,
            'CHAT_ERROR',
            error
        );
    }
}

/**
 * Get list of available search indexes
 */
export async function listIndexes(): Promise<string[]> {
    try {
        const response = await apiRequest<IndexListResponse>(API_ENDPOINTS.LIST_INDEXES);
        return response.data || [];
    } catch (error) {
        logError(error, 'List Indexes API');
        throw error;
    }
}

/**
 * Get citation document content
 */
export async function getCitationDocument(fileName: string): Promise<unknown> {
    try {
        return await apiRequest(API_ENDPOINTS.GET_CITATION_DOC, {
            method: 'POST',
            body: JSON.stringify({ fileName }),
        });
    } catch (error) {
        logError(error, 'Get Citation Document API');
        throw error;
    }
}

/**
 * Upload files to the system
 */
export async function uploadFiles(files: File[]): Promise<UploadResponse> {
    try {
        const formData = new FormData();
        files.forEach((file, index) => {
            formData.append(`file_${index}`, file);
        });

        const response = await fetch(API_ENDPOINTS.UPLOAD, {
            method: 'POST',
            body: formData,
            credentials: 'same-origin',
        });

        if (!response.ok) {
            throw new ApiError(
                'Upload failed',
                response.status,
                `HTTP_${response.status}`
            );
        }

        return await response.json();
    } catch (error) {
        logError(error, 'Upload Files API');
        throw error;
    }
}

/**
 * Check upload status
 */
export async function getUploadStatus(uploadId: string): Promise<unknown> {
    try {
        return await apiRequest(`${API_ENDPOINTS.UPLOAD_STATUS}?upload_id=${uploadId}`);
    } catch (error) {
        logError(error, 'Upload Status API');
        throw error;
    }
}

/**
 * Process uploaded documents
 */
export async function processDocuments(request: ProcessDocumentRequest): Promise<ProcessDocumentResponse> {
    try {
        const formData = new FormData();
        formData.append('index_name', request.index_name);
        
        request.files.forEach((file, index) => {
            formData.append(`file_${index}`, file);
        });

        const response = await fetch(API_ENDPOINTS.PROCESS_DOCUMENT, {
            method: 'POST',
            body: formData,
            credentials: 'same-origin',
        });

        if (!response.ok) {
            throw new ApiError(
                'Document processing failed',
                response.status,
                `HTTP_${response.status}`
            );
        }

        return await response.json();
    } catch (error) {
        logError(error, 'Process Documents API');
        throw error;
    }
}

/**
 * Delete search index with improved error handling
 */
export async function deleteIndex(): Promise<unknown> {
    const tryCall = async (path: string) => {
        const response = await fetch(path, {
            method: 'POST',
            headers: API_CONFIG.headers,
            body: JSON.stringify({ cascade: true }),
        });
        
        const responseText = await response.text();
        let responseData: unknown = {};
        
        try {
            responseData = responseText ? JSON.parse(responseText) : {};
        } catch {
            responseData = { error: responseText };
        }
        
        return { response, responseData };
    };

    try {
        // Prefer namespaced route, fall back to legacy route
        let { response, responseData } = await tryCall('/api/delete_index')
            .catch(() => ({ response: undefined as any, responseData: { error: 'network' } }));
        
        if (!response || response.status === 404 || response.status === 405) {
            ({ response, responseData } = await tryCall('/delete_index'));
        }
        
        if (!response.ok) {
            throw new ApiError(
                (responseData as any)?.error || `Failed to delete index`,
                response.status,
                `HTTP_${response.status}`,
                responseData
            );
        }
        
        return responseData;
    } catch (error) {
        logError(error, 'Delete Index API');
        throw error;
    }
}

/**
 * Get admin data
 */
export async function getAdminData(): Promise<unknown> {
    try {
        return await apiRequest(API_ENDPOINTS.ADMIN);
    } catch (error) {
        logError(error, 'Admin API');
        throw error;
    }
}
