from app.use_cases.chat.query_orchestrator import QueryOrchestrator

from .formatter import format_response


def create_message_handler(orchestrator: QueryOrchestrator | None = None):
    chat_orchestrator = orchestrator or QueryOrchestrator()

    async def handle_message(ctx):
        question = (ctx.activity.text or "").strip()
        if not question:
            await ctx.send("Please send a question about the policy.")
            return

        result = chat_orchestrator.answer(question)
        await ctx.send(format_response(result))

    return handle_message