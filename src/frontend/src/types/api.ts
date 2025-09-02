/**
 * API-related types and interfaces
 */

import type { Thread } from './chat';
import type { SearchConfig } from './config';
import type { ApiResponse } from './common';

// API Request/Response types
export interface ChatRequest {
    query: string;
    request_id: string;
    chat_history: Array<{
        role: string;
        content: Array<{
            text: string;
            type: string;
        }>;
    }>;
    config: SearchConfig;
}

export interface ChatResponse extends ApiResponse<Thread> {}

export interface UploadResponse extends ApiResponse<{
    filename: string;
    size: number;
    upload_id: string;
}> {}

export interface IndexListResponse extends ApiResponse<string[]> {}

export interface ProcessDocumentRequest {
    files: File[];
    index_name: string;
}

export interface ProcessDocumentResponse extends ApiResponse<{
    processed_files: string[];
    failed_files: string[];
}> {}

// API Error types
export interface ApiError {
    message: string;
    code?: string;
    details?: unknown;
}

// Event Stream types
export interface StreamMessage {
    event: string;
    data: string;
}

export type StreamMessageHandler = (message: StreamMessage) => void;
export type StreamErrorHandler = (error: Error) => void;
