//! Core runtime pieces for Phase 1: configuration, logging initialization,
//! simple resource manager, and a minimal browser process representation.

use log::{error, info, LevelFilter};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

/// Simple configuration for Phase 1.
#[derive(Debug, Clone)]
pub struct Config {
    pub log_level: LevelFilter,
    pub max_resources: usize,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            log_level: LevelFilter::Info,
            max_resources: 1024,
        }
    }
}

/// Initialize logging according to the provided configuration.
pub fn init_logging(cfg: &Config) {
    let mut builder = env_logger::Builder::new();
    builder.filter(None, cfg.log_level);
    builder.init();
    info!("logging initialized (level = {:?})", cfg.log_level);
}

/// A small resource manager that tracks allocations and enforces a soft limit.
#[derive(Clone, Debug)]
pub struct ResourceManager {
    count: Arc<AtomicUsize>,
    max: usize,
}

impl ResourceManager {
    pub fn new(max: usize) -> Self {
        Self {
            count: Arc::new(AtomicUsize::new(0)),
            max,
        }
    }

    /// Try to allocate a resource. Returns true if allocation succeeded.
    pub fn try_allocate(&self) -> bool {
        let prev = self.count.fetch_add(1, Ordering::SeqCst);
        if prev + 1 > self.max {
            // revert
            self.count.fetch_sub(1, Ordering::SeqCst);
            error!("resource allocation failed: limit reached ({} >= {})", prev + 1, self.max);
            return false;
        }
        info!("allocated resource (count = {})", prev + 1);
        true
    }

    pub fn release(&self) {
        let prev = self.count.fetch_sub(1, Ordering::SeqCst);
        info!("released resource (count = {})", prev - 1);
    }

    pub fn current_count(&self) -> usize {
        self.count.load(Ordering::SeqCst)
    }
}

/// A minimal browser process/engine entry point for Phase 1.
pub struct BrowserProcess {
    pub cfg: Config,
    pub resources: ResourceManager,
    running: bool,
}

impl BrowserProcess {
    pub fn new(cfg: Config) -> Self {
        let resources = ResourceManager::new(cfg.max_resources);
        Self {
            cfg,
            resources,
            running: false,
        }
    }

    pub fn start(&mut self) {
        init_logging(&self.cfg);
        self.running = true;
        info!("BrowserProcess started");
    }

    pub fn stop(&mut self) {
        self.running = false;
        info!("BrowserProcess stopped");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn config_defaults() {
        let c = Config::default();
        assert_eq!(c.max_resources, 1024);
    }

    #[test]
    fn resource_manager_limits() {
        let rm = ResourceManager::new(2);
        assert!(rm.try_allocate());
        assert!(rm.try_allocate());
        assert!(!rm.try_allocate());
        assert_eq!(rm.current_count(), 2);
        rm.release();
        assert_eq!(rm.current_count(), 1);
    }
}
