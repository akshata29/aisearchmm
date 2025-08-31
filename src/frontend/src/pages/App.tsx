import { Caption1, FluentProvider, webDarkTheme, webLightTheme } from "@fluentui/react-components";
import { Title1 } from "@fluentui/react-components";

import "./App.css";
import { Header } from "../components/layout/Header/Header";
import { NavBar } from "../components/layout/NavBar/NavBar";
import Samples from "../components/search/Samples/Samples";
import SearchInput from "../components/search/SearchInput/SearchInput";
import { TabNavigation } from "../components/layout/TabNavigation/TabNavigation";
import ProfessionalDocumentUpload from "../components/upload/DocumentUpload/DocumentUpload";
import useChat from "../hooks/useChat";
import useConfig from "../hooks/useConfig";
import useTheme from "../hooks/useTheme";
import { IntroTitle } from "../api/defaults";
import { useState } from "react";
import ProfessionalChatContent from "../components/chat/ChatContent/ChatContent";

function App() {
    const { config, setConfig, indexes } = useConfig();
    const { thread, processingStepsMessage, chats, isLoading, handleQuery, onNewChat } = useChat(config);
    const { darkMode, setDarkMode } = useTheme();
    const [newQ, setnewQ] = useState(false);
    const [selectedTab, setSelectedTab] = useState("chat");

    const handleTabSelect = (tabId: string) => {
        setSelectedTab(tabId);
        if (tabId === "chat" && !thread.length && !newQ) {
            // Reset to intro state when switching to chat tab
            setnewQ(false);
        }
    };

    return (
        <FluentProvider theme={darkMode ? webDarkTheme : webLightTheme}>
            <div className="container">
                <Header darkMode={darkMode} toggleMode={setDarkMode} />
                <TabNavigation selectedTab={selectedTab} onTabSelect={handleTabSelect} />

                <div className="content-wrapper">
                    {selectedTab === "chat" ? (
                        <>
                            <NavBar config={config} indexes={indexes} setConfig={setConfig} onNewChat={onNewChat} chats={Object.values(chats || {})} />
                            
                            <div className="content">
                                {thread.length || newQ ? (
                                    <>
                                        {thread.length ? <ProfessionalChatContent thread={thread} processingStepMsg={processingStepsMessage} /> : <></>}
                                    </>
                                ) : (
                                    <>
                                        <div className="intro-card">
                                            <Title1 block align="center">
                                                {IntroTitle}
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
                    ) : (
                        <ProfessionalDocumentUpload />
                    )}
                </div>
            </div>
        </FluentProvider>
    );
}

export default App;
