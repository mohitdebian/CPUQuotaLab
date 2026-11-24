use crate::protocol::TaskClass;
use crate::{DynError, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::env;
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkloadConfig {
    pub short_iterations: u64,
    pub long_iterations: u64,
    pub uniform_iterations: u64,
}

impl Default for WorkloadConfig {
    fn default() -> Self {
        Self {
            short_iterations: 50_000,
            long_iterations: 500_000,
            uniform_iterations: 95_000,
        }
    }
}

impl WorkloadConfig {
    #[must_use]
    pub fn iterations_for(&self, class: TaskClass) -> u64 {
        match class {
            TaskClass::Uniform => self.uniform_iterations,
            TaskClass::Short => self.short_iterations,
            TaskClass::Long => self.long_iterations,
        }
    }

    pub fn validate(&self) -> Result<()> {
        if self.short_iterations == 0 || self.long_iterations == 0 || self.uniform_iterations == 0 {
            return Err("workload iterations must all be positive".into());
        }
        if self.long_iterations <= self.short_iterations {
            return Err("long iterations must exceed short iterations".into());
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServerConfig {
    pub socket_path: PathBuf,
    pub output_dir: PathBuf,
    pub workers: usize,
    pub queue_capacity: usize,
    pub drain_timeout_seconds: u64,
    pub workload: WorkloadConfig,
}

impl ServerConfig {
    pub fn validate(&self) -> Result<()> {
        if self.workers == 0 {
            return Err("workers must be positive".into());
        }
        if self.queue_capacity == 0 {
            return Err("queue capacity must be positive".into());
        }
        if self.drain_timeout_seconds == 0 {
            return Err("drain timeout must be positive".into());
        }
        if self.socket_path.as_os_str().is_empty() {
            return Err("socket path must not be empty".into());
        }
        self.workload.validate()
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum WorkloadKind {
    Uniform,
    Mixed,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeneratorConfig {
    pub socket_path: PathBuf,
    pub output_dir: PathBuf,
    pub workload_kind: WorkloadKind,
    pub rate_per_sec: f64,
    pub warmup_seconds: f64,
    pub measurement_seconds: f64,
    pub lead_in_ms: u64,
    pub spin_threshold_us: u64,
    pub seed: u64,
    pub long_fraction: f64,
    pub max_sender_backlog: u64,
    pub scheduler_cpu: Option<usize>,
    pub writer_cpu: Option<usize>,
    pub reader_cpu: Option<usize>,
}

impl GeneratorConfig {
    pub fn validate(&self) -> Result<()> {
        if !self.rate_per_sec.is_finite() || self.rate_per_sec <= 0.0 {
            return Err("rate must be finite and positive".into());
        }
        if !self.warmup_seconds.is_finite() || self.warmup_seconds < 0.0 {
            return Err("warmup seconds must be finite and nonnegative".into());
        }
        if !self.measurement_seconds.is_finite() || self.measurement_seconds <= 0.0 {
            return Err("measurement seconds must be finite and positive".into());
        }
        if !(0.0..=1.0).contains(&self.long_fraction) {
            return Err("long fraction must be in [0, 1]".into());
        }
        if self.max_sender_backlog == 0 {
            return Err("max sender backlog must be positive".into());
        }
        Ok(())
    }
}

pub enum Command {
    Server(ServerConfig),
    Generator(GeneratorConfig),
    Detect,
}

pub fn parse_command() -> Result<Command> {
    parse_command_from(env::args().skip(1))
}

pub fn parse_command_from<I, S>(args: I) -> Result<Command>
where
    I: IntoIterator<Item = S>,
    S: Into<String>,
{
    let mut iter = args.into_iter().map(Into::into);
    let command = iter.next().ok_or_else(usage_error)?;
    if command == "detect" {
        if iter.next().is_some() {
            return Err("detect takes no arguments".into());
        }
        return Ok(Command::Detect);
    }
    let values = parse_flags(iter)?;
    match command.as_str() {
        "server" => {
            let cfg = ServerConfig {
                socket_path: required_path(&values, "socket")?,
                output_dir: required_path(&values, "output-dir")?,
                workers: required_parse(&values, "workers")?,
                queue_capacity: required_parse(&values, "queue-capacity")?,
                drain_timeout_seconds: optional_parse(&values, "drain-timeout-seconds", 10)?,
                workload: WorkloadConfig {
                    short_iterations: optional_parse(&values, "short-iterations", 50_000)?,
                    long_iterations: optional_parse(&values, "long-iterations", 500_000)?,
                    uniform_iterations: optional_parse(&values, "uniform-iterations", 95_000)?,
                },
            };
            cfg.validate()?;
            Ok(Command::Server(cfg))
        }
        "generator" => {
            let workload_kind = match required(&values, "workload")?.as_str() {
                "uniform" => WorkloadKind::Uniform,
                "mixed" => WorkloadKind::Mixed,
                other => return Err(format!("unknown workload kind: {other}").into()),
            };
            let cfg = GeneratorConfig {
                socket_path: required_path(&values, "socket")?,
                output_dir: required_path(&values, "output-dir")?,
                workload_kind,
                rate_per_sec: required_parse(&values, "rate")?,
                warmup_seconds: optional_parse(&values, "warmup-seconds", 5.0)?,
                measurement_seconds: optional_parse(&values, "measurement-seconds", 30.0)?,
                lead_in_ms: optional_parse(&values, "lead-in-ms", 200)?,
                spin_threshold_us: optional_parse(&values, "spin-threshold-us", 100)?,
                seed: optional_parse(&values, "seed", 1)?,
                long_fraction: optional_parse(&values, "long-fraction", 0.1)?,
                max_sender_backlog: optional_parse(&values, "max-sender-backlog", 100_000)?,
                scheduler_cpu: optional_value_parse(&values, "scheduler-cpu")?,
                writer_cpu: optional_value_parse(&values, "writer-cpu")?,
                reader_cpu: optional_value_parse(&values, "reader-cpu")?,
            };
            cfg.validate()?;
            Ok(Command::Generator(cfg))
        }
        _ => Err(usage_error()),
    }
}

fn parse_flags<I>(mut args: I) -> Result<HashMap<String, String>>
where
    I: Iterator<Item = String>,
{
    let mut values = HashMap::new();
    while let Some(flag) = args.next() {
        let key = flag
            .strip_prefix("--")
            .ok_or_else(|| format!("expected --flag, got {flag}"))?;
        let value = args
            .next()
            .ok_or_else(|| format!("missing value for --{key}"))?;
        if values.insert(key.to_owned(), value).is_some() {
            return Err(format!("duplicate flag --{key}").into());
        }
    }
    Ok(values)
}

fn required(values: &HashMap<String, String>, key: &str) -> Result<String> {
    values
        .get(key)
        .cloned()
        .ok_or_else(|| format!("missing --{key}").into())
}

fn required_path(values: &HashMap<String, String>, key: &str) -> Result<PathBuf> {
    Ok(PathBuf::from(required(values, key)?))
}

fn required_parse<T>(values: &HashMap<String, String>, key: &str) -> Result<T>
where
    T: std::str::FromStr,
    T::Err: std::error::Error + Send + Sync + 'static,
{
    Ok(required(values, key)?.parse()?)
}

fn optional_parse<T>(values: &HashMap<String, String>, key: &str, default: T) -> Result<T>
where
    T: std::str::FromStr,
    T::Err: std::error::Error + Send + Sync + 'static,
{
    match values.get(key) {
        Some(value) => Ok(value.parse()?),
        None => Ok(default),
    }
}

fn optional_value_parse<T>(values: &HashMap<String, String>, key: &str) -> Result<Option<T>>
where
    T: std::str::FromStr,
    T::Err: std::error::Error + Send + Sync + 'static,
{
    values
        .get(key)
        .map(|value| value.parse())
        .transpose()
        .map_err(Into::into)
}

fn usage_error() -> DynError {
    "usage: cpu-quota-lab <server|generator|detect> [--flag value ...]".into()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_server_configuration() {
        let command = parse_command_from([
            "server",
            "--socket",
            "/tmp/lab.sock",
            "--output-dir",
            "/tmp/out",
            "--workers",
            "2",
            "--queue-capacity",
            "16",
        ])
        .unwrap();
        let Command::Server(config) = command else {
            panic!("wrong command")
        };
        assert_eq!(config.workers, 2);
        assert_eq!(config.queue_capacity, 16);
        assert_eq!(config.drain_timeout_seconds, 10);
    }

    #[test]
    fn rejects_zero_workers() {
        let result = parse_command_from([
            "server",
            "--socket",
            "/tmp/lab.sock",
            "--output-dir",
            "/tmp/out",
            "--workers",
            "0",
            "--queue-capacity",
            "16",
        ]);
        assert!(result.is_err());
    }

    #[test]
    fn rejects_invalid_long_fraction() {
        let result = parse_command_from([
            "generator",
            "--socket",
            "/tmp/lab.sock",
            "--output-dir",
            "/tmp/out",
            "--workload",
            "mixed",
            "--rate",
            "10",
            "--long-fraction",
            "1.1",
        ]);
        assert!(result.is_err());
    }
}
