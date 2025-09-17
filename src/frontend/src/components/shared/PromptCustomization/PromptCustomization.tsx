import React, { useState, useEffect } from 'react';
import {
    Dialog,
    DialogTrigger,
    DialogSurface,
    DialogTitle,
    DialogContent,
    DialogActions,
    DialogBody,
    Button,
    Tab,
    TabList,
    TabValue,
    SelectTabData,
    SelectTabEvent,
    Textarea,
    Text,
    Divider,
    Badge,
    InfoLabel,
    Tooltip
} from '@fluentui/react-components';
import {
    SettingsRegular,
    DismissRegular,
    ArrowResetRegular
} from '@fluentui/react-icons';
import { SearchConfig } from '../../search/SearchSettings/SearchSettings';
import './PromptCustomization.css';

// Default prompts - we'll get these from the backend or define them here
const DEFAULT_SEARCH_QUERY_PROMPT = `Generate an optimal search query for a search index, given the user question.
Return **only** the query string (no JSON, no comments).
Incorporate key entities, facts, dates, synonyms, and disambiguating contextual terms from the question.
Prefer specific nouns over broad descriptors.
Limit to ≤ 32 tokens.`;

const DEFAULT_SYSTEM_PROMPT = `You are an expert assistant in a Retrieval‑Augmented Generation (RAG) system. Provide concise, well‑cited answers **using only the indexed documents and images**.
Your input is a list of text and image documents identified by a reference ID (ref_id). Your response is a well-structured JSON object.

### Input format provided by the orchestrator
• Text document → A JSON object with a ref_id field and content fields containing textual information.
• Image document → A text message starting with "IMAGE REFERENCE with ID [ref_id]:" followed by the actual image content.

### Citation format you must output
Return **one valid JSON object** with exactly these fields:

• \`answer\` → your answer in Markdown.
• \`text_citations\` → every text reference ID (ref_id) you used from text documents to generate the answer.
• \`image_citations\` → every image reference ID (ref_id) you used from image documents to generate the answer.

### Response rules
1. The value of the **answer** property must be formatted in Markdown.
2. **Cite every factual statement** via the appropriate citations list (text_citations for text sources, image_citations for image sources).
3. When you reference information from an image, put the ref_id in \`image_citations\`.
4. When you reference information from text content, put the ref_id in \`text_citations\`.
5. If *no* relevant source exists, reply exactly:
   > I cannot answer with the provided knowledge base.
6. Keep answers succinct yet self‑contained.
7. Ensure citations directly support your statements; avoid speculation.`;

interface PromptCustomizationProps {
    config: SearchConfig;
    setConfig: (config: SearchConfig) => void;
}

