from langchain.memory import ConversationWindowBufferMemory


class SessionMemory:
    def __init__(self, k: int = 6):
        self.memory = ConversationWindowBufferMemory(k=k, memory_key="chat_history", return_messages=True)

    def add_user_message(self, message: str):
        self.memory.chat_memory.add_user_message(message)

    def add_ai_message(self, message: str):
        self.memory.chat_memory.add_ai_message(message)

    def get_history(self):
        return self.memory.load_memory_variables({})
