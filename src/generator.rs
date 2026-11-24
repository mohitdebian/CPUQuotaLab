use crate::Result;
use crate::affinity::pin_current_thread;
use crate::clock::{monotonic_ns, process_cpu_time_ns};
use crate::config::{GeneratorConfig, WorkloadKind};
use crate::protocol::{
    ClientMessage, ControlEvent, Outcome, Phase, RawRequestRecord, RequestWire, ResponseWire,
    SendRecord, TaskClass,
};
use serde::Serialize;
use std::collections::HashMap;
use std::fs::{self, File};
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::net::Shutdown;
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, mpsc};
use std::thread;
use std::time::Duration;

#[derive(Debug, Serialize)]
pub struct GeneratorSummary {
    pub config: GeneratorConfig,
    pub schedule_start_ns: u64,
    pub measurement_start_ns: u64,
    pub measurement_end_ns: u64,
    pub planned_requests: u64,
    pub scheduled_requests: u64,
    pub unissued_requests: u64,
    pub sent_requests: u64,
    pub received_responses: usize,
    pub completed: usize,
    pub dropped: usize,
    pub incomplete: usize,
    pub failed: usize,
    pub maximum_observed_sender_backlog: u64,
    pub aborted_reason: Option<String>,
    pub writer_error: Option<String>,
    pub reader_error: Option<String>,
    pub process_cpu_time_ns: u64,
}

enum Outbound {
    Request(RequestWire),
    Control(ControlEvent, u64),
}

struct WriterReport {
    records: Vec<SendRecord>,
    error: Option<String>,
}

struct ReaderReport {
    responses: Vec<ResponseWire>,
    error: Option<String>,
}

