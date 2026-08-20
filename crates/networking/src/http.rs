use std::io::{self, Read, Write};
use std::net::TcpStream;
use rustls::{ClientConfig, ClientConnection, StreamOwned, OwnedTrustAnchor};
use std::sync::Arc;
use webpki_roots::TLS_SERVER_ROOTS;
use std::convert::TryFrom;

pub fn wrap_tls(stream: TcpStream, domain: &str) -> io::Result<StreamOwned<ClientConnection, TcpStream>> {
    // Build rustls client config with root certificates
    let mut root_store = rustls::RootCertStore::empty();
    let trust_anchors = TLS_SERVER_ROOTS.0.iter().map(|ta| {
        OwnedTrustAnchor::from_subject_spki_name_constraints(
            ta.subject, ta.spki, ta.name_constraints
        )
    });
    root_store.add_server_trust_anchors(trust_anchors);

    let config = ClientConfig::builder()
        .with_safe_defaults()
        .with_root_certificates(root_store)
        .with_no_client_auth();

    let rcfg = Arc::new(config);

    let server_name = match rustls::ServerName::try_from(domain) {
        Ok(s) => s,
        Err(_) => return Err(io::Error::new(io::ErrorKind::InvalidInput, "invalid dnsname for tls")),
    };

    let conn = ClientConnection::new(rcfg, server_name).map_err(|e| io::Error::new(io::ErrorKind::Other, format!("tls conn error: {}", e)))?;
    let stream = StreamOwned::new(conn, stream);
    Ok(stream)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;
    use std::thread;

    // We will not perform a real TLS handshake in unit tests; this module is exercised
    // indirectly via integration tests that connect to real TLS endpoints if needed.
    #[test]
    fn wrap_tls_invalid_name() {
        // connecting to an invalid server name should error early when constructing ServerName
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let addr = listener.local_addr().unwrap();
        thread::spawn(move || {
            let (_socket, _) = listener.accept().unwrap();
        });
        let stream = TcpStream::connect(addr).unwrap();
        let res = wrap_tls(stream, "not a domain!");
        assert!(res.is_err());
    }
}
