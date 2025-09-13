import { useEffect, useState } from "react";
import { listIndexes } from "../api/api";
import { OpenAIAPIMode } from "../api/models";
import { SearchConfig } from "../components/search/SearchSettings/SearchSettings";

export default function useConfig() {
    const [config, setConfig] = useState<SearchConfig>({
        use_semantic_ranker: false,
        chunk_count: 10,
        openai_api_mode: OpenAIAPIMode.ChatCompletions,
        use_streaming: true,
        use_knowledge_agent: true,
        
        // Enhanced Knowledge Agent options with defaults
        recency_preference_days: 90,
        query_complexity: "medium",
        preferred_document_types: [],
        enable_post_processing_boost: true,
        additional_filters: [],
        
        // Hybrid Search Configuration defaults (when not using Knowledge Agent)
        use_hybrid_search: false,
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

    const [indexes, setIndexes] = useState<string[]>([]);

    useEffect(() => {
        // const fetchIndexes = async () => {
        //     const indexes = await listIndexes();
        //     setIndexes(indexes);
        // };

        // fetchIndexes();
    }, []);

    return { config, setConfig, indexes };
}