pub fn run(config: GeneratorConfig) -> Result<GeneratorSummary> {
    config.validate()?;
    let process_cpu_start_ns = process_cpu_time_ns()?;
    fs::create_dir_all(&config.output_dir)?;
    let stream = UnixStream::connect(&config.socket_path)?;
    let writer_stream = stream.try_clone()?;
    let reader_stream = stream;

    let (outbound_tx, outbound_rx) = mpsc::channel::<Outbound>();
    let sent = Arc::new(AtomicU64::new(0));
    let scheduled_shared = Arc::new(AtomicU64::new(0));
    let writer_failed = Arc::new(AtomicBool::new(false));
    let writer_sent = Arc::clone(&sent);
    let writer_scheduled = Arc::clone(&scheduled_shared);
    let writer_failure = Arc::clone(&writer_failed);
    let writer_cpu = config.writer_cpu;
    let writer_handle = thread::Builder::new()
        .name("cpuquota-socket-writer".to_owned())
        .spawn(move || {
            if let Some(cpu) = writer_cpu {
                pin_current_thread(cpu)?;
            }
            send_messages(
                writer_stream,
                outbound_rx,
                writer_scheduled,
                writer_sent,
                writer_failure,
            )
        })?;

    let reader_cpu = config.reader_cpu;
    let reader_handle = thread::Builder::new()
        .name("cpuquota-response-reader".to_owned())
        .spawn(move || {
            if let Some(cpu) = reader_cpu
                && let Err(error) = pin_current_thread(cpu)
            {
                return ReaderReport {
                    responses: Vec::new(),
                    error: Some(format!("reader affinity failed: {error}")),
                };
            }
            read_responses(reader_stream)
        })?;

    if let Some(cpu) = config.scheduler_cpu {
        pin_current_thread(cpu)?;
    }

    let interval_ns = (1_000_000_000.0 / config.rate_per_sec).round() as u64;
    if interval_ns == 0 {
        return Err("offered rate is too high for nanosecond scheduling".into());
    }
    let schedule_start_ns = monotonic_ns()?
        .checked_add(config.lead_in_ms.saturating_mul(1_000_000))
        .ok_or("schedule start overflow")?;
    let warmup_ns = duration_ns(config.warmup_seconds)?;
    let measurement_ns = duration_ns(config.measurement_seconds)?;
    let measurement_start_ns = schedule_start_ns
        .checked_add(warmup_ns)
        .ok_or("measurement start overflow")?;
    let measurement_end_ns = measurement_start_ns
        .checked_add(measurement_ns)
        .ok_or("measurement end overflow")?;
    let spin_ns = config.spin_threshold_us.saturating_mul(1_000);
    let warmup_count = request_count(config.warmup_seconds, config.rate_per_sec)?;
    let measurement_count = request_count(config.measurement_seconds, config.rate_per_sec)?;
    let planned_requests = warmup_count.saturating_add(measurement_count);

    let mut scheduled = 0_u64;
    let mut emitted_requests = Vec::new();
    let mut maximum_backlog = 0_u64;
    let mut aborted_reason = None;

    wait_until(schedule_start_ns, spin_ns)?;
    if outbound_tx
        .send(Outbound::Control(
            ControlEvent::WarmupStart,
            schedule_start_ns,
        ))
        .is_err()
    {
        aborted_reason = Some("socket writer stopped before warm-up".to_owned());
    } else {
        schedule_phase(
            &config,
            Phase::Warmup,
            schedule_start_ns,
            warmup_count,
            interval_ns,
            spin_ns,
            &outbound_tx,
            &sent,
            &scheduled_shared,
            &writer_failed,
            &mut scheduled,
            &mut emitted_requests,
            &mut maximum_backlog,
            &mut aborted_reason,
        )?;
    }

    if aborted_reason.is_none() {
        wait_until(measurement_start_ns, spin_ns)?;
        if outbound_tx
            .send(Outbound::Control(
                ControlEvent::MeasurementStart,
                measurement_start_ns,
            ))
            .is_err()
        {
            aborted_reason = Some("socket writer stopped before measurement".to_owned());
        } else {
            schedule_phase(
                &config,
                Phase::Measurement,
                measurement_start_ns,
                measurement_count,
                interval_ns,
                spin_ns,
                &outbound_tx,
                &sent,
                &scheduled_shared,
                &writer_failed,
                &mut scheduled,
                &mut emitted_requests,
                &mut maximum_backlog,
                &mut aborted_reason,
            )?;
        }
    }

    if aborted_reason.is_none() {
        wait_until(measurement_end_ns, spin_ns)?;
    }
    if outbound_tx
        .send(Outbound::Control(
            ControlEvent::MeasurementEnd,
            measurement_end_ns,
        ))
        .is_err()
        && aborted_reason.is_none()
    {
        aborted_reason = Some("socket writer stopped before measurement-end control".to_owned());
    }
    drop(outbound_tx);

    let writer_report = writer_handle
        .join()
        .map_err(|_| "socket writer panicked")??;
    if aborted_reason.is_none() && writer_report.error.is_some() {
        aborted_reason = writer_report.error.clone();
    }
    let reader_report = reader_handle
        .join()
        .map_err(|_| "response reader panicked")?;

    let response_count = reader_report.responses.len();
    let raw = merge_records(
        emitted_requests,
        writer_report.records,
        reader_report.responses,
    )?;
    write_ndjson(&config.output_dir.join("requests.ndjson"), &raw)?;
    let completed = raw
        .iter()
        .filter(|record| record.final_outcome == Outcome::Completed)
        .count();
    let dropped = raw
        .iter()
        .filter(|record| {
            matches!(
                record.final_outcome,
                Outcome::DroppedQueueFull | Outcome::DroppedQueueClosed
            )
        })
        .count();
    let incomplete = raw
        .iter()
        .filter(|record| record.final_outcome == Outcome::Incomplete)
        .count();
    let failed = raw
        .iter()
        .filter(|record| record.final_outcome == Outcome::Failed)
        .count();
    let summary = GeneratorSummary {
        config: config.clone(),
        schedule_start_ns,
        measurement_start_ns,
        measurement_end_ns,
        planned_requests,
        scheduled_requests: scheduled,
        unissued_requests: planned_requests.saturating_sub(scheduled),
        sent_requests: sent.load(Ordering::Acquire),
        received_responses: response_count,
        completed,
        dropped,
        incomplete,
        failed,
        maximum_observed_sender_backlog: maximum_backlog,
        aborted_reason,
        writer_error: writer_report.error,
        reader_error: reader_report.error,
        process_cpu_time_ns: process_cpu_time_ns()?.saturating_sub(process_cpu_start_ns),
    };
    write_json(&config.output_dir.join("generator-summary.json"), &summary)?;
    Ok(summary)
}

