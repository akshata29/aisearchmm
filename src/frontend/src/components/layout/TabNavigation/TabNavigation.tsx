import {
    Tab,
    TabList,
    SelectTabData,
    SelectTabEvent,
} from "@fluentui/react-components";

import "./TabNavigation.css";

interface TabNavigationProps {
    selectedTab: string;
    onTabSelect: (tabId: string) => void;
    isAdmin?: boolean;
}

export const TabNavigation = ({ selectedTab, onTabSelect, isAdmin }: TabNavigationProps) => {
    const handleTabSelect = (_event: SelectTabEvent, data: SelectTabData) => {
        onTabSelect(data.value as string);
    };

    return (
        <div className="tab-navigation">
            <TabList selectedValue={selectedTab} onTabSelect={handleTabSelect}>
                <Tab value="chat">Chat</Tab>
                <Tab value="teams">Teams Integration</Tab>
                {isAdmin && <Tab value="upload">Upload Documents</Tab>}
                {isAdmin && <Tab value="feedback">Feedback</Tab>}
                {isAdmin && <Tab value="admin">Admin</Tab>}
            </TabList>
        </div>
    );
};
