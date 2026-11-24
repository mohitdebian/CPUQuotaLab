use cpu_quota_lab::config::{GeneratorConfig, ServerConfig, WorkloadConfig, WorkloadKind};
use cpu_quota_lab::{generator, server};
use std::fs;
use std::path::{Path, PathBuf};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

#[test]
fn server_and_open_loop_generator_exchange_accounted_requests() {
    let output_dir = unique_temp_dir();
    fs::create_dir(&output_dir).unwrap();
    let socket_path = output_dir.join("test.sock");
    let server_output = output_dir.clone();
    let server_socket = socket_path.clone();
    let server_handle = thread::spawn(move || {
        server::run(ServerConfig {
            socket_path: server_socket,
            output_dir: server_output,
            workers: 2,
            queue_capacity: 32,
            drain_timeout_seconds: 1,
            workload: WorkloadConfig {
                short_iterations: 100,
                long_iterations: 1_000,
                uniform_iterations: 190,
            },
        })
        .unwrap()
    });

    wait_for(&output_dir.join("server-ready.json"));
    let generator_summary = generator::run(GeneratorConfig {
        socket_path,
        output_dir: output_dir.clone(),
        workload_kind: WorkloadKind::Mixed,
        rate_per_sec: 100.0,
        warmup_seconds: 0.0,
        measurement_seconds: 0.1,
        lead_in_ms: 10,
        spin_threshold_us: 50,
        seed: 42,
        long_fraction: 0.1,
        max_sender_backlog: 1_000,
        scheduler_cpu: None,
        writer_cpu: None,
        reader_cpu: None,
    })
    .unwrap();
    let server_summary = server_handle.join().unwrap();

    assert_eq!(generator_summary.scheduled_requests, 10);
    assert_eq!(generator_summary.sent_requests, 10);
    assert_eq!(generator_summary.completed, 10);
    assert_eq!(generator_summary.dropped, 0);
    assert_eq!(generator_summary.incomplete, 0);
    assert_eq!(server_summary.counters.received, 10);
    assert_eq!(server_summary.counters.admitted, 10);
    assert_eq!(server_summary.counters.completed, 10);
    assert!(output_dir.join("requests.ndjson").is_file());
    assert!(output_dir.join("server-summary.json").is_file());

    fs::remove_dir_all(output_dir).unwrap();
}

fn wait_for(path: &Path) {
    for _ in 0..200 {
        if path.exists() {
            return;
        }
        thread::sleep(Duration::from_millis(5));
    }
    panic!("timed out waiting for {}", path.display());
}

fn unique_temp_dir() -> PathBuf {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!("cpuquota-e2e-{nonce}"))
}
