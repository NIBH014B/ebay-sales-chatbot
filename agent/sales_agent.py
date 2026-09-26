"""Google ADK agent and conversation runner."""

from __future__ import annotations

import os
import asyncio

from google.genai import types
from agent.prompts import SALES_ANALYST_INSTRUCTIONS
from services.data_service import DataService
from services.jev_service import JevIntentService, fallback_intent
from tools.sales_tools import build_tools


def build_agent(data_service: DataService):
    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("Set GOOGLE_API_KEY in your .env file to enable Gemini.")
    try:
        from google.adk.agents import Agent
    except ImportError as exc:
        raise RuntimeError("Google ADK is not installed. Install dependencies from requirements.txt.") from exc
    return Agent(
        name="sales_data_intelligence_analyst",
        model=os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest"),
        description="Answers sales and product questions using verified repository data.",
        instruction=SALES_ANALYST_INSTRUCTIONS,
        tools=build_tools(data_service, include_extended=False),
        generate_content_config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=512,
        ),
    )


class AgentChat:
    def __init__(self, data_service: DataService, user_id: str = "streamlit-user", session_id: str = "sales-chat") -> None:
        try:
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService
        except ImportError as exc:
            raise RuntimeError("Google ADK is not installed. Install dependencies from requirements.txt.") from exc
        self.user_id = user_id
        self.session_id = session_id
        self.session_service = InMemorySessionService()
        self.agent = build_agent(data_service)
        self.runner = Runner(agent=self.agent, app_name="sales_intelligence", session_service=self.session_service)
        self.jev = None
        if os.getenv("TYPESAFE_API_KEY"):
            try:
                self.jev = JevIntentService()
            except RuntimeError:
                self.jev = None
        self._session_ready = False

    async def ask(self, question: str) -> str:
        from google.genai import types

        routed_question = question
        if self.jev:
            try:
                routing = await asyncio.to_thread(self.jev.classify, question)
            except Exception:
                routing = fallback_intent(question)
        else:
            routing = fallback_intent(question)
        if float(routing.get("confidence", 0)) >= 0.6:
            routed_question = f"{question}\n\nIntent routing hint: {routing['intent']} (confidence {routing['confidence']:.2f}, source {routing.get('source', 'jev')})."

        if not self._session_ready:
            await self.session_service.create_session(app_name="sales_intelligence", user_id=self.user_id, session_id=self.session_id)
            self._session_ready = True
        final_text = ""
        async for event in self.runner.run_async(
            user_id=self.user_id,
            session_id=self.session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=routed_question)]),
        ):
            if event.is_final_response() and event.content:
                final_text = "".join(part.text or "" for part in event.content.parts)
        return final_text or "I could not produce a response. Please try a more specific question."