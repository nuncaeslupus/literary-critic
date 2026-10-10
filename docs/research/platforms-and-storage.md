# Platforms and storage: persisting a project folder across chatbots

Research date: 2026-10-10. Confidence tags: [V] verified on a vendor page this session; [S] secondary/third-party source; [K] background knowledge, not re-verified (the Google developer docs host was unreachable from the sandbox). Vendor features change monthly; re-check before building on any [S]/[K] item.

## Bottom line

- Only one path works identically in every chatbot: the user is the transport. A single **project zip** (or a few files) is uploaded at session start and the chatbot hands back a downloadable zip/files at the end. Drive is then just where the user keeps the zip.
- Native Drive write exists but is uneven. ChatGPT: yes, gated by OAuth scope and admin setting. Claude: creates/edits Google Docs/Sheets/Slides natively; writing arbitrary files (JSON, zip) to Drive is unconfirmed. Gemini: reads Drive well, writing arbitrary files back is unconfirmed.
- Design the tool so that all state lives in one self-contained folder with a manifest, can be exported to a single zip, and can be re-imported by an uploaded script. Treat Drive connectors as an optional accelerator.

## 1. ChatGPT (Plus/Pro/Business)

- **Read from Drive:** yes. The Google Drive app reads files and folders the connected account can open [V: OpenAI help, Drive app]. Content is indexed, so changes can lag [V].
- **Write to Drive:** yes in principle. Create/update/move/share/delete actions need the broader Google Drive OAuth scope and must be enabled in the workspace; without admin approval a user can view but gets an authorization error on update [V]. Defaults are inconsistent across OpenAI pages (on by default for Business per one note, off until admin enables per others) [V, conflicting]. Aug 13 2026 release note: Drive was added to Library and ChatGPT can update the source file directly where supported; Shared Drives were excluded at launch [V]. Third-party claims that write is impossible [S, Fast.io, a vendor of an alternative] appear outdated.
- **Code Interpreter / data analysis:** works on files uploaded in the chat (or attached from Drive, which copies them into the sandbox). The sandbox has no direct Drive mount and no general internet [K]. Whether a connector-attached file is exposed to Python as a path is not documented; assume upload semantics.
- **Download of produced files:** yes, the sandbox produces a download link for zips/files (links expire with the sandbox session) [K].
- **Projects persistence:** project files persist across chats in that project; reported caps are about 20-25 files per project at ~30-40 MB each, varying by plan [S: elephas, northlabapps]. No verified Plus-vs-Pro split. Files in Projects are read-only context; ChatGPT cannot update them in place, so edits must go out as downloads.
- **Practical:** best native Drive round-trip of the three, but needs admin/scope consent. Fall back to zip upload.

## 2. Claude.ai (Pro/Max/Team)

- **Drive connector (read):** reads/searches Drive files for context [V: Anthropic announcement; S].
- **Write:** Anthropic's Oct 2026 beta Google connectors for **Docs, Sheets, Slides** let Claude create and edit those native Google files from chat, honoring Google sharing permissions [V]. A Claude for Google Workspace sidebar add-on (Marketplace, all paid plans) edits the open file in place and offers "suggestion cards" in Docs, with Ask-before-edits / Accept-all modes [V]. Whether the plain Drive connector saves arbitrary generated files (JSON, zip) is contradicted across third-party pages [S]: treat as unsupported.
- **Code execution / file creation:** with "Code execution and file creation" enabled, Claude runs Python/bash in a sandbox, can read uploaded files, run uploaded .py scripts (and unzip), and produce downloadable files (docx, md, zip) [K]. Sandbox has restricted network [K].
- **Projects knowledge:** persistent files per project; large knowledge triggers RAG automatically; sources disagree on caps (30 MB/file; ~200k tokens before RAG) [S]. Read-only to Claude; Claude cannot rewrite project files.
- **Claude Code (cloud sessions):** can reach Drive only through an MCP server/connector the user configures (the session docs describe adding connectors) [K]; not available by default. A git repo (GitHub attached to the session) is the natural persistence layer for developers, but not for non-technical users.
- **Practical:** zip round-trip for the folder; use Docs connector for human-facing reports (reports as native Google Docs the author can comment on).

## 3. Gemini (web/app, Google AI Pro/Ultra, Workspace)

