use std::net::{TcpStream, ToSocketAddrs, SocketAddr, IpAddr};
use std::time::Duration;

pub fn resolve_host(host: &str) -> std::io::Result<Vec<IpAddr>> {
    // Use ToSocketAddrs to perform name resolution.
    // We append a dummy port and extract IPs.
    let addr_iter = (host, 0).to_socket_addrs()?;
    let mut ips = Vec::new();
    for a in addr_iter {
        ips.push(a.ip());
    }
    Ok(ips)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resolve_localhost() {
        let ips = resolve_host("localhost").unwrap();
        assert!(!ips.is_empty());
    }
}