#[allow(clippy::too_many_arguments)]
fn schedule_phase(
    config: &GeneratorConfig,
    phase: Phase,
    phase_start_ns: u64,
    count: u64,
    interval_ns: u64,
    spin_ns: u64,
    outbound: &mpsc::Sender<Outbound>,
    sent: &AtomicU64,
    scheduled_shared: &AtomicU64,
    writer_failed: &AtomicBool,
    scheduled: &mut u64,
    emitted_requests: &mut Vec<RequestWire>,
    maximum_backlog: &mut u64,
    aborted_reason: &mut Option<String>,
) -> Result<()> {
    for phase_index in 0..count {
        if writer_failed.load(Ordering::Acquire) {
            *aborted_reason = Some("socket writer failed".to_owned());
            break;
        }
        let intended = phase_start_ns
            .checked_add(phase_index.saturating_mul(interval_ns))
            .ok_or("intended arrival overflow")?;
        wait_until(intended, spin_ns)?;
        let emit = monotonic_ns()?;
        let sequence_index = *scheduled;
        let class = class_for(config, sequence_index);
        let request = RequestWire {
            request_id: sequence_index,
            sequence_index,
            phase,
            class,
            seed: config.seed,
            intended_arrival_ns: intended,
            scheduler_emit_ns: emit,
        };
        emitted_requests.push(request.clone());
        *scheduled += 1;
        scheduled_shared.store(*scheduled, Ordering::Release);
        if outbound.send(Outbound::Request(request)).is_err() {
            *aborted_reason =
                Some("socket writer stopped with emitted requests pending".to_owned());
            break;
        }
        let backlog = scheduled.saturating_sub(sent.load(Ordering::Acquire));
        *maximum_backlog = (*maximum_backlog).max(backlog);
        if backlog > config.max_sender_backlog {
            *aborted_reason = Some(format!(
                "sender backlog {backlog} exceeded configured maximum {}",
                config.max_sender_backlog
            ));
            break;
        }
    }
    Ok(())
}

fn send_messages(
    mut stream: UnixStream,
    receiver: mpsc::Receiver<Outbound>,
    scheduled: Arc<AtomicU64>,
    sent: Arc<AtomicU64>,
    failed: Arc<AtomicBool>,
) -> Result<WriterReport> {
    let mut records = Vec::new();
    let mut writer_error = None;
    loop {
        let outbound = match receiver.try_recv() {
            Ok(outbound) => outbound,
            Err(mpsc::TryRecvError::Empty) => {
                std::hint::spin_loop();
                continue;
            }
            Err(mpsc::TryRecvError::Disconnected) => break,
        };
        let (message, request) = match outbound {
            Outbound::Request(request) => (
                ClientMessage::Request {
                    request: request.clone(),
                },
                Some(request),
            ),
            Outbound::Control(event, timestamp) => (
                ClientMessage::Control {
                    event,
                    generator_timestamp_ns: timestamp,
                },
                None,
            ),
        };
        let mut encoded = serde_json::to_vec(&message)?;
        encoded.push(b'\n');
        let write_start = monotonic_ns()?;
        let backlog = scheduled
            .load(Ordering::Acquire)
            .saturating_sub(sent.load(Ordering::Acquire));
        let result = stream.write_all(&encoded);
        let write_end = monotonic_ns()?;
        if let Some(request) = request {
            let error = result.as_ref().err().map(ToString::to_string);
            records.push(SendRecord {
                request,
                socket_write_start_ns: write_start,
                socket_write_end_ns: write_end,
                sender_backlog_at_start: backlog,
                write_error: error,
            });
            if result.is_ok() {
                sent.fetch_add(1, Ordering::Release);
            }
        }
        if let Err(error) = result {
            failed.store(true, Ordering::Release);
            let _ = stream.shutdown(Shutdown::Both);
            writer_error = Some(format!("socket write failed: {error}"));
            break;
        }
    }
    if writer_error.is_none()
        && let Err(error) = stream.shutdown(Shutdown::Write)
    {
        writer_error = Some(format!("socket write shutdown failed: {error}"));
    }
    Ok(WriterReport {
        records,
        error: writer_error,
    })
}

