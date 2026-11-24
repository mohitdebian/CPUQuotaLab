use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicU64, Ordering};

#[derive(Default)]
pub struct ServerCounters {
    received: AtomicU64,
    admitted: AtomicU64,
    dropped_full: AtomicU64,
    dropped_closed: AtomicU64,
    completed: AtomicU64,
    incomplete_drain_timeout: AtomicU64,
    checksum_xor: AtomicU64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServerCounterSnapshot {
    pub received: u64,
    pub admitted: u64,
    pub dropped_full: u64,
    pub dropped_closed: u64,
    pub completed: u64,
    pub incomplete_drain_timeout: u64,
    pub checksum_xor: u64,
}

impl ServerCounters {
    pub fn received(&self) {
        self.received.fetch_add(1, Ordering::Relaxed);
    }

    pub fn admitted(&self) {
        self.admitted.fetch_add(1, Ordering::Relaxed);
    }

    pub fn dropped_full(&self) {
        self.dropped_full.fetch_add(1, Ordering::Relaxed);
    }

    pub fn dropped_closed(&self) {
        self.dropped_closed.fetch_add(1, Ordering::Relaxed);
    }

    pub fn completed(&self, checksum: u64) {
        self.completed.fetch_add(1, Ordering::Relaxed);
        self.checksum_xor.fetch_xor(checksum, Ordering::Relaxed);
    }

    pub fn incomplete_drain_timeout(&self) {
        self.incomplete_drain_timeout
            .fetch_add(1, Ordering::Relaxed);
    }

    #[must_use]
    pub fn snapshot(&self) -> ServerCounterSnapshot {
        ServerCounterSnapshot {
            received: self.received.load(Ordering::Relaxed),
            admitted: self.admitted.load(Ordering::Relaxed),
            dropped_full: self.dropped_full.load(Ordering::Relaxed),
            dropped_closed: self.dropped_closed.load(Ordering::Relaxed),
            completed: self.completed.load(Ordering::Relaxed),
            incomplete_drain_timeout: self.incomplete_drain_timeout.load(Ordering::Relaxed),
            checksum_xor: self.checksum_xor.load(Ordering::Relaxed),
        }
    }
}
