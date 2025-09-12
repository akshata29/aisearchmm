import asyncio
import os
from app import create_app

def _get_loop_policy():
    # Use SelectorEventLoop on Windows to avoid aiodns issues
    if os.name == 'nt':
        try:
            return asyncio.WindowsSelectorEventLoopPolicy()
        except Exception:
            return None
    return None

loop_policy = _get_loop_policy()
if loop_policy is not None:
    asyncio.set_event_loop_policy(loop_policy)

async def _app():
    return await create_app()

# Gunicorn with aiohttp expects a module-level `app` that is either an Application or a coroutine returning one.
app = asyncio.get_event_loop().run_until_complete(_app())
