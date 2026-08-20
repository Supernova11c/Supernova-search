//! Minimal URL parsing, normalization, and origin representation for Phase 1.
//!
//! This crate intentionally implements a very small subset of URL parsing to
//! satisfy Phase 1 requirements. It is not a full implementation of the
//! URL Standard.

use std::fmt;

/// A parsed URL with a small, well-tested subset of fields.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Url {
    pub scheme: String,
    pub host: String,
    pub port: Option<u16>,
    pub path: String,
}

/// An origin as defined by scheme + host + effective port.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Origin {
    pub scheme: String,
    pub host: String,
    pub port: u16,
}

#[derive(Debug, thiserror::Error)]
pub enum UrlError {
    #[error("empty input")]
    Empty,
    #[error("invalid URL: {0}")]
    Invalid(String),
}

impl fmt::Display for Url {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if let Some(port) = self.port {
            write!(f, "{}://{}:{}{}", self.scheme, self.host, port, self.path)
        } else {
            write!(f, "{}://{}{}", self.scheme, self.host, self.path)
        }
    }
}

impl Url {
    /// Parse a very small subset of URLs: `<scheme>://<host>[:port][/<path>]`
    pub fn parse(input: &str) -> Result<Self, UrlError> {
        let s = input.trim();
        if s.is_empty() {
            return Err(UrlError::Empty);
        }
        // Find scheme
        let scheme_end = s.find("://").ok_or_else(|| UrlError::Invalid(s.to_string()))?;
        let scheme = &s[..scheme_end].to_lowercase();
        let rest = &s[scheme_end + 3..];
        // Split host[:port] and path
        let mut host_port = rest;
        let mut path = "/";
        if let Some(slash_idx) = rest.find('/') {
            host_port = &rest[..slash_idx];
            path = &rest[slash_idx..];
        }
        // Check for port
        let (host, port) = if let Some(colon_idx) = host_port.rfind(':') {
            // naive: treat the last ':' as port separator
            let p = &host_port[colon_idx + 1..];
            if !p.is_empty() && p.chars().all(|c| c.is_ascii_digit()) {
                let host = &host_port[..colon_idx];
                let port: u16 = p.parse().map_err(|_| UrlError::Invalid(s.to_string()))?;
                (host.to_lowercase(), Some(port))
            } else {
                (host_port.to_lowercase(), None)
            }
        } else {
            (host_port.to_lowercase(), None)
        };

        Ok(Url {
            scheme: scheme.to_string(),
            host,
            port,
            path: path.to_string(),
        })
    }

    /// Normalize the URL according to a tiny set of rules used in Phase 1.
    /// - scheme and host to lowercase
    /// - remove default ports (http:80, https:443)
    pub fn normalize(mut self) -> Self {
        if let Some(p) = self.port {
            if (self.scheme == "http" && p == 80) || (self.scheme == "https" && p == 443) {
                self.port = None;
            }
        }
        if self.path.is_empty() {
            self.path = "/".to_string();
        }
        self
    }

    /// Compute the origin of the URL.
    pub fn origin(&self) -> Origin {
        let default_port = match self.scheme.as_str() {
            "http" => 80,
            "https" => 443,
            _ => 0,
        };
        Origin {
            scheme: self.scheme.clone(),
            host: self.host.clone(),
            port: self.port.unwrap_or(default_port),
        }
    }
}

impl Origin {
    pub fn is_same_origin(&self, other: &Origin) -> bool {
        self.scheme == other.scheme && self.host == other.host && self.port == other.port
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_simple_http() {
        let u = Url::parse("http://example.com/path").unwrap();
        assert_eq!(u.scheme, "http");
        assert_eq!(u.host, "example.com");
        assert_eq!(u.port, None);
        assert_eq!(u.path, "/path");
    }

    #[test]
    fn parse_with_port_and_normalize() {
        let u = Url::parse("HTTP://Example.COM:80/").unwrap();
        let n = u.normalize();
        assert_eq!(n.scheme, "http");
        assert_eq!(n.host, "example.com");
        assert_eq!(n.port, None); // default port removed
        assert_eq!(n.path, "/");
    }

    #[test]
    fn origin_equality() {
        let a = Url::parse("https://site:443").unwrap().normalize();
        let b = Url::parse("https://site").unwrap().normalize();
        assert!(a.origin().is_same_origin(&b.origin()));
    }
}