- **Read:** native "@Google Drive" / Workspace connection; Gems accept Drive files as knowledge and use the latest version of the Drive file [V: Google support Gems page; a blog disputes this [S]]. Shared Gems store their files in a Drive folder [V]. Requires Workspace connected to Gemini Apps and activity setting on [V].
- **Write:** can export responses to Docs/Sheets and "save to Drive" for generated documents [K]; no verified way to overwrite an existing JSON/zip in a Drive folder from the consumer app. Apps Script/API workflows can write but are developer-only [V: Medium walkthrough].
- **Code execution:** Python sandbox in Gemini app for analysis and charts; file output as downloads/Docs/Sheets, uploads accepted [K]. Upload file-count limits per prompt are small (about 10) [K], favoring a single zip, but zip support in Gemini upload is unreliable; fallback is pasting a consolidated markdown.
- **Practical:** Gem + Drive folder for read-only inputs (manuscript snapshot, index), and a consolidated text export for returns.

## 4. Best pattern per chatbot (non-technical user)

| Chatbot | Primary | Fallback |
|---|---|---|
| ChatGPT | Drive app (if write scope approved) so ChatGPT updates files; else Project holding latest zip | Upload zip, download zip, replace file in Drive/Project by hand |
| Claude.ai | Project knowledge = latest `project.zip` + the tool script; code execution runs the script; user downloads result zip | Docs connector for reports |
| Gemini | Gem pointed at Drive folder (read) | Paste/upload consolidated export, save outputs to Docs/Drive manually |
| Any | **Drive for desktop** syncs a local folder, so the user drags the downloaded zip/files into it. This is the universal, vendor-neutral "persistence" step | |

Tool requirements that follow: single-command `pack` and `unpack` (zip with manifest, version, content hashes); idempotent merge when an older zip is re-imported; tolerate chatbots that return only changed files (delta zips); human-readable markdown reports so Gemini/ChatGPT can work without running code; each session begins "load folder, print state summary".

## 5. Google Docs API: comments and suggestions

- **Suggestions:** the Docs API reads suggestions (`suggestionsViewMode`, `suggestedInsertionIds`, etc.) and can hand you the document with all suggestions accepted or rejected [V: Google docs "Work with comments and suggestions", via search]. Creating suggest-mode edits is **not supported** in the stable `documents.batchUpdate` as far as I know (edits apply directly) [K]; the guide mentions Developer Preview features for managing comment/suggestion threads which I could not read, so check the current page and preview terms before ruling it out. Claude's and Gemini's in-Docs UIs create suggestions only inside their own sidebars.
- **Comments:** done through the Drive API v3 `comments.create`, not the Docs API. The `anchor` field accepts JSON but for Google Docs the anchor is not honored: comments appear as unanchored (or "original content deleted") rather than attached to a text range; only the editor UI makes true anchors [K; S: MCP server vendor claim]. Workaround: quote the target text in the comment body (`quotedFileContent` is stored but display is not guaranteed anchored), or add a `[[c1]]` marker; or write a report doc and insert **named ranges**/footnote-style markers via batchUpdate.
- **Pragmatic alternative:** produce a .docx with real comments/tracked changes (section 6) and let the user upload it to Drive; Docs imports Word comments and tracked changes as comments and suggestions. This is the dependable way to get suggestions into Google Docs [K].

## 6. .docx comments and tracked changes with the stdlib

Feasible with `zipfile` + `xml.etree.ElementTree`/`re`; no third-party dependencies needed.

- **Comments:** add `word/comments.xml` (`<w:comments>` with `<w:comment w:id w:author w:date w:initials>` containing `<w:p>`); register it in `[Content_Types].xml` (`application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml`) and `word/_rels/document.xml.rels` (type `.../relationships/comments`). In `document.xml` wrap the range with `<w:commentRangeStart w:id>`, `<w:commentRangeEnd w:id>` and follow with a run containing `<w:commentReference w:id>` (style `CommentReference` optional).
- **Tracked changes:** `<w:ins w:id w:author w:date><w:r><w:t>..</w:t></w:r></w:ins>` and `<w:del ...><w:r><w:delText xml:space="preserve">..</w:delText></w:r></w:del>`. Deleted text must use `w:delText`, not `w:t`.
- **Pitfalls:**
  - Anchors fall inside runs: the target text is often split across several `<w:r>` with differing `rPr`; you must split runs at offsets and copy `rPr` to both halves. Always set `xml:space="preserve"`.
  - IDs: `w:id` of comments, ins, del, bookmarks live in overlapping spaces; keep one monotonically increasing counter to be safe.
  - Preserve namespaces: ElementTree rewrites prefixes (`ns0:`) and drops unused declarations such as `mc:Ignorable` targets (`w14`, `w15`), which makes Word report corruption. Register all namespaces up front, or edit by string/regex surgery on the raw XML.
  - Preserve everything else in the zip byte-for-byte; write `[Content_Types].xml` first and use deflate.
  - Modern Word also uses `commentsExtended.xml`/`commentsIds.xml` for threading; plain `comments.xml` is enough for flat comments. Google Docs and LibreOffice accept it.
  - Comments crossing paragraphs, tables, or existing ins/del need care; restrict v1 to single-paragraph anchors and reject others loudly.
