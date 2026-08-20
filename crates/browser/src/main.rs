//! A tiny example binary that exercises Phase 1-3 pieces: fetch an HTML page,
//! parse it for linked CSS and JS, and download those resources.

use supernova_core::{BrowserProcess, Config};
use supernova_url::Url;
use supernova_networking::HttpClient;
use supernova_html::HtmlFetcher;

fn main() {
    let cfg = Config::default();
    let mut bp = BrowserProcess::new(cfg);
    bp.start();

    let raw = "https://example.com/";
    match Url::parse(raw) {
        Ok(u) => {
            let client = HttpClient::new();
            let base = u.normalize();
            println!("Fetching {}", base);
            match client.get(&base.to_string()) {
                Ok((status, body)) => {
                    println!("Status: {}", status);
                    let fetcher = HtmlFetcher::new(client);
                    let resources = fetcher.fetch_resources(&base.to_string(), &body);
                    for r in resources {
                        match r {
                            Ok((url, bytes)) => println!("Fetched {} ({} bytes)", url, bytes.len()),
                            Err(e) => eprintln!("Resource fetch error: {}", e),
                        }
                    }
                }
                Err(e) => eprintln!("HTTP error: {}", e),
            }
        }
        Err(e) => eprintln!("URL parse error: {}", e),
    }

    bp.stop();
}
