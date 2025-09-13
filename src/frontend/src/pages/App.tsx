import { Caption1, FluentProvider, webDarkTheme, webLightTheme } from "@fluentui/react-components";
import { Title1 } from "@fluentui/react-components";
import { useEffect, useState } from "react";

import "./App.css";
import { Header } from "../components/layout/Header/Header";
import { NavBar } from "../components/layout/NavBar/NavBar";
import Samples from "../components/search/Samples/Samples";
import SearchInput from "../components/search/SearchInput/SearchInput";
import { TabNavigation } from "../components/layout/TabNavigation/TabNavigation";
import ProfessionalDocumentUpload from "../components/upload/DocumentUpload/DocumentUpload";
import Admin from "../components/admin/Admin";
import ProfessionalChatContent from "../components/chat/ChatContent/ChatContent";
import { ErrorBoundary } from "../components/shared/ErrorBoundary";
import { ThemeProvider, useTheme } from "../contexts";
import useChat from "../hooks/useChat";
import useConfig from "../hooks/useConfig";
import { INTRO_TITLE } from "@/constants";

function AppContent() {
    const { config, setConfig, indexes } = useConfig();
    const { thread, processingStepsMessage, chats, isLoading, handleQuery, onNewChat } = useChat(config);
    const { darkMode, setDarkMode } = useTheme();
    const [newQ, setnewQ] = useState(false);
    const [selectedTab, setSelectedTab] = useState("chat");
    const [isAdmin, setIsAdmin] = useState(false);

    useEffect(() => {
        // Fetch authoritative runtime config from backend
        (async () => {
            try {
                const url = '/api/runtime-config' + (import.meta.env.DEV ? `?t=${Date.now()}` : '');
                console.debug('[App] fetching runtime-config ->', url);
                const res = await fetch(url, { credentials: 'same-origin' });
                console.debug('[App] runtime-config response status', res.status);
                if (res.ok) {
                    const data = await res.json();
                    console.debug('[App] runtime-config payload', data);
                    setIsAdmin(Boolean(data?.isAdmin));
                } else {
                    console.warn('[App] runtime-config fetch failed', res.status, await res.text());
                }
            } catch (e) {
                // ignore and keep defaults
                console.warn('Failed to load runtime config', e);
            }
        })();
    }, []);

    const handleTabSelect = (tabId: string) => {
        setSelectedTab(tabId);
        if (tabId === "chat" && !thread.length && !newQ) {
            // Reset to intro state when switching to chat tab
            setnewQ(false);
        }
    };

    // isAdmin is fetched from server; fall back to runtime-injected value if present
    const injected = Boolean(window.__RUNTIME_CONFIG__?.['IS_ADMIN'] === true || window.__RUNTIME_CONFIG__?.['IS_ADMIN'] === 'true');
    const effectiveIsAdmin = isAdmin || injected;

    return (
        <FluentProvider theme={darkMode ? webDarkTheme : webLightTheme}>
            <div className="container">
                <Header darkMode={darkMode} toggleMode={setDarkMode} isAdmin={effectiveIsAdmin} />
                <TabNavigation selectedTab={selectedTab} onTabSelect={handleTabSelect} isAdmin={effectiveIsAdmin} />

                <div className="content-wrapper">
                    {selectedTab === "chat" ? (
                        <>
                            <NavBar 
                                config={config} 
                                indexes={indexes} 
                                setConfig={setConfig} 
                                onNewChat={onNewChat} 
                                chats={Object.values(chats || {})} 
                                isAdmin={effectiveIsAdmin}
                            />
                            
                            <div className="content">
                                {thread.length || newQ ? (
                                    <>
                                        {thread.length ? (
                                            <ProfessionalChatContent 
                                                thread={thread} 
                                                processingStepMsg={processingStepsMessage} 
                                                darkMode={darkMode} 
                                            />
                                        ) : null}
                                    </>
                                ) : (
                                    <>
                                        <div className="intro-card">
                                            <Title1 block align="center">
                                                {INTRO_TITLE}
                                            </Title1>
                                            <br />
                                            <Caption1 style={{ fontWeight: "bold" }} block align="center">
                                                Choose an example to start with...
                                            </Caption1>
                                            <Samples
                                                handleQuery={(q, isNew) => {
                                                    if (isNew) {
                                                        setnewQ(true);
                                                    } else {
                                                        handleQuery(q);
                                                    }
                                                }}
                                            />
                                        </div>
                                    </>
                                )}
                                {/* Always show search footer in the same position */}
                                <div className="search-footer">
                                    <SearchInput onSearch={handleQuery} isLoading={isLoading} />
                                </div>
                            </div>
                        </>
                    ) : selectedTab === "upload" && isAdmin ? (
                        <ErrorBoundary>
                            <ProfessionalDocumentUpload />
                        </ErrorBoundary>
                    ) : selectedTab === "admin" && isAdmin ? (
                        <ErrorBoundary>
                            <Admin />
                        </ErrorBoundary>
                    ) : null}
                </div>
            </div>
        </FluentProvider>
    );
}

function App() {
    return (
        <ErrorBoundary>
            <ThemeProvider>
                <AppContent />
            </ThemeProvider>
        </ErrorBoundary>
    );
}

export default App;
