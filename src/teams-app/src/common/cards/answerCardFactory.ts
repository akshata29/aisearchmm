import answerCardTemplate from '../../bot/cards/answerCard.json';
import type { RagCitation } from '../../types/rag';

interface AnswerCardInput {
  answer: string;
  citations: RagCitation[];
  deepLinkUrl?: string;
}

export function buildAnswerCard({ answer, citations, deepLinkUrl }: AnswerCardInput) {
  const card = JSON.parse(JSON.stringify(answerCardTemplate));

  const answerText = card.body.find((item: { id?: string }) => item.id === 'answerText');
  if (answerText) {
    answerText.text = answer;
  }

  const toggle = card.body.find((item: { id?: string }) => item.id === 'sourceToggle');
  const sourcesContainer = card.body.find((item: { id?: string }) => item.id === 'sourcesContainer');

  if (!citations.length) {
    if (toggle && typeof toggle === 'object') {
      card.body = card.body.filter((item: { id?: string }) => item.id !== 'sourceToggle');
    }
    if (sourcesContainer && typeof sourcesContainer === 'object') {
      sourcesContainer.isVisible = true;
      sourcesContainer.items = [
        {
          type: 'TextBlock',
          text: 'No sources provided.',
          isSubtle: true,
          wrap: true
        }
      ];
    }
  } else if (sourcesContainer && typeof sourcesContainer === 'object') {
    sourcesContainer.isVisible = false;
    sourcesContainer.items = citations.map((citation) => ({
      type: 'Container',
      spacing: 'Small',
      items: [
        {
          type: 'TextBlock',
          text: citation.title ?? citation.id,
          wrap: true,
          weight: 'Bolder'
        },
        citation.snippet
          ? {
              type: 'TextBlock',
              text: citation.snippet,
              wrap: true,
              isSubtle: true
            }
          : undefined,
        citation.url
          ? {
              type: 'ActionSet',
              actions: [
                {
                  type: 'Action.OpenUrl',
                  title: 'Open source',
                  url: citation.url
                }
              ]
            }
          : undefined
      ].filter(Boolean)
    }));
  }

  const actions = card.actions ?? [];
  const openInTabAction = actions.find((action: { id?: string }) => action.id === 'openInTab');
  const copyAction = actions.find((action: { id?: string }) => action.id === 'copyLink');

  if (openInTabAction) {
    if (deepLinkUrl) {
      openInTabAction.url = deepLinkUrl;
    } else {
      card.actions = actions.filter((action: { id?: string }) => action.id !== 'openInTab');
    }
  }

  if (copyAction) {
    const context = encodeURIComponent(
      JSON.stringify({
        locale: 'en-us',
        message: answer
      })
    );
    copyAction.url = `https://teams.microsoft.com/l/message/compose?context=${context}`;
  }

  return card;
}
