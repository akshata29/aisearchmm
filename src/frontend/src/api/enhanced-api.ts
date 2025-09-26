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
import type { 
    FeedbackSubmissionData, 
    FeedbackEntry, 
    FeedbackListResponse 
} from './models';
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

// Ensure a per-browser session id exists and return session-related headers.
function ensureSession() {
    try {
        if (!localStorage.getItem('session_id')) {
            const id = (window.crypto && (window.crypto as any).randomUUID)
                ? (window.crypto as any).randomUUID()
                : `sid-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
            localStorage.setItem('session_id', id);
        }
    } catch (e) {
        // best-effort; ignore
        if (!localStorage.getItem('session_id')) {
            localStorage.setItem('session_id', `sid-${Date.now()}`);
        }
    }
}

export function getSessionHeaders(): Record<string, string> {
    ensureSession();
    const sessionId = localStorage.getItem('session_id') || '';
    const useMi = localStorage.getItem('use_managed_identity') === 'true' ? 'true' : 'false';
    const useHistory = localStorage.getItem('use_chat_history') === 'true' ? 'true' : 'false';
    return {
        'X-Session-Id': sessionId,
        'X-Use-Managed-Identity': useMi,
        'X-Use-Chat-History': useHistory,
    };
}

// Expose helper for legacy components or non-module users in the app
try {
    (window as any).getSessionHeaders = getSessionHeaders;
} catch (e) {
    // ignore in non-browser or restricted environments
}

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
        const mergedHeaders = {
            ...API_CONFIG.headers,
            ...getSessionHeaders(),
            ...(options.headers || {}),
        };

        const response = await fetch(endpoint, {
            ...API_CONFIG,
            ...options,
            headers: mergedHeaders,
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
        // Create AbortController for timeout handling
        const controller = new AbortController();
        
        // Set up timeout - use PROCESSING timeout for chat as it involves complex operations
        const timeoutId = setTimeout(() => {
            controller.abort();
        }, TIMEOUTS.PROCESSING);
        
        // Enhanced error handler that clears timeout and handles abort
        const enhancedErrorHandler = (error: any) => {
            clearTimeout(timeoutId);
            
            if (controller.signal.aborted) {
                const timeoutError = new Error('Chat request timed out. Large document processing may need more time.');
                logError(timeoutError, 'Chat API Timeout');
                onError?.(timeoutError);
            } else {
                logError(error, 'Chat API Stream');
                onError?.(new Error('Chat stream error'));
            }
        };
        
        // Enhanced message handler that clears timeout on END event
        const enhancedMessageHandler = (message: any) => {
            if (message.event === '[END]') {
                clearTimeout(timeoutId);
            }
            onMessage(message);
        };

        // Single fetchEventSource call that includes session headers so backend can pick auth mode
        await fetchEventSource(API_ENDPOINTS.CHAT, {
            openWhenHidden: true,
            method: 'POST',
            headers: {
                ...API_CONFIG.headers,
                ...getSessionHeaders(),
            },
            body: JSON.stringify({
                query: message,
                request_id: requestId,
                chatThread,
                ...request
            }),
            signal: controller.signal,
            onmessage: enhancedMessageHandler,
            onerror: enhancedErrorHandler,
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

        // Use AbortController for timeout handling with extended timeout for uploads
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), TIMEOUTS.UPLOAD);

        try {
            const response = await fetch(API_ENDPOINTS.UPLOAD, {
                method: 'POST',
                body: formData,
                credentials: 'same-origin',
                headers: getSessionHeaders(),
                signal: controller.signal,
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                throw new ApiError('Upload failed', response.status, `HTTP_${response.status}`);
            }

            return await response.json();
        } catch (fetchError) {
            clearTimeout(timeoutId);
            
            if (fetchError instanceof DOMException && fetchError.name === 'AbortError') {
                throw new ApiError('Upload timeout - file too large or network slow', 408, 'UPLOAD_TIMEOUT');
            }
            
            throw fetchError;
        }
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

        // Use AbortController for timeout handling with extended timeout for processing
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), TIMEOUTS.PROCESSING);

        try {
            const response = await fetch(API_ENDPOINTS.PROCESS_DOCUMENT, {
                method: 'POST',
                body: formData,
                credentials: 'same-origin',
                headers: getSessionHeaders(),
                signal: controller.signal,
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                throw new ApiError('Document processing failed', response.status, `HTTP_${response.status}`);
            }

            return await response.json();
        } catch (fetchError) {
            clearTimeout(timeoutId);
            
            if (fetchError instanceof DOMException && fetchError.name === 'AbortError') {
                throw new ApiError('Document processing timeout - large document may need more time', 408, 'PROCESSING_TIMEOUT');
            }
            
            throw fetchError;
        }
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
            headers: {
                ...API_CONFIG.headers,
                ...getSessionHeaders(),
            },
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

/**
 * Submit user feedback for a response
 */
export async function submitFeedback(feedbackData: FeedbackSubmissionData): Promise<{ status: string; feedback_id: string; operation_id: string }> {
    try {
        return await apiRequest(API_ENDPOINTS.FEEDBACK_SUBMIT, {
            method: 'POST',
            body: JSON.stringify(feedbackData),
        });
    } catch (error) {
        logError(error, 'Submit Feedback API');
        throw error;
    }
}

/**
 * Get paginated list of feedback entries (admin only)
 */
export async function getFeedbackList(params?: {
    page?: number;
    page_size?: number;
    search?: string;
    feedback_type?: string;
    reviewed?: boolean;
    sort_by?: string;
    sort_order?: string;
}): Promise<FeedbackListResponse> {
    try {
        const queryParams = new URLSearchParams();
        if (params) {
            Object.entries(params).forEach(([key, value]) => {
                if (value !== undefined && value !== null) {
                    queryParams.append(key, value.toString());
                }
            });
        }
        
        const url = queryParams.toString() 
            ? `${API_ENDPOINTS.FEEDBACK_LIST}?${queryParams}`
            : API_ENDPOINTS.FEEDBACK_LIST;
            
        return await apiRequest<FeedbackListResponse>(url);
    } catch (error) {
        logError(error, 'Get Feedback List API');
        throw error;
    }
}

/**
 * Get detailed feedback entry (admin only)
 */
export async function getFeedbackDetail(feedbackId: string): Promise<{ status: string; data: FeedbackEntry; operation_id: string }> {
    try {
        return await apiRequest(`${API_ENDPOINTS.FEEDBACK_DETAIL}/${feedbackId}`);
    } catch (error) {
        logError(error, 'Get Feedback Detail API');
        throw error;
    }
}

/**
 * Update feedback entry (admin only)
 */
export async function updateFeedback(feedbackId: string, updateData: {
    admin_notes?: string;
    is_reviewed?: boolean;
    response_text?: string;
    modified_by?: string;
}): Promise<{ status: string; data: FeedbackEntry; operation_id: string }> {
    try {
        return await apiRequest(`${API_ENDPOINTS.FEEDBACK_DETAIL}/${feedbackId}`, {
            method: 'PUT',
            body: JSON.stringify(updateData),
        });
    } catch (error) {
        logError(error, 'Update Feedback API');
        throw error;
    }
}
