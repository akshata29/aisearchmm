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
}

export const TabNavigation = ({ selectedTab, onTabSelect }: TabNavigationProps) => {
    const handleTabSelect = (_event: SelectTabEvent, data: SelectTabData) => {
        onTabSelect(data.value as string);
    };

    return (
        <div className="tab-navigation">
            <TabList selectedValue={selectedTab} onTabSelect={handleTabSelect}>
                <Tab value="chat">Chat</Tab>
                <Tab value="upload">Upload Documents</Tab>
                <Tab value="admin">Admin</Tab>
            </TabList>
        </div>
    );
};
