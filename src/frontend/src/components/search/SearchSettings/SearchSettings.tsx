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
}

const SearchSettings: React.FC<Props> = ({ config, setConfig }) => {
    // Document type options - same as in DocumentUpload component for consistency
    const documentTypeOptions = [
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
        { key: 'other', text: 'Other' }
    ];

    const handleSwitchChange = (key: keyof typeof config, checked: boolean) => {
        setConfig(prev => {
            const newConfig = { ...prev, [key]: checked } as SearchConfig;
            // When Knowledge Agent is enabled, Semantic Ranker must also be enabled
            if (key === "use_knowledge_agent" && checked) {
                newConfig.use_semantic_ranker = true;
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
        setConfig(prev => ({
            ...prev,
            preferred_document_types: newTypes
        }));
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
                disabled={config.use_knowledge_agent}
                onChange={(_, data: SwitchOnChangeData) => handleSwitchChange("use_semantic_ranker", data.checked)}
                label={
                    <InfoLabel
                        label={"Use semantic ranker"}
                        info={<>Enable semantic ranker for improved results especially if your data is indexed using image verbalization technique</>}
                    />
                }
            />
            <Switch
                id="useKnowledgeAgentSwitch"
                checked={config.use_knowledge_agent}
                onChange={(_, data: SwitchOnChangeData) => handleSwitchChange("use_knowledge_agent", data.checked)}
                label={<InfoLabel label={"Use Knowledge Agent"} info={<>Enable knowledge agent for grounding answers</>} />}
            />

            {/* Knowledge Agent specific settings */}
            {config.use_knowledge_agent && (
                <>
                    <Divider style={{ margin: "16px 0" }} />
                    <Text size={300} weight="semibold" style={{ display: "block", marginBottom: "12px", color: "var(--colorNeutralForeground2)" }}>
                        Knowledge Agent Options
                    </Text>

                    <div className="input-group">
                        <Label htmlFor="RecencySlider">Recency preference (days) [{config.recency_preference_days || 365}]</Label>
                        <Slider
                            id="recencySlider"
                            className="weightSlider"
                            value={config.recency_preference_days || 365}
                            onChange={(_: React.ChangeEvent<HTMLInputElement>, data: SliderOnChangeData) => handleSliderChange("recency_preference_days", data.value)}
                            min={30}
                            max={1095}
                            step={30}
                        />
                        <Text size={200} style={{ fontSize: "11px", color: "var(--colorNeutralForeground3)", marginTop: "4px" }}>
                            Boost documents published within this timeframe
                        </Text>
                    </div>

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
                            Select document types to prioritize in search results. You can also type custom types below.
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