export const PromptCustomization: React.FC<PromptCustomizationProps> = ({ 
    config, 
    setConfig 
}) => {
    const [isOpen, setIsOpen] = useState(false);
    const [selectedTab, setSelectedTab] = useState<TabValue>("search");
    const [searchPrompt, setSearchPrompt] = useState('');
    const [systemPrompt, setSystemPrompt] = useState('');
    const [hasChanges, setHasChanges] = useState(false);

    // Initialize prompts from config or defaults
    useEffect(() => {
        const currentSearchPrompt = config.custom_search_query_prompt || DEFAULT_SEARCH_QUERY_PROMPT;
        const currentSystemPrompt = config.custom_system_prompt || DEFAULT_SYSTEM_PROMPT;
        
        setSearchPrompt(currentSearchPrompt);
        setSystemPrompt(currentSystemPrompt);
        setHasChanges(false);
    }, [config, isOpen]);

    // Track changes
    useEffect(() => {
        const originalSearchPrompt = config.custom_search_query_prompt || DEFAULT_SEARCH_QUERY_PROMPT;
        const originalSystemPrompt = config.custom_system_prompt || DEFAULT_SYSTEM_PROMPT;
        
        setHasChanges(
            searchPrompt !== originalSearchPrompt || 
            systemPrompt !== originalSystemPrompt
        );
    }, [searchPrompt, systemPrompt, config]);

    const handleTabChange = (_event: SelectTabEvent, data: SelectTabData) => {
        setSelectedTab(data.value);
    };

    const handleSave = () => {
        try {
            // Update config with new prompts
            const newConfig = {
                ...config,
                custom_search_query_prompt: searchPrompt.trim() || DEFAULT_SEARCH_QUERY_PROMPT,
                custom_system_prompt: systemPrompt.trim() || DEFAULT_SYSTEM_PROMPT
            };
            
            setConfig(newConfig);
            
            // Save to localStorage
            localStorage.setItem('custom_search_query_prompt', searchPrompt.trim());
            localStorage.setItem('custom_system_prompt', systemPrompt.trim());
            
            setIsOpen(false);
            setHasChanges(false);
            
            // Show success toast
            const toast = document.createElement('div');
            toast.className = 'prompt-toast success';
            toast.textContent = 'Prompts saved successfully!';
            document.body.appendChild(toast);
            setTimeout(() => { try { toast.remove(); } catch(e) {} }, 3000);
        } catch (error) {
            console.error('Error saving prompts:', error);
            
            // Show error toast
            const toast = document.createElement('div');
            toast.className = 'prompt-toast error';
            toast.textContent = 'Error saving prompts. Please try again.';
            document.body.appendChild(toast);
            setTimeout(() => { try { toast.remove(); } catch(e) {} }, 3000);
        }
    };

    const handleCancel = () => {
        if (hasChanges) {
            const confirmDiscard = window.confirm('You have unsaved changes. Are you sure you want to cancel?');
            if (!confirmDiscard) return;
        }
        
        // Reset to original values
        setSearchPrompt(config.custom_search_query_prompt || DEFAULT_SEARCH_QUERY_PROMPT);
        setSystemPrompt(config.custom_system_prompt || DEFAULT_SYSTEM_PROMPT);
        setHasChanges(false);
        setIsOpen(false);
    };

    const handleResetToDefault = (promptType: 'search' | 'system') => {
        const confirmReset = window.confirm(
            `Are you sure you want to reset the ${promptType === 'search' ? 'search query' : 'system'} prompt to default?`
        );
        
        if (!confirmReset) return;
        
        if (promptType === 'search') {
            setSearchPrompt(DEFAULT_SEARCH_QUERY_PROMPT);
        } else {
            setSystemPrompt(DEFAULT_SYSTEM_PROMPT);
        }
    };

    const getCharacterCount = (text: string) => {
        return text.length;
    };

    const getWordCount = (text: string) => {
        return text.trim().split(/\s+/).filter(word => word.length > 0).length;
    };

    const isSearchPromptDefault = searchPrompt.trim() === DEFAULT_SEARCH_QUERY_PROMPT.trim();
    const isSystemPromptDefault = systemPrompt.trim() === DEFAULT_SYSTEM_PROMPT.trim();

    return (
        <Dialog open={isOpen} onOpenChange={(_event, data) => setIsOpen(data.open)}>
            <DialogTrigger disableButtonEnhancement>
                <Tooltip 
                    content="Customize Search and System Prompts" 
                    relationship="label"
                >
                    <Button 
                        appearance="subtle" 
                        icon={<SettingsRegular />}
                        aria-label="Customize prompts"
                        className="prompt-customization-trigger"
                    />
                </Tooltip>
            </DialogTrigger>
            
            <DialogSurface className="prompt-customization-dialog">
                <DialogBody>
                    <DialogTitle
                        action={
                            <DialogTrigger action="close">
                                <Button
                                    appearance="subtle"
                                    aria-label="close"
                                    icon={<DismissRegular />}
                                />
                            </DialogTrigger>
                        }
                    >
                        <div className="dialog-title-content">
                            <SettingsRegular />
                            Customize Prompts
                            {hasChanges && <Badge color="warning" size="small">Unsaved</Badge>}
                        </div>
                    </DialogTitle>
                    
                    <DialogContent>
                        <Text className="dialog-description">
                            Customize the prompts used for search query generation and RAG system responses.
                            Changes will be applied immediately when saved.
                        </Text>
                        
                        <Divider />
                        
                        <div className="prompt-tabs-container">
                            <TabList
                                selectedValue={selectedTab}
                                onTabSelect={handleTabChange}
                                size="medium"
                            >
                                <Tab value="search">
                                    Search Query Prompt
                                    {!isSearchPromptDefault && <Badge color="brand" size="tiny">Custom</Badge>}
                                </Tab>
                                <Tab value="system">
                                    System Prompt
                                    {!isSystemPromptDefault && <Badge color="brand" size="tiny">Custom</Badge>}
                                </Tab>
                            </TabList>
                            
                            {selectedTab === "search" && (
                                <div className="prompt-tab-content">
                                    <div className="prompt-header">
                                        <InfoLabel
                                            info={
                                                <div>
                                                    This prompt is used to generate optimized search queries from user questions.
                                                    It helps the system understand what to search for in the knowledge base.
                                                </div>
                                            }
                                        >
                                            Search Query Generation Prompt
                                        </InfoLabel>
                                        
                                        <div className="prompt-actions">
                                            <Button
                                                size="small"
                                                appearance="subtle"
                                                icon={<ArrowResetRegular />}
                                                disabled={isSearchPromptDefault}
                                                onClick={() => handleResetToDefault('search')}
                                            >
                                                Reset to Default
                                            </Button>
                                        </div>
                                    </div>
                                    
                                    <Textarea
                                        value={searchPrompt}
                                        onChange={(e) => setSearchPrompt(e.target.value)}
                                        placeholder="Enter your custom search query prompt..."
                                        rows={8}
                                        className="prompt-textarea"
                                        resize="vertical"
                                    />
                                    
                                    <div className="prompt-stats">
                                        <Text size={200}>
                                            {getCharacterCount(searchPrompt)} characters • {getWordCount(searchPrompt)} words
                                        </Text>
                                    </div>
                                </div>
                            )}
                            
                            {selectedTab === "system" && (
                                <div className="prompt-tab-content">
                                    <div className="prompt-header">
                                        <InfoLabel
                                            info={
                                                <div>
                                                    This is the main system prompt that guides how the AI generates responses
                                                    using the retrieved documents and images. It defines the response format,
                                                    citation requirements, and overall behavior.
                                                </div>
                                            }
                                        >
                                            RAG System Prompt
                                        </InfoLabel>
                                        
                                        <div className="prompt-actions">
                                            <Button
                                                size="small"
                                                appearance="subtle"
                                                icon={<ArrowResetRegular />}
                                                disabled={isSystemPromptDefault}
                                                onClick={() => handleResetToDefault('system')}
                                            >
                                                Reset to Default
                                            </Button>
                                        </div>
                                    </div>
                                    
                                    <Textarea
                                        value={systemPrompt}
                                        onChange={(e) => setSystemPrompt(e.target.value)}
                                        placeholder="Enter your custom system prompt..."
                                        rows={12}
                                        className="prompt-textarea"
                                        resize="vertical"
                                    />
                                    
                                    <div className="prompt-stats">
                                        <Text size={200}>
                                            {getCharacterCount(systemPrompt)} characters • {getWordCount(systemPrompt)} words
                                        </Text>
                                    </div>
                                </div>
                            )}
                        </div>
                    </DialogContent>
                    
                    <DialogActions>
                        <DialogTrigger disableButtonEnhancement>
                            <Button 
                                appearance="secondary" 
                                onClick={handleCancel}
                            >
                                Cancel
                            </Button>
                        </DialogTrigger>
                        <Button 
                            appearance="primary" 
                            disabled={!hasChanges}
                            onClick={handleSave}
                        >
                            Save Changes
                        </Button>
                    </DialogActions>
                </DialogBody>
            </DialogSurface>
        </Dialog>
    );
};

export default PromptCustomization;