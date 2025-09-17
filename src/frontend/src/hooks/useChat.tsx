import { useState, useEffect } from "react";
import { sendChatApi } from "../api/api";
import { Thread, ProcessingStepsMessage, Chat, ThreadType, RoleType } from "../api/models";
import { SearchConfig } from "../components/search/SearchSettings/SearchSettings";

// Custom hook for managing chat state
export default function useChat(config: SearchConfig) {
    const [chatId, setChatId] = useState<string>();
    const [thread, setThread] = useState<Thread[]>([]);
    const [processingStepsMessage, setProcessingStepsMessage] = useState<Record<string, ProcessingStepsMessage[]>>({});
    const [chats, setChats] = useState<Record<string, Chat>>();
    const [isLoading, setIsLoading] = useState<boolean>(false);

    const refreshChats = async () => {
        setChats({});
    };

    const handleQuery = async (query: string) => {
        setIsLoading(true);
        const request_id = new Date().getTime().toString();
        
        try {
            if (!chatId) setChatId(request_id);

            // Create chat thread based on history setting
            let chatThread: any[];
            if (config.use_chat_history) {
                // Use last 10 chat conversations (Q&A pairs) for context
                const lastMessages = thread
                    .filter(message => message.role === "user" || message.role === "assistant")
                    .slice(-20) // Get last 20 messages (approximately 10 Q&A pairs)
                    .map(msg => ({
                        role: msg.role,
                        content: [
                            {
                                text: msg.role === "assistant" ? msg.answerPartial?.answer : msg.message,
                                type: "text"
                            }
                        ]
                    }));
                chatThread = lastMessages;
            } else {
                // Only use current query without history
                chatThread = [];
            }

            setThread(prevThread => {
                const newThread = [...prevThread, { request_id, type: ThreadType.Message, message: query, role: RoleType.User }];
                return newThread;
            });

            refreshChats();

            await sendChatApi(
                query,
                request_id,
                chatThread,
                config,
                message => {
                    if (message.event === "processing_step") {
                        setProcessingStepsMessage(steps => {
                            const newStep = JSON.parse(message.data);
                            const updatedSteps = { ...steps };
                            updatedSteps[newStep.request_id] = [...(steps[newStep.request_id] || []), newStep];
                            return updatedSteps;
                        });
                    } else if (message.event === "[END]") {
                        setIsLoading(false);
                    } else {
                        const data = JSON.parse(message.data);
                        data.type = message.event;

                        setThread(prevThread => {
                            const index = prevThread.findIndex(msg => msg.message_id === data.message_id);
                            const newThread = index !== -1 ? [...prevThread] : [...prevThread, data];
                            if (index !== -1) newThread[index] = data;

                            newThread.sort((a, b) => new Date(a.request_id).getTime() - new Date(b.request_id).getTime());
                            refreshChats();

                            return newThread;
                        });
                    }
                },
                err => {
                    console.error('Chat stream error:', err);
                    
                    // Handle timeout errors specifically
                    const errorMessage = err instanceof Error ? err.message : 'Chat request failed';
                    const isTimeout = errorMessage.includes('timed out') || errorMessage.includes('timeout');
                    
                    // Add error message to thread
                    setThread(prevThread => [...prevThread, {
                        request_id: request_id,
                        type: ThreadType.Error,
                        message: isTimeout 
                            ? 'Request timed out. Large documents may need more time to process. Please try again or contact support.'
                            : 'Chat request failed. Please try again.',
                        role: RoleType.Assistant
                    }]);
                    
                    setIsLoading(false);
                }
            );
        } catch (err) {
            console.error('Chat error:', err);
            
            // Handle any other errors
            const errorMessage = err instanceof Error ? err.message : 'An unexpected error occurred';
            const isTimeout = errorMessage.includes('timed out') || errorMessage.includes('timeout');
            
            setThread(prevThread => [...prevThread, {
                request_id: request_id,
                type: ThreadType.Error,
                message: isTimeout 
                    ? 'Request timed out. Large documents may need more time to process. Please try again or contact support.'
                    : 'An unexpected error occurred. Please try again.',
                role: RoleType.Assistant
            }]);
        } finally {
            setIsLoading(false);
        }
    };

    const onNewChat = () => {
        setChatId(undefined);
        setThread([]);
    };

    useEffect(() => {
        refreshChats();
    }, [config]);

    return { chatId, thread, processingStepsMessage, chats, isLoading, handleQuery, onNewChat };
}
