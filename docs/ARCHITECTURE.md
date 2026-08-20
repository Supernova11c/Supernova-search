Phase 1-3 architecture

This file explains the minimal workspace and the role of each crate for Phases 1-3.

Crates:
- crates/url: minimal URL parsing, normalization, and origin representation.
- crates/core: core runtime utilities (Config, logging initialization, ResourceManager, BrowserProcess).
- crates/browser: tiny example binary that wires core + url + networking + html to demonstrate fetching.
- crates/networking: minimal HTTP client wrapper (blocking) for HTTP/HTTPS, redirects, and compression.
- crates/html: minimal HTML tokenizer/parser that can extract stylesheet and script references and fetch them.

Goals completed in this push:
- Rust workspace with independent crates
- Basic URL parsing
- Core runtime utilities and logging
- Networking client for fetching resources (HTTP/HTTPS)
- Simple HTML parser that extracts linked CSS/JS and a fetcher to retrieve them
- Unit tests for key components

Limitations and next steps are documented inline in each crate.