fn read_responses(stream: UnixStream) -> ReaderReport {
    let mut reader = BufReader::new(stream);
    let mut responses = Vec::new();
    let mut error = None;
    let mut line = String::new();
    loop {
        line.clear();
        match reader.read_line(&mut line) {
            Ok(0) => break,
            Ok(_) => match serde_json::from_str(&line) {
                Ok(response) => responses.push(response),
                Err(parse_error) => {
                    error = Some(format!("invalid response: {parse_error}"));
                    break;
                }
            },
            Err(read_error) => {
                error = Some(format!("response read failed: {read_error}"));
                break;
            }
        }
    }
    ReaderReport { responses, error }
}

fn merge_records(
    emitted: Vec<RequestWire>,
    sends: Vec<SendRecord>,
    responses: Vec<ResponseWire>,
) -> Result<Vec<RawRequestRecord>> {
    let mut by_id = HashMap::with_capacity(responses.len());
    for response in responses {
        let id = response.request_id;
        if by_id.insert(id, response).is_some() {
            return Err(format!("duplicate response for request {id}").into());
        }
    }
    let mut sends_by_id = HashMap::with_capacity(sends.len());
    for send in sends {
        if sends_by_id.insert(send.request.request_id, send).is_some() {
            return Err("duplicate socket send record".into());
        }
    }
    let mut raw = Vec::with_capacity(emitted.len());
    for request in emitted {
        let send = sends_by_id.remove(&request.request_id);
        let response = by_id.remove(&request.request_id);
        let transport_error = match &send {
            Some(record) => record.write_error.clone(),
            None => Some("socket writer stopped before attempting request".to_owned()),
        };
        let final_outcome = if transport_error.is_some() {
            Outcome::Failed
        } else {
            response
                .as_ref()
                .map_or(Outcome::Incomplete, |value| value.outcome)
        };
        raw.push(RawRequestRecord {
            request,
            socket_write_start_ns: send.as_ref().map(|value| value.socket_write_start_ns),
            socket_write_end_ns: send.as_ref().map(|value| value.socket_write_end_ns),
            sender_backlog_at_start: send.as_ref().map(|value| value.sender_backlog_at_start),
            socket_write_error: transport_error,
            response,
            final_outcome,
        });
    }
    if !by_id.is_empty() || !sends_by_id.is_empty() {
        return Err(format!("{} responses had no send record", by_id.len()).into());
    }
    Ok(raw)
}

fn class_for(config: &GeneratorConfig, sequence_index: u64) -> TaskClass {
    if config.workload_kind == WorkloadKind::Uniform {
        return TaskClass::Uniform;
    }
    let mut value = config.seed ^ sequence_index.wrapping_mul(0x9E37_79B9_7F4A_7C15);
    value ^= value >> 12;
    value ^= value << 25;
    value ^= value >> 27;
    let unit = (value as f64) / (u64::MAX as f64);
    if unit < config.long_fraction {
        TaskClass::Long
    } else {
        TaskClass::Short
    }
}

