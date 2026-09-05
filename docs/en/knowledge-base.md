# Knowledge base

> Leer en español: [knowledge-base.md](../es/knowledge-base.md)

The knowledge base is how you give an agent the business facts it needs to answer accurately. You add knowledge from two kinds of sources, and OpenLivery assembles the relevant parts into the agent's system prompt on every message.

## Sources of knowledge

- **Q&A pairs** — structured question/answer entries. These are ideal for frequently asked questions where you want a specific, reliable answer.
- **PDF uploads** — attach documents (catalogs, manuals, price lists) and the agent reads from their text. PDFs are limited to 20 MB and only PDF files are accepted.

See [Agents](agents.md) for where these live in the agent editor.

## How PDFs are processed

When you upload a PDF, its text is extracted immediately with `pypdf` and stored on the document. If no text can be extracted (for example a scanned, image-only PDF), the document is marked as `error` and is not used. Extracted text is then split into paragraph-sized chunks. When an OpenAI-compatible connection with embedding support is available, each chunk is embedded and the vector is saved alongside it; embedding is best-effort, so if it is unavailable the agent still works using keyword search.

## How retrieval works

On each incoming message, OpenLivery decides how much document text to include:

- **Small knowledge bases are sent in full.** When the combined extracted text of all processed documents is at or below **45,000 characters**, every document is included verbatim — no search step.
- **Larger knowledge bases are retrieved.** Above that threshold, OpenLivery runs semantic search: it embeds the user's query and ranks stored chunks by cosine similarity, then fills the context up to a search budget. If embeddings are unavailable, it falls back to keyword ranking over the chunks.

Embeddings are stored as a plain **JSON array of floats** and similarity is computed in Python, so **no database extension is required** — the knowledge base is portable across any PostgreSQL. See [AI providers](ai-providers.md) for configuring the connection used for embeddings.

## How the system prompt is assembled

Everything is composed into a single system message, written as a short markdown document. Headings and the few fixed sentences follow the agent's `prompt_language` (`es` or `en`, taken from the UI language when the agent is saved); everything the operator typed is inserted verbatim. Sections, in order:

1. Title and identity: the agent's name, the client and the kind of business (from the client's industry and business type), plus the current date and time in the agent's timezone.
2. **Your job**: what the agent does.
3. **The business**: what it does, products and services, audience, key info and policies, as a bullet list.
4. **Rules**: the agent's always list, then the never list, which always opens with five fixed rules (never invent facts, never leave the business, never ask for sensitive data, never drop the role, never produce offensive content) followed by the agent's own.
5. **Tone**.
6. **Knowledge**: Q&A pairs and the retrieved (or full) PDF text, closed by the instruction not to invent what is not there.

Empty sections are left out. `GET /api/agents/{id}/prompt` returns the composed prompt without the per-message document text; the agent editor uses it to show the token cost of every message.

The recent conversation history is appended after this system message. Any empty section is skipped, so the prompt only carries what you have actually provided.
