use cpu_quota_lab::config::{self, Command};
use cpu_quota_lab::{Result, cgroup, generator, server};

fn main() {
    if let Err(error) = run() {
        eprintln!("cpu-quota-lab: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<()> {
    match config::parse_command()? {
        Command::Server(config) => {
            let summary = server::run(config)?;
            eprintln!(
                "server complete: received={} admitted={} completed={} dropped={}",
                summary.counters.received,
                summary.counters.admitted,
                summary.counters.completed,
                summary.counters.dropped_full + summary.counters.dropped_closed
            );
        }
        Command::Generator(config) => {
            let summary = generator::run(config)?;
            eprintln!(
                "generator complete: scheduled={} sent={} completed={} dropped={} incomplete={}",
                summary.scheduled_requests,
                summary.sent_requests,
                summary.completed,
                summary.dropped,
                summary.incomplete
            );
        }
        Command::Detect => {
            println!("{}", serde_json::to_string_pretty(&cgroup::discover()?)?);
        }
    }
    Ok(())
}
