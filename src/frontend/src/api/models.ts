export enum ThreadType {
    Answer = "answer",
    Message = "message",
    Citation = "citation",
    Info = "info",
    Error = "error"
}

export enum RoleType {
    User = "user",
    Assistant = "assistant"
}

export enum OpenAIAPIMode {
    ChatCompletions = "chat_completions"
}

export interface KnowledgeAgentMessage {
    role: RoleType;
    content: string;
}

export interface Thread {
    message?: string;
    request_id: string;
    message_id?: string;
    type: ThreadType;
    answerPartial?: { answer: string };
    log_json?: string;
    role: RoleType;
    textCitations?: Citation[];
    imageCitations?: Citation[];
    knowledgeAgentMessage?: KnowledgeAgentMessage;
}

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

export interface Chat {
    name: string;
    thread: Thread[];
    id: string;
    lastUpdated: number;
}

export enum ProcessingStepType {
    Text = "text"
}

export interface ProcessingStep {
    title: string;
    description: string;
    type: ProcessingStepType;
    content: string;
}

export interface ProcessingStepsMessage {
    message_id: string;
    request_id: string;
    processingStep: ProcessingStep;
}

// Feedback-related interfaces
export interface FeedbackProcessingStep {
    step_id: string;
    step_type: string;
    title: string;
    description?: string | undefined;
    status: string;
    duration_ms?: number | undefined;
    details?: { [key: string]: any } | undefined;
}

export interface FeedbackSubmissionData {
    request_id: string;
    session_id: string;
    feedback_type: "thumbs_up" | "thumbs_down";
    question: string;
    response: string;
    text_citations?: Citation[];
    image_citations?: Citation[];
    processing_steps?: FeedbackProcessingStep[];
    search_config?: any;
}

export interface FeedbackEntry {
    feedback_id: string;
    request_id: string;
    session_id: string;
    timestamp: string;
    feedback_type: "thumbs_up" | "thumbs_down";
    question: string;
    response_text: string;
    text_citations?: Citation[];
    image_citations?: Citation[];
    processing_steps?: FeedbackProcessingStep[];
    search_config?: any;
    admin_notes?: string;
    is_reviewed: boolean;
    last_modified?: string;
    modified_by?: string;
    text_citations_count: number;
    image_citations_count: number;
}

export interface FeedbackListResponse {
    status: string;
    data: {
        feedback_items: FeedbackEntry[];
        pagination: {
            page: number;
            page_size: number;
            total_count: number;
            total_pages: number;
            has_next: boolean;
            has_prev: boolean;
        };
    };
    operation_id: string;
}
