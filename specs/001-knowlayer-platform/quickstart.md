# Quickstart: KnowLayer MVP 1

## Prerequisites

- Python 3.11+
- A virtual environment
- Access to an OpenRouter API key
- Optional Groq API key for fallback testing
- A local HR policy document placed in the documents folder

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy the environment template:
   ```bash
   copy .env.example .env
   ```
4. Fill in the required API keys and local configuration values.

## Ingest the source document

```bash
python scripts/ingest_documents.py
```

Expected result: the HR policy document is parsed, chunked, and loaded into Chroma DB.

## Run the app

```bash
streamlit run streamlit_app/app.py
```

Expected result: the Streamlit chat UI loads and can accept policy questions.

## Validate the flow

1. Open the chat UI.
2. Ask a question such as: "What is the annual leave policy?"
3. Confirm the answer is grounded in the policy document and includes citations.
4. Ask a question outside the document scope.
5. Confirm the system responds clearly that the information is not present in the current source.

## Expected outcomes

- The app answers from the approved HR policy document.
- Retrieval uses Chroma DB.
- Responses contain citations and source grounding.
- The flow is lightweight and easy to validate during MVP 1.
