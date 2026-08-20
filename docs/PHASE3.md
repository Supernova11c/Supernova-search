# docs/PHASE3.md

Phase 3 (HTML) design notes

- Current implementation includes a minimal resource extractor that finds
  <link rel="stylesheet"> and <script src=> attributes and resolves
  relative URLs to absolute URLs relative to the document's origin/path.
- The tokenizer and parser will be expanded into a full state-machine-based
  implementation in subsequent commits.
