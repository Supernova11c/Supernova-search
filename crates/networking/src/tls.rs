use std::io;
use std::net::{SocketAddr, TcpStream, ToSocketAddrs};
use std::time::Duration;

pub fn connect(addr: SocketAddr, timeout: Duration) -> io::Result<TcpStream> {
    let stream = TcpStream::connect_timeout(&addr, timeout)?;
    stream.set_read_timeout(Some(timeout))?;
    stream.set_write_timeout(Some(timeout))?;
    Ok(stream)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::{TcpListener};
    use std::thread;

    #[test]
    fn connect_local_listener() {
        // start a local listener to accept one connection
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let addr = listener.local_addr().unwrap();
        thread::spawn(move || {
            let (mut socket, _) = listener.accept().unwrap();
            // drop immediately
            drop(socket);
        });
        let stream = connect(addr, Duration::from_secs(1)).unwrap();
        assert!(stream.peer_addr().is_ok());
    }
}
