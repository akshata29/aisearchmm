import { useState, useEffect } from "react";
import { OpenAIAPIMode } from "../api/models";
import { SearchConfig } from "../components/search/SearchSettings/SearchSettings";

export default function useConfig() {
    const [config, setConfig] = useState<SearchConfig>({
        use_semantic_ranker: true,
        chunk_count: 50,
        openai_api_mode: OpenAIAPIMode.ChatCompletions,
        use_streaming: true,
        use_knowledge_agent: false,
        use_chat_history: false,  // Default to disabled
        
        // Enhanced Knowledge Agent options with defaults
        recency_preference_days: 90,
        query_complexity: "medium",
        preferred_document_types: ["book", "nyp, nl", "cr"],
        enable_post_processing_boost: true,
        additional_filters: [],
        
        // Hybrid Search Configuration defaults (when not using Knowledge Agent)
        use_hybrid_search: true,
        use_query_rewriting: false,
        use_scoring_profile: true,  // Enable scoring profile by default for freshness boosting
        scoring_profile_name: "freshness_and_type_boost",
        vector_weight: 0.5,
        rrf_k_parameter: 60,
        semantic_ranking_threshold: 2.0,
        enable_vector_filters: false,
        vector_filter_mode: "preFilter",
        query_rewrite_count: 3
    });

    // Update config when localStorage changes
    useEffect(() => {
        const updateConfigFromStorage = () => {
            try {
                const historyState = localStorage.getItem('use_chat_history') === 'true';
                const customSearchPrompt = localStorage.getItem('custom_search_query_prompt');
                const customSystemPrompt = localStorage.getItem('custom_system_prompt');
                
                setConfig(prev => { 
                    const newConfig = { 
                        ...prev, 
                        use_chat_history: historyState
                    };
                    
                    if (customSearchPrompt) {
                        newConfig.custom_search_query_prompt = customSearchPrompt;
                    }
                    if (customSystemPrompt) {
                        newConfig.custom_system_prompt = customSystemPrompt;
                    }
                    
                    return newConfig;
                });
            } catch (e) {
                // ignore localStorage errors
            }
        };

        // Initial read
        updateConfigFromStorage();

        // Listen for storage events (for when other tabs change the setting)
        window.addEventListener('storage', updateConfigFromStorage);
        
        return () => {
            window.removeEventListener('storage', updateConfigFromStorage);
        };
    }, []);

    return { config, setConfig };
}
