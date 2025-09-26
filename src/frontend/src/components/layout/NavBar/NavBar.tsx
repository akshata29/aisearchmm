import { Dispatch, SetStateAction, useState } from "react";

import { Button, Tooltip } from "@fluentui/react-components";
import { ChatAddRegular } from "@fluentui/react-icons";
import { Hamburger, NavDrawer, NavDrawerHeader, NavSectionHeader } from "@fluentui/react-nav-preview";

import { Chat } from "../../../api/models";
import "./NavBar.css";
import SearchSettings, { SearchConfig } from "../../search/SearchSettings/SearchSettings";

interface Props {
    config: SearchConfig;
    chats: Chat[];
    onNewChat: () => void;
    setConfig: Dispatch<SetStateAction<SearchConfig>>;
    isAdmin?: boolean;
}

export const NavBar = ({ setConfig, onNewChat, config, isAdmin: propIsAdmin }: Props) => {
    const injected = Boolean(window.__RUNTIME_CONFIG__?.['IS_ADMIN'] === true || window.__RUNTIME_CONFIG__?.['IS_ADMIN'] === 'true');
    const isAdmin = typeof propIsAdmin === 'boolean' ? propIsAdmin : injected;
    // For admin sessions, keep settings expanded by default. Non-admins start collapsed since they have no settings to show.
    const [isOpen, setIsOpen] = useState(Boolean(isAdmin));

    const getToolTipContent = () => {
        if (!isAdmin) {
            return isOpen ? "Close Menu" : "Open Menu";
        }
        return isOpen ? "Close Settings" : "Open Settings";
    };

    return (
        <>
            <NavDrawer open={isOpen} type={"inline"} className="menu">
                <div className="menu-items">
                    <Button appearance="secondary" icon={<ChatAddRegular />} className="custom-menu-item new-chat" onClick={onNewChat}>
                        New Chat
                    </Button>
                    {isAdmin && (
                        <div className="menu-item-settings">
                            <NavSectionHeader>Search Settings</NavSectionHeader>
                            <div className="custom-menu-item">
                                <SearchSettings config={config} setConfig={setConfig} />
                            </div>
                        </div>
                    )}
                </div>
            </NavDrawer>
            <NavDrawerHeader style={{ width: "25px" }}>
                <Tooltip content={getToolTipContent()} relationship="label">
                    <Hamburger onClick={() => setIsOpen(!isOpen)} />
                </Tooltip>
            </NavDrawerHeader>
        </>
    );
};
