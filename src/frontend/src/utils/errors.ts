/**
 * Error handling utilities
 */

export class AppError extends Error {
    constructor(
        message: string,
        public code?: string,
        public details?: unknown
    ) {
        super(message);
        this.name = 'AppError';
    }
}

export class ApiError extends AppError {
    constructor(
        message: string,
        public status?: number,
        code?: string,
        details?: unknown
    ) {
        super(message, code, details);
        this.name = 'ApiError';
    }
}

export function isApiError(error: unknown): error is ApiError {
    return error instanceof ApiError;
}

export function isAppError(error: unknown): error is AppError {
    return error instanceof AppError;
}

export function formatError(error: unknown): string {
    if (isApiError(error)) {
        return `API Error (${error.status}): ${error.message}`;
    }
    
    if (isAppError(error)) {
        return `App Error: ${error.message}`;
    }
    
    if (error instanceof Error) {
        return error.message;
    }
    
    return 'An unknown error occurred';
}

export function logError(error: unknown, context?: string): void {
    const errorMessage = formatError(error);
    const logMessage = context 
        ? `[${context}] ${errorMessage}`
        : errorMessage;
    
    console.error(logMessage, error);
}
