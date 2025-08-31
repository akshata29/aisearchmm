import { EventSourceMessage, fetchEventSource } from "@microsoft/fetch-event-source";

import { SearchConfig } from "../components/search/SearchSettings/SearchSettings";

const sendChatApi = async (
    message: string,
    requestId: string,
    chatThread: any,
    config: SearchConfig,
    onMessage: (message: EventSourceMessage) => void,
    onError?: (err: unknown) => void
) => {
    const endpoint = "/chat";

    await fetchEventSource(endpoint, {
        openWhenHidden: true,
        method: "POST",
        body: JSON.stringify({ query: message, request_id: requestId, chatThread: chatThread, config }),
        onerror: onError,
        onmessage: onMessage
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
