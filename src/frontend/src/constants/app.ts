/**
 * Application constants
 */

// App information
export const APP_NAME = "AI Search Multimodal";
export const APP_VERSION = "1.0.0";

// UI Constants
export const INTRO_TITLE = "Chat with Your Data (Text + Images)";
export const INTRO_TEXT = 
    "Build intelligent applications that can query and reason over both text and image data. With multimodal RAG, you can retrieve relevant content from documents, screenshots, and visuals, then generate grounded responses using large language models.";

// API Constants
export const API_ENDPOINTS = {
    CHAT: "/chat",
    LIST_INDEXES: "/list_indexes",
    GET_CITATION_DOC: "/get_citation_doc",
    UPLOAD: "/upload",
    UPLOAD_STATUS: "/upload_status",
    PROCESS_DOCUMENT: "/process_document",
    DELETE_INDEX: "/delete_index",
    ADMIN: "/api/admin"
} as const;

// Default configurations
export const DEFAULT_SEARCH_CONFIG = {
    searchIndex: "",
    searchService: "",
    searchKey: "",
    useSemanticRanker: true,
    useQueryContextSummary: true,
    useSuggestFollowupQuestions: true,
    queryType: "simple",
    retrievalMode: "hybrid",
    searchAnalyzer: "en.microsoft",
    indexAnalyzer: "en.microsoft",
    enableVectorSearch: true,
    vectorFields: ["contentVector"],
    vectorSearchMode: "simple",
    retrieveCount: 5,
    minimumSearchScore: 0.0,
    minimumRerankerScore: 0.0,
    enableLogProbabilities: false,
    enablePIILogging: false,
    enableContentSafety: false
} as const;

// Timeouts and limits
export const TIMEOUTS = {
    API_REQUEST: 30000,
    UPLOAD: 600000,         // Increased from 5 minutes to 10 minutes for large files
    PROCESSING: 1200000     // Increased from 10 minutes to 20 minutes for large document processing
} as const;

export const LIMITS = {
    MAX_FILE_SIZE: 50 * 1024 * 1024, // 50MB
    MAX_FILES_PER_UPLOAD: 10,
    MAX_THREAD_LENGTH: 100
} as const;
