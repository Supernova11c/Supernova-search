# docs/PHASE2.md

Phase 2 (Networking) design notes

- Current implementation uses reqwest blocking client as a reliable starting point.
- Later we will replace the implementation with our own HTTP parser, connection pool,
  TLS integration using rustls, and explicit support for HTTP/2/3.

APIs provided:
- networking::HttpClient::new()
- networking::HttpClient::get(url) -> Result<(status_code, bytes), NetworkError>
