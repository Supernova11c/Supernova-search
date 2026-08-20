//! Minimal networking client for Phase 2. This wraps `reqwest` blocking
//! client to perform HTTP/HTTPS requests, follow redirects, and handle
//! compression. In later phases this will be replaced with our own
//! implementation (HTTP parser, TLS integration, etc.).

use reqwest::blocking::Client;
use reqwest::StatusCode;
use std::time::Duration;

#[derive(Debug, thiserror::Error)]
pub enum NetworkError {
    #[error("reqwest error: {0}")]
    Reqwest(#[from] reqwest::Error),
}

pub struct HttpClient {
    client: Client,
}

impl HttpClient {
    pub fn new() -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(20))
            .redirect(reqwest::redirect::Policy::limited(10))
            .build()
            .expect("failed to build reqwest client");
        Self { client }
    }

    /// Perform a GET request for the given URL and return (status_code, body_bytes)
    pub fn get(&self, url: &str) -> Result<(u16, Vec<u8>), NetworkError> {
        let resp = self.client.get(url).send()?;
        let status = resp.status().as_u16();
        let bytes = resp.bytes()?.to_vec();
        Ok((status, bytes))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn build_client() {
        let c = HttpClient::new();
        // not making network requests in unit tests
        assert!(c.client.timeout() == Some(Duration::from_secs(20)));
    }
}
