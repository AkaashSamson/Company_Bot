import asyncio
import logging
from unittest.mock import patch, MagicMock

import pytest
from fastapi import FastAPI
from app.main import lifespan, periodic_log_cleanup_task

@pytest.mark.asyncio
async def test_lifespan_starts_and_cancels_background_task(caplog):
    caplog.set_level(logging.INFO, logger="knowlayer")
    
    app = FastAPI()
    
    # We will patch init_orchestrator and initialize_persistence to avoid db setup
    with patch("app.main.init_orchestrator"), patch("app.infrastructure.persistence.factory.initialize_persistence"), patch("app.infrastructure.logging.conversation_log_cleanup.ConversationLogCleanup") as MockCleanup:
        
        async with lifespan(app):
            # The background task is now running and sleeping.
            await asyncio.sleep(0.01)
            
        # Once we exit the context block, lifespan will cancel the task.
        assert "Lifespan: shutdown." in caplog.text


@pytest.mark.asyncio
async def test_periodic_log_cleanup_task_executes_and_cancels(caplog):
    caplog.set_level(logging.INFO, logger="knowlayer")
    
    with patch("app.infrastructure.logging.conversation_log_cleanup.ConversationLogCleanup") as MockCleanup:
        mock_instance = MockCleanup.return_value
        
        # We mock the return value of cleanup_expired_logs
        mock_result = MagicMock()
        mock_result.deleted = 5
        mock_result.preserved = 10
        mock_result.failed = 0
        mock_instance.cleanup_expired_logs.return_value = mock_result
        
        # Start the task with an interval of 0 seconds
        task = asyncio.create_task(periodic_log_cleanup_task(interval_seconds=0))
        
        # Allow it to run one iteration
        await asyncio.sleep(0.01)
        
        # Verify the cleanup was called at least once
        mock_instance.cleanup_expired_logs.assert_called()
        
        # Cancel the task
        task.cancel()
        
        # Wait for cancellation to complete
        try:
            await task
        except asyncio.CancelledError:
            pass
            
        assert "Periodic conversation log cleanup task cancelled." in caplog.text
