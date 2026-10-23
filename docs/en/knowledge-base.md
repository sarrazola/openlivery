# Knowledge base

> Leer en español: [knowledge-base.md](../es/knowledge-base.md)

The knowledge base is how you give an agent the business facts it needs to answer accurately. You add knowledge from two kinds of sources, and OpenLivery assembles the relevant parts into the agent's system prompt on every message.

## Sources of knowledge

- **Q&A pairs** — structured question/answer entries. These are ideal for frequently asked questions where you want a specific, reliable answer.
- **PDF uploads** — attach documents (catalogs, manuals, price lists) and the agent reads from their text. PDFs are limited to 20 MB and only PDF files are accepted.

See [Agents](agents.md) for where these live in the agent editor.

## Files the agent can send

Not everything a business wants the agent to use is text. A product photo, a catalog or a price list is something the customer asks to *see*, so the Knowledge tab also has **Files to send**: a small library per agent, separate from the documents above. Nothing in it is read, chunked or indexed. Each file carries a **name** and a short note on **when to send it** ("when they ask to see the chair or its colors"), and that is all the model ever sees.

An agent with at least one file gets a built-in tool, `send_file`, whose choices are those names, with the rules for using it appended to the system prompt in the agent's language: send only what fits, one at a time unless asked for several, never resend one already sent in the conversation, never promise a file that is not in the list. When the model calls it, the file leaves as a message attachment through the conversation's channel (WhatsApp, Instagram, Messenger, the web widget and the playground), after the text of the reply, the same way files returned by [HTTP tools](custom-tools.md) do; the bytes never enter the model's context.

Images are normalized on upload: resized so the longest side is 1600 px and re-encoded as JPEG, or PNG when the image is transparent. WebP is not kept even though it is smaller, because the WhatsApp Cloud API accepts it only for stickers and Instagram messaging rejects it. PDFs are stored as uploaded. Limits: 30 files per agent, images up to 10 MB before normalization, PDFs up to 20 MB. Routes: `GET`/`POST /api/agents/{id}/media`, `PATCH`/`DELETE /api/agents/{id}/media/{asset_id}` and `GET /api/agents/{id}/media/{asset_id}/content` for the preview.

## How PDFs are processed

When you upload a PDF, its text is extracted immediately with `pypdf` and stored on the document. If no text can be extracted (for example a scanned, image-only PDF), the document is marked as `error` and is not used. Extracted text is then split into paragraph-sized chunks. When the agency has an OpenRouter key, each chunk is embedded with the agent's **embedding model** (`openai/text-embedding-3-small` by default, chosen in the Knowledge tab from OpenRouter's embedding catalog) and the vector is saved alongside it, tagged with the model that produced it; embedding is best-effort, so if it is unavailable the agent still works using keyword search. Vectors from different models are not comparable, so changing the model reindexes every document of the agent, and **Reindex documents** repairs uploads that were indexed without a working key.

## How retrieval works

On each incoming message, OpenLivery decides how much document text to include:

- **Small knowledge bases are sent in full.** When the combined extracted text of all processed documents is at or below **45,000 characters**, every document is included verbatim — no search step.
- **Larger knowledge bases are retrieved.** Above that threshold, OpenLivery runs semantic search: it embeds the user's query with the agent's model and ranks the chunks indexed with that same model by cosine similarity, keeping the ten best and dropping any that scores well below the top match, within a search budget. If embeddings are unavailable, it falls back to keyword ranking over the chunks.

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
