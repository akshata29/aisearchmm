import React, { Dispatch, SetStateAction } from "react";

import { 
    Label, 
    Slider, 
    SliderOnChangeData, 
    InfoLabel, 
    Switch, 
    SwitchOnChangeData,
    Dropdown,
    Option,
    Input,
    Button,
    Divider,
    Text
} from "@fluentui/react-components";
import { Dismiss24Regular } from "@fluentui/react-icons";

import { OpenAIAPIMode } from "../../../api/models";
import { buildApiUrl } from "../../../utils/api-config";
import "./SearchSettings.css";

interface Props {
    config: SearchConfig;
    setConfig: Dispatch<SetStateAction<SearchConfig>>;
}

export interface SearchConfig {
    chunk_count: number;
    use_semantic_ranker: boolean;
    openai_api_mode: OpenAIAPIMode;
    use_streaming: boolean;
    use_knowledge_agent: boolean;
    
    // Enhanced Knowledge Agent options
    recency_preference_days?: number;  // Boost documents within this many days
    query_complexity?: "low" | "medium" | "high";
    preferred_document_types?: string[];  // e.g., ["research_paper", "technical_document"]
    enable_post_processing_boost?: boolean;
    additional_filters?: string[];  // Additional OData filters
    
    // Hybrid Search Configuration (when not using Knowledge Agent)
    use_hybrid_search?: boolean;  // Enable hybrid search (text + vector)
    use_query_rewriting?: boolean;  // Enable semantic query rewriting
    use_scoring_profile?: boolean;  // Enable scoring profile for freshness/type boosts
    scoring_profile_name?: string;  // Name of the scoring profile to use
    vector_weight?: number;  // Weight for vector queries in hybrid search (0.0-1.0)
    rrf_k_parameter?: number;  // RRF k parameter for ranking fusion
    semantic_ranking_threshold?: number;  // Minimum semantic score threshold
    enable_vector_filters?: boolean;  // Enable pre/post filtering for vector queries
    vector_filter_mode?: "preFilter" | "postFilter";  // Vector filter mode
    query_rewrite_count?: number;  // Number of query rewrites to generate
}

