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
        recency_preference_days: 365,
        query_complexity: "medium",
        preferred_document_types: [],
        enable_post_processing_boost: true,
        additional_filters: []
    });

    const [indexes, setIndexes] = useState<string[]>([]);

    useEffect(() => {
        const fetchIndexes = async () => {
            const indexes = await listIndexes();
            setIndexes(indexes);
        };

        fetchIndexes();
    }, []);

    return { config, setConfig, indexes };
}
