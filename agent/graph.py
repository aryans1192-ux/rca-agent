import os
import logging
from typing import Optional
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

DEBUG = os.getenv("RCA_DEBUG", "0") == "1"
log = logging.getLogger("rca.agent")

from agent.state import AgentState
from services.rca_service import rca_service
from core.prompts import SYSTEM_PROMPT

load_dotenv()


@tool
def get_problem_hours(city: str = "", store: str = "", date: str = "2026-04-22") -> str:
    """List all OR2A problem hours for a city, store, or date. Leave city/store blank for all."""
    return rca_service.get_problem_hours_summary(date=date, city=city, store=store)


@tool
def run_rca_for_store(store: str, date: str = "2026-04-22", hour: Optional[int] = None) -> str:
    """Run full RCA for a store. Omit hour for all problem hours, or pass specific hour (0-23). Never pass text like 'morning' — omit hour instead."""
    return rca_service.run_store_rca(store=store, date=date, hour=hour if hour is not None else -1)


@tool
def get_city_summary(city: str, date: str = "2026-04-22") -> str:
    """Get weighted day-level summary for a city: orders, breach rate, avg OR2A, problem hours."""
    return rca_service.get_city_summary(city=city, date=date)


@tool
def list_cities(date: str = "2026-04-22") -> str:
    """List all cities available in the dataset."""
    return rca_service.list_cities(date=date)


@tool
def list_stores_in_city(city: str, date: str = "2026-04-22") -> str:
    """List all stores in a city with problem hour flags."""
    return rca_service.list_stores(city=city, date=date)


ALL_TOOLS = [get_problem_hours, run_rca_for_store, get_city_summary, list_cities, list_stores_in_city]


def build_graph(mcp_tools: list = None):
    llm = ChatGroq(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0,
    )
    tools = mcp_tools if mcp_tools else ALL_TOOLS
    llm_with_tools = llm.bind_tools(tools)

    def agent_node(state: AgentState):
        messages = state["messages"]
        if not any(isinstance(m, SystemMessage) for m in messages):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages

        if DEBUG:
            for m in messages:
                if isinstance(m, ToolMessage):
                    log.debug("TOOL RESULT [%s]: %s", m.tool_call_id, m.content[:200])

        response = llm_with_tools.invoke(messages)

        if DEBUG:
            if hasattr(response, "tool_calls") and response.tool_calls:
                for tc in response.tool_calls:
                    log.debug("TOOL CALL: %s(%s)", tc["name"], tc["args"])
            else:
                log.debug("FINAL ANSWER (%d chars)", len(response.content))

        return {"messages": [response]}

    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()