- **Reading paragraphs reliably:** iterate `w:p` in body order (including inside `w:tbl` and `w:sdt`); concatenate `w:t` plus `w:tab` (tab), `w:br`/`w:cr` (newline), `w:noBreakHyphen`; skip `w:delText` unless you want the "original" view and include `w:ins` content for the "final" view; fields appear as `w:fldChar`/`w:instrText` runs (skip instrText; the cached result between `separate` and `end` is the visible text) or `w:fldSimple`; hyperlinks wrap runs in `w:hyperlink`. Footnotes/endnotes are in `word/footnotes.xml`/`endnotes.xml`, referenced from body by `w:footnoteReference w:id`; ids -1/0 are separator notes. Also `mc:AlternateContent` (text boxes) can duplicate text in Choice and Fallback: read only one.
- Store a stable paragraph key (index + hash of normalized text) in the JSON index so annotations survive re-extraction.

## 7. Public-domain novels as fixtures (MIT repo)

- **Project Gutenberg** (EN and ES; e.g. Don Quijote in Spanish, Pride and Prejudice in English). Texts are public domain in the US; the "Project Gutenberg" trademark license applies to the boilerplate. Free redistribution is allowed; if you keep the PG name, the license text must stay with the work, and commercial redistribution under the trademark needs permission [V: gutenberg.org/policy/license, via search summary]. Cleanest approach: strip the header/footer and the name entirely (permitted under the "without the trademark" path), keep a short NOTICE/source line, and use only works verified public domain in the US (pre-1929 publication or author long dead). Spanish translations may be separately copyrighted: choose works originally in Spanish, or old translations.
- **Wikisource** (es/en): text is typically CC BY-SA 4.0 for the wiki contribution layer even when the work itself is public domain [K]. ShareAlike conflicts with a clean MIT story; avoid or isolate under a `fixtures/third_party/` folder with its own LICENSE.
- **Biblioteca Virtual Miguel de Cervantes:** reuse conditions vary per edition (digital editions carry the institutional rights notice); not verified here [unverified]. Do not vendor; reference by URL only.
- **Recommendation:** keep fixtures short (a chapter, not a novel), originate from Gutenberg, add `fixtures/README` with title, author, death year, source URL, and "public domain in the US; not covered by the repo MIT license". Alternatively generate synthetic text for CI and download real novels in an optional script. Spanish works that are safe: Cervantes (Quijote), Galdós, Clarín (La Regenta), Pardo Bazán; English: Austen, Dickens, Wilde.

## Sources

- OpenAI, Google Drive app and setup in ChatGPT: https://help.openai.com/en/articles/10929079-google-drive-app-and-setup-in-chatgpt
- OpenAI, Managing app permissions: https://help.openai.com/en/articles/20001495-managing-app-permissions-in-chatgpt
- OpenAI, File storage and Library: https://help.openai.com/en/articles/20001052
- OpenAI release notes: https://help.openai.com/en/articles/6825453
- Fast.io, Can ChatGPT upload files to Drive [S, vendor]: https://fast.io/resources/can-chatgpt-upload-files-to-google-drive.md
- ChatGPT Projects limits [S]: https://elephas.app/resources/chatgpt-projects-limits-files-size-and-how-many-projects
- Anthropic, Claude works with Google Docs, Sheets, Slides: https://claude.com/blog/claude-now-works-in-google-docs-sheets-and-slides
- Claude Projects limits [S]: https://northlabapps.com/blog/claude-projects-explained/
- Google, Use Gems in Gemini Apps: https://support.google.com/gemini/answer/15146780
- Medium, Gemini code execution with Drive via Apps Script: https://medium.com/google-cloud/stop-looking-for-pdf-tools-how-i-use-gemini-code-execution-to-edit-pdfs-in-google-drive-with-apps-5bf4a471ef7b
- Google Docs API, Work with comments and suggestions: https://developers.google.com/workspace/docs/api/how-tos/suggestions
- Project Gutenberg License: https://www.gutenberg.org/policy/license
- Project Gutenberg Permissions: https://gutenberg.org/policy/permission
- ECMA-376 / Open XML WordprocessingML (comments, ins, del): https://learn.microsoft.com/en-us/office/open-xml/word/working-with-comments (background)
