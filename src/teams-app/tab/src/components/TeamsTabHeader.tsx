import { Avatar, Button, Subtitle2, Title3, Tooltip } from '@fluentui/react-components';
import { OpenRegular } from '@fluentui/react-icons';
import { motion } from 'framer-motion';
import clsx from 'clsx';

interface TeamsTabHeaderProps {
  userName?: string;
  entityId?: string;
  onOpenStandalone?: () => void;
  onReset?: () => void;
  isBusy?: boolean;
}

export function TeamsTabHeader({ userName, entityId, onOpenStandalone, onReset, isBusy }: TeamsTabHeaderProps) {
  const initials = userName ? userName[0]?.toUpperCase() : 'U';
  const title = entityId ? `Workspace • ${entityId}` : 'RAG Assistant Tab';

  return (
    <header className={clsx('tab-header')}>
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
        <Title3 className="tab-header__title">RAG Assistant</Title3>
        <Subtitle2 className="tab-header__subtitle">Insights from your multimodal knowledge base</Subtitle2>
      </motion.div>

      <div className="tab-header__actions">
        {onReset && (
          <Tooltip content="Clear the current answer" relationship="label">
            <Button appearance="secondary" onClick={onReset} disabled={isBusy}>
              Reset
            </Button>
          </Tooltip>
        )}

        {onOpenStandalone && (
          <Tooltip content="Open in full browser view" relationship="label">
            <Button icon={<OpenRegular />} appearance="subtle" onClick={onOpenStandalone}>
              Pop out
            </Button>
          </Tooltip>
        )}

        <Tooltip content={title} relationship="description">
          <Avatar name={userName ?? 'Teams user'} aria-label="Current user" color="colorful" size={32} className="tab-header__avatar">
            {initials}
          </Avatar>
        </Tooltip>
      </div>
    </header>
  );
}