fn wait_until(target_ns: u64, spin_ns: u64) -> Result<()> {
    loop {
        let now = monotonic_ns()?;
        if now >= target_ns {
            return Ok(());
        }
        let remaining = target_ns - now;
        if remaining > spin_ns.saturating_add(50_000) {
            thread::sleep(Duration::from_nanos(remaining - spin_ns));
        } else {
            std::hint::spin_loop();
        }
    }
}

fn duration_ns(seconds: f64) -> Result<u64> {
    let value = seconds * 1_000_000_000.0;
    if !value.is_finite() || value < 0.0 || value > u64::MAX as f64 {
        return Err("duration cannot be represented in nanoseconds".into());
    }
    Ok(value.round() as u64)
}

fn request_count(seconds: f64, rate: f64) -> Result<u64> {
    let value = (seconds * rate).floor();
    if !value.is_finite() || value < 0.0 || value > u64::MAX as f64 {
        return Err("request count overflow".into());
    }
    Ok(value as u64)
}

fn write_ndjson<T: Serialize>(path: &Path, values: &[T]) -> Result<()> {
    let mut writer = BufWriter::new(File::create(path)?);
    for value in values {
        serde_json::to_writer(&mut writer, value)?;
        writer.write_all(b"\n")?;
    }
    writer.flush()?;
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
    use std::path::PathBuf;

    fn config(kind: WorkloadKind) -> GeneratorConfig {
        GeneratorConfig {
            socket_path: PathBuf::from("/tmp/test.sock"),
            output_dir: PathBuf::from("/tmp/test-output"),
            workload_kind: kind,
            rate_per_sec: 100.0,
            warmup_seconds: 1.0,
            measurement_seconds: 1.0,
            lead_in_ms: 1,
            spin_threshold_us: 10,
            seed: 42,
            long_fraction: 0.1,
            max_sender_backlog: 100,
            scheduler_cpu: None,
            writer_cpu: None,
            reader_cpu: None,
        }
    }

    #[test]
    fn uniform_class_is_always_uniform() {
        let cfg = config(WorkloadKind::Uniform);
        assert!((0..100).all(|i| class_for(&cfg, i) == TaskClass::Uniform));
    }

    #[test]
    fn mixed_sequence_is_deterministic() {
        let cfg = config(WorkloadKind::Mixed);
        let first: Vec<_> = (0..100).map(|i| class_for(&cfg, i)).collect();
        let second: Vec<_> = (0..100).map(|i| class_for(&cfg, i)).collect();
        assert_eq!(first, second);
        assert!(first.contains(&TaskClass::Long));
        assert!(first.contains(&TaskClass::Short));
    }

    #[test]
    fn merges_missing_response_as_incomplete() {
        let request = RequestWire {
            request_id: 1,
            sequence_index: 1,
            phase: Phase::Measurement,
            class: TaskClass::Uniform,
            seed: 1,
            intended_arrival_ns: 1,
            scheduler_emit_ns: 2,
        };
        let raw = merge_records(
            vec![request.clone()],
            vec![SendRecord {
                request,
                socket_write_start_ns: 3,
                socket_write_end_ns: 4,
                sender_backlog_at_start: 0,
                write_error: None,
            }],
            vec![],
        )
        .unwrap();
        assert_eq!(raw[0].final_outcome, Outcome::Incomplete);
    }

    #[test]
    fn emitted_request_without_socket_attempt_is_failed_and_auditable() {
        let request = RequestWire {
            request_id: 5,
            sequence_index: 5,
            phase: Phase::Measurement,
            class: TaskClass::Short,
            seed: 2,
            intended_arrival_ns: 10,
            scheduler_emit_ns: 11,
        };
        let raw = merge_records(vec![request], vec![], vec![]).unwrap();
        assert_eq!(raw.len(), 1);
        assert_eq!(raw[0].final_outcome, Outcome::Failed);
        assert!(raw[0].socket_write_start_ns.is_none());
        assert!(raw[0].socket_write_error.is_some());
    }
}
