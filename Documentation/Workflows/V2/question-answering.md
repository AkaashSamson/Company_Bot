# Question-Answering Workflow

Chat uses trusted identity and optional project selection to constrain retrieval before the LLM is called.

1. Streamlit sends the question, conversation history, and optional project ID to `POST /api/chat`.
2. The route resolves the authenticated principal and asks authorization for the active project set.
3. An omitted project selects all projects authorized for the principal; an explicit project is intersected with that set. An unauthorized selection returns `403` before retrieval.
4. The retrieval service passes only the resulting project IDs to Chroma. Document metadata supplies project and document identity.
5. Selected evidence is assembled into the bounded LLM context. The provider generates an answer only from that evidence.
6. Citations are built from the same selected evidence and returned to Streamlit.

Inactive or unknown principals and users with no authorized projects receive no restricted evidence.
