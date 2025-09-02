/**
 * Common types used across the application
 */

export type Coordinates = { x: number; y: number };

export type BoundingPolygon = Coordinates[];

export interface Citation {
    docId: string;
    content_id: string;
    title: string;
    text?: string;
    locationMetadata: {
        pageNumber: number;
        boundingPolygons: string;
    };
    content_type?: string;
    is_image?: boolean;
    image_url?: string;
    linked_image_path?: string;
    source_figure_id?: string;
    show_image?: boolean;
}

export enum OpenAIAPIMode {
    ChatCompletions = "chat_completions"
}

// API Response types
export interface ApiResponse<T = unknown> {
    success: boolean;
    data?: T;
    error?: string;
    message?: string;
}

export interface LoadingState {
    isLoading: boolean;
    error?: string;
}

// Generic utility types
export type Optional<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>;
export type RequiredBy<T, K extends keyof T> = T & Required<Pick<T, K>>;
