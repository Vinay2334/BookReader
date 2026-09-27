from functools import lru_cache

from openai import AsyncOpenAI
from supabase import AsyncClient, acreate_client

from .config import settings


@lru_cache
def _openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


def get_openai_client() -> AsyncOpenAI:
    return _openai_client()


async def get_supabase_client() -> AsyncClient:
    return await acreate_client(settings.supabase_url, settings.supabase_service_role_key)
