# Reverse Logistics Control Tower

A local-first Python application for monitoring reusable assets, shipments, returns, repairs, and custody events. It combines a Streamlit dashboard, SQLite operational data, deterministic business rules, and a locally hosted Qwen model with retrieval-augmented generation (RAG).

## Features

- Operational dashboard for reusable assets, shipments, returns, and repairs.
- Exception monitoring and shipment investigation.
- Synthetic data generation with a reproducible random seed.
- SQLite-based operational storage with read-only dashboard and assistant access.
- Local AI assistant using Ollama and Qwen.
- Local business-rule retrieval using ChromaDB and Ollama embeddings.
- Evaluation metrics, ground-truth checks, and automated tests.

## Architecture

- **Language:** Python
- **UI:** Streamlit
- **Operational database:** SQLite
- **Local LLM runtime:** Ollama
- **Language model:** Qwen (`qwen3.5:4b`)s
- **Embeddings:** `nomic-embed-text`
- **Vector store:** ChromaDB
- **Retrieval:** Local RAG over logistics business-rule documents

Business rules and database queries provide the operational evidence. The LLM explains that evidence; its output should be verified before operational decisions are made.

## Requirements

- Python 3.9 or a compatible Python version.
- Ollama installed locally.
- The Qwen and embedding models downloaded in Ollama.
- Python dependencies listed in `requirements.txt`.

## Setup

Clone or download the repository, then open its root directory in a terminal.

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install Python dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Download the local models:

```bash
ollama pull qwen3.5:4b
ollama pull nomic-embed-text
```

Ensure Ollama is running locally before using AI features.

## Generate synthetic data

Generate a test database with 20,000 reusable assets, 10,000 shipments, and 10,000 custody events:

```bash
python generate_data.py \
  --assets 20000 \
  --shipments 10000 \
  --events 10000 \
  --seed 20261022 \
  --output data/generated/reverse_logistics_test.db
```

The generator refuses to overwrite an existing output database. Use a new output filename for each test run.

For the validated large dataset, the project has also been tested with 100,000 custody events. Confirm the database path and record counts before launching the dashboard.

## Run the dashboard

```bash
streamlit run main.py
```

Open the local address printed by Streamlit in your browser.

## Run tests

From the project root, with the virtual environment activated:

```bash
python -m unittest discover -s tests -v
```

Use the project's validation and evaluation modules to check database integrity, business rules, and detection metrics.

## Data and privacy

The intended configuration is local-first: the application uses local SQLite data, Ollama, and a local vector store. No remote LLM API key is required for the configured local workflow.

Generated databases, local vector-store files, virtual environments, and secrets should not be committed to version control.

## Limitations

- Synthetic data is for development and evaluation, not a representation of a real logistics operation.
- Potential-delay indicators do not prove that a delivery commitment was missed.
- LLM answers can be incomplete or incorrect; verify important findings against the database and documented rules.
- Model availability and response speed depend on the local machine and Ollama configuration.

## License

Add a license before distributing this project publicly.
