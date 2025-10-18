import { ChangeEvent, FormEvent, useEffect, useState } from 'react';
import { Button, Field, Input, Tooltip } from '@fluentui/react-components';
import { Search24Regular } from '@fluentui/react-icons';
import clsx from 'clsx';

interface SearchFormProps {
  defaultQuery?: string;
  onSubmit: (query: string) => void;
  isBusy?: boolean;
}

const HINTS = [
  'How does our multimodal RAG pipeline work?',
  'Show recent citations about market themes',
  'Summarize the latest compliance guidance'
];

export function SearchForm({ defaultQuery = '', onSubmit, isBusy }: SearchFormProps) {
  const [value, setValue] = useState(defaultQuery);
  const [hintIndex, setHintIndex] = useState(0);

  useEffect(() => {
    setValue(defaultQuery);
  }, [defaultQuery]);

  const handleChange = (_: ChangeEvent<HTMLInputElement>, data: { value: string }) => {
    setValue(data.value);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) {
      return;
    }
    onSubmit(trimmed);
  };

  const handleHintClick = () => {
    const nextIndex = (hintIndex + 1) % HINTS.length;
    setHintIndex(nextIndex);
    setValue(HINTS[nextIndex]);
  };

  return (
    <form className={clsx('search-form')} onSubmit={handleSubmit}>
      <Field size="large" label="Ask the assistant" className="search-form__field">
        <Input
          value={value}
          onChange={handleChange}
          placeholder="Ask about strategy, documents, or recent insights"
          contentAfter={
            <Tooltip content="Generate another suggestion" relationship="label">
              <Button appearance="subtle" onClick={handleHintClick} type="button" size="small">
                Shuffle
              </Button>
            </Tooltip>
          }
        />
      </Field>
      <Button type="submit" appearance="primary" size="large" icon={<Search24Regular />} disabled={isBusy}>
        Ask
      </Button>
    </form>
  );
}