const SearchSettings: React.FC<Props> = ({ config, setConfig }) => {
    // Document types state - will be loaded dynamically
    const [documentTypeOptions, setDocumentTypeOptions] = React.useState([
        { key: 'quarterly_report', text: 'Quarterly Report' },
        { key: 'newsletter', text: 'Newsletter' },
        { key: 'articles', text: 'Articles' },
        { key: 'annual_report', text: 'Annual Report' },
        { key: 'financial_statement', text: 'Financial Statement' },
        { key: 'presentation', text: 'Presentation' },
        { key: 'whitepaper', text: 'Whitepaper' },
        { key: 'research_report', text: 'Research Report' },
        { key: 'policy_document', text: 'Policy Document' },
        { key: 'manual', text: 'Manual' },
        { key: 'guide', text: 'Guide' },
        { key: 'cr', text: 'Client Reviews' },
        { key: 'Nyp, Nl', text: 'NYP Columns' },
        { key: 'book', text: 'Only Three Questions' },
        { key: 'other', text: 'Other' }
    ]);

    // Load document types on component mount
    React.useEffect(() => {
        const loadDocumentTypes = async () => {
            try {
                const response = await fetch(buildApiUrl('get_document_types'), { headers: (window as any).getSessionHeaders ? (window as any).getSessionHeaders() : {} });
                if (response.ok) {
                    const result = await response.json();
                    if (result.success && result.document_types) {
                        setDocumentTypeOptions(result.document_types);
                    }
                }
            } catch (error) {
                console.warn('Could not load document types from server, using defaults:', error);
                // Keep the default types that are already set in state
            }
        };
        
        loadDocumentTypes();
    }, []);

    const handleSwitchChange = (key: keyof typeof config, checked: boolean) => {
        setConfig(prev => {
            const newConfig = { ...prev, [key]: checked } as SearchConfig;
            
            // When Knowledge Agent is enabled, Semantic Ranker must also be enabled
            if (key === "use_knowledge_agent" && checked) {
                newConfig.use_semantic_ranker = true;
                // Disable hybrid search features when Knowledge Agent is enabled
                newConfig.use_hybrid_search = false;
                newConfig.use_query_rewriting = false;
                newConfig.use_scoring_profile = false;
                newConfig.enable_vector_filters = false;
            }
            
            // When Hybrid Search is enabled, Semantic Ranker should also be enabled for best results
            if (key === "use_hybrid_search" && checked) {
                newConfig.use_semantic_ranker = true;
            }
            
            // When Knowledge Agent is disabled, allow advanced search features
            if (key === "use_knowledge_agent" && !checked) {
                // Keep semantic ranker setting as user configured
                // Don't automatically enable hybrid search - let user choose
            }
            
            return newConfig;
        });
    };

    const handleSliderChange = (key: keyof typeof config, value: number) => {
        setConfig(prev => ({
            ...prev,
            [key]: value
        }));
    };

    const handleDropdownChange = (key: keyof typeof config, value: string) => {
        setConfig(prev => ({
            ...prev,
            [key]: value
        }));
    };

    const handleDocumentTypesChange = (newTypes: string[]) => {
        // Ensure proper ordering: book, nyp, Nl, cr first, then others
        const orderedTypes = orderDocumentTypes(newTypes);
        setConfig(prev => ({
            ...prev,
            preferred_document_types: orderedTypes
        }));
    };

    const orderDocumentTypes = (types: string[]): string[] => {
        const priorityOrder = ["book", "Nyp,Nl", "cr"];
        const orderedTypes: string[] = [];
        
        // Add priority types first if they exist in the list
        for (const priorityType of priorityOrder) {
            if (types.includes(priorityType)) {
                orderedTypes.push(priorityType);
            }
        }
        
        // Add remaining types that are not in priority list
        for (const docType of types) {
            if (!priorityOrder.includes(docType) && !orderedTypes.includes(docType)) {
                orderedTypes.push(docType);
            }
        }
        
        return orderedTypes;
    };

    const addDocumentType = (type: string) => {
        if (type.trim() && !config.preferred_document_types?.includes(type.trim())) {
            const currentTypes = config.preferred_document_types || [];
            handleDocumentTypesChange([...currentTypes, type.trim()]);
        }
    };

    const removeDocumentType = (typeToRemove: string) => {
        const currentTypes = config.preferred_document_types || [];
        handleDocumentTypesChange(currentTypes.filter(type => type !== typeToRemove));
    };

    const addDocumentTypeFromDropdown = (selectedKey: string) => {
        if (selectedKey && !config.preferred_document_types?.includes(selectedKey)) {
            const currentTypes = config.preferred_document_types || [];
            handleDocumentTypesChange([...currentTypes, selectedKey]);
        }
    };

    // Ensure default document types are set if none exist
    React.useEffect(() => {
        if (!config.preferred_document_types || config.preferred_document_types.length === 0) {
            handleDocumentTypesChange(["book", "Nyp,Nl", "cr"]);
        }
    }, []);

    return (
        <div className="input-container">
            <div className="input-group">
                <Label htmlFor="ChunkCountSlider">Top chunks count [{config.chunk_count}]</Label>
                <Slider
                    id="chunkCountSlider"
                    className="weightSlider"
                    value={config.chunk_count}
                    onChange={(_: React.ChangeEvent<HTMLInputElement>, data: SliderOnChangeData) => handleSliderChange("chunk_count", data.value)}
                    min={5}
                    max={50}
                    step={5}
                />
            </div>

            <Switch
                id="useSemanticRankerSwitch"
                checked={config.use_semantic_ranker}
                disabled={config.use_knowledge_agent || config.use_hybrid_search}
                onChange={(_, data: SwitchOnChangeData) => handleSwitchChange("use_semantic_ranker", data.checked)}
                label={
                    <InfoLabel
                        label={"Use semantic ranker"}
                        info={<>Enable semantic ranker for improved results especially if your data is indexed using image verbalization technique. Automatically enabled with Knowledge Agent and Hybrid Search.</>}
                    />
                }
            />

            {/* Managed Identity toggle moved to Header for global placement */}
            <Switch
                id="useKnowledgeAgentSwitch"
                checked={config.use_knowledge_agent}
                onChange={(_, data: SwitchOnChangeData) => handleSwitchChange("use_knowledge_agent", data.checked)}
                label={<InfoLabel label={"Use Knowledge Agent"} info={<>Enable knowledge agent for grounding answers</>} />}
            />

            {/* Recency preference slider - available for all search types */}
            <div className="input-group">
                <Label htmlFor="RecencySlider">Recency preference (days) [{config.recency_preference_days || 90}]</Label>
                <Slider
                    id="recencySlider"
                    className="weightSlider"
                    value={config.recency_preference_days || 90}
                    onChange={(_: React.ChangeEvent<HTMLInputElement>, data: SliderOnChangeData) => handleSliderChange("recency_preference_days", data.value)}
                    min={0}
                    max={1095}
                    step={30}
                />
                <Text size={200} style={{ fontSize: "11px", color: "var(--colorNeutralForeground3)", marginTop: "4px" }}>
                    {config.use_knowledge_agent 
                        ? "Boost documents published within this timeframe" 
                        : "Filter and boost documents published within this timeframe"}
                </Text>
            </div>

            {/* Document Type Filtering - Available for both Knowledge Agent and Search Grounding */}
            <div className="input-group">
                <Label htmlFor="DocumentTypesDropdown">Preferred document types</Label>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", marginBottom: "8px" }}>
                    {(config.preferred_document_types || []).map((type, index) => {
                        const typeOption = documentTypeOptions.find(opt => opt.key === type);
                        const displayText = typeOption ? typeOption.text : type;
                        return (
                            <div key={index} style={{ 
                                display: "inline-flex", 
                                alignItems: "center", 
                                padding: "2px 8px", 
                                backgroundColor: "var(--colorNeutralBackground1Selected)",
                                borderRadius: "12px",
                                fontSize: "12px",
                                border: "1px solid var(--colorNeutralStroke2)"
                            }}>
                                <span>{displayText}</span>
                                <Button
                                    appearance="transparent"
                                    size="small"
                                    icon={<Dismiss24Regular />}
                                    onClick={() => removeDocumentType(type)}
                                    style={{ marginLeft: "4px", minWidth: "16px", height: "16px" }}
                                />
                            </div>
                        );
                    })}
                </div>
                <Dropdown
                    id="documentTypesDropdown"
                    placeholder="Select document type to add"
                    onOptionSelect={(_, data) => {
                        if (data.optionValue) {
                            addDocumentTypeFromDropdown(data.optionValue);
                        }
                    }}
                >
                    {documentTypeOptions
                        .filter(option => !(config.preferred_document_types || []).includes(option.key))
                        .map((option) => (
                            <Option key={option.key} value={option.key}>
                                {option.text}
                            </Option>
                        ))
                    }
                </Dropdown>
                <Text size={200} style={{ fontSize: "11px", color: "var(--colorNeutralForeground3)", marginTop: "4px" }}>
                    {config.use_knowledge_agent 
                        ? "Select document types to prioritize in search results. Defaults to: Only Three Questions, NYP Columns, Client Reviews." 
                        : "Select document types to filter and prioritize in search results. Defaults to: Only Three Questions, NYP Columns, Client Reviews."}
                </Text>
                <Input
                    placeholder="Or type custom document type and press Enter"
                    onKeyDown={(e: React.KeyboardEvent<HTMLInputElement>) => {
                        if (e.key === "Enter") {
                            e.preventDefault();
                            const input = e.target as HTMLInputElement;
                            addDocumentType(input.value);
                            input.value = "";
                        }
                    }}
                    style={{ marginTop: "8px" }}
                />
            </div>

            {/* Knowledge Agent specific settings */}
            {config.use_knowledge_agent && (
                <>
                    <Divider style={{ margin: "16px 0" }} />
                    <Text size={300} weight="semibold" style={{ display: "block", marginBottom: "12px", color: "var(--colorNeutralForeground2)" }}>
                        Knowledge Agent Options
                    </Text>

                    <div className="input-group">
                        <Label htmlFor="QueryComplexityDropdown">Query complexity</Label>
                        <Dropdown
                            id="queryComplexityDropdown"
                            value={config.query_complexity || "medium"}
                            selectedOptions={[config.query_complexity || "medium"]}
                            onOptionSelect={(_, data) => {
                                if (data.optionValue) {
                                    handleDropdownChange("query_complexity", data.optionValue);
                                }
                            }}
                        >
                            <Option value="low">Low - Simple queries (faster)</Option>
                            <Option value="medium">Medium - Balanced performance</Option>
                            <Option value="high">High - Complex queries (comprehensive)</Option>
                        </Dropdown>
                        <Text size={200} style={{ fontSize: "11px", color: "var(--colorNeutralForeground3)", marginTop: "4px" }}>
                            Adjusts reranker thresholds and document count for retrieval. 
                            Final results will be limited to your "Top chunks count" setting ({config.chunk_count}).
                        </Text>
                    </div>

                    <Switch
                        id="postProcessingBoostSwitch"
                        checked={config.enable_post_processing_boost !== false}
                        onChange={(_, data: SwitchOnChangeData) => handleSwitchChange("enable_post_processing_boost", data.checked)}
                        label={
                            <InfoLabel
                                label={"Enable post-processing boost"}
                                info={<>Apply additional prioritization logic after retrieval based on recency and document type</>}
                            />
                        }
                    />
                </>
            )}

            {/* Hybrid Search specific settings - only when Knowledge Agent is OFF */}
            {!config.use_knowledge_agent && (
                <>
                    <Divider style={{ margin: "16px 0" }} />
                    <Text size={300} weight="semibold" style={{ display: "block", marginBottom: "12px", color: "var(--colorNeutralForeground2)" }}>
                        Advanced Search Options
                    </Text>

                    <Switch
                        id="useHybridSearchSwitch"
                        checked={config.use_hybrid_search || false}
                        onChange={(_, data: SwitchOnChangeData) => handleSwitchChange("use_hybrid_search", data.checked)}
                        label={
                            <InfoLabel
                                label={"Use Hybrid Search"}
                                info={<>Enable hybrid search combining text and vector search with Reciprocal Rank Fusion (RRF) for better relevance</>}
                            />
                        }
                    />

                    {config.use_hybrid_search && (
                        <div className="input-group" style={{ marginLeft: "20px", paddingLeft: "10px", borderLeft: "2px solid var(--colorNeutralStroke2)" }}>
                            <div className="input-group">
                                <Label htmlFor="VectorWeightSlider">Vector Weight [{(config.vector_weight || 0.5).toFixed(1)}]</Label>
                                <Slider
                                    id="vectorWeightSlider"
                                    className="weightSlider"
                                    value={config.vector_weight || 0.5}
                                    onChange={(_: React.ChangeEvent<HTMLInputElement>, data: SliderOnChangeData) => handleSliderChange("vector_weight", data.value)}
                                    min={0.1}
                                    max={1.0}
                                    step={0.1}
                                />
                                <Text size={200} style={{ fontSize: "11px", color: "var(--colorNeutralForeground3)", marginTop: "4px" }}>
                                    Balance between text search (lower values) and vector search (higher values)
                                </Text>
                            </div>

                            <Switch
                                id="enableVectorFiltersSwitch"
                                checked={config.enable_vector_filters || false}
                                onChange={(_, data: SwitchOnChangeData) => handleSwitchChange("enable_vector_filters", data.checked)}
                                label={
                                    <InfoLabel
                                        label={"Enable Vector Filters"}
                                        info={<>Apply filtering to vector queries for better performance with large datasets</>}
                                    />
                                }
                            />

                            {config.enable_vector_filters && (
                                <div className="input-group" style={{ marginLeft: "20px" }}>
                                    <Label htmlFor="VectorFilterModeDropdown">Vector Filter Mode</Label>
                                    <Dropdown
                                        id="vectorFilterModeDropdown"
                                        value={config.vector_filter_mode || "preFilter"}
                                        selectedOptions={[config.vector_filter_mode || "preFilter"]}
                                        onOptionSelect={(_, data) => {
                                            if (data.optionValue) {
                                                handleDropdownChange("vector_filter_mode", data.optionValue);
                                            }
                                        }}
                                    >
                                        <Option value="preFilter">Pre-filter (Better recall, slower)</Option>
                                        <Option value="postFilter">Post-filter (Faster, may return fewer results)</Option>
                                    </Dropdown>
                                    <Text size={200} style={{ fontSize: "11px", color: "var(--colorNeutralForeground3)", marginTop: "4px" }}>
                                        Pre-filtering guarantees k results but is slower. Post-filtering is faster but may return fewer results.
                                    </Text>
                                </div>
                            )}
                        </div>
                    )}

                    <Switch
                        id="useScoringProfileSwitch"
                        checked={config.use_scoring_profile || false}
                        onChange={(_, data: SwitchOnChangeData) => handleSwitchChange("use_scoring_profile", data.checked)}
                        label={
                            <InfoLabel
                                label={"Use Scoring Profile"}
                                info={<>Apply scoring profile to boost relevance based on document freshness and type after semantic reranking</>}
                            />
                        }
                    />

                    {config.use_scoring_profile && (
                        <div className="input-group" style={{ marginLeft: "20px", paddingLeft: "10px", borderLeft: "2px solid var(--colorNeutralStroke2)" }}>
                            <Input
                                placeholder="Enter scoring profile name (e.g., freshness_and_type_boost)"
                                value={config.scoring_profile_name || ""}
                                onChange={(_, data) => setConfig(prev => ({ ...prev, scoring_profile_name: data.value }))}
                            />
                            <Text size={200} style={{ fontSize: "11px", color: "var(--colorNeutralForeground3)", marginTop: "4px" }}>
                                Name of the scoring profile defined in your search index
                            </Text>
                        </div>
                    )}

                    <Switch
                        id="useQueryRewritingSwitch"
                        checked={config.use_query_rewriting || false}
                        onChange={(_, data: SwitchOnChangeData) => handleSwitchChange("use_query_rewriting", data.checked)}
                        label={
                            <InfoLabel
                                label={"Use Query Rewriting"}
                                info={<>Enable AI-powered query rewriting to improve search results by generating alternative query formulations</>}
                            />
                        }
                    />

                    {config.use_query_rewriting && (
                        <div className="input-group" style={{ marginLeft: "20px", paddingLeft: "10px", borderLeft: "2px solid var(--colorNeutralStroke2)" }}>
                            <Label htmlFor="QueryRewriteCountSlider">Query Rewrite Count [{config.query_rewrite_count || 3}]</Label>
                            <Slider
                                id="queryRewriteCountSlider"
                                className="weightSlider"
                                value={config.query_rewrite_count || 3}
                                onChange={(_: React.ChangeEvent<HTMLInputElement>, data: SliderOnChangeData) => handleSliderChange("query_rewrite_count", data.value)}
                                min={1}
                                max={10}
                                step={1}
                            />
                            <Text size={200} style={{ fontSize: "11px", color: "var(--colorNeutralForeground3)", marginTop: "4px" }}>
                                Number of alternative query formulations to generate for better results
                            </Text>
                        </div>
                    )}
                </>
            )}

            <Switch
                id="useStreamingSwitch"
                checked={config.use_streaming}
                onChange={(_, data: SwitchOnChangeData) => handleSwitchChange("use_streaming", data.checked)}
                label={"Use Streaming Response"}
            />
        </div>
    );
};

export default SearchSettings;
