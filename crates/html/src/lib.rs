//! Minimal HTML utilities for Phase 3: a tiny parser that extracts linked CSS
//! and JS resources (link rel=stylesheet and script src=...) and a fetcher that
//! downloads those resources using the networking crate.

use regex::Regex;
use supernova_networking::HttpClient;
use supernova_url::Url;

#[derive(Debug, thiserror::Error)]
pub enum HtmlError {
    #[error("url error: {0}")]
    Url(#[from] supernova_url::UrlError),
    #[error("network error: {0}")]
    Network(#[from] supernova_networking::NetworkError),
}

pub struct HtmlFetcher {
    client: HttpClient,
}

impl HtmlFetcher {
    pub fn new(client: HttpClient) -> Self {
        Self { client }
    }

    /// Extract stylesheet and script URLs from HTML. Returns absolute URLs based on base_url.
    pub fn extract_resource_urls(&self, base_url: &str, html: &str) -> Result<Vec<String>, HtmlError> {
        let base = Url::parse(base_url)?.normalize();
        let mut urls = Vec::new();

        // regex to find <link ... rel="stylesheet" ... href="...">
        let link_re = Regex::new(r#"<link[^>]*rel=["']?stylesheet["']?[^>]*href=["']([^"']+)["']"#).unwrap();
        for cap in link_re.captures_iter(html) {
            let href = cap.get(1).unwrap().as_str();
            let abs = self.resolve_url(&base, href)?;
            urls.push(abs);
        }

        // regex to find <script ... src="...">
        let script_re = Regex::new(r#"<script[^>]*src=["']([^"']+)["']"#).unwrap();
        for cap in script_re.captures_iter(html) {
            let src = cap.get(1).unwrap().as_str();
            let abs = self.resolve_url(&base, src)?;
            urls.push(abs);
        }

        Ok(urls)
    }

    fn resolve_url(&self, base: &Url, ref_url: &str) -> Result<String, HtmlError> {
        // Very small relative resolution: if ref starts with http:// or https:// treat as absolute
        let trimmed = ref_url.trim();
        if trimmed.starts_with("http://") || trimmed.starts_with("https://") {
            return Ok(trimmed.to_string());
        }
        // If starts with '/', resolve against origin
        if trimmed.starts_with('/') {
            let port = if let Some(p) = base.port { p } else { match base.scheme.as_str() { "http" => 80, "https" => 443, _ => 0 } };
            if let Some(port_opt) = base.port {
                if (base.scheme == "http" && port_opt == 80) || (base.scheme == "https" && port_opt == 443) {
                    return Ok(format!("{}://{}{}", base.scheme, base.host, trimmed));
                }
                return Ok(format!("{}://{}:{}{}", base.scheme, base.host, port_opt, trimmed));
            }
            return Ok(format!("{}://{}{}", base.scheme, base.host, trimmed));
        }
        // else treat as relative path against base.path (very naive)
        let base_path = if base.path.ends_with('/') { base.path.clone() } else { format!("{}/", base.path) };
        let combined = format!("{}://{}{}{}", base.scheme, base.host, base_path, trimmed);
        Ok(combined)
    }

    /// Fetch resources found in the HTML. Returns Vec of Results either (url, bytes) or error.
    pub fn fetch_resources(&self, base_url: &str, html: &str) -> Vec<Result<(String, Vec<u8>), HtmlError>> {
        match self.extract_resource_urls(base_url, html) {
            Ok(urls) => urls.into_iter().map(|u| self.client.get(&u).map(|(_s, b)| (u, b)).map_err(HtmlError::Network)).collect(),
            Err(e) => vec![Err(e)],
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = r#"
    <html>
    <head>
        <link rel="stylesheet" href="/styles/main.css">
        <link rel='stylesheet' href='https://cdn.example.com/lib.css'>
    </head>
    <body>
        <script src="/scripts/app.js"></script>
        <script src='https://cdn.example.com/lib.js'></script>
    </body>
    </html>
    "#;

    #[test]
    fn extract_resources() {
        let client = HttpClient::new();
        let fetcher = HtmlFetcher::new(client);
        let urls = fetcher.extract_resource_urls("https://example.com/", SAMPLE).unwrap();
        assert!(urls.contains(&"https://example.com/styles/main.css".to_string()));
        assert!(urls.contains(&"https://cdn.example.com/lib.css".to_string()));
        assert!(urls.contains(&"https://example.com/scripts/app.js".to_string()));
        assert!(urls.contains(&"https://cdn.example.com/lib.js".to_string()));
    }
}
