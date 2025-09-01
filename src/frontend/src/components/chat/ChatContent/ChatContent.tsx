import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
    Card,
    CardPreview,
    CardFooter,
    Button,
    Text,
    Title3,
    Title2,
    Body1,
    Caption1,
    Tooltip,
    Avatar,
    Badge,
    MessageBar,
    Divider,
    Spinner
} from "@fluentui/react-components";
import {
    Copy20Regular,
    BrainCircuit20Regular,
    Person20Regular,
    CheckmarkCircle20Filled,
    ErrorCircle20Filled,
    Info20Regular,
    Sparkle20Regular,
    Clock20Regular,
    Share20Regular,
    ThumbLike20Regular,
    ThumbDislike20Regular,
    MoreHorizontal20Regular
} from "@fluentui/react-icons";

import { ProcessingStepsMessage, RoleType, Thread, ThreadType, Citation } from "../../../api/models";
import "./ChatContent.css";
import Citations from "../Citations/Citations";
import CitationViewer from "../CitationViewer/CitationViewer";
import ProcessingSteps from "../ProcessingSteps/ProcessingSteps";

interface Props {
    processingStepMsg: Record<string, ProcessingStepsMessage[]>;
    thread: Thread[];
}

const ProfessionalChatContent: React.FC<Props> = ({ thread, processingStepMsg }) => {
    const [showProcessingSteps, setShowProcessingSteps] = useState(false);
    const [processRequestId, setProcessRequestId] = useState("");
    const [highlightedCitation, setHighlightedCitation] = useState<string | undefined>();
    const [showCitationViewer, setShowCitationViewer] = useState(false);
    const [selectedCitation, setSelectedCitation] = useState<Citation | undefined>();
    const [copiedMessages, setCopiedMessages] = useState<Set<string>>(new Set());
    const [likedMessages, setLikedMessages] = useState<Set<string>>(new Set());
    const [dislikedMessages, setDislikedMessages] = useState<Set<string>>(new Set());
    const [isTyping, setIsTyping] = useState(false);

    const chatContainerRef = useRef<HTMLDivElement>(null);
    const messageToBeCopied: Record<string, string> = {};

    useEffect(() => {
        if (chatContainerRef.current) {
            chatContainerRef.current.scrollTo({
                top: chatContainerRef.current.scrollHeight,
                behavior: 'smooth'
            });
        }
    }, [thread]);

    // Simulate typing indicator for new messages
    useEffect(() => {
        if (thread.length > 0) {
            const lastMessage = thread[thread.length - 1];
            if (lastMessage.role === RoleType.Assistant && lastMessage.type === ThreadType.Answer) {
                setIsTyping(true);
                const timer = setTimeout(() => setIsTyping(false), 1000);
                return () => clearTimeout(timer);
            }
        }
    }, [thread]);

    const messagesGroupedByRequestId = Object.values(
        thread.reduce((acc: { [key: string]: Thread[] }, message: Thread) => {
            if (!acc[message.request_id]) {
                acc[message.request_id] = [];
            }
            acc[message.request_id].push(message);
            return acc;
        }, {})
    );

    // Enhanced citation handling with numbering
    const citationRegex = /\[([^\]]+)\]/g;

    const createCitationRenderer = (textCitations: Citation[], imageCitations: Citation[]) => {
        return (children: React.ReactNode) => {
            // Track unique citations and assign sequential numbers
            const citationMap = new Map<string, number>();
            let citationCounter = 1;
            
            // Combine all citations for lookup
            const allCitations = [...textCitations, ...imageCitations];
            
            const handleCitationClick = (citationId: string) => {
                // Find the citation by content_id
                const citation = allCitations.find(c => c.content_id === citationId);
                if (citation) {
                    setSelectedCitation(citation);
                    setShowCitationViewer(true);
                }
            };
            
            return React.Children.map(children, child => {
                if (typeof child === "string") {
                    return child
                        .split(citationRegex)
                        .map((part, index) => {
                            if (index % 2 === 0) {
                                return part; // Regular text
                            } else if (index % 2 === 1) {
                                // This is a citation ID
                                if (!citationMap.has(part)) {
                                    citationMap.set(part, citationCounter++);
                                }
                                const citationNumber = citationMap.get(part)!;
                                
                                return (
                                    <span
                                        key={`${part}-${index}`}
                                        onMouseLeave={() => setHighlightedCitation(undefined)}
                                        onMouseEnter={() => setHighlightedCitation(part)}
                                        onClick={() => handleCitationClick(part)}
                                        className="citation-link"
                                        style={{ cursor: 'pointer' }}
                                    >
                                        <Badge 
                                            size="tiny" 
                                            color="brand"
                                            appearance="tint"
                                            className="citation-badge-modern"
                                        >
                                            {citationNumber}
                                        </Badge>
                                    </span>
                                );
                            }
                            return null;
                        });
                }
                return child;
            });
        };
    };

    const getCurProcessingStep = (requestId: string): Record<string, ProcessingStepsMessage[]> => {
        const processingSteps = processingStepMsg[requestId];
        return { [requestId]: processingSteps };
    };

    const handleCopyMessage = (requestId: string) => {
        const textToCopy = messageToBeCopied[requestId] || "";
        navigator.clipboard.writeText(textToCopy).catch(err => {
            console.error("Failed to copy text: ", err);
        });
        setCopiedMessages(prev => new Set(prev).add(requestId));
        setTimeout(() => {
            setCopiedMessages(prev => {
                const newSet = new Set(prev);
                newSet.delete(requestId);
                return newSet;
            });
        }, 2000);
    };

    const handleLikeMessage = (requestId: string) => {
        setLikedMessages(prev => {
            const newSet = new Set(prev);
            if (newSet.has(requestId)) {
                newSet.delete(requestId);
            } else {
                newSet.add(requestId);
                // Remove from disliked if present
                setDislikedMessages(prevDisliked => {
                    const newDisliked = new Set(prevDisliked);
                    newDisliked.delete(requestId);
                    return newDisliked;
                });
            }
            return newSet;
        });
    };

    const handleDislikeMessage = (requestId: string) => {
        setDislikedMessages(prev => {
            const newSet = new Set(prev);
            if (newSet.has(requestId)) {
                newSet.delete(requestId);
            } else {
                newSet.add(requestId);
                // Remove from liked if present
                setLikedMessages(prevLiked => {
                    const newLiked = new Set(prevLiked);
                    newLiked.delete(requestId);
                    return newLiked;
                });
            }
            return newSet;
        });
    };

    const formatTimestamp = () => {
        return new Date().toLocaleTimeString([], { 
            hour: '2-digit', 
            minute: '2-digit',
            hour12: true 
        });
    };

    const getMessageIcon = (message: Thread) => {
        if (message.role === RoleType.User) {
            return <Person20Regular />;
        }
        if (message.type === ThreadType.Error) {
            return <ErrorCircle20Filled />;
        }
        if (message.type === ThreadType.Info) {
            return <Info20Regular />;
        }
        return <Sparkle20Regular />;
    };

    return (
        <div className="professional-chat-container-modern">
            <div className="chat-workspace-modern" ref={chatContainerRef}>
                {thread.length === 0 ? (
                    <div className="empty-state-modern">
                        <h2>Ready to explore your data?</h2>
                        <p>Ask me anything about your uploaded documents.</p>
                    </div>
                ) : (
                    <div className="chat-content-modern">
                        {messagesGroupedByRequestId.map((group, groupIndex) => {
                        // Filter out citation messages since they should be part of the answer
                        const mainMessages = group.filter(msg => msg.type !== ThreadType.Citation);
                        // Find citation data from citation messages
                        const citationMessages = group.filter(msg => msg.type === ThreadType.Citation);
                        const imageCitations = citationMessages.length > 0 ? citationMessages[0].imageCitations || [] : [];
                        const textCitations = citationMessages.length > 0 ? citationMessages[0].textCitations || [] : [];
                        
                        return (
                            <div key={groupIndex} className="conversation-group-modern">
                                {mainMessages.map((message, msgIndex) => {
                                    if (message.type === ThreadType.Answer) {
                                        messageToBeCopied[message.request_id] = message.answerPartial?.answer || "";
                                    }

                                    const isUser = message.role === RoleType.User;
                                    const isCopied = copiedMessages.has(message.request_id);
                                    const isLiked = likedMessages.has(message.request_id);
                                    const isDisliked = dislikedMessages.has(message.request_id);

                                return (
                                    <div 
                                        key={`${groupIndex}-${msgIndex}`}
                                        className={`message-container-modern ${isUser ? "user-message-container" : "assistant-message-container"}`}
                                    >
                                        <div className="message-avatar-modern">
                                            <Avatar
                                                icon={getMessageIcon(message)}
                                                size={40}
                                                color={isUser ? "brand" : "colorful"}
                                                className={`avatar-modern ${isUser ? "user-avatar" : "assistant-avatar"}`}
                                            />
                                        </div>
                                        
                                        <div className="message-content-wrapper-modern">
                                            <div className="message-header-modern">
                                                <div className="message-author-info">
                                                    <Text weight="semibold" className="author-name">
                                                        {isUser ? "You" : "AI Assistant"}
                                                    </Text>
                                                    <div className="message-meta">
                                                        <Caption1 className="timestamp">
                                                            <Clock20Regular className="clock-icon" />
                                                            {formatTimestamp()}
                                                        </Caption1>
                                                        {!isUser && message.type === ThreadType.Answer && (
                                                            <Badge 
                                                                color="success"
                                                                appearance="tint"
                                                                size="small"
                                                                className="status-badge"
                                                            >
                                                                AI Response
                                                            </Badge>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                            
                                            <Card className={`message-card-modern ${isUser ? "user-card" : "assistant-card"}`}>
                                                <CardPreview className="message-body-modern">
                                                    {message.type === ThreadType.Message && (
                                                        <Body1 className="message-text">
                                                            {message.message}
                                                        </Body1>
                                                    )}
                                                    
                                                    {message.type === ThreadType.Answer && (
                                                        <div 
                                                            className="answer-content-modern"
                                                            style={isUser ? { color: 'white' } : {}}
                                                        >
                                                            <ReactMarkdown
                                                                components={{
                                                                    p: ({ children }) => (
                                                                        <Body1 
                                                                            className="markdown-paragraph"
                                                                            style={isUser ? { color: 'white' } : {}}
                                                                        >
                                                                            {createCitationRenderer(textCitations, imageCitations)(children)}
                                                                        </Body1>
                                                                    ),
                                                                    h1: ({ children }) => (
                                                                        <Title2 
                                                                            className="markdown-h1"
                                                                            style={isUser ? { color: 'white' } : {}}
                                                                        >
                                                                            {children}
                                                                        </Title2>
                                                                    ),
                                                                    h2: ({ children }) => (
                                                                        <Title3 
                                                                            className="markdown-h2"
                                                                            style={isUser ? { color: 'white' } : {}}
                                                                        >
                                                                            {children}
                                                                        </Title3>
                                                                    ),
                                                                    h3: ({ children }) => (
                                                                        <Text 
                                                                            weight="semibold" 
                                                                            className="markdown-h3"
                                                                            style={isUser ? { color: 'white' } : {}}
                                                                        >
                                                                            {children}
                                                                        </Text>
                                                                    ),
                                                                    li: ({ children }) => (
                                                                        <Body1 
                                                                            className="markdown-li"
                                                                            style={isUser ? { color: 'white' } : {}}
                                                                        >
                                                                            {createCitationRenderer(textCitations, imageCitations)(children)}
                                                                        </Body1>
                                                                    ),
                                                                    strong: ({ children }) => (
                                                                        <Text 
                                                                            weight="bold"
                                                                            style={isUser ? { color: 'white' } : {}}
                                                                        >
                                                                            {children}
                                                                        </Text>
                                                                    ),
                                                                    em: ({ children }) => (
                                                                        <Text 
                                                                            italic
                                                                            style={isUser ? { color: 'white' } : {}}
                                                                        >
                                                                            {children}
                                                                        </Text>
                                                                    ),
                                                                    code: ({ children }) => <code className="inline-code">{children}</code>,
                                                                    pre: ({ children }) => <pre className="code-block">{children}</pre>,
                                                                    blockquote: ({ children }) => <div className="blockquote-modern">{children}</div>
                                                                }}
                                                                remarkPlugins={[remarkGfm]}
                                                            >
                                                                {message.answerPartial?.answer}
                                                            </ReactMarkdown>
                                                            {isTyping && msgIndex === group.length - 1 && (
                                                                <div className="typing-indicator">
                                                                    <Spinner size="tiny" />
                                                                    <Caption1>Processing...</Caption1>
                                                                </div>
                                                            )}
                                                        </div>
                                                    )}
                                                    
                                                    {message.type === ThreadType.Error && (
                                                        <MessageBar intent="error" className="error-message-modern">
                                                            <Body1>{message.message || "An error occurred."}</Body1>
                                                        </MessageBar>
                                                    )}
                                                    
                                                    {message.type === ThreadType.Info && (
                                                        <MessageBar intent="info" className="info-message-modern">
                                                            <Body1>{message.message}</Body1>
                                                        </MessageBar>
                                                    )}
                                                </CardPreview>

                                                {(message.type === ThreadType.Answer) && (imageCitations.length > 0 || textCitations.length > 0) && (
                                                    <CardFooter className="message-footer-modern">
                                                        <div className="message-actions-modern">
                                                            <div className="primary-actions">
                                                                <Tooltip content={isCopied ? "Copied!" : "Copy response"} relationship="label">
                                                                    <Button
                                                                        size="small"
                                                                        icon={isCopied ? <CheckmarkCircle20Filled /> : <Copy20Regular />}
                                                                        appearance="subtle"
                                                                        className={`action-button ${isCopied ? "copied" : ""}`}
                                                                        onClick={() => handleCopyMessage(message.request_id)}
                                                                    >
                                                                        {isCopied ? "Copied" : "Copy"}
                                                                    </Button>
                                                                </Tooltip>
                                                                
                                                                <Tooltip content="Share response" relationship="label">
                                                                    <Button
                                                                        size="small"
                                                                        icon={<Share20Regular />}
                                                                        appearance="subtle"
                                                                        className="action-button"
                                                                    >
                                                                        Share
                                                                    </Button>
                                                                </Tooltip>
                                                            </div>
                                                            
                                                            <div className="feedback-actions">
                                                                <Tooltip content={isLiked ? "Remove like" : "Like response"} relationship="label">
                                                                    <Button
                                                                        size="small"
                                                                        icon={<ThumbLike20Regular />}
                                                                        appearance="subtle"
                                                                        className={`feedback-button ${isLiked ? "liked" : ""}`}
                                                                        onClick={() => handleLikeMessage(message.request_id)}
                                                                    />
                                                                </Tooltip>
                                                                
                                                                <Tooltip content={isDisliked ? "Remove dislike" : "Dislike response"} relationship="label">
                                                                    <Button
                                                                        size="small"
                                                                        icon={<ThumbDislike20Regular />}
                                                                        appearance="subtle"
                                                                        className={`feedback-button ${isDisliked ? "disliked" : ""}`}
                                                                        onClick={() => handleDislikeMessage(message.request_id)}
                                                                    />
                                                                </Tooltip>
                                                                
                                                                <Tooltip content="View processing steps" relationship="label">
                                                                    <Button
                                                                        size="small"
                                                                        icon={<BrainCircuit20Regular />}
                                                                        appearance="subtle"
                                                                        className="action-button"
                                                                        disabled={!processingStepMsg?.[message.request_id] || processingStepMsg[message.request_id].length === 0}
                                                                        onClick={() => {
                                                                            setShowProcessingSteps(true);
                                                                            setProcessRequestId(message.request_id);
                                                                        }}
                                                                    >
                                                                        Steps
                                                                    </Button>
                                                                </Tooltip>
                                                                
                                                                <Tooltip content="More options" relationship="label">
                                                                    <Button
                                                                        size="small"
                                                                        icon={<MoreHorizontal20Regular />}
                                                                        appearance="subtle"
                                                                        className="action-button"
                                                                    />
                                                                </Tooltip>
                                                            </div>
                                                        </div>
                                                        
                                                        {(imageCitations.length > 0 || textCitations.length > 0) && (
                                                            <>
                                                                <Divider className="citations-divider" />
                                                                <div className="citations-section">
                                                                    <Citations
                                                                        imageCitations={imageCitations}
                                                                        textCitations={textCitations}
                                                                        highlightedCitation={highlightedCitation}
                                                                    />
                                                                </div>
                                                            </>
                                                        )}
                                                    </CardFooter>
                                                )}
                                            </Card>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                        );
                    })}
                    </div>
                )}
            </div>

            <ProcessingSteps
                showProcessingSteps={showProcessingSteps}
                processingStepMsg={getCurProcessingStep(processRequestId)}
                toggleEditor={() => {
                    setShowProcessingSteps(!showProcessingSteps);
                }}
            />

            {showCitationViewer && selectedCitation && (
                <CitationViewer
                    citation={selectedCitation}
                    onClose={() => {
                        setShowCitationViewer(false);
                        setSelectedCitation(undefined);
                    } } show={false} toggle={function (): void {
                        throw new Error("Function not implemented.");
                    } }                />
            )}
        </div>
    );
};

export default ProfessionalChatContent;
