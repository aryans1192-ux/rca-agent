import sys
import os
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp.server.fastmcp import FastMCP
from services.rca_service import rca_service

mcp = FastMCP("rca-agent", port=8001)

DEFAULT_DATE = "2026-04-22"


@mcp.tool()
def get_problem_hours(city: str = "", store: str = "", date: str = DEFAULT_DATE) -> str:
    """
    List all problem hours (OR2A SLA breached) for a given city, store, or date.
    Leave city or store blank to get a city-level summary across all locations.
    """
    return rca_service.get_problem_hours_summary(date=date, city=city, store=store)


@mcp.tool()
def run_rca_for_store(store: str, date: str = DEFAULT_DATE) -> str:
    """
    Run full RCA (demand spike, pileup, supply L1/L2) for a specific store — returns all problem hours.
    To discuss a specific time range like morning or evening, call this tool then filter in your response.
    """
    return rca_service.run_store_rca(store=store, date=date, hour=-1)


@mcp.tool()
def get_city_summary(city: str, date: str = DEFAULT_DATE) -> str:
    """
    Weighted day-level summary for a city: total orders, breach rate, avg OR2A, problem hours.
    Breach rate and OR2A are weighted by order volume as per the RCA playbook.
    """
    return rca_service.get_city_summary(city=city, date=date)


@mcp.tool()
def list_cities(date: str = DEFAULT_DATE) -> str:
    """List all cities available in the dataset for a given date."""
    return rca_service.list_cities(date=date)


@mcp.tool()
def list_stores_in_city(city: str, date: str = DEFAULT_DATE) -> str:
    """List all stores in a city with problem hour counts."""
    return rca_service.list_stores(city=city, date=date)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", default="stdio", choices=["stdio", "streamable-http"])
    args = parser.parse_args()
    mcp.run(transport=args.transport)
