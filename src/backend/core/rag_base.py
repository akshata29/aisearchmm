import logging
import json
import os
import time
from typing import List
import uuid
from abc import ABC, abstractmethod
from enum import Enum
from aiohttp import web
import instructor
from openai import AsyncAzureOpenAI
from retrieval.grounding_retriever import GroundingRetriever
from core.models import (
    AnswerFormat,
    SearchConfig,
    GroundingResult,
    GroundingResults,
)
from core.processing_step import ProcessingStep

logger = logging.getLogger("rag")


class MessageType(Enum):
    ANSWER = "answer"
    CITATION = "citation"
    LOG = "log"
    ERROR = "error"
    END = "[END]"
    ProcessingStep = "processing_step"
    INFO = "info"


class RagBase(ABC):
    def __init__(
        self,
        openai_client: AsyncAzureOpenAI,
        chatcompletions_model_name: str,
    ):
        self.openai_client = openai_client
        self.chatcompletions_model_name = chatcompletions_model_name

    async def _handle_request(self, request: web.Request):
        request_params = await request.json()
        search_text = request_params.get("query", "")
        chat_thread = request_params.get("chatThread", [])
        config_dict = request_params.get("config", {})
        search_config = SearchConfig(
            chunk_count=config_dict.get("chunk_count", 10),
            openai_api_mode=config_dict.get("openai_api_mode", "chat_completions"),
            use_semantic_ranker=config_dict.get("use_semantic_ranker", False),
            use_streaming=config_dict.get("use_streaming", False),
            use_knowledge_agent=config_dict.get("use_knowledge_agent", False),
            # Enhanced Knowledge Agent configurations
            recency_preference_days=config_dict.get("recency_preference_days", 365),
            query_complexity=config_dict.get("query_complexity", "medium"),
            preferred_document_types=config_dict.get("preferred_document_types", []),
            enable_post_processing_boost=config_dict.get("enable_post_processing_boost", True),
            additional_filters=config_dict.get("additional_filters", []),
        )
        request_id = request_params.get("request_id", str(int(time.time())))
        response = await self._create_stream_response(request)
        
        try:
            await self._process_request(
                request_id, response, search_text, chat_thread, search_config
            )
        except Exception as e:
            logger.error(f"Error processing request: {str(e)}")
            # Always send processing step to show what went wrong
            try:
                await self._send_processing_step_message(
                    request_id,
                    response,
                    ProcessingStep(
                        title="Request processing failed",
                        type="code",
                        description=f"An error occurred during request processing: {str(e)}",
                        content={
                            "error": str(e),
                            "query": search_text,
                            "config": search_config
                        }
                    ),
                )
            except Exception as step_error:
                logger.error(f"Failed to send error processing step: {str(step_error)}")
            
            await self._send_error_message(request_id, response, str(e))

        await self._send_end(response)
        return response

    @abstractmethod
    async def _process_request(
        self,
        request_id: str,
        response: web.StreamResponse,
        search_text: str,
        chat_thread: list,
        search_config: SearchConfig,
    ):
        pass

    async def _formulate_response(
        self,
        request_id: str,
        response: web.StreamResponse,
        messages: list,
        grounding_retriever: GroundingRetriever,
        grounding_results: GroundingResults,
        search_config: SearchConfig,
    ):
        """Handles streaming chat completion and sends citations."""

        logger.info("Formulating LLM response")
        await self._send_processing_step_message(
            request_id,
            response,
            ProcessingStep(title="LLM Payload", type="code", content=messages),
        )

        complete_response: dict = {}

        try:
            if search_config.get("use_streaming", False):
                logger.info("Streaming chat completion")
                chat_stream_response = instructor.from_openai(
                    self.openai_client,
                ).chat.completions.create_partial(
                    stream=True,
                    model=self.chatcompletions_model_name,
                    response_model=AnswerFormat,
                    messages=messages,
                )
                msg_id = str(uuid.uuid4())

                async for stream_response in chat_stream_response:
                    if stream_response.answer is not None:
                        await self._send_answer_message(
                            request_id, response, msg_id, stream_response.answer
                        )
                        complete_response = stream_response.model_dump()
                if len(complete_response.keys()) == 0:
                    raise ValueError("No response received from chat completion stream.")

            else:
                logger.info("Waiting for chat completion")
                chat_completion = await instructor.from_openai(
                    self.openai_client,
                ).chat.completions.create(
                    stream=False,
                    model=self.chatcompletions_model_name,
                    response_model=AnswerFormat,
                    messages=messages,
                )
                msg_id = str(uuid.uuid4())

                if chat_completion is not None:
                    await self._send_answer_message(
                        request_id, response, msg_id, chat_completion.answer
                    )
                    complete_response = chat_completion.model_dump()
                else:
                    raise ValueError("No response received from chat completion stream.")
                
        except Exception as llm_error:
            # Always send processing step even if LLM fails
            await self._send_processing_step_message(
                request_id,
                response,
                ProcessingStep(
                    title="LLM Error", 
                    type="code", 
                    description=f"LLM processing encountered an error: {str(llm_error)}",
                    content={
                        "error": str(llm_error),
                        "llm_model": self.chatcompletions_model_name,
                        "message_count": len(messages),
                        "grounding_results_count": len(grounding_results.get('references', []))
                    }
                ),
            )
            # Re-raise the error so it can be handled by the calling method
            raise
            
        # Always send LLM response processing step (even for "cannot answer" responses)
        await self._send_processing_step_message(
            request_id,
            response,
            ProcessingStep(
                title="LLM response", 
                type="code", 
                description=f"LLM generated response. Answer length: {len(complete_response.get('answer', ''))} characters",
                content=complete_response
            ),
        )

        # Always try to extract and send citations, even if answer is "cannot answer"
        try:
            await self._extract_and_send_citations(
                request_id,
                response,
                grounding_retriever,
                grounding_results["references"],
                complete_response["text_citations"] or [],
                complete_response["image_citations"] or [],
            )
        except Exception as citation_error:
            await self._send_processing_step_message(
                request_id,
                response,
                ProcessingStep(
                    title="Citation extraction failed", 
                    type="code", 
                    description=f"Failed to extract citations: {str(citation_error)}",
                    content={
                        "error": str(citation_error),
                        "text_citations": complete_response.get("text_citations", []),
                        "image_citations": complete_response.get("image_citations", [])
                    }
                ),
            )
            # Don't re-raise citation errors, just log them

    async def _extract_and_send_citations(
        self,
        request_id: str,
        response: web.StreamResponse,
        grounding_retriever: GroundingRetriever,
        grounding_results: List[GroundingResult],
        text_citation_ids: list,
        image_citation_ids: list,
    ):
        """Extracts and sends citations from search results."""
        citations = await self.extract_citations(
            grounding_retriever,
            grounding_results,
            text_citation_ids,
            image_citation_ids,
        )

        await self._send_citation_message(
            request_id,
            response,
            request_id,
            citations.get("text_citations", []),
            citations.get("image_citations", []),
        )

    @abstractmethod
    async def extract_citations(
        self,
        grounding_retriever: GroundingRetriever,
        grounding_results: List[GroundingResult],
        text_citation_ids: list,
        image_citation_ids: list,
    ) -> dict:
        pass

    async def _create_stream_response(self, request):
        """Creates and prepares the SSE stream response."""
        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "text/event-stream",
                "Connection": "keep-alive",
                "Cache-Control": "no-cache, no-transform",
            },
        )
        await response.prepare(request)
        return response

    async def _send_error_message(
        self, request_id: str, response: web.StreamResponse, message: str
    ):
        """Sends an error message through the stream."""
        await self._send_message(
            response,
            MessageType.ERROR.value,
            {
                "request_id": request_id,
                "message_id": str(uuid.uuid4()),
                "message": message,
            },
        )

    async def _send_info_message(
        self,
        request_id: str,
        response: web.StreamResponse,
        message: str,
        details: str = None,
    ):
        """Sends an info message through the stream."""
        await self._send_message(
            response,
            MessageType.INFO.value,
            {
                "request_id": request_id,
                "message_id": str(uuid.uuid4()),
                "message": message,
                "details": details,
            },
        )

    async def _send_processing_step_message(
        self,
        request_id: str,
        response: web.StreamResponse,
        processing_step: ProcessingStep,
    ):
        logger.info(
            f"Sending processing step message for step: {processing_step.title}"
        )
        step_data = {
            "request_id": request_id,
            "message_id": str(uuid.uuid4()),
            "processingStep": processing_step.to_dict(),
        }
        
        try:
            await self._send_message(
                response,
                MessageType.ProcessingStep.value,
                step_data
            )
            logger.info(f"Successfully sent processing step: {processing_step.title}")
        except Exception as e:
            logger.error(f"Failed to send processing step '{processing_step.title}': {str(e)}")
            raise

    async def _send_answer_message(
        self,
        request_id: str,
        response: web.StreamResponse,
        message_id: str,
        content: str,
    ):
        await self._send_message(
            response,
            MessageType.ANSWER.value,
            {
                "request_id": request_id,
                "message_id": message_id,
                "role": "assistant",
                "answerPartial": {"answer": content},
            },
        )

    async def _send_citation_message(
        self,
        request_id: str,
        response: web.StreamResponse,
        message_id: str,
        text_citations: list,
        image_citations: list,
    ):

        await self._send_message(
            response,
            MessageType.CITATION.value,
            {
                "request_id": request_id,
                "message_id": message_id,
                "textCitations": text_citations,
                "imageCitations": image_citations,
            },
        )

    async def _send_message(self, response, event, data):
        try:
            await response.write(
                f"event:{event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")
            )
        except ConnectionResetError:
            # TODO: Something is wrong here, the messages attempted and failed here is not what the UI sees, thats another set of stream...
            # logger.warning("Connection reset by client.")
            pass
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    async def _send_end(self, response):
        await self._send_message(response, MessageType.END.value, {})

    def attach_to_app(self, app, path):
        """Attaches the handler to the web app."""
        app.router.add_post(path, self._handle_request)
