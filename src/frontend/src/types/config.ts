/**
 * Configuration-related types
 */

export interface SearchConfig {
    searchIndex: string;
    searchService: string;
    searchKey: string;
    useSemanticRanker: boolean;
    useQueryContextSummary: boolean;
    excludeCategory?: string;
    useSuggestFollowupQuestions: boolean;
    queryType: string;
    retrievalMode: string;
    searchAnalyzer: string;
    indexAnalyzer: string;
    enableVectorSearch: boolean;
    vectorFields: string[];
    vectorSearchMode: string;
    retrieveCount: number;
    minimumSearchScore: number;
    minimumRerankerScore: number;
    enableLogProbabilities: boolean;
    enablePIILogging: boolean;
    enableContentSafety: boolean;
}

export interface AppConfig {
    theme: 'light' | 'dark';
    language: string;
    autoSave: boolean;
}

export interface FeatureFlags {
    enableMultimodal: boolean;
    enableAdvancedSearch: boolean;
    enableFileUpload: boolean;
    enableCitationPreview: boolean;
}
