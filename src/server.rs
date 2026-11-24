use crate::Result;
use crate::cgroup::{self, CgroupInfo, CgroupSnapshot};
use crate::clock::{monotonic_ns, process_cpu_time_ns};
use crate::config::ServerConfig;
use crate::metrics::{ServerCounterSnapshot, ServerCounters};
use crate::protocol::{ClientMessage, ControlEvent, Outcome, ResponseWire};
use crate::queue::{BoundedQueue, PushError, PushWithError};
use crate::thread_pool::{Task, ThreadPool};
use serde::Serialize;
use std::collections::BTreeMap;
use std::fs::{self, File};
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::os::unix::fs::FileTypeExt;
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc;
use std::thread;

#[derive(Debug, Serialize)]
pub struct ServerReady {
    pub pid: u32,
    pub cgroup_path: PathBuf,
    pub affinity_cpus: Vec<u32>,
    pub socket_path: PathBuf,
}

#[derive(Debug, Serialize)]
pub struct ServerSummary {
    pub config: ServerConfig,
    pub pid: u32,
    pub cgroup: CgroupInfo,
    pub snapshots: BTreeMap<String, CgroupSnapshot>,
    pub counters: ServerCounterSnapshot,
    pub thread_cgroups_start: BTreeMap<u32, PathBuf>,
    pub thread_cgroups_end: BTreeMap<u32, PathBuf>,
    pub process_cpu_time_ns: u64,
}

struct SocketGuard(PathBuf);

impl Drop for SocketGuard {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.0);
    }
}

