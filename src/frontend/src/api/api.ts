import { EventSourceMessage, fetchEventSource } from "@microsoft/fetch-event-source";

import { SearchConfig } from "../components/search/SearchSettings/SearchSettings";
import { TIMEOUTS } from "../constants/app";

const sendChatApi = async (
    message: string,
    requestId: string,
    chatThread: any,
    config: SearchConfig,
    onMessage: (message: EventSourceMessage) => void,
    onError?: (err: unknown) => void
) => {
    const endpoint = "/chat";

    // Create AbortController for timeout handling
    const controller = new AbortController();
    
    // Set up timeout - use PROCESSING timeout for chat as it involves complex operations
    const timeoutId = setTimeout(() => {
        controller.abort();
    }, TIMEOUTS.PROCESSING);
    
    // Enhanced error handler that clears timeout and handles abort
    const enhancedErrorHandler = (error: any) => {
        clearTimeout(timeoutId);
        
        if (controller.signal.aborted) {
            const timeoutError = new Error('Chat request timed out. Large document processing may need more time.');
            console.error('Chat API Timeout:', timeoutError);
            onError?.(timeoutError);
        } else {
            console.error('Chat API Stream Error:', error);
            onError?.(error);
        }
    };
    
    // Enhanced message handler that clears timeout on END event
    const enhancedMessageHandler = (message: EventSourceMessage) => {
        if (message.event === '[END]') {
            clearTimeout(timeoutId);
        }
        onMessage(message);
    };

    await fetchEventSource(endpoint, {
        openWhenHidden: true,
        method: "POST",
        body: JSON.stringify({ query: message, request_id: requestId, chatThread: chatThread, config }),
        signal: controller.signal,
        onerror: enhancedErrorHandler,
        onmessage: enhancedMessageHandler
    });
};

const listIndexes = async () => {
    const response = await fetch(`/list_indexes`);

    return await response.json();
};

const getCitationDocument = async (fileName: string) => {
    const response = await fetch(`/get_citation_doc`, {
        method: "POST",
        body: JSON.stringify({ fileName })
    });

    return await response.json();
};

const deleteIndex = async () => {
    const tryCall = async (path: string) => {
        const res = await fetch(path, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cascade: true })
        });
        const raw = await res.text();
        let out: any = {};
        try { out = raw ? JSON.parse(raw) : {}; } catch { out = { error: raw }; }
        return { res, out };
    };

    // Prefer namespaced route in dev/prod, but fall back if unavailable
    let { res, out } = await tryCall(`/api/delete_index`).catch(() => ({ res: undefined as any, out: { error: 'network' } }));
    if (!res || res.status === 404 || res.status === 405) {
        ({ res, out } = await tryCall(`/delete_index`));
    }
    if (!res.ok) {
        throw new Error(out?.error || `Failed to delete index (HTTP ${res.status})`);
    }
    return out;
};

export { sendChatApi, listIndexes, getCitationDocument, deleteIndex };
