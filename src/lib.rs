//! CPUQuotaLab experimental instrument.
//!
//! The crate intentionally uses native threads, a bounded FIFO queue, and
//! Unix-domain sockets so the measured mechanisms stay visible.

pub mod affinity;
pub mod cgroup;
pub mod clock;
pub mod config;
pub mod generator;
pub mod metrics;
pub mod protocol;
pub mod queue;
pub mod server;
pub mod thread_pool;
pub mod workload;

pub type DynError = Box<dyn std::error::Error + Send + Sync + 'static>;
pub type Result<T> = std::result::Result<T, DynError>;