pub fn run(config: ServerConfig) -> Result<ServerSummary> {
    config.validate()?;
    let process_cpu_start_ns = process_cpu_time_ns()?;
    fs::create_dir_all(&config.output_dir)?;
    prepare_socket_path(&config.socket_path)?;
    let _socket_guard = SocketGuard(config.socket_path.clone());
    let listener = UnixListener::bind(&config.socket_path)?;

    let cgroup = cgroup::discover()?;
    let pid = std::process::id();
    let ready = ServerReady {
        pid,
        cgroup_path: cgroup.relative_path.clone(),
        affinity_cpus: cgroup.affinity_cpus.clone(),
        socket_path: config.socket_path.clone(),
    };
    write_json(&config.output_dir.join("server-ready.json"), &ready)?;

    let (stream, _) = listener.accept()?;
    let writer_stream = stream.try_clone()?;
    let (response_tx, response_rx) = mpsc::channel::<ResponseWire>();
    let writer = thread::Builder::new()
        .name("cpuquota-response-writer".to_owned())
        .spawn(move || write_responses(writer_stream, response_rx))?;

    let queue = Arc::new(BoundedQueue::new(config.queue_capacity));
    let counters = Arc::new(ServerCounters::default());
    let drain_deadline_ns = Arc::new(AtomicU64::new(u64::MAX));
    let pool = ThreadPool::start(
        config.workers,
        Arc::clone(&queue),
        config.workload.clone(),
        response_tx.clone(),
        Arc::clone(&counters),
        Arc::clone(&drain_deadline_ns),
    )?;

    let thread_cgroups_start = cgroup::thread_cgroup_paths(pid)?;
    let mut snapshots = BTreeMap::new();
    snapshots.insert(
        "server_start".to_owned(),
        cgroup::snapshot(&cgroup.absolute_path)?,
    );

    let mut reader = BufReader::new(stream);
    let mut line = String::new();
    loop {
        line.clear();
        if reader.read_line(&mut line)? == 0 {
            break;
        }
        let message: ClientMessage = match serde_json::from_str(&line) {
            Ok(message) => message,
            Err(error) => {
                return Err(format!("invalid client message: {error}").into());
            }
        };
        match message {
            ClientMessage::Control { event, .. } => {
                let key = match event {
                    ControlEvent::WarmupStart => "warmup_start",
                    ControlEvent::MeasurementStart => "measurement_start",
                    ControlEvent::MeasurementEnd => "measurement_end",
                };
                snapshots.insert(key.to_owned(), cgroup::snapshot(&cgroup.absolute_path)?);
                if event == ControlEvent::MeasurementEnd {
                    let deadline = monotonic_ns()?
                        .saturating_add(config.drain_timeout_seconds.saturating_mul(1_000_000_000));
                    drain_deadline_ns.store(deadline, Ordering::Release);
                    queue.close();
                }
            }
            ClientMessage::Request { request } => {
                counters.received();
                let receive_ns = monotonic_ns()?;
                let request_id = request.request_id;
                let result = queue.try_push_with_result(|queue_len| {
                    Ok::<Task, std::io::Error>(Task {
                        request,
                        server_receive_ns: receive_ns,
                        admission_ns: monotonic_ns()?,
                        queue_len_at_admission: queue_len,
                    })
                });
                match result {
                    Ok(_) => counters.admitted(),
                    Err(PushWithError::Build(error)) => return Err(error.into()),
                    Err(PushWithError::Queue(error)) => {
                        let (outcome, message) = match error {
                            PushError::Full => {
                                counters.dropped_full();
                                (Outcome::DroppedQueueFull, "bounded queue full")
                            }
                            PushError::Closed => {
                                counters.dropped_closed();
                                (Outcome::DroppedQueueClosed, "bounded queue closed")
                            }
                        };
                        response_tx.send(ResponseWire {
                            request_id,
                            outcome,
                            server_receive_ns: receive_ns,
                            admission_ns: None,
                            execution_start_ns: None,
                            completion_ns: Some(monotonic_ns()?),
                            execution_cpu_ns: None,
                            worker_id: None,
                            checksum: None,
                            queue_len_at_admission: queue.len(),
                            error: Some(message.to_owned()),
                        })?;
                    }
                }
            }
        }
    }

    if drain_deadline_ns.load(Ordering::Acquire) == u64::MAX {
        let deadline = monotonic_ns()?
            .saturating_add(config.drain_timeout_seconds.saturating_mul(1_000_000_000));
        drain_deadline_ns.store(deadline, Ordering::Release);
    }
    queue.close();
    pool.join()?;
    drop(response_tx);
    writer.join().map_err(|_| "response writer panicked")??;

    snapshots.insert(
        "server_end".to_owned(),
        cgroup::snapshot(&cgroup.absolute_path)?,
    );
    let thread_cgroups_end = cgroup::thread_cgroup_paths(pid)?;
    let summary = ServerSummary {
        config: config.clone(),
        pid,
        cgroup,
        snapshots,
        counters: counters.snapshot(),
        thread_cgroups_start,
        thread_cgroups_end,
        process_cpu_time_ns: process_cpu_time_ns()?.saturating_sub(process_cpu_start_ns),
    };
    write_json(&config.output_dir.join("server-summary.json"), &summary)?;
    Ok(summary)
}

fn write_responses(stream: UnixStream, receiver: mpsc::Receiver<ResponseWire>) -> Result<()> {
    let mut writer = BufWriter::new(stream);
    for response in receiver {
        serde_json::to_writer(&mut writer, &response)?;
        writer.write_all(b"\n")?;
    }
    writer.flush()?;
    Ok(())
}

fn prepare_socket_path(path: &Path) -> Result<()> {
    if !path.exists() {
        return Ok(());
    }
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.file_type().is_socket() {
        return Err(format!("refusing to replace non-socket path: {}", path.display()).into());
    }
    fs::remove_file(path)?;
    Ok(())
}

fn write_json<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    let mut writer = BufWriter::new(File::create(path)?);
    serde_json::to_writer_pretty(&mut writer, value)?;
    writer.write_all(b"\n")?;
    writer.flush()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::net::UnixListener;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn refuses_to_replace_regular_file() {
        let path = unique_temp_path("regular");
        fs::write(&path, b"not a socket").unwrap();
        assert!(prepare_socket_path(&path).is_err());
        fs::remove_file(path).unwrap();
    }

    #[test]
    fn removes_stale_socket() {
        let path = unique_temp_path("socket");
        let listener = UnixListener::bind(&path).unwrap();
        drop(listener);
        prepare_socket_path(&path).unwrap();
        assert!(!path.exists());
    }

    fn unique_temp_path(label: &str) -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!("cpuquota-{label}-{nonce}.sock"))
    }
}
